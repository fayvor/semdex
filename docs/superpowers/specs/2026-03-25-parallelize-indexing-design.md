# Parallelize Indexing Design

## Problem Statement

Semdex indexing is too slow for large repositories (20,000+ files, >60 minutes) and performance degrades within a single run. The current sequential implementation processes files one at a time, leaving 11 of 12 CPU cores idle during embedding generation. Additionally, per-file LanceDB appends cause write performance to degrade as the table grows.

**Target performance**: Reduce 60+ minute indexing to 6-8 minutes using parallelism and batched writes.

## Goals

1. **Primary**: Achieve 8-10x speedup on large repositories through parallel processing
2. **Secondary**: Eliminate within-run performance degradation via batched writes
3. **Tertiary**: Maintain backward compatibility with existing indexes and sequential fallback

## Non-Goals

- Distributed indexing across multiple machines
- Real-time incremental updates (git hook remains sequential)
- Parallelizing file discovery (fast enough already)

## Architecture Overview

### High-Level Design

```
Main Process:
├─ Discover files (sequential, fast)
├─ Filter by mtime (sequential, fast)
├─ Create ProcessPoolExecutor (10 workers)
├─ Submit file processing tasks to pool
├─ Collect results in memory buffer
├─ When buffer reaches threshold (500 files):
│  └─ Write batch to LanceDB (single operation)
└─ Progress bar updates on completion
```

### Worker Process Flow

Each worker operates independently:

```
Worker receives: file_path + metadata
Worker returns: list[chunk_dict] with embeddings

Steps per file:
1. Read file content
2. Chunk file (tree-sitter or sliding window)
3. Generate embeddings via fastembed
4. Return chunk dicts with vectors + metadata
```

### Key Design Principles

1. **Shared-nothing workers**: Each process has its own embedder instance (no IPC for large objects)
2. **Single writer pattern**: Main thread coordinates all database writes (eliminates contention)
3. **Batched writes**: Accumulate 500-1000 files worth of chunks before writing to LanceDB
4. **Memory bounded**: Target ~10-15 GB peak usage on 32 GB system

## Technology Choices

### ProcessPoolExecutor vs ThreadPoolExecutor

**Decision**: Use `concurrent.futures.ProcessPoolExecutor`

**Rationale**:
- Embedding generation is CPU-bound (fastembed/ONNX)
- Python GIL prevents true parallelism with threads
- Process pool provides true multi-core utilization
- Clean API with futures pattern

**Trade-offs**:
- **Pro**: Full CPU utilization, clean error handling
- **Con**: ~50-100 MB overhead per worker, pickling overhead
- **Con**: Can't share embedder instances (but workers cache their own)

### Batch Size Selection

**Decision**: Default batch size of 500 files per LanceDB write

**Rationale**:
- Typical file produces 1-5 chunks × ~1 KB = ~2.5 MB per batch
- 500 files ≈ 50-100 MB in memory (comfortable on 32 GB system)
- Large enough to amortize LanceDB write overhead
- Small enough to provide frequent progress updates

**Configurable**: Users can adjust via `write_batch_size` config option

### Worker Count

**Decision**: `min(cpu_count - 1, 11)` workers (10 on 12-core system)

**Rationale**:
- Leave 1-2 cores for OS, main thread, and other processes
- Prevents system from becoming unresponsive
- 10 workers provide ~10x parallelism for CPU-bound work

**Configurable**: Users can override via `parallel_workers` config

## Implementation Details

### Worker Function Signature

```python
def _process_file_worker(args: tuple) -> dict:
    """Process a single file in worker process.

    Args:
        args: (
            file_path: Path,
            base_path: Path,
            config_dict: dict,  # Serializable config
            model_name: str,
            source_dir: str,
            now: str (ISO timestamp)
        )

    Returns:
        {
            'file_path': str (relative path),
            'chunks': list[dict] with vectors,
            'mtime': float,
            'error': str | None
        }
    """
```

**Key implementation notes**:
- Worker creates embedder on first call (process-local, cached)
- Config passed as dict to avoid pickling custom objects
- Errors caught and returned (don't crash worker process)
- Relative paths computed in worker (reduce data transfer)

### Main Process Logic

```python
def index_project(project_root, config, files=None, target_dir=None, force=False):
    # ... existing discovery/filtering logic ...

    if config.parallel_enabled and len(to_index) > 50:
        return _index_parallel(to_index, store, config, ...)
    else:
        return _index_sequential(to_index, store, config, ...)

def _index_parallel(files, store, config, ...):
    NUM_WORKERS = config.parallel_workers or (os.cpu_count() - 1)
    BATCH_SIZE = config.write_batch_size

    results_buffer = []
    stats = {...}

    with ProcessPoolExecutor(max_workers=NUM_WORKERS) as executor:
        # Submit all files to pool
        futures = {
            executor.submit(_process_file_worker, (f, ...)): f
            for f in files
        }

        with click.progressbar(length=len(files), label="Indexing") as bar:
            for future in as_completed(futures):
                result = future.result()

                if result['error']:
                    stats['files_failed'] += 1
                    bar.update(1)
                    continue

                results_buffer.extend(result['chunks'])
                stats['files_indexed'] += 1
                bar.update(1)

                # Batch write when buffer is full
                if len(results_buffer) >= BATCH_SIZE:
                    store.add_chunks(results_buffer)
                    results_buffer.clear()

            # Flush remaining chunks
            if results_buffer:
                store.add_chunks(results_buffer)

    return stats
```

### Batched Write Implementation

**LanceDB optimization**: Single large `add()` call instead of many small appends.

```python
# Current (slow):
for file in files:
    chunks = process(file)
    store.add_chunks(chunks)  # Many small writes

# New (fast):
all_chunks = []
for file in files:
    chunks = process(file)
    all_chunks.extend(chunks)
store.add_chunks(all_chunks)  # One large write
```

**Expected impact**: Eliminates within-run degradation pattern by avoiding LanceDB's append overhead accumulation.

### Error Handling Strategy

**Worker-level errors** (file unreadable, chunking fails):
- Catch exception in worker
- Return `{'error': 'description', 'file_path': ...}`
- Main thread logs error and continues
- Failed files tracked in stats

**Process crashes** (rare):
- `ProcessPoolExecutor` detects via future
- Main thread logs "Worker crashed on file X"
- Other files continue processing

**Database write errors**:
- Retry batch write once
- If retry fails, log error with file paths
- Continue to next batch (don't abort entire run)

**Shutdown handling**:
- Catch `KeyboardInterrupt` in main thread
- Call `executor.shutdown(wait=False)`
- Flush partial results_buffer if possible

## Configuration

### New Config Fields

```python
@dataclass
class SemdexConfig:
    # ... existing fields ...

    # Parallelism
    parallel_enabled: bool = True
    parallel_workers: int = 0  # 0 = auto-detect (cpu_count - 1)

    # Batching
    write_batch_size: int = 500  # Files per LanceDB write

    # Safety
    min_files_for_parallel: int = 50  # Use sequential for small jobs
```

### CLI Options

```bash
# Override config
semdex index --workers 8 --batch-size 1000

# Disable parallelism
semdex index --no-parallel

# Force sequential (for debugging)
semdex index --sequential
```

## Performance Characteristics

### Expected Memory Usage

**Per worker**:
- Embedder model: ~200 MB (ONNX model loaded once per worker)
- Working memory: ~100-300 MB (file content + chunks)
- Total per worker: ~500 MB

**Main process**:
- Results buffer: ~5-10 MB per file × 500 = 2.5-5 GB
- Progress tracking: negligible
- Database connection: ~50 MB

**Total system**: ~10-15 GB peak (10 workers × 500 MB + 5 GB buffer)

**Safety**: Monitor available RAM, warn if < 16 GB total system RAM

### Expected Speedup

**Theoretical maximum**: 12x (12 cores)

**Realistic estimate**: 8-10x
- Worker startup overhead: ~2-3 seconds per worker (one-time)
- Process pool coordination: minimal with `as_completed()`
- Batch write overhead: ~100-500ms per batch (amortized)
- GIL overhead: none (separate processes)

**Benchmark targets**:
- 20,000 files, 60 minutes sequential → 6-8 minutes parallel
- 5,000 files, 15 minutes sequential → 1.5-2 minutes parallel
- 1,000 files, 3 minutes sequential → 20-30 seconds parallel

### Performance Optimizations

**File ordering**: Sort by size descending before submitting to pool
- Large files processed first
- Prevents straggler effect (last few large files holding up completion)

**Embedder caching**: Workers reuse embedder instance
- First file: ~2 second startup to load ONNX model
- Subsequent files: negligible overhead
- Amortized over hundreds of files per worker

**LanceDB write batching**: 500-file batches
- Single large write operation
- Avoids per-append overhead
- Should eliminate within-run degradation

## Testing Strategy

### Unit Tests

```python
# Worker function tests
test_process_file_worker_success()
test_process_file_worker_handles_errors()
test_worker_relative_paths()
test_worker_embedder_caching()

# Batch writing tests
test_write_batch_performance()
test_write_batch_vs_individual_writes()
test_write_batch_handles_duplicates()
```

### Integration Tests

```python
# Correctness tests
test_parallel_produces_same_results_as_sequential()
test_parallel_respects_mtime_skip()
test_parallel_handles_force_flag()

# Performance tests
test_parallel_speedup_on_large_project()
test_parallel_memory_stays_bounded()
test_batch_writes_faster_than_sequential()
```

### End-to-End Tests

```python
# Full workflow
test_index_project_parallel_large_repo()  # 5000+ files
test_parallel_handles_worker_crash_gracefully()
test_parallel_keyboard_interrupt_cleanup()
test_parallel_with_git_hook()
```

### Stress Tests

- 20,000 files, monitor memory usage (< 16 GB)
- Very large files (> 10 MB), ensure worker doesn't OOM
- Empty files, binary files, unicode edge cases
- Files deleted during indexing

### Backward Compatibility Tests

```python
test_sequential_mode_still_works()
test_existing_indexes_work_with_parallel()
test_config_migration_from_old_version()
```

## Backward Compatibility

### Sequential Fallback

**When to use sequential**:
- `config.parallel_enabled = False`
- File count < `min_files_for_parallel` (default: 50)
- Worker spawn failure (automatic fallback)

**Implementation**: Keep existing `_index_sequential()` function unchanged, add new `_index_parallel()` alongside it.

### Data Format Compatibility

**No schema changes needed**:
- Chunks still have same fields: `file_path`, `vector`, `content`, `mtime`, etc.
- LanceDB doesn't distinguish batched vs individual writes
- Existing indexes work with parallel writes seamlessly

### Configuration Migration

**Existing configs**: Continue to work, new fields use defaults

**No breaking changes**: All new fields are optional with sensible defaults

## Deployment & Rollout

### Phase 1: Feature Flag (Safe Rollout)

- Ship with `parallel_enabled=False` by default
- Add CLI flag: `semdex index --parallel` for testing
- Collect performance feedback from early adopters

### Phase 2: Gradual Enablement

- Enable by default for `semdex init` (fresh installs)
- Keep sequential for incremental re-indexing (git hook)
- Monitor for stability issues

### Phase 3: Full Enablement

- Enable by default everywhere (large speedup benefit outweighs risk)
- Keep `--sequential` flag for edge cases
- Document performance expectations in README

## Platform Compatibility

**Supported**:
- ✅ macOS (Darwin) - tested on 12-core M2
- ✅ Linux - `multiprocessing` is mature and well-tested
- ⚠️ Windows - `ProcessPoolExecutor` works but needs testing
  - May require `if __name__ == '__main__':` guard in CLI
  - Consider `spawn` vs `fork` start method

**Resource requirements**:
- Minimum: 8 GB RAM (will auto-reduce workers)
- Recommended: 16+ GB RAM
- Optimal: 32 GB RAM (as tested)

## Monitoring & Observability

### Enhanced Stats Tracking

```python
return {
    "files_discovered": total_files,
    "files_indexed": files_indexed,
    "files_skipped": files_skipped,
    "files_failed": files_failed,  # NEW
    "files_deleted": files_deleted,
    "chunks_created": total_chunks,
    "time_seconds": elapsed,  # NEW
    "workers_used": num_workers,  # NEW
    "avg_files_per_second": files_indexed / elapsed,  # NEW
}
```

### Logging Enhancements

- Log worker pool startup time
- Log batch write times (track degradation)
- Log any worker crashes with file paths
- Summary at end: "Indexed 20,000 files in 8m 23s using 10 workers (40 files/sec)"

### Performance Metrics

Track in logs:
- Worker utilization (how many workers busy at any time)
- Batch write times (detect if degradation still occurs)
- Memory high-water mark
- Files processed per second (should increase after worker warmup)

## Documentation Updates

### README Performance Section

```markdown
## Performance

Semdex uses parallel processing to index large repositories quickly:

- **Small repos** (< 100 files): Sequential, completes in seconds
- **Medium repos** (1,000-5,000 files): 10 workers, 1-2 minutes
- **Large repos** (20,000+ files): 10 workers, 6-8 minutes

On a 12-core system, expect 8-10x speedup vs sequential processing.

### Tuning Performance

Configure in `.claude/semdex/config.json`:

```json
{
  "parallel_workers": 8,        // Reduce if system becomes unresponsive
  "write_batch_size": 1000,     // Increase for very large repos
  "parallel_enabled": true      // Set false to use sequential mode
}
```

Or via CLI:
```bash
semdex index --workers 8 --batch-size 1000
```
```

### Troubleshooting Guide

**"Indexing is slow"**:
- Check `parallel_enabled` is `true` in config
- Verify workers are being used (see log output)
- Try `semdex index --parallel` to force enable

**"Running out of memory"**:
- Reduce `write_batch_size` to 250 or 100
- Reduce `parallel_workers` to 6 or 4
- Close memory-intensive applications

**"System becomes unresponsive"**:
- Reduce `parallel_workers` to 6-8 (leave more CPU headroom)
- Check system has adequate cooling (CPU throttling)

## Success Metrics

### Performance Targets

- ✅ 8-10x speedup on 20,000 file repositories
- ✅ No within-run performance degradation
- ✅ Memory usage < 16 GB peak

### Quality Targets

- ✅ Zero data corruption or index inconsistencies
- ✅ Identical results to sequential mode (same files, chunks, embeddings)
- ✅ Graceful error handling (failed files don't crash indexing)

### Adoption Metrics

- Time to index large repos (target: < 10 minutes for 20,000 files)
- User reports of performance improvements
- Zero reports of index corruption or data loss

## Future Enhancements

**Not in scope for v1, but possible future work**:

1. **Adaptive worker count**: Monitor CPU usage and adjust workers dynamically
2. **Progress estimation**: Show ETA based on completed files and current throughput
3. **Distributed indexing**: Support multiple machines for extremely large repos (100,000+ files)
4. **Streaming writes**: Write chunks as soon as available instead of buffering
5. **GPU acceleration**: Use GPU for embedding generation if available

## Open Questions & Risks

### Resolved

- ✅ **Will batched writes eliminate degradation?** Likely yes - LanceDB append overhead is the culprit
- ✅ **Is 500 file batch size optimal?** Should be, but we'll measure and tune
- ✅ **Can workers pickle all necessary data?** Yes, pass config as dict

### Remaining

- ⚠️ **Windows compatibility**: Needs testing on Windows platform
- ⚠️ **LanceDB concurrent write behavior**: Assumes single writer is safe (should be)
- ⚠️ **Embedder model loading overhead**: 2-3 sec per worker might add up - measure in practice

## References

- Current implementation: [indexer.py:55-144](src/semdex/indexer.py#L55-L144)
- Embedding API: [embeddings.py:12-16](src/semdex/embeddings.py#L12-L16)
- Chunking logic: [chunker.py:128-137](src/semdex/chunker.py#L128-L137)
- Store implementation: [store.py:46-49](src/semdex/store.py#L46-L49)
- Original design doc: [docs/designs/2026-03-21-01-semdex-design.md](docs/designs/2026-03-21-01-semdex-design.md)

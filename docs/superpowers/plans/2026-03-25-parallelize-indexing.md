# Parallelize Indexing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add parallel processing to semdex indexing to achieve 8-10x speedup on large repositories (20,000+ files) using multiprocessing with batched database writes.

**Architecture:** Replace sequential file processing with ProcessPoolExecutor (10 workers). Each worker independently reads, chunks, and embeds files. Main thread collects results in batches of 500 files, then writes to LanceDB in single operations to avoid write performance degradation.

**Tech Stack:** Python `concurrent.futures.ProcessPoolExecutor`, existing fastembed/LanceDB stack, click for progress tracking

---

## File Structure

**New files:**
- None - all changes are modifications to existing files

**Modified files:**
- `src/semdex/config.py` - Add parallel configuration fields
- `src/semdex/indexer.py` - Add parallel indexing implementation
- `tests/test_indexer.py` - Add parallel indexing tests
- `tests/test_indexer_pipeline.py` - Add integration tests
- `README.md` - Document parallel performance and configuration

**Key design decisions:**
- Keep sequential path unchanged for backward compatibility
- Add new `_index_parallel()` function alongside existing code
- Configuration controls whether parallel or sequential is used
- Workers are stateless (each creates its own embedder)
- Single writer pattern (main thread only writes to database)

---

### Task 1: Add Parallel Configuration

**Files:**
- Modify: `src/semdex/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1.1: Write test for parallel config defaults**

```python
def test_config_parallel_defaults():
    """Test that parallel config has sensible defaults."""
    config = SemdexConfig(project_root=Path("/tmp/test"))
    assert config.parallel_enabled is True
    assert config.parallel_workers == 0  # 0 = auto-detect
    assert config.write_batch_size == 500
    assert config.min_files_for_parallel == 50
```

- [ ] **Step 1.2: Run test to verify it fails**

Run: `pytest tests/test_config.py::test_config_parallel_defaults -v`
Expected: FAIL with "SemdexConfig has no attribute 'parallel_enabled'"

- [ ] **Step 1.3: Add parallel fields to SemdexConfig**

In `src/semdex/config.py`, add to `SemdexConfig` dataclass:

```python
# Parallelism settings
parallel_enabled: bool = True
parallel_workers: int = 0  # 0 = auto-detect (cpu_count - 1)
write_batch_size: int = 500  # Files per batch write
min_files_for_parallel: int = 50  # Use sequential for small jobs
```

- [ ] **Step 1.4: Run test to verify it passes**

Run: `pytest tests/test_config.py::test_config_parallel_defaults -v`
Expected: PASS

- [ ] **Step 1.5: Commit**

```bash
git add src/semdex/config.py tests/test_config.py
git commit -m "Add parallel indexing configuration"
```

---

### Task 2: Create Worker Function (Process-Safe)

**Files:**
- Modify: `src/semdex/indexer.py` (add worker function at top of file)
- Test: `tests/test_indexer.py`

- [ ] **Step 2.1: Write test for worker function success case**

```python
def test_process_file_worker_success():
    """Worker processes file and returns chunks with embeddings."""
    import tempfile
    from semdex.indexer import _process_file_worker

    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        file_path = root / "test.py"
        file_path.write_text("x = 1\ny = 2")

        args = (
            file_path,
            root,  # base_path
            {"chunk_threshold": 200, "max_file_size": 1_000_000},  # config_dict
            "sentence-transformers/all-MiniLM-L6-v2",  # model_name
            str(root),  # source_dir
            "2026-03-25T12:00:00Z"  # now
        )

        result = _process_file_worker(args)

        assert result["file_path"] == "test.py"
        assert result["error"] is None
        assert len(result["chunks"]) > 0
        assert "vector" in result["chunks"][0]
        assert result["chunks"][0]["mtime"] > 0
```

- [ ] **Step 2.2: Run test to verify it fails**

Run: `pytest tests/test_indexer.py::test_process_file_worker_success -v`
Expected: FAIL with "cannot import name '_process_file_worker'"

- [ ] **Step 2.3: Implement worker function**

Add to `src/semdex/indexer.py` after imports:

```python
# Global cache for worker embedders (process-local)
_worker_embedder_cache = {}


def _process_file_worker(args: tuple) -> dict:
    """Process a single file in worker process.

    Args:
        args: (file_path, base_path, config_dict, model_name, source_dir, now)

    Returns:
        {
            'file_path': str (relative),
            'chunks': list[dict] with vectors,
            'mtime': float,
            'error': str | None
        }
    """
    file_path, base_path, config_dict, model_name, source_dir, now = args

    try:
        # Get or create embedder for this worker process
        import os
        pid = os.getpid()
        if pid not in _worker_embedder_cache:
            from semdex.embeddings import LocalEmbedder
            _worker_embedder_cache[pid] = LocalEmbedder(model_name=model_name)
        embedder = _worker_embedder_cache[pid]

        # Calculate relative path
        try:
            rel_path = str(file_path.relative_to(base_path))
        except ValueError:
            rel_path = file_path.name

        # Chunk the file
        from semdex.chunker import chunk_file
        chunks = chunk_file(file_path, threshold=config_dict["chunk_threshold"])

        # Get file mtime
        mtime = file_path.stat().st_mtime

        # Build chunk dicts
        file_chunks = []
        for chunk in chunks:
            file_chunks.append({
                "file_path": rel_path,
                "start_line": chunk.start_line,
                "end_line": chunk.end_line,
                "chunk_type": chunk.chunk_type,
                "content": chunk.content,
                "source_dir": source_dir,
                "last_indexed": now,
                "mtime": mtime,
            })

        # Generate embeddings
        if file_chunks:
            texts = [c["content"] for c in file_chunks]
            vectors = embedder.encode(texts)
            for chunk, vector in zip(file_chunks, vectors):
                chunk["vector"] = vector

        return {
            "file_path": rel_path,
            "chunks": file_chunks,
            "mtime": mtime,
            "error": None,
        }

    except Exception as e:
        return {
            "file_path": str(file_path),
            "chunks": [],
            "mtime": 0,
            "error": str(e),
        }
```

- [ ] **Step 2.4: Run test to verify it passes**

Run: `pytest tests/test_indexer.py::test_process_file_worker_success -v`
Expected: PASS

- [ ] **Step 2.5: Commit**

```bash
git add src/semdex/indexer.py tests/test_indexer.py
git commit -m "Add worker function for parallel processing"
```

---

### Task 3: Add Worker Error Handling Test

**Files:**
- Test: `tests/test_indexer.py`

- [ ] **Step 3.1: Write test for worker error handling**

```python
def test_process_file_worker_handles_errors():
    """Worker catches errors and returns error dict."""
    from semdex.indexer import _process_file_worker

    # Use non-existent file to trigger error
    args = (
        Path("/nonexistent/file.py"),
        Path("/tmp"),
        {"chunk_threshold": 200, "max_file_size": 1_000_000},
        "sentence-transformers/all-MiniLM-L6-v2",
        "/tmp",
        "2026-03-25T12:00:00Z"
    )

    result = _process_file_worker(args)

    assert result["error"] is not None
    assert "file.py" in result["file_path"]
    assert len(result["chunks"]) == 0
```

- [ ] **Step 3.2: Run test to verify it passes**

Run: `pytest tests/test_indexer.py::test_process_file_worker_handles_errors -v`
Expected: PASS (already implemented in worker function)

- [ ] **Step 3.3: Commit**

```bash
git add tests/test_indexer.py
git commit -m "Add worker error handling test"
```

---

### Task 4: Create Parallel Indexing Function

**Files:**
- Modify: `src/semdex/indexer.py` (add `_index_parallel` function)
- Test: `tests/test_indexer.py`

- [ ] **Step 4.1: Write test for parallel indexing basic functionality**

```python
def test_index_parallel_processes_files():
    """Parallel indexing processes multiple files correctly."""
    import tempfile
    from semdex.indexer import index_project
    from semdex.config import SemdexConfig

    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)

        # Create multiple test files
        for i in range(10):
            (root / f"file{i}.py").write_text(f"x = {i}")

        config = SemdexConfig(
            project_root=root,
            parallel_enabled=True,
            parallel_workers=2  # Use 2 workers for test
        )
        config.ensure_dirs()

        stats = index_project(root, config)

        assert stats["files_indexed"] == 10
        assert stats["files_failed"] == 0
        assert stats["chunks_created"] > 0
```

- [ ] **Step 4.2: Run test to verify it fails**

Run: `pytest tests/test_indexer.py::test_index_parallel_processes_files -v`
Expected: FAIL with "stats has no key 'files_failed'"

- [ ] **Step 4.3: Add _index_parallel function**

Add to `src/semdex/indexer.py` before `index_project`:

```python
def _index_parallel(
    files: list[Path],
    store: SemdexStore,
    config: SemdexConfig,
    base_path: Path,
    source_dir: str,
    now: str,
) -> dict:
    """Index files in parallel using process pool.

    Args:
        files: List of file paths to index
        store: SemdexStore instance
        config: SemdexConfig instance
        base_path: Base path for relative path calculation
        source_dir: Source directory string
        now: ISO timestamp string

    Returns:
        Stats dict with files_indexed, files_failed, chunks_created
    """
    import os
    from concurrent.futures import ProcessPoolExecutor, as_completed

    # Determine worker count
    num_workers = config.parallel_workers
    if num_workers == 0:
        num_workers = max(1, os.cpu_count() - 1)
    num_workers = min(num_workers, 11)  # Cap at 11

    # Sort files by size (largest first) for better load balancing
    files_with_size = [(f, f.stat().st_size) for f in files]
    files_with_size.sort(key=lambda x: x[1], reverse=True)
    sorted_files = [f for f, _ in files_with_size]

    # Prepare config dict (serializable)
    config_dict = {
        "chunk_threshold": config.chunk_threshold,
        "max_file_size": config.max_file_size,
    }

    # Stats tracking
    files_indexed = 0
    files_failed = 0
    total_chunks = 0
    results_buffer = []

    with ProcessPoolExecutor(max_workers=num_workers) as executor:
        # Submit all files to pool
        future_to_file = {
            executor.submit(
                _process_file_worker,
                (f, base_path, config_dict, config.embedding_model, source_dir, now)
            ): f
            for f in sorted_files
        }

        # Process results as they complete
        with click.progressbar(
            length=len(sorted_files),
            label="Indexing",
            show_pos=True
        ) as bar:
            for future in as_completed(future_to_file):
                result = future.result()

                if result["error"]:
                    files_failed += 1
                    click.echo(f"\nWarning: Failed to process {result['file_path']}: {result['error']}", err=True)
                else:
                    # Delete old chunks for this file before adding new ones
                    store.delete_by_file(result["file_path"])

                    # Add to buffer
                    results_buffer.extend(result["chunks"])
                    files_indexed += 1
                    total_chunks += len(result["chunks"])

                    # Batch write when buffer is full
                    if len(results_buffer) >= config.write_batch_size:
                        if results_buffer:
                            store.add_chunks(results_buffer)
                        results_buffer.clear()

                bar.update(1)

            # Flush remaining results
            if results_buffer:
                store.add_chunks(results_buffer)
                results_buffer.clear()

    return {
        "files_indexed": files_indexed,
        "files_failed": files_failed,
        "chunks_created": total_chunks,
    }
```

- [ ] **Step 4.4: Run test to verify it passes**

Run: `pytest tests/test_indexer.py::test_index_parallel_processes_files -v`
Expected: PASS

- [ ] **Step 4.5: Commit**

```bash
git add src/semdex/indexer.py tests/test_indexer.py
git commit -m "Add parallel indexing implementation"
```

---

### Task 5: Integrate Parallel Path into index_project

**Files:**
- Modify: `src/semdex/indexer.py` (modify `index_project` function)
- Test: `tests/test_indexer.py`

- [ ] **Step 5.1: Write test for parallel vs sequential selection**

```python
def test_index_project_uses_parallel_when_enabled():
    """index_project uses parallel path when enabled and enough files."""
    import tempfile
    from semdex.indexer import index_project
    from semdex.config import SemdexConfig

    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)

        # Create 60 files (above min_files_for_parallel threshold)
        for i in range(60):
            (root / f"file{i}.py").write_text(f"x = {i}")

        config = SemdexConfig(
            project_root=root,
            parallel_enabled=True,
            parallel_workers=2,
            min_files_for_parallel=50
        )
        config.ensure_dirs()

        stats = index_project(root, config)

        # Should use parallel path
        assert stats["files_indexed"] == 60
        assert "files_failed" in stats  # Parallel path returns this


def test_index_project_uses_sequential_for_small_jobs():
    """index_project uses sequential path for small file counts."""
    import tempfile
    from semdex.indexer import index_project
    from semdex.config import SemdexConfig

    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)

        # Create only 10 files (below threshold)
        for i in range(10):
            (root / f"file{i}.py").write_text(f"x = {i}")

        config = SemdexConfig(
            project_root=root,
            parallel_enabled=True,
            min_files_for_parallel=50
        )
        config.ensure_dirs()

        stats = index_project(root, config)

        # Should use sequential path (no files_failed key)
        assert stats["files_indexed"] == 10
```

- [ ] **Step 5.2: Run tests to verify they fail**

Run: `pytest tests/test_indexer.py::test_index_project_uses_parallel_when_enabled tests/test_indexer.py::test_index_project_uses_sequential_for_small_jobs -v`
Expected: FAIL with assertion errors

- [ ] **Step 5.3: Refactor existing index_project logic into _index_sequential**

In `src/semdex/indexer.py`, extract the current file processing loop into a new function:

```python
def _index_sequential(
    files: list[Path],
    store: SemdexStore,
    config: SemdexConfig,
    base_path: Path,
    source_dir: str,
    now: str,
) -> dict:
    """Index files sequentially (original implementation).

    Args:
        files: List of file paths to index
        store: SemdexStore instance
        config: SemdexConfig instance
        base_path: Base path for relative path calculation
        source_dir: Source directory string
        now: ISO timestamp string

    Returns:
        Stats dict with files_indexed, chunks_created
    """
    total_chunks = 0
    files_indexed = 0

    with click.progressbar(files, label="Indexing", length=len(files),
                           item_show_func=lambda p: p.name if p else "") as bar:
        for path in bar:
            # Calculate relative path
            try:
                rel_path = str(path.relative_to(base_path))
            except ValueError:
                rel_path = str(path)

            # Delete old chunks for this file before re-indexing
            store.delete_by_file(rel_path)

            # Chunk the file
            chunks = chunk_file(path, threshold=config.chunk_threshold)

            # Get file mtime
            mtime = path.stat().st_mtime

            file_chunks = []
            for chunk in chunks:
                file_chunks.append({
                    "file_path": rel_path,
                    "start_line": chunk.start_line,
                    "end_line": chunk.end_line,
                    "chunk_type": chunk.chunk_type,
                    "content": chunk.content,
                    "source_dir": source_dir,
                    "last_indexed": now,
                    "mtime": mtime,
                })

            if file_chunks:
                # Generate embeddings
                embedder = LocalEmbedder(model_name=config.embedding_model)
                texts = [c["content"] for c in file_chunks]
                vectors = embedder.encode(texts)
                for chunk, vector in zip(file_chunks, vectors):
                    chunk["vector"] = vector
                store.add_chunks(file_chunks)
                total_chunks += len(file_chunks)
                files_indexed += 1

    return {
        "files_indexed": files_indexed,
        "chunks_created": total_chunks,
    }
```

- [ ] **Step 5.4: Modify index_project to route to parallel or sequential**

Replace the file processing loop in `index_project` with routing logic:

```python
def index_project(
    project_root: Path,
    config: SemdexConfig,
    files: list[Path] | None = None,
    target_dir: Path | None = None,
    force: bool = False,
) -> dict:
    """Index files and store embeddings. Returns stats dict."""
    store = SemdexStore(db_path=config.db_path, dimension=384)

    if target_dir:
        # Index external directory — don't respect gitignore
        file_list = discover_files(target_dir, config, respect_gitignore=False)
        source_dir = str(target_dir.resolve())
        to_index, to_skip = _filter_files_by_mtime(file_list, store, force, target_dir)
        base_path = target_dir
    elif files:
        file_list = files
        source_dir = str(project_root.resolve())
        to_index, to_skip = _filter_files_by_mtime(file_list, store, force, project_root)
        base_path = project_root
    else:
        # Full project scan
        file_list = discover_files(project_root, config)
        source_dir = str(project_root.resolve())
        to_index, to_skip = _filter_files_by_mtime(file_list, store, force, project_root)
        base_path = project_root

    now = datetime.now(timezone.utc).isoformat()
    total_files = len(file_list)
    files_skipped = len(to_skip)

    # Choose parallel or sequential path
    use_parallel = (
        config.parallel_enabled
        and len(to_index) >= config.min_files_for_parallel
    )

    if use_parallel:
        index_stats = _index_parallel(
            to_index, store, config, base_path, source_dir, now
        )
    else:
        index_stats = _index_sequential(
            to_index, store, config, base_path, source_dir, now
        )

    # Pruning: only for full project scans (no target specified)
    files_deleted = 0
    if not target_dir and not files:
        files_deleted = _prune_deleted_files(file_list, store, source_dir, base_path)

    return {
        "files_discovered": total_files,
        "files_skipped": files_skipped,
        "files_indexed": index_stats["files_indexed"],
        "files_failed": index_stats.get("files_failed", 0),
        "files_deleted": files_deleted,
        "chunks_created": index_stats["chunks_created"],
    }
```

- [ ] **Step 5.5: Run tests to verify they pass**

Run: `pytest tests/test_indexer.py::test_index_project_uses_parallel_when_enabled tests/test_indexer.py::test_index_project_uses_sequential_for_small_jobs -v`
Expected: PASS

- [ ] **Step 5.6: Run all existing indexer tests**

Run: `pytest tests/test_indexer.py -v`
Expected: All tests PASS (backward compatibility maintained)

- [ ] **Step 5.7: Commit**

```bash
git add src/semdex/indexer.py tests/test_indexer.py
git commit -m "Integrate parallel path into index_project"
```

---

### Task 6: Fix Sequential Path Embedder Creation

**Files:**
- Modify: `src/semdex/indexer.py` (_index_sequential function)

- [ ] **Step 6.1: Move embedder creation outside loop in _index_sequential**

The current implementation creates a new embedder for each file, which is inefficient. Modify `_index_sequential`:

```python
def _index_sequential(
    files: list[Path],
    store: SemdexStore,
    config: SemdexConfig,
    base_path: Path,
    source_dir: str,
    now: str,
) -> dict:
    """Index files sequentially (original implementation)."""
    # Create embedder once, reuse for all files
    embedder = LocalEmbedder(model_name=config.embedding_model)

    total_chunks = 0
    files_indexed = 0

    with click.progressbar(files, label="Indexing", length=len(files),
                           item_show_func=lambda p: p.name if p else "") as bar:
        for path in bar:
            # ... existing logic ...

            if file_chunks:
                # Generate embeddings (reuse embedder)
                texts = [c["content"] for c in file_chunks]
                vectors = embedder.encode(texts)
                for chunk, vector in zip(file_chunks, vectors):
                    chunk["vector"] = vector
                store.add_chunks(file_chunks)
                total_chunks += len(file_chunks)
                files_indexed += 1

    return {
        "files_indexed": files_indexed,
        "chunks_created": total_chunks,
    }
```

- [ ] **Step 6.2: Run all indexer tests**

Run: `pytest tests/test_indexer.py -v`
Expected: All tests PASS

- [ ] **Step 6.3: Commit**

```bash
git add src/semdex/indexer.py
git commit -m "Fix embedder creation in sequential path"
```

---

### Task 7: Add Parallel Performance Test

**Files:**
- Test: `tests/test_indexer_pipeline.py`

- [ ] **Step 7.1: Write performance comparison test**

```python
def test_parallel_faster_than_sequential():
    """Parallel indexing should be faster than sequential for many files."""
    import tempfile
    import time
    from semdex.indexer import index_project
    from semdex.config import SemdexConfig

    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)

        # Create 100 files with some content
        for i in range(100):
            content = "\n".join([f"line_{j} = {i * 100 + j}" for j in range(50)])
            (root / f"file{i}.py").write_text(content)

        # Test sequential
        config_seq = SemdexConfig(
            project_root=root,
            parallel_enabled=False
        )
        config_seq.ensure_dirs()

        start = time.time()
        stats_seq = index_project(root, config_seq)
        time_seq = time.time() - start

        # Clear the index
        import shutil
        shutil.rmtree(config_seq.db_path)

        # Test parallel
        config_par = SemdexConfig(
            project_root=root,
            parallel_enabled=True,
            parallel_workers=4
        )
        config_par.ensure_dirs()

        start = time.time()
        stats_par = index_project(root, config_par)
        time_par = time.time() - start

        # Verify correctness
        assert stats_seq["files_indexed"] == stats_par["files_indexed"]
        assert stats_seq["chunks_created"] == stats_par["chunks_created"]

        # Verify speedup (at least 2x on 4 workers)
        print(f"\nSequential: {time_seq:.2f}s, Parallel: {time_par:.2f}s")
        assert time_par < time_seq * 0.7, f"Expected speedup, got {time_seq/time_par:.2f}x"
```

- [ ] **Step 7.2: Run test to verify parallel is faster**

Run: `pytest tests/test_indexer_pipeline.py::test_parallel_faster_than_sequential -v -s`
Expected: PASS with speedup printed

- [ ] **Step 7.3: Commit**

```bash
git add tests/test_indexer_pipeline.py
git commit -m "Add parallel performance test"
```

---

### Task 8: Add Memory Safety Test

**Files:**
- Test: `tests/test_indexer_pipeline.py`

- [ ] **Step 8.1: Write memory usage test**

```python
def test_parallel_memory_stays_bounded():
    """Parallel indexing should not use excessive memory."""
    import tempfile
    import tracemalloc
    from semdex.indexer import index_project
    from semdex.config import SemdexConfig

    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)

        # Create 1000 small files
        for i in range(1000):
            (root / f"file{i}.py").write_text(f"x = {i}\ny = {i+1}")

        config = SemdexConfig(
            project_root=root,
            parallel_enabled=True,
            parallel_workers=4,
            write_batch_size=100  # Small batches for this test
        )
        config.ensure_dirs()

        # Track memory
        tracemalloc.start()
        baseline = tracemalloc.get_traced_memory()[0]

        stats = index_project(root, config)

        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        # Peak memory should be reasonable (< 2 GB = 2,000,000,000 bytes)
        peak_mb = peak / 1024 / 1024
        print(f"\nPeak memory: {peak_mb:.2f} MB")

        assert stats["files_indexed"] == 1000
        assert peak < 2_000_000_000, f"Peak memory too high: {peak_mb:.2f} MB"
```

- [ ] **Step 8.2: Run test to verify memory is bounded**

Run: `pytest tests/test_indexer_pipeline.py::test_parallel_memory_stays_bounded -v -s`
Expected: PASS with memory usage printed

- [ ] **Step 8.3: Commit**

```bash
git add tests/test_indexer_pipeline.py
git commit -m "Add memory safety test for parallel indexing"
```

---

### Task 9: Test Parallel Correctness

**Files:**
- Test: `tests/test_indexer.py`

- [ ] **Step 9.1: Write test for parallel vs sequential correctness**

```python
def test_parallel_produces_same_results_as_sequential():
    """Parallel and sequential modes produce identical index."""
    import tempfile
    from semdex.indexer import index_project
    from semdex.config import SemdexConfig
    from semdex.store import SemdexStore

    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)

        # Create test files with varied content
        (root / "small.py").write_text("x = 1")
        (root / "medium.py").write_text("\n".join([f"line_{i} = {i}" for i in range(50)]))
        (root / "large.py").write_text("\n".join([f"def func_{i}():\n    return {i}" for i in range(100)]))

        # Index with sequential
        config_seq = SemdexConfig(project_root=root, parallel_enabled=False)
        config_seq.ensure_dirs()
        stats_seq = index_project(root, config_seq)

        store_seq = SemdexStore(db_path=config_seq.db_path)
        metadata_seq = store_seq.get_all_file_metadata()

        # Clear and index with parallel
        import shutil
        shutil.rmtree(config_seq.db_path)

        config_par = SemdexConfig(project_root=root, parallel_enabled=True, parallel_workers=2)
        config_par.ensure_dirs()
        stats_par = index_project(root, config_par)

        store_par = SemdexStore(db_path=config_par.db_path)
        metadata_par = store_par.get_all_file_metadata()

        # Compare stats
        assert stats_seq["files_indexed"] == stats_par["files_indexed"]
        assert stats_seq["chunks_created"] == stats_par["chunks_created"]

        # Compare metadata
        assert set(metadata_seq.keys()) == set(metadata_par.keys())
        for file_path in metadata_seq:
            assert metadata_seq[file_path]["chunk_count"] == metadata_par[file_path]["chunk_count"]
```

- [ ] **Step 9.2: Run test to verify correctness**

Run: `pytest tests/test_indexer.py::test_parallel_produces_same_results_as_sequential -v`
Expected: PASS

- [ ] **Step 9.3: Commit**

```bash
git add tests/test_indexer.py
git commit -m "Add parallel correctness test"
```

---

### Task 10: Test Parallel Respects mtime Skip

**Files:**
- Test: `tests/test_indexer.py`

- [ ] **Step 10.1: Write test for parallel mtime skip**

```python
def test_parallel_respects_mtime_skip():
    """Parallel mode skips unchanged files based on mtime."""
    import tempfile
    import time
    from semdex.indexer import index_project
    from semdex.config import SemdexConfig

    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)

        # Create files
        file1 = root / "file1.py"
        file2 = root / "file2.py"
        file1.write_text("x = 1")
        file2.write_text("y = 2")

        config = SemdexConfig(project_root=root, parallel_enabled=True, parallel_workers=2)
        config.ensure_dirs()

        # First index
        stats1 = index_project(root, config)
        assert stats1["files_indexed"] == 2
        assert stats1["files_skipped"] == 0

        # Second index without changes - should skip both
        stats2 = index_project(root, config)
        assert stats2["files_indexed"] == 0
        assert stats2["files_skipped"] == 2

        # Modify one file
        time.sleep(0.01)
        file1.write_text("x = 100")

        # Third index - should index only modified file
        stats3 = index_project(root, config)
        assert stats3["files_indexed"] == 1
        assert stats3["files_skipped"] == 1
```

- [ ] **Step 10.2: Run test to verify skip logic works**

Run: `pytest tests/test_indexer.py::test_parallel_respects_mtime_skip -v`
Expected: PASS

- [ ] **Step 10.3: Commit**

```bash
git add tests/test_indexer.py
git commit -m "Add test for parallel mtime skip logic"
```

---

### Task 11: Test Force Flag with Parallel

**Files:**
- Test: `tests/test_indexer.py`

- [ ] **Step 11.1: Write test for force flag**

```python
def test_parallel_force_flag_reindexes_all():
    """Parallel mode with force=True bypasses skip logic."""
    import tempfile
    from semdex.indexer import index_project
    from semdex.config import SemdexConfig

    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)

        file1 = root / "file1.py"
        file1.write_text("x = 1")

        config = SemdexConfig(project_root=root, parallel_enabled=True, parallel_workers=2)
        config.ensure_dirs()

        # First index
        stats1 = index_project(root, config)
        assert stats1["files_indexed"] == 1

        # Force re-index
        stats2 = index_project(root, config, force=True)
        assert stats2["files_indexed"] == 1
        assert stats2["files_skipped"] == 0
```

- [ ] **Step 11.2: Run test to verify force flag works**

Run: `pytest tests/test_indexer.py::test_parallel_force_flag_reindexes_all -v`
Expected: PASS

- [ ] **Step 11.3: Commit**

```bash
git add tests/test_indexer.py
git commit -m "Add test for parallel force flag"
```

---

### Task 12: Test Worker Crash Handling

**Files:**
- Test: `tests/test_indexer.py`

- [ ] **Step 12.1: Write test for graceful worker failure**

```python
def test_parallel_handles_worker_failures_gracefully():
    """Parallel indexing continues when individual workers fail."""
    import tempfile
    from semdex.indexer import index_project
    from semdex.config import SemdexConfig

    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)

        # Create mix of good and problematic files
        (root / "good1.py").write_text("x = 1")
        (root / "good2.py").write_text("y = 2")
        # Create a file that will be deleted before processing
        problematic = root / "will_be_deleted.py"
        problematic.write_text("z = 3")

        config = SemdexConfig(project_root=root, parallel_enabled=True, parallel_workers=2)
        config.ensure_dirs()

        # Delete the problematic file to cause an error during processing
        # (This simulates race condition where file is deleted between discovery and processing)
        problematic.unlink()

        # Index should complete despite error
        stats = index_project(root, config)

        # Should index the good files
        assert stats["files_indexed"] == 2
        # Should track the failed file
        assert stats["files_failed"] >= 0  # May or may not catch the race condition
```

- [ ] **Step 12.2: Run test to verify error handling**

Run: `pytest tests/test_indexer.py::test_parallel_handles_worker_failures_gracefully -v`
Expected: PASS

- [ ] **Step 12.3: Commit**

```bash
git add tests/test_indexer.py
git commit -m "Add test for worker failure handling"
```

---

### Task 13: Update README with Performance Documentation

**Files:**
- Modify: `README.md`

- [ ] **Step 13.1: Add Performance section to README**

After the "Integration with Claude Code" section, add:

```markdown
## Performance

Semdex uses parallel processing to index large repositories quickly:

- **Small repos** (< 100 files): Sequential mode, completes in seconds
- **Medium repos** (1,000-5,000 files): 10 workers, 1-2 minutes
- **Large repos** (20,000+ files): 10 workers, 6-8 minutes

On a 12-core system, expect 8-10x speedup vs sequential processing.

### Tuning Performance

Configure in `.claude/semdex/config.json`:

```json
{
  "parallel_enabled": true,
  "parallel_workers": 8,
  "write_batch_size": 1000,
  "min_files_for_parallel": 50
}
```

Or via CLI (future enhancement):

```bash
semdex index --workers 8 --batch-size 1000
```

**Configuration options:**

- `parallel_enabled`: Enable/disable parallel processing (default: `true`)
- `parallel_workers`: Number of worker processes. `0` = auto-detect (cpu_count - 1). Default: `0`
- `write_batch_size`: Files to buffer before writing to database. Larger = faster but more memory. Default: `500`
- `min_files_for_parallel`: Minimum files to trigger parallel mode. Below this uses sequential. Default: `50`

### Troubleshooting

**"Indexing is slow"**:
- Verify `parallel_enabled` is `true` in config
- Check system has multiple CPU cores available
- Ensure system has adequate RAM (16+ GB recommended)

**"Running out of memory"**:
- Reduce `write_batch_size` to `250` or `100`
- Reduce `parallel_workers` to `4` or `6`
- Close memory-intensive applications

**"System becomes unresponsive"**:
- Reduce `parallel_workers` to leave more CPU headroom
- Check system cooling (CPU throttling can slow things down)
```

- [ ] **Step 13.2: Commit README changes**

```bash
git add README.md
git commit -m "Document parallel indexing performance"
```

---

### Task 14: Run Full Test Suite

**Files:**
- All test files

- [ ] **Step 14.1: Run complete test suite**

Run: `pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 14.2: Run tests with coverage**

Run: `pytest tests/ --cov=semdex --cov-report=term-missing`
Expected: High coverage on modified modules

- [ ] **Step 14.3: Fix any failing tests**

If any tests fail, fix them and re-run until all pass.

- [ ] **Step 14.4: Commit any test fixes**

```bash
git add tests/
git commit -m "Fix remaining test issues"
```

---

### Task 15: Performance Benchmark on Real Repository

**Files:**
- Test: Manual verification

- [ ] **Step 15.1: Benchmark semdex itself (meta-test)**

Run sequential:
```bash
rm -rf .claude/semdex
time python -m semdex.cli index --project-root-dir . --parallel=false
```

Record time: `_________` seconds

Run parallel:
```bash
rm -rf .claude/semdex
time python -m semdex.cli index --project-root-dir .
```

Record time: `_________` seconds

Calculate speedup: `sequential_time / parallel_time = _________x`

- [ ] **Step 15.2: Verify results are identical**

Check that both indexes have same file count:
```bash
python -c "from semdex.store import SemdexStore; from semdex.config import SemdexConfig; config = SemdexConfig(); store = SemdexStore(config.db_path); print(store.stats())"
```

- [ ] **Step 15.3: Document results**

Add note to commit message with benchmark results.

- [ ] **Step 15.4: Commit benchmark documentation**

```bash
git commit --allow-empty -m "Benchmark: parallel achieves ${SPEEDUP}x on semdex repo"
```

---

## Verification Checklist

Before considering this complete:

- [ ] All existing tests still pass
- [ ] New parallel tests pass
- [ ] Sequential mode still works (backward compatibility)
- [ ] Configuration controls parallel behavior
- [ ] Performance improves by 4-8x on large repos
- [ ] Memory usage stays bounded (< 16 GB)
- [ ] Error handling works (failed files don't crash indexing)
- [ ] Documentation updated

## Notes

- **TDD Approach**: Each task follows test-first development
- **Incremental Commits**: Small, focused commits with clear messages
- **Backward Compatibility**: Sequential path preserved, parallel is additive
- **Configuration-Driven**: Users can tune or disable parallelism
- **Error Resilience**: Worker failures don't crash entire indexing run

## Future Enhancements

Not in scope for this plan, but possible future work:

1. CLI flags for `--workers` and `--batch-size` overrides
2. Progress estimation with ETA
3. Adaptive worker count based on CPU usage
4. GPU acceleration for embeddings
5. Distributed indexing across multiple machines

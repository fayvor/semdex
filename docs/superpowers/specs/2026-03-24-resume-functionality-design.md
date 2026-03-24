# Resume Functionality Design

## Problem Statement

Currently, `semdex index` always re-indexes every file in the project, even if most files haven't changed. This is wasteful for large projects. Additionally, if indexing is interrupted (Ctrl+C, crash, terminal close), there's no way to resume - the user must start over from scratch.

## Solution Overview

Implement smart indexing that tracks file modification times (`mtime`) and automatically skips unchanged files. This provides two key benefits:

1. **Automatic resume after interruption** - If indexing stops partway through, the next run will skip already-indexed files and continue with the rest
2. **Skip up-to-date files** - Only re-index files that have changed since the last index

Add a `--force` flag to override this behavior when a full rebuild is needed.

## Architecture & High-Level Changes

**Core concept:** Augment the existing indexing pipeline to track file modification times and use them to make indexing incremental by default.

**Key changes:**
1. **Store enhancement** - Add `mtime` field to chunk records in LanceDB
2. **Indexer enhancement** - Before processing files, query store for existing metadata and skip files where `mtime` hasn't changed
3. **CLI enhancement** - Add `--force` flag to `semdex index` with scope-dependent behavior

**Data flow:**
```
Discover files → Check each file's mtime against store → Skip if unchanged / Index if changed or new → Store chunks with mtime
```

**Backwards compatibility:** If `mtime` field is missing from existing chunks (old indexes), treat those files as "needs indexing" to bootstrap the new metadata.

## Store Changes (store.py)

### New Field in Chunk Schema

Add `mtime` (float) - Unix timestamp of file's last modification time.

This goes alongside existing fields: `file_path`, `start_line`, `end_line`, `chunk_type`, `content`, `source_dir`, `last_indexed`, `vector`.

### New Store Methods

#### `get_file_metadata(file_path: str) -> dict | None`

Returns metadata for a single file:
```python
{
    'file_path': str,
    'mtime': float,           # Unix timestamp
    'last_indexed': str,      # ISO timestamp
    'chunk_count': int
}
```

Returns `None` if file is not in the index.

Implementation: Query LanceDB for chunks matching the file path, extract `mtime` from the first chunk (all chunks for a file share the same mtime), and return the metadata.

#### `get_all_file_metadata() -> dict[str, dict]`

Returns a map of `file_path` -> metadata for all files in the index:
```python
{
    'src/foo.py': {'mtime': 1234567890.0, 'last_indexed': '2026-03-24T...', 'chunk_count': 5},
    'src/bar.py': {'mtime': 1234567891.0, 'last_indexed': '2026-03-24T...', 'chunk_count': 3},
    ...
}
```

**Purpose:** For large projects with thousands of files, querying one file at a time would be slow. This method fetches all file metadata in a single query, returning a dictionary we can check against during file discovery.

**Performance:** For a 10k file project, this loads ~10k dict entries into memory - negligible overhead.

## Indexer Changes (indexer.py)

### Enhanced `index_project()` Signature

```python
def index_project(
    project_root: Path,
    config: SemdexConfig,
    files: list[Path] | None = None,
    target_dir: Path | None = None,
    force: bool = False,  # NEW: bypass smart skip logic
) -> dict:
```

### New Indexing Logic Flow

1. **Discover files** (unchanged - still uses `discover_files()`)

2. **Load existing metadata**
   - Call `store.get_all_file_metadata()` once upfront
   - This gives us a snapshot of all indexed files and their mtimes

3. **Filter files**
   - For each discovered file:
     - Get current `mtime` from filesystem (`path.stat().st_mtime`)
     - Look up stored metadata from step 2
     - Apply skip logic (see below)
   - Separate files into: `to_skip` and `to_index` lists

4. **Index filtered files**
   - Process only the files in `to_index` list
   - For each file:
     - Delete old chunks for that file
     - Chunk the file
     - Generate embeddings
     - Store chunks with current `mtime` and `last_indexed`

5. **Prune deleted files** (only for full project scans)
   - Compare discovered files with indexed files
   - Remove chunks for files that no longer exist on disk
   - Only applies to files with matching `source_dir` (don't touch externally indexed directories)

6. **Progress bar**
   - Display: "Processing: X/Y (Z skipped, W indexed, D deleted)"
   - Update as each file is processed or skipped

### Skip Logic

**When to index a file:**
- `force=True` → index all files (skip detection disabled)
- File not in store → index (new file)
- File has no `mtime` in store → index (old schema, needs bootstrap)
- File's current `mtime` > stored `mtime` → index (modified)

**When to skip a file:**
- `force=False` AND file exists in index AND current `mtime` == stored `mtime` → skip (unchanged)

### Deleted File Pruning

After indexing, cleanup stale entries:

1. Get all file paths from store filtered by project's `source_dir`
2. Compare with discovered files
3. Delete chunks for files that are in store but not discovered
4. Track count for statistics

**When pruning runs:**
- During `semdex index` (full project scan without `target` argument)
- Skipped when indexing specific files/directories (`semdex index file.py`)

**Note:** `--force` doesn't affect deletion - we always prune when doing a full project scan.

### Updated Statistics

```python
{
    "files_discovered": 100,    # Total files found on disk
    "files_skipped": 85,        # NEW: Files skipped (unchanged)
    "files_indexed": 15,        # Files actually indexed
    "files_deleted": 3,         # NEW: Stale entries pruned from index
    "chunks_created": 42,       # Total chunks created for indexed files
}
```

## CLI Changes (cli.py)

### Add `--force` Flag

```python
@cli.command()
@click.argument("target", required=False)
@click.option("--force", is_flag=True, help="Force re-index (bypass mtime checks or rebuild from scratch)")
def index(target, force):
    """Build or rebuild the semantic index."""
    root = _find_project_root()
    config = SemdexConfig.load(root)
    config.ensure_dirs()

    if force and not target:
        # Full project + force: nuclear option - wipe and rebuild
        click.echo("Deleting existing index...")
        if config.db_path.exists():
            import shutil
            shutil.rmtree(config.db_path)
        click.echo("Rebuilding full index from scratch...")
        stats = index_project(root, config)
    elif target:
        # Specific file/dir: pass force flag to bypass mtime check
        target_path = Path(target).resolve()
        if target_path.is_dir():
            click.echo(f"Indexing directory: {target_path}")
            stats = index_project(root, config, target_dir=target_path, force=force)
        elif target_path.is_file():
            click.echo(f"Indexing file: {target_path}")
            stats = index_project(root, config, files=[target_path], force=force)
        else:
            click.echo(f"Error: {target} not found", err=True)
            raise SystemExit(1)
    else:
        # Full project, no force: smart indexing
        click.echo("Rebuilding full index...")
        stats = index_project(root, config)

    # Display results
    click.echo(f"Indexed {stats['files_indexed']} files ({stats['chunks_created']} chunks)")
```

### `--force` Flag Semantics

The `--force` flag has different behavior depending on scope:

1. **`semdex index --force`** (full project)
   - Delete entire index database
   - Rebuild everything from scratch
   - Use when index is corrupted or you want a clean slate

2. **`semdex index --force file.py`** (specific file)
   - Bypass mtime check for this file
   - Delete its old chunks and re-index
   - Use when file content changed but mtime didn't update

3. **`semdex index --force /some/dir`** (specific directory)
   - Bypass mtime check for all files in directory
   - Re-index entire directory regardless of mtimes

4. **`semdex index`** (no force, full project)
   - Smart indexing with skip detection
   - Default behavior

### Output Messages

**Smart indexing (default):**
```
Rebuilding full index...
Processing: 100/100 files (85 skipped, 15 indexed, 3 deleted)
Indexed 15 files (42 chunks)
```

**Force mode (full project):**
```
Deleting existing index...
Rebuilding full index from scratch...
Processing: 100/100 files (0 skipped, 100 indexed, 0 deleted)
Indexed 100 files (283 chunks)
```

**Specific file:**
```
Indexing file: /path/to/file.py
Indexed 1 file (3 chunks)
```

**Specific file with force:**
```
Indexing file: /path/to/file.py
Indexed 1 file (3 chunks)
```

### Progress Bar Implementation

Use click's progressbar with custom display:
- Show current file being processed
- Track running counts: skipped, indexed, deleted
- Update in real-time as files are processed

Example:
```python
with click.progressbar(
    all_files,
    label="Processing",
    length=len(all_files),
    item_show_func=lambda p: f"{p.name} (skipped: {skipped}, indexed: {indexed})" if p else ""
) as bar:
    for path in bar:
        # check skip logic, process or skip
```

## Error Handling & Edge Cases

### Scenario 1: Corrupted Index with Missing mtime Fields

**Problem:** Index was created before this feature, so `mtime` column doesn't exist.

**Solution:**
- When querying metadata, handle missing `mtime` gracefully
- Treat files with missing `mtime` as needing indexing
- This automatically bootstraps old indexes with the new field
- User can always use `--force` to rebuild cleanly if needed

### Scenario 2: Clock Skew or Filesystem Issues

**Problem:** File's `mtime` is in the future, zero, or otherwise suspicious.

**Solution:**
- Don't validate or sanitize `mtime` values
- Trust the filesystem and proceed with indexing
- If comparison fails due to weird timestamps, err on the side of re-indexing
- Don't fail the entire operation due to one bad timestamp

### Scenario 3: Interrupted Indexing

**Problem:** User hits Ctrl+C during indexing.

**Solution:**
- Chunks written so far are persisted (LanceDB writes are durable)
- Next run will skip successfully indexed files (based on mtime match)
- Partially-indexed files will be re-indexed:
  - We delete all chunks for a file before re-indexing it
  - If deletion completed but indexing didn't, file won't be in store
  - Next run treats it as a new file and indexes it

**Result:** Automatic resume without any special checkpoint mechanism.

### Scenario 4: File Modified During Indexing

**Problem:** A file changes while we're in the middle of indexing it.

**Solution:**
- Capture file's `mtime` before reading its content
- Store that `mtime` with the chunks
- If file was modified during indexing, next run will detect the newer `mtime` and re-index
- This is acceptable - we're not trying to be real-time consistent

### Scenario 5: Large Projects (10k+ Files)

**Problem:** Loading metadata for 10k files could be slow or memory-intensive.

**Solution:**
- `get_all_file_metadata()` loads all metadata into memory in one query
- For 10k files, this is ~10k dict entries with ~100 bytes each = ~1MB
- Negligible memory usage, and much faster than 10k individual queries
- If this becomes a bottleneck in the future, add batching (but unlikely to be needed)

### Scenario 6: External Directories

**Problem:** `semdex index /some/dir` indexes content outside the project.

**Solution:**
- Skip detection applies to external directories too
- They're tagged with their own `source_dir`, so won't interfere with project file pruning
- `--force` flag works the same way for external directories

### Scenario 7: File Permissions Changed but Content Didn't

**Problem:** File's `mtime` changed due to chmod, but content is identical.

**Solution:**
- We still re-index the file (based on `mtime` change)
- This is a false positive, but acceptable
- Content hashing would prevent this, but adds complexity and overhead
- The design prioritizes simplicity and performance over perfect accuracy

## Testing Considerations

Key scenarios to test:

1. **Fresh index** - Verify all files are indexed on first run
2. **Unchanged files** - Verify skip logic works, no unnecessary re-indexing
3. **Modified files** - Verify only modified files are re-indexed
4. **New files** - Verify new files are detected and indexed
5. **Deleted files** - Verify stale entries are pruned
6. **Interrupted indexing** - Kill process mid-index, verify resume works
7. **Force flag (full)** - Verify `--force` deletes and rebuilds everything
8. **Force flag (specific)** - Verify `--force file.py` re-indexes that file
9. **Large project** - Test with 1k+ files to verify performance
10. **Old index** - Test migration from index without `mtime` field
11. **External directory** - Verify skip logic works for `semdex index /path`
12. **Progress bar** - Verify counts are accurate and update in real-time

## Implementation Notes

### Store Schema Migration

LanceDB is schema-flexible, so adding `mtime` won't break existing indexes. When inserting new chunks:
- New chunks will have `mtime` field
- Old chunks won't have `mtime` field
- Query for `mtime` on old chunks returns `None` or missing field
- Treat missing `mtime` as "needs indexing" during skip logic

### Atomic Operations

Each file's indexing is atomic:
1. Delete old chunks for file
2. Index file and generate chunks
3. Insert chunks (with `mtime`)

If step 2 or 3 fails, old chunks are gone but file isn't in index - next run will index it.

### Performance Impact

**Query overhead:**
- One bulk query (`get_all_file_metadata()`) at start of indexing
- For 10k files: ~100-500ms query time (depends on LanceDB performance)
- Acceptable overhead compared to indexing time (seconds to minutes)

**Skip benefit:**
- If 90% of files unchanged, save 90% of indexing time
- For large projects, this is a massive win (minutes → seconds)

## Success Criteria

1. Running `semdex index` on an unchanged project should skip all files and complete in <5 seconds
2. Interrupting indexing and re-running should resume without re-indexing already-processed files
3. Progress bar should show accurate counts of skipped/indexed/deleted files
4. `--force` should reliably rebuild from scratch
5. Existing indexes without `mtime` should automatically bootstrap the new field
6. No performance regression for small projects (<100 files)

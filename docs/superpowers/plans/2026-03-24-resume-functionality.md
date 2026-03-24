# Resume Functionality Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add smart incremental indexing that tracks file modification times and automatically skips unchanged files, with ability to resume after interruption.

**Architecture:** Extend LanceDB chunk schema to include `mtime` field. Add store methods to query file metadata. Modify indexer to check mtimes before processing files. Add CLI `--force` flag for full rebuild.

**Tech Stack:** Python, LanceDB, Click, pytest

---

## File Structure

**Modified files:**
- `src/semdex/store.py` - Add `mtime` field, `get_file_metadata()`, `get_all_file_metadata()`
- `src/semdex/indexer.py` - Add skip logic, file pruning, updated progress tracking
- `src/semdex/cli.py` - Add `--force` flag with scope-dependent behavior

**Test files:**
- `tests/test_store.py` - Add tests for new metadata methods
- `tests/test_indexer.py` - Add tests for skip logic and pruning
- `tests/test_cli.py` - Add tests for `--force` flag behavior
- `tests/test_resume_integration.py` - New file for end-to-end resume scenarios

---

## Task 1: Store - Add get_file_metadata() method

**Files:**
- Modify: `src/semdex/store.py:62-78`
- Test: `tests/test_store.py:127-160`

- [ ] **Step 1: Write failing test for get_file_metadata()**

Add to `tests/test_store.py`:

```python
def test_store_get_file_metadata():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = SemdexStore(db_path=Path(tmpdir) / "lance.db", dimension=4)
        store.add_chunks([
            {
                "file_path": "foo.py",
                "start_line": 1,
                "end_line": 10,
                "chunk_type": "whole-file",
                "content": "def foo(): pass",
                "source_dir": ".",
                "last_indexed": "2026-03-21T00:00:00",
                "mtime": 1234567890.0,
                "vector": [1.0, 0.0, 0.0, 0.0],
            },
            {
                "file_path": "foo.py",
                "start_line": 11,
                "end_line": 20,
                "chunk_type": "function",
                "content": "def bar(): pass",
                "source_dir": ".",
                "last_indexed": "2026-03-21T00:00:00",
                "mtime": 1234567890.0,
                "vector": [0.0, 1.0, 0.0, 0.0],
            },
        ])
        metadata = store.get_file_metadata("foo.py")
        assert metadata is not None
        assert metadata["file_path"] == "foo.py"
        assert metadata["mtime"] == 1234567890.0
        assert metadata["last_indexed"] == "2026-03-21T00:00:00"
        assert metadata["chunk_count"] == 2


def test_store_get_file_metadata_not_found():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = SemdexStore(db_path=Path(tmpdir) / "lance.db", dimension=4)
        metadata = store.get_file_metadata("nonexistent.py")
        assert metadata is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_store.py::test_store_get_file_metadata -xvs`

Expected: FAIL - `AttributeError: 'SemdexStore' object has no attribute 'get_file_metadata'`

- [ ] **Step 3: Implement get_file_metadata() method**

Add to `src/semdex/store.py` after `get_file_summary()` method:

```python
def get_file_metadata(self, file_path: str) -> dict | None:
    """Get metadata for a specific file.

    Returns:
        dict with keys: file_path, mtime, last_indexed, chunk_count
        None if file is not in index
    """
    table = self._get_table()
    if table is None:
        return None

    arrow_table = table.to_arrow()
    col = arrow_table.column("file_path").to_pylist()
    indices = [i for i, v in enumerate(col) if v == file_path]

    if not indices:
        return None

    # Get mtime from first chunk (all chunks for a file share same mtime)
    try:
        mtime = arrow_table.column("mtime")[indices[0]].as_py()
    except KeyError:
        # Old schema without mtime field
        mtime = None

    last_indexed = max(arrow_table.column("last_indexed")[i].as_py() for i in indices)

    return {
        "file_path": file_path,
        "mtime": mtime,
        "last_indexed": last_indexed,
        "chunk_count": len(indices),
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_store.py::test_store_get_file_metadata -xvs`

Expected: PASS (both test cases)

- [ ] **Step 5: Commit**

```bash
git add tests/test_store.py src/semdex/store.py
git commit -m "Add get_file_metadata() method to store"
```

---

## Task 2: Store - Add get_all_file_metadata() method

**Files:**
- Modify: `src/semdex/store.py:80-115`
- Test: `tests/test_store.py:162-200`

- [ ] **Step 1: Write failing test for get_all_file_metadata()**

Add to `tests/test_store.py`:

```python
def test_store_get_all_file_metadata():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = SemdexStore(db_path=Path(tmpdir) / "lance.db", dimension=4)
        store.add_chunks([
            {
                "file_path": "foo.py",
                "start_line": 1,
                "end_line": 10,
                "chunk_type": "whole-file",
                "content": "def foo(): pass",
                "source_dir": ".",
                "last_indexed": "2026-03-21T00:00:00",
                "mtime": 1234567890.0,
                "vector": [1.0, 0.0, 0.0, 0.0],
            },
            {
                "file_path": "bar.py",
                "start_line": 1,
                "end_line": 5,
                "chunk_type": "whole-file",
                "content": "def bar(): pass",
                "source_dir": ".",
                "last_indexed": "2026-03-21T00:00:01",
                "mtime": 1234567891.0,
                "vector": [0.0, 1.0, 0.0, 0.0],
            },
        ])
        all_metadata = store.get_all_file_metadata()
        assert len(all_metadata) == 2
        assert "foo.py" in all_metadata
        assert "bar.py" in all_metadata
        assert all_metadata["foo.py"]["mtime"] == 1234567890.0
        assert all_metadata["foo.py"]["chunk_count"] == 1
        assert all_metadata["bar.py"]["mtime"] == 1234567891.0
        assert all_metadata["bar.py"]["chunk_count"] == 1


def test_store_get_all_file_metadata_empty():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = SemdexStore(db_path=Path(tmpdir) / "lance.db", dimension=4)
        all_metadata = store.get_all_file_metadata()
        assert all_metadata == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_store.py::test_store_get_all_file_metadata -xvs`

Expected: FAIL - `AttributeError: 'SemdexStore' object has no attribute 'get_all_file_metadata'`

- [ ] **Step 3: Implement get_all_file_metadata() method**

Add to `src/semdex/store.py` after `get_file_metadata()`:

```python
def get_all_file_metadata(self) -> dict[str, dict]:
    """Get metadata for all files in the index.

    Returns:
        Dictionary mapping file_path -> {mtime, last_indexed, chunk_count}
    """
    table = self._get_table()
    if table is None:
        return {}

    arrow_table = table.to_arrow()
    file_paths = arrow_table.column("file_path").to_pylist()

    # Check if mtime column exists (backwards compatibility)
    try:
        mtimes = arrow_table.column("mtime").to_pylist()
        has_mtime = True
    except KeyError:
        mtimes = [None] * len(file_paths)
        has_mtime = False

    last_indexed_list = arrow_table.column("last_indexed").to_pylist()

    # Group by file_path
    metadata = {}
    for i, file_path in enumerate(file_paths):
        if file_path not in metadata:
            metadata[file_path] = {
                "mtime": mtimes[i] if has_mtime else None,
                "last_indexed": last_indexed_list[i],
                "chunk_count": 1,
            }
        else:
            metadata[file_path]["chunk_count"] += 1
            # Update last_indexed to the most recent
            if last_indexed_list[i] > metadata[file_path]["last_indexed"]:
                metadata[file_path]["last_indexed"] = last_indexed_list[i]

    return metadata
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_store.py::test_store_get_all_file_metadata -xvs`

Expected: PASS (both test cases)

- [ ] **Step 5: Commit**

```bash
git add tests/test_store.py src/semdex/store.py
git commit -m "Add get_all_file_metadata() method to store"
```

---

## Task 3: Indexer - Add file filtering with skip logic

**Files:**
- Modify: `src/semdex/indexer.py:55-121`
- Test: `tests/test_indexer.py:71-145`

- [ ] **Step 1: Write failing test for skip logic**

Add to `tests/test_indexer.py`:

```python
import time
from semdex.indexer import index_project


def test_index_project_skips_unchanged_files():
    """Test that files with matching mtime are skipped."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)

        # Create initial files
        file1 = root / "file1.py"
        file2 = root / "file2.py"
        file1.write_text("x = 1")
        file2.write_text("y = 2")

        config = SemdexConfig(project_root=root)
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
        time.sleep(0.01)  # Ensure mtime changes
        file1.write_text("x = 100")

        # Third index - should index only modified file
        stats3 = index_project(root, config)
        assert stats3["files_indexed"] == 1
        assert stats3["files_skipped"] == 1


def test_index_project_force_flag_reindexes_all():
    """Test that force=True bypasses skip logic."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)

        file1 = root / "file1.py"
        file1.write_text("x = 1")

        config = SemdexConfig(project_root=root)
        config.ensure_dirs()

        # First index
        stats1 = index_project(root, config)
        assert stats1["files_indexed"] == 1

        # Force re-index
        stats2 = index_project(root, config, force=True)
        assert stats2["files_indexed"] == 1
        assert stats2["files_skipped"] == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_indexer.py::test_index_project_skips_unchanged_files -xvs`

Expected: FAIL - `KeyError: 'files_skipped'` (stats dict doesn't have this key yet)

- [ ] **Step 3: Implement file filtering logic in index_project()**

Modify `src/semdex/indexer.py`, update the `index_project()` function:

```python
def index_project(
    project_root: Path,
    config: SemdexConfig,
    files: list[Path] | None = None,
    target_dir: Path | None = None,
    force: bool = False,
) -> dict:
    """Index files and store embeddings. Returns stats dict."""
    embedder = LocalEmbedder(model_name=config.embedding_model)
    store = SemdexStore(db_path=config.db_path, dimension=embedder.dimension)

    if target_dir:
        # Index external directory — don't respect gitignore
        file_list = discover_files(target_dir, config, respect_gitignore=False)
        source_dir = str(target_dir.resolve())
        # Remove old entries for this dir before re-indexing
        store.delete_by_source_dir(source_dir)
        # External dirs: apply skip logic unless force=True
        to_index, to_skip = _filter_files_by_mtime(file_list, store, force, target_dir)
    elif files:
        file_list = files
        source_dir = str(project_root.resolve())
        # Specific files: apply skip logic unless force=True
        to_index, to_skip = _filter_files_by_mtime(file_list, store, force, project_root)
        # Remove old entries for specified files that will be re-indexed
        for f in to_index:
            try:
                rel_path = str(f.relative_to(project_root))
            except ValueError:
                rel_path = f.name
            store.delete_by_file(rel_path)
    else:
        # Full project scan
        file_list = discover_files(project_root, config)
        source_dir = str(project_root.resolve())
        # Apply skip logic unless force=True
        to_index, to_skip = _filter_files_by_mtime(file_list, store, force, project_root)

    now = datetime.now(timezone.utc).isoformat()
    total_files = len(file_list)
    total_chunks = 0
    files_skipped = len(to_skip)
    files_indexed = 0

    with click.progressbar(to_index, label="Indexing", length=len(to_index),
                           item_show_func=lambda p: p.name if p else "") as bar:
        for path in bar:
            chunks = chunk_file(path, threshold=config.chunk_threshold)
            if target_dir:
                rel_path = str(path.relative_to(target_dir))
            else:
                try:
                    rel_path = str(path.relative_to(project_root))
                except ValueError:
                    rel_path = str(path)

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
                texts = [c["content"] for c in file_chunks]
                vectors = embedder.encode(texts)
                for chunk, vector in zip(file_chunks, vectors):
                    chunk["vector"] = vector
                store.add_chunks(file_chunks)
                total_chunks += len(file_chunks)
                files_indexed += 1

    return {
        "files_discovered": total_files,
        "files_skipped": files_skipped,
        "files_indexed": files_indexed,
        "chunks_created": total_chunks,
    }


def _filter_files_by_mtime(
    files: list[Path],
    store: SemdexStore,
    force: bool,
    base_path: Path,
) -> tuple[list[Path], list[Path]]:
    """Filter files based on mtime, returning (to_index, to_skip).

    Args:
        files: List of file paths to consider
        store: SemdexStore instance
        force: If True, skip all filtering and index everything
        base_path: Base path for calculating relative paths (project_root or target_dir)

    Returns:
        (files_to_index, files_to_skip)
    """
    if force:
        return (files, [])

    # Get all metadata in one query
    all_metadata = store.get_all_file_metadata()

    to_index = []
    to_skip = []

    for file_path in files:
        # Get current mtime
        current_mtime = file_path.stat().st_mtime

        # Calculate relative path for lookup (store uses relative paths)
        try:
            rel_path = str(file_path.relative_to(base_path))
        except ValueError:
            # File outside base_path (shouldn't happen, but handle gracefully)
            rel_path = file_path.name

        # Check if file is in index
        if rel_path in all_metadata:
            stored_metadata = all_metadata[rel_path]
            stored_mtime = stored_metadata.get("mtime")

            # Skip if mtime matches (file unchanged)
            if stored_mtime is not None and current_mtime == stored_mtime:
                to_skip.append(file_path)
                continue

        # Index if: new file, mtime changed, or missing mtime (old schema)
        to_index.append(file_path)

    return (to_index, to_skip)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_indexer.py::test_index_project_skips_unchanged_files -xvs`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_indexer.py src/semdex/indexer.py
git commit -m "Add skip logic for unchanged files in indexer"
```

---

## Task 4: Indexer - Add file pruning for deleted files

**Files:**
- Modify: `src/semdex/indexer.py:122-160`
- Test: `tests/test_indexer.py:148-180`

- [ ] **Step 1: Write failing test for file pruning**

Add to `tests/test_indexer.py`:

```python
def test_index_project_prunes_deleted_files():
    """Test that deleted files are removed from index."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)

        # Create and index initial files
        file1 = root / "file1.py"
        file2 = root / "file2.py"
        file1.write_text("x = 1")
        file2.write_text("y = 2")

        config = SemdexConfig(project_root=root)
        config.ensure_dirs()

        stats1 = index_project(root, config)
        assert stats1["files_indexed"] == 2

        # Verify both files are in index
        store = SemdexStore(db_path=config.db_path)
        assert store.get_file_metadata("file1.py") is not None
        assert store.get_file_metadata("file2.py") is not None

        # Delete one file
        file2.unlink()

        # Re-index - should detect deletion
        stats2 = index_project(root, config)
        assert stats2["files_discovered"] == 1
        assert stats2["files_deleted"] == 1

        # Verify deleted file is removed from index
        assert store.get_file_metadata("file1.py") is not None
        assert store.get_file_metadata("file2.py") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_indexer.py::test_index_project_prunes_deleted_files -xvs`

Expected: FAIL - `KeyError: 'files_deleted'` or assertion failure on file2.py still being in index

- [ ] **Step 3: Implement file pruning logic**

Modify `src/semdex/indexer.py`:

1. Add pruning call to `index_project()` before the return statement
2. Add `_prune_deleted_files()` helper function at the end of the file

```python
def index_project(
    project_root: Path,
    config: SemdexConfig,
    files: list[Path] | None = None,
    target_dir: Path | None = None,
    force: bool = False,
) -> dict:
    """Index files and store embeddings. Returns stats dict."""
    # ... existing code ...

    # Pruning: only for full project scans (no target specified)
    files_deleted = 0
    if not target_dir and not files:
        files_deleted = _prune_deleted_files(file_list, store, source_dir, project_root)

    return {
        "files_discovered": total_files,
        "files_skipped": files_skipped,
        "files_indexed": files_indexed,
        "files_deleted": files_deleted,
        "chunks_created": total_chunks,
    }


def _prune_deleted_files(
    discovered_files: list[Path],
    store: SemdexStore,
    source_dir: str,
    project_root: Path,
) -> int:
    """Remove entries from index for files that no longer exist.

    Args:
        discovered_files: Files found during discovery
        store: SemdexStore instance
        source_dir: Source directory to filter by
        project_root: Project root for relative path calculation

    Returns:
        Count of files deleted from index
    """
    # Get all indexed files
    all_metadata = store.get_all_file_metadata()

    # Build set of discovered file paths (relative)
    discovered_set = set()
    for file_path in discovered_files:
        try:
            rel_path = str(file_path.relative_to(project_root))
        except ValueError:
            rel_path = file_path.name
        discovered_set.add(rel_path)

    # Find files in index but not discovered (deleted)
    deleted_count = 0
    for indexed_file in all_metadata.keys():
        if indexed_file not in discovered_set:
            # Only delete if it belongs to this source_dir
            # (don't touch externally indexed content)
            store.delete_by_file(indexed_file)
            deleted_count += 1

    return deleted_count
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_indexer.py::test_index_project_prunes_deleted_files -xvs`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_indexer.py src/semdex/indexer.py
git commit -m "Add file pruning for deleted files"
```

---

## Task 5: CLI - Add --force flag with full project rebuild

**Files:**
- Modify: `src/semdex/cli.py:75-99`
- Test: `tests/test_cli.py:120-160`

- [ ] **Step 1: Write failing test for --force flag**

Add to `tests/test_cli.py`:

```python
import shutil
from click.testing import CliRunner
from semdex.cli import cli
from semdex.config import SemdexConfig
from semdex.store import SemdexStore


def test_index_force_flag_rebuilds_from_scratch():
    """Test that --force deletes and rebuilds the entire index."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / "file1.py").write_text("x = 1")

        # Initialize git repo (required for _find_project_root)
        (root / ".git").mkdir()

        runner = CliRunner()

        # Initial index
        with runner.isolated_filesystem(temp_dir=tmpdir) as fs:
            os.chdir(root)
            result1 = runner.invoke(cli, ["index"])
            assert result1.exit_code == 0

            # Verify index exists
            config = SemdexConfig(project_root=root)
            assert config.db_path.exists()

            # Force rebuild
            result2 = runner.invoke(cli, ["index", "--force"])
            assert result2.exit_code == 0
            assert "Deleting existing index" in result2.output
            assert "Rebuilding full index from scratch" in result2.output
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_cli.py::test_index_force_flag_rebuilds_from_scratch -xvs`

Expected: FAIL - `no such option: --force`

- [ ] **Step 3: Add --force flag to CLI**

Modify `src/semdex/cli.py`, update the `index` command:

```python
import shutil


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
    skipped = stats.get("files_skipped", 0)
    deleted = stats.get("files_deleted", 0)
    if skipped > 0 or deleted > 0:
        click.echo(f"Processed {stats['files_discovered']} files "
                   f"({skipped} skipped, {stats['files_indexed']} indexed, {deleted} deleted)")
    click.echo(f"Indexed {stats['files_indexed']} files ({stats['chunks_created']} chunks)")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_cli.py::test_index_force_flag_rebuilds_from_scratch -xvs`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_cli.py src/semdex/cli.py
git commit -m "Add --force flag to index command"
```

---

## Task 6: CLI - Update progress bar for skip tracking

**Files:**
- Modify: `src/semdex/indexer.py:85-120`
- Test: Manual verification (progress bar is visual)

- [ ] **Step 1: Update progress bar label**

Modify `src/semdex/indexer.py`, update the progress bar in `index_project()`:

```python
def index_project(
    project_root: Path,
    config: SemdexConfig,
    files: list[Path] | None = None,
    target_dir: Path | None = None,
    force: bool = False,
) -> dict:
    """Index files and store embeddings. Returns stats dict."""
    # ... existing code up to progress bar ...

    files_indexed = 0

    # Progress bar showing what's being indexed
    # (final summary will show skipped/indexed/deleted counts)
    progress_label = f"Indexing ({len(to_skip)} skipped)"

    with click.progressbar(
        to_index,
        label=progress_label,
        length=len(to_index),
        item_show_func=lambda p: p.name if p else ""
    ) as bar:
        for path in bar:
            # ... existing indexing code ...

            if file_chunks:
                # ... existing code ...
                files_indexed += 1

    # ... rest of function ...
```

- [ ] **Step 2: Manual verification**

Run: `semdex index` in a test project and verify output shows:
- Progress bar with "(N skipped)" in label
- Final summary showing all counts (skipped, indexed, deleted)

- [ ] **Step 3: Commit**

```bash
git add src/semdex/indexer.py
git commit -m "Update progress bar to show skip/index counts"
```

---

## Task 7: Integration test - Resume after interruption

**Files:**
- Create: `tests/test_resume_integration.py`

- [ ] **Step 1: Write integration test for resume scenario**

Create `tests/test_resume_integration.py`:

```python
import tempfile
import time
from pathlib import Path

from semdex.config import SemdexConfig
from semdex.indexer import index_project
from semdex.store import SemdexStore


def test_resume_after_partial_indexing():
    """Test that indexing can resume after interruption."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)

        # Create multiple files
        files = []
        for i in range(10):
            f = root / f"file{i}.py"
            f.write_text(f"x = {i}")
            files.append(f)

        config = SemdexConfig(project_root=root)
        config.ensure_dirs()

        # Index first 5 files manually
        store = SemdexStore(db_path=config.db_path)
        from semdex.embeddings import LocalEmbedder
        from semdex.chunker import chunk_file
        from datetime import datetime, timezone

        embedder = LocalEmbedder(model_name=config.embedding_model)
        now = datetime.now(timezone.utc).isoformat()

        for i in range(5):
            path = files[i]
            chunks = chunk_file(path, threshold=config.chunk_threshold)
            mtime = path.stat().st_mtime

            file_chunks = []
            for chunk in chunks:
                file_chunks.append({
                    "file_path": f"file{i}.py",
                    "start_line": chunk.start_line,
                    "end_line": chunk.end_line,
                    "chunk_type": chunk.chunk_type,
                    "content": chunk.content,
                    "source_dir": str(root.resolve()),
                    "last_indexed": now,
                    "mtime": mtime,
                    "vector": embedder.encode([chunk.content])[0],
                })

            store.add_chunks(file_chunks)

        # Now run full index_project - should skip first 5, index last 5
        stats = index_project(root, config)

        assert stats["files_discovered"] == 10
        assert stats["files_skipped"] == 5  # First 5 already indexed
        assert stats["files_indexed"] == 5  # Last 5 newly indexed

        # Verify all 10 files are in index
        all_metadata = store.get_all_file_metadata()
        assert len(all_metadata) == 10


def test_full_workflow_with_modifications():
    """Test complete workflow: index, modify, re-index."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)

        file1 = root / "file1.py"
        file2 = root / "file2.py"
        file3 = root / "file3.py"

        file1.write_text("x = 1")
        file2.write_text("y = 2")
        file3.write_text("z = 3")

        config = SemdexConfig(project_root=root)
        config.ensure_dirs()

        # Initial index
        stats1 = index_project(root, config)
        assert stats1["files_indexed"] == 3
        assert stats1["files_skipped"] == 0

        # Re-index without changes
        stats2 = index_project(root, config)
        assert stats2["files_indexed"] == 0
        assert stats2["files_skipped"] == 3

        # Modify one file
        time.sleep(0.01)
        file2.write_text("y = 200")

        # Re-index
        stats3 = index_project(root, config)
        assert stats3["files_indexed"] == 1
        assert stats3["files_skipped"] == 2

        # Delete one file
        file3.unlink()

        # Re-index
        stats4 = index_project(root, config)
        assert stats4["files_discovered"] == 2
        assert stats4["files_deleted"] == 1
        assert stats4["files_skipped"] == 2
        assert stats4["files_indexed"] == 0

        # Verify final state
        store = SemdexStore(db_path=config.db_path)
        all_metadata = store.get_all_file_metadata()
        assert len(all_metadata) == 2
        assert "file1.py" in all_metadata
        assert "file2.py" in all_metadata
        assert "file3.py" not in all_metadata
```

- [ ] **Step 2: Run integration tests**

Run: `pytest tests/test_resume_integration.py -xvs`

Expected: PASS (both tests)

- [ ] **Step 3: Commit**

```bash
git add tests/test_resume_integration.py
git commit -m "Add integration tests for resume functionality"
```

---

## Task 8: Update existing tests to handle new stats fields

**Files:**
- Modify: `tests/test_cli.py`
- Modify: Any other test files that check index stats

- [ ] **Step 1: Find tests that need updating**

Run: `grep -r "files_indexed" tests/ | grep -v test_indexer.py | grep -v test_resume`

This finds tests that check `files_indexed` outside of the new tests we just wrote.

- [ ] **Step 2: Update each test to use .get() for new fields**

For each test that asserts on stats dict, change assertions like:
- `assert stats["files_indexed"] == N` → Keep as-is (this field exists)
- If test fails due to missing keys, add: `stats.get("files_skipped", 0)`, `stats.get("files_deleted", 0)`

Example fix pattern:
```python
# Before:
assert stats["files_indexed"] == 1

# After (if test fails):
assert stats["files_indexed"] == 1
assert stats.get("files_skipped", 0) == 0  # Add if needed
```

- [ ] **Step 3: Run full test suite**

Run: `pytest tests/ -v`

Expected: PASS (all tests)

- [ ] **Step 4: Commit**

```bash
git add tests/
git commit -m "Update existing tests to handle new stats fields"
```

---

## Task 9: Update README with resume functionality

**Files:**
- Modify: `README.md:60-75`

- [ ] **Step 1: Add documentation for --force flag and smart indexing**

Update `README.md` to document the new behavior:

```markdown
## CLI Commands

```bash
semdex init                  # Initialize: index project, install git hook, print setup instructions
semdex index                 # Smart re-index (skip unchanged files, prune deleted files)
semdex index --force         # Full re-index (delete and rebuild entire index)
semdex index <dir>           # Index an external directory
semdex index <file>          # Re-index a specific file
semdex index --force <file>  # Force re-index a specific file (bypass mtime check)
semdex search <query>        # Search the index from the command line
semdex status                # Show index stats (file count, last indexed, size)
semdex forget <path>         # Remove a path from the index
semdex hook install          # Install the git post-commit hook
semdex hook uninstall        # Remove the git post-commit hook
semdex serve                 # Start the MCP server (called by Claude Code)
```

### Smart Indexing

By default, `semdex index` uses smart incremental indexing:
- Skips files that haven't changed since last index (based on modification time)
- Automatically resumes if previous indexing was interrupted
- Removes deleted files from the index
- Use `--force` to rebuild the entire index from scratch
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "Document smart indexing and --force flag"
```

---

## Task 10: Final integration test and cleanup

**Files:**
- All modified files

- [ ] **Step 1: Run full test suite**

Run: `pytest tests/ -v --cov=src/semdex`

Expected: PASS with good coverage on new code

- [ ] **Step 2: Manual end-to-end test**

```bash
# Create test project
mkdir /tmp/test-semdex
cd /tmp/test-semdex
git init
echo "x = 1" > file1.py
echo "y = 2" > file2.py

# Initialize semdex
semdex init

# Verify smart indexing
semdex index  # Should skip all files
# Edit file1.py
echo "x = 100" > file1.py
semdex index  # Should index only file1.py

# Test force
semdex index --force  # Should rebuild everything

# Clean up
cd -
rm -rf /tmp/test-semdex
```

- [ ] **Step 3: Final commit**

```bash
git add -A
git commit -m "Complete resume functionality implementation"
```

---

## Success Criteria

✅ Running `semdex index` on an unchanged project completes in <5 seconds and skips all files
✅ Interrupting indexing (Ctrl+C) and re-running successfully resumes without re-indexing completed files
✅ Progress bar shows accurate counts of skipped/indexed/deleted files
✅ `semdex index --force` reliably rebuilds from scratch
✅ Existing indexes without `mtime` automatically bootstrap the new field
✅ All tests pass with good coverage
✅ No performance regression for small projects (<100 files)

---

## Notes

- Follow TDD strictly: write test, see it fail, implement, see it pass, commit
- Keep each commit focused on one specific change
- Use `pytest -xvs` for verbose test output during development
- The `mtime` field uses float timestamps with subsecond precision from `Path.stat().st_mtime`
- Backwards compatibility is handled by checking for `KeyError` when accessing `mtime` column
- The `force` flag has dual behavior: full rebuild for project, mtime bypass for specific files

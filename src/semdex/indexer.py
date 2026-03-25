from __future__ import annotations

from pathlib import Path

import pathspec

from semdex.config import SemdexConfig, DEFAULT_EXCLUDES, BINARY_EXTENSIONS


def discover_files(
    root: Path, config: SemdexConfig, respect_gitignore: bool = True
) -> list[Path]:
    """Walk root and return indexable file paths."""
    ignore_patterns = list(DEFAULT_EXCLUDES) + config.extra_excludes

    if respect_gitignore:
        gitignore_path = root / ".gitignore"
        if gitignore_path.exists():
            ignore_patterns.extend(
                gitignore_path.read_text().splitlines()
            )

    spec = pathspec.GitIgnoreSpec.from_lines(ignore_patterns)
    files = []

    for path in root.rglob("*"):
        if not path.is_file():
            continue

        rel = path.relative_to(root)

        if spec.match_file(str(rel)):
            continue

        if path.suffix.lower() in BINARY_EXTENSIONS:
            continue

        if path.stat().st_size > config.max_file_size:
            continue

        files.append(path)

    return sorted(files)


from datetime import datetime, timezone

import click

from semdex.chunker import chunk_file
from semdex.embeddings import LocalEmbedder
from semdex.store import SemdexStore


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
    # Create embedder once, reuse for all files
    embedder = LocalEmbedder(model_name=config.embedding_model)

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
        # External dirs: apply skip logic unless force=True
        to_index, to_skip = _filter_files_by_mtime(file_list, store, force, target_dir)
    elif files:
        file_list = files
        source_dir = str(project_root.resolve())
        # Specific files: apply skip logic unless force=True
        to_index, to_skip = _filter_files_by_mtime(file_list, store, force, project_root)
    else:
        # Full project scan
        file_list = discover_files(project_root, config)
        source_dir = str(project_root.resolve())
        # Apply skip logic unless force=True
        to_index, to_skip = _filter_files_by_mtime(file_list, store, force, project_root)

    now = datetime.now(timezone.utc).isoformat()
    total_files = len(file_list)
    files_skipped = len(to_skip)

    # Determine base_path for relative path calculation
    if target_dir:
        base_path = target_dir
    else:
        base_path = project_root

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
        source_dir: Source directory to filter by (only delete files from this source)
        project_root: Project root for relative path calculation

    Returns:
        Count of files deleted from index
    """
    # Build set of discovered file paths (relative)
    discovered_set = set()
    for file_path in discovered_files:
        try:
            rel_path = str(file_path.relative_to(project_root))
        except ValueError:
            rel_path = file_path.name
        discovered_set.add(rel_path)

    # Get all chunks from the store and check source_dir
    table = store._get_table()
    if table is None:
        return 0

    arrow_table = table.to_arrow()
    file_paths = arrow_table.column("file_path").to_pylist()
    source_dirs = arrow_table.column("source_dir").to_pylist()

    # Find unique files in this source_dir that weren't discovered
    files_to_delete = set()
    for file_path, file_source_dir in zip(file_paths, source_dirs):
        # Only consider files from our source_dir (don't touch external indexes)
        if file_source_dir == source_dir and file_path not in discovered_set:
            files_to_delete.add(file_path)

    # Delete stale files
    for file_path in files_to_delete:
        store.delete_by_file(file_path)

    return len(files_to_delete)

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
    total_chunks = 0
    files_skipped = len(to_skip)
    files_indexed = 0

    with click.progressbar(to_index, label="Indexing", length=len(to_index),
                           item_show_func=lambda p: p.name if p else "") as bar:
        for path in bar:
            # Calculate relative path
            if target_dir:
                rel_path = str(path.relative_to(target_dir))
            else:
                try:
                    rel_path = str(path.relative_to(project_root))
                except ValueError:
                    rel_path = str(path)

            # Delete old chunks for this file before re-indexing (atomic operation)
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

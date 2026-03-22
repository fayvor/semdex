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

from semdex.chunker import chunk_file
from semdex.embeddings import LocalEmbedder
from semdex.store import SemdexStore


def index_project(
    project_root: Path,
    config: SemdexConfig,
    files: list[Path] | None = None,
    target_dir: Path | None = None,
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
    elif files:
        file_list = files
        source_dir = str(project_root.resolve())
        # Remove old entries for specified files
        for f in file_list:
            store.delete_by_file(str(f.relative_to(project_root)))
    else:
        file_list = discover_files(project_root, config)
        source_dir = str(project_root.resolve())

    now = datetime.now(timezone.utc).isoformat()
    all_chunks = []

    for path in file_list:
        chunks = chunk_file(path, threshold=config.chunk_threshold)
        if target_dir:
            rel_path = str(path.relative_to(target_dir))
        else:
            try:
                rel_path = str(path.relative_to(project_root))
            except ValueError:
                rel_path = str(path)

        for chunk in chunks:
            all_chunks.append({
                "file_path": rel_path,
                "start_line": chunk.start_line,
                "end_line": chunk.end_line,
                "chunk_type": chunk.chunk_type,
                "content": chunk.content,
                "source_dir": source_dir,
                "last_indexed": now,
            })

    if not all_chunks:
        return {"files_indexed": 0, "chunks_created": 0}

    # Batch embed all chunks
    texts = [c["content"] for c in all_chunks]
    vectors = embedder.encode(texts)

    for chunk, vector in zip(all_chunks, vectors):
        chunk["vector"] = vector

    store.add_chunks(all_chunks)

    return {
        "files_indexed": len(file_list),
        "chunks_created": len(all_chunks),
    }

from __future__ import annotations

import json
import signal
from datetime import datetime, timezone
from pathlib import Path

import click
import pathspec

from semdex.chunker import chunk_file
from semdex.config import SemdexConfig, DEFAULT_EXCLUDES, BINARY_EXTENSIONS
from semdex.embeddings import LocalEmbedder
from semdex.store import SemdexStore

BATCH_SIZE = 50  # files per batch before flushing to DB


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


class Checkpoint:
    """Track indexing progress so interrupted runs can resume."""

    def __init__(self, path: Path):
        self._path = path
        self._data: dict = {"completed": {}, "version": 1}
        self._load()

    def _load(self):
        if self._path.exists():
            try:
                self._data = json.loads(self._path.read_text())
            except (json.JSONDecodeError, OSError):
                pass

    def save(self):
        self._path.write_text(json.dumps(self._data))

    def is_current(self, rel_path: str, mtime: float) -> bool:
        """True if file was already indexed with the same mtime."""
        entry = self._data["completed"].get(rel_path)
        return entry is not None and entry.get("mtime") == mtime

    def mark_done(self, rel_path: str, mtime: float):
        self._data["completed"][rel_path] = {"mtime": mtime}

    def clear(self):
        self._data = {"completed": {}, "version": 1}

    def remove(self):
        if self._path.exists():
            self._path.unlink()


class _IndexingInterrupted(Exception):
    pass


def index_project(
    project_root: Path,
    config: SemdexConfig,
    files: list[Path] | None = None,
    target_dir: Path | None = None,
) -> dict:
    """Index files and store embeddings. Returns stats dict."""
    embedder = LocalEmbedder(model_name=config.embedding_model)
    store = SemdexStore(db_path=config.db_path, dimension=embedder.dimension)
    checkpoint = Checkpoint(config.semdex_dir / "checkpoint.json")

    interrupted = False

    def _handle_signal(signum, frame):
        nonlocal interrupted
        interrupted = True

    old_sigint = signal.signal(signal.SIGINT, _handle_signal)
    old_sigterm = signal.signal(signal.SIGTERM, _handle_signal)

    if target_dir:
        file_list = discover_files(target_dir, config, respect_gitignore=False)
        source_dir = str(target_dir.resolve())
        store.delete_by_source_dir(source_dir)
        base_dir = target_dir
        # No checkpoint for external dirs — always full reindex
        checkpoint.clear()
    elif files:
        file_list = files
        source_dir = str(project_root.resolve())
        base_dir = project_root
        for f in file_list:
            store.delete_by_file(str(f.relative_to(project_root)))
        checkpoint.clear()
    else:
        file_list = discover_files(project_root, config)
        source_dir = str(project_root.resolve())
        base_dir = project_root

    now = datetime.now(timezone.utc).isoformat()
    total_files = len(file_list)
    files_indexed = 0
    total_chunks = 0
    skipped = 0

    # Batch buffer
    batch_chunks: list[dict] = []
    batch_file_count = 0

    def _flush_batch():
        nonlocal total_chunks, batch_chunks, batch_file_count
        if not batch_chunks:
            return
        texts = [c["content"] for c in batch_chunks]
        vectors = embedder.encode(texts)
        for chunk, vector in zip(batch_chunks, vectors):
            chunk["vector"] = vector
        store.add_chunks(batch_chunks)
        total_chunks += len(batch_chunks)
        batch_chunks = []
        batch_file_count = 0
        checkpoint.save()

    try:
        with click.progressbar(
            file_list, label="Indexing", length=total_files,
            item_show_func=lambda p: p.name if p else ""
        ) as bar:
            for path in bar:
                if interrupted:
                    break

                try:
                    rel_path = str(path.relative_to(base_dir))
                except ValueError:
                    rel_path = str(path)

                # Skip files unchanged since last checkpoint
                try:
                    mtime = path.stat().st_mtime
                except OSError:
                    continue

                if not files and not target_dir and checkpoint.is_current(rel_path, mtime):
                    skipped += 1
                    continue

                chunks = chunk_file(path, threshold=config.chunk_threshold)
                for chunk in chunks:
                    batch_chunks.append({
                        "file_path": rel_path,
                        "start_line": chunk.start_line,
                        "end_line": chunk.end_line,
                        "chunk_type": chunk.chunk_type,
                        "content": chunk.content,
                        "source_dir": source_dir,
                        "last_indexed": now,
                    })

                checkpoint.mark_done(rel_path, mtime)
                files_indexed += 1
                batch_file_count += 1

                if batch_file_count >= BATCH_SIZE:
                    _flush_batch()

        # Flush remaining
        _flush_batch()
    finally:
        # Always save checkpoint and restore signals
        checkpoint.save()
        signal.signal(signal.SIGINT, old_sigint)
        signal.signal(signal.SIGTERM, old_sigterm)

    if interrupted:
        click.echo(f"\nInterrupted — progress saved. Run again to resume.")

    # Clean up checkpoint on successful full completion
    if not interrupted and not files and not target_dir:
        checkpoint.remove()

    return {
        "files_indexed": files_indexed,
        "chunks_created": total_chunks,
        "skipped": skipped,
        "interrupted": interrupted,
    }

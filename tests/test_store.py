import tempfile
from pathlib import Path

from semdex.store import SemdexStore


def test_store_add_and_search():
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
                "vector": [1.0, 0.0, 0.0, 0.0],
            },
            {
                "file_path": "bar.py",
                "start_line": 1,
                "end_line": 5,
                "chunk_type": "whole-file",
                "content": "def bar(): pass",
                "source_dir": ".",
                "last_indexed": "2026-03-21T00:00:00",
                "vector": [0.0, 1.0, 0.0, 0.0],
            },
        ])
        results = store.search([1.0, 0.0, 0.0, 0.0], top_k=1)
        assert len(results) == 1
        assert results[0]["file_path"] == "foo.py"


def test_store_delete_by_file():
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
                "vector": [1.0, 0.0, 0.0, 0.0],
            },
        ])
        store.delete_by_file("foo.py")
        results = store.search([1.0, 0.0, 0.0, 0.0], top_k=10)
        assert len(results) == 0


def test_store_delete_by_source_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = SemdexStore(db_path=Path(tmpdir) / "lance.db", dimension=4)
        store.add_chunks([
            {
                "file_path": "/ext/foo.py",
                "start_line": 1,
                "end_line": 10,
                "chunk_type": "whole-file",
                "content": "def foo(): pass",
                "source_dir": "/ext",
                "last_indexed": "2026-03-21T00:00:00",
                "vector": [1.0, 0.0, 0.0, 0.0],
            },
        ])
        store.delete_by_source_dir("/ext")
        results = store.search([1.0, 0.0, 0.0, 0.0], top_k=10)
        assert len(results) == 0


def test_store_get_file_summary():
    with tempfile.TemporaryDirectory() as tmpdir:
        store = SemdexStore(db_path=Path(tmpdir) / "lance.db", dimension=4)
        store.add_chunks([
            {
                "file_path": "foo.py",
                "start_line": 1,
                "end_line": 10,
                "chunk_type": "function",
                "content": "def foo(): pass",
                "source_dir": ".",
                "last_indexed": "2026-03-21T00:00:00",
                "vector": [1.0, 0.0, 0.0, 0.0],
            },
            {
                "file_path": "foo.py",
                "start_line": 11,
                "end_line": 20,
                "chunk_type": "class",
                "content": "class Foo: pass",
                "source_dir": ".",
                "last_indexed": "2026-03-21T00:00:00",
                "vector": [0.0, 1.0, 0.0, 0.0],
            },
        ])
        summary = store.get_file_summary("foo.py")
        assert summary["file_path"] == "foo.py"
        assert summary["chunk_count"] == 2
        assert "function" in summary["chunk_types"]
        assert "class" in summary["chunk_types"]


def test_store_stats():
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
                "vector": [1.0, 0.0, 0.0, 0.0],
            },
        ])
        stats = store.stats()
        assert stats["total_chunks"] == 1
        assert stats["total_files"] == 1


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

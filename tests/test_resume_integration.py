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

        # Verify all 10 files are in index (use fresh store to avoid cache)
        store_fresh = SemdexStore(db_path=config.db_path)
        all_metadata = store_fresh.get_all_file_metadata()
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

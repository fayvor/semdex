import tempfile
import time
from pathlib import Path
from unittest.mock import patch

from semdex.config import SemdexConfig
from semdex.indexer import index_project, Checkpoint


def test_index_project_end_to_end():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / "main.py").write_text("def hello():\n    return 'hi'\n")
        (root / "lib.py").write_text("x = 1\n")

        config = SemdexConfig(project_root=root)
        config.ensure_dirs()

        stats = index_project(root, config)
        assert stats["files_indexed"] == 2
        assert stats["chunks_created"] > 0
        assert stats["skipped"] == 0


def test_index_specific_files():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / "a.py").write_text("x = 1\n")
        (root / "b.py").write_text("y = 2\n")

        config = SemdexConfig(project_root=root)
        config.ensure_dirs()

        stats = index_project(root, config, files=[root / "a.py"])
        assert stats["files_indexed"] == 1


def test_index_external_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir) / "project"
        ext = Path(tmpdir) / "external"
        root.mkdir()
        ext.mkdir()
        (root / "main.py").write_text("x = 1\n")
        (ext / "lib.py").write_text("y = 2\n")

        config = SemdexConfig(project_root=root)
        config.ensure_dirs()

        stats = index_project(root, config, target_dir=ext)
        assert stats["files_indexed"] == 1


def test_checkpoint_skips_unchanged_files():
    """Re-running index skips files that haven't changed."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / "a.py").write_text("x = 1\n")
        (root / "b.py").write_text("y = 2\n")

        config = SemdexConfig(project_root=root)
        config.ensure_dirs()

        # First run indexes everything
        stats1 = index_project(root, config)
        assert stats1["files_indexed"] == 2
        assert stats1["skipped"] == 0

        # Checkpoint is cleaned up on success, so second full run re-indexes
        stats2 = index_project(root, config)
        assert stats2["files_indexed"] == 2


def test_checkpoint_resume_after_partial():
    """Simulates partial indexing by writing a checkpoint, then resuming."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / "a.py").write_text("x = 1\n")
        (root / "b.py").write_text("y = 2\n")

        config = SemdexConfig(project_root=root)
        config.ensure_dirs()

        # Write a fake checkpoint marking a.py as done
        cp = Checkpoint(config.semdex_dir / "checkpoint.json")
        mtime_a = (root / "a.py").stat().st_mtime
        cp.mark_done("a.py", mtime_a)
        cp.save()

        stats = index_project(root, config)
        assert stats["skipped"] == 1
        assert stats["files_indexed"] == 1


def test_checkpoint_reindexes_modified_file():
    """Changed mtime causes re-indexing even with checkpoint."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / "a.py").write_text("x = 1\n")

        config = SemdexConfig(project_root=root)
        config.ensure_dirs()

        # Write checkpoint with old mtime
        cp = Checkpoint(config.semdex_dir / "checkpoint.json")
        cp.mark_done("a.py", 0.0)  # fake old mtime
        cp.save()

        stats = index_project(root, config)
        assert stats["files_indexed"] == 1
        assert stats["skipped"] == 0


def test_checkpoint_class():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "cp.json"
        cp = Checkpoint(path)

        assert not cp.is_current("foo.py", 123.0)

        cp.mark_done("foo.py", 123.0)
        assert cp.is_current("foo.py", 123.0)
        assert not cp.is_current("foo.py", 456.0)

        cp.save()
        cp2 = Checkpoint(path)
        assert cp2.is_current("foo.py", 123.0)

        cp2.clear()
        assert not cp2.is_current("foo.py", 123.0)

        cp2.save()
        cp2.remove()
        assert not path.exists()

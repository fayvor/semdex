import tempfile
from pathlib import Path
from unittest.mock import patch

from semdex.config import SemdexConfig
from semdex.indexer import index_project


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

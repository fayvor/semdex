import tempfile
from pathlib import Path

from semdex.indexer import discover_files
from semdex.config import SemdexConfig


def test_discover_files_finds_source_files():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / "main.py").write_text("print('hello')")
        (root / "lib.js").write_text("console.log('hi')")
        (root / "README.md").write_text("# hi")
        config = SemdexConfig(project_root=root)
        files = discover_files(root, config)
        names = {f.name for f in files}
        assert "main.py" in names
        assert "lib.js" in names
        assert "README.md" in names


def test_discover_files_skips_excluded_dirs():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / "main.py").write_text("x = 1")
        nm = root / "node_modules"
        nm.mkdir()
        (nm / "dep.js").write_text("module.exports = {}")
        config = SemdexConfig(project_root=root)
        files = discover_files(root, config)
        paths = [str(f) for f in files]
        assert not any("node_modules" in p for p in paths)


def test_discover_files_skips_binary():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / "main.py").write_text("x = 1")
        (root / "image.png").write_bytes(b"\x89PNG\r\n")
        config = SemdexConfig(project_root=root)
        files = discover_files(root, config)
        names = {f.name for f in files}
        assert "main.py" in names
        assert "image.png" not in names


def test_discover_files_respects_gitignore():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / "main.py").write_text("x = 1")
        (root / "secret.env").write_text("KEY=val")
        (root / ".gitignore").write_text("*.env\n")
        config = SemdexConfig(project_root=root)
        files = discover_files(root, config)
        names = {f.name for f in files}
        assert "main.py" in names
        assert "secret.env" not in names


def test_discover_files_skips_large_files():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / "small.py").write_text("x = 1")
        (root / "huge.py").write_text("x" * 2_000_000)
        config = SemdexConfig(project_root=root, max_file_size=1_000_000)
        files = discover_files(root, config)
        names = {f.name for f in files}
        assert "small.py" in names
        assert "huge.py" not in names

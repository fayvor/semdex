import json
import os
import tempfile
from pathlib import Path

from semdex.config import SemdexConfig


def test_default_config():
    with tempfile.TemporaryDirectory() as tmpdir:
        config = SemdexConfig(project_root=Path(tmpdir))
        assert config.semdex_dir == Path(tmpdir) / ".claude" / "semdex"
        assert config.db_path == Path(tmpdir) / ".claude" / "semdex" / "lance.db"
        assert config.max_file_size == 1_000_000
        assert config.chunk_threshold == 200
        assert config.embedding_model == "sentence-transformers/all-MiniLM-L6-v2"


def test_ensure_dirs_creates_structure():
    with tempfile.TemporaryDirectory() as tmpdir:
        config = SemdexConfig(project_root=Path(tmpdir))
        config.ensure_dirs()
        assert config.semdex_dir.exists()


def test_save_and_load_config():
    with tempfile.TemporaryDirectory() as tmpdir:
        config = SemdexConfig(project_root=Path(tmpdir))
        config.ensure_dirs()
        config.max_file_size = 500_000
        config.save()

        loaded = SemdexConfig.load(Path(tmpdir))
        assert loaded.max_file_size == 500_000


def test_config_parallel_defaults():
    """Test that parallel config has sensible defaults."""
    config = SemdexConfig(project_root=Path("/tmp/test"))
    assert config.parallel_enabled is True
    assert config.parallel_workers == 0  # 0 = auto-detect
    assert config.write_batch_size == 500
    assert config.min_files_for_parallel == 50

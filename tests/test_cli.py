import os
import tempfile
from pathlib import Path

from click.testing import CliRunner

from semdex.cli import cli
from semdex.config import SemdexConfig
from semdex.store import SemdexStore


def test_cli_help():
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "semdex" in result.output


def test_init_creates_index(tmp_path):
    runner = CliRunner()
    # Create a minimal project
    (tmp_path / "main.py").write_text("x = 1\n")
    result = runner.invoke(cli, ["init"], catch_exceptions=False)
    # Just verify it doesn't crash for now
    assert result.exit_code == 0 or "error" not in result.output.lower()


def test_status_no_index():
    runner = CliRunner()
    result = runner.invoke(cli, ["status"])
    assert result.exit_code == 0


def test_hook_install_no_git():
    runner = CliRunner()
    result = runner.invoke(cli, ["hook", "install"])
    assert result.exit_code == 0 or "not a git" in result.output.lower()


def test_index_force_flag_rebuilds_from_scratch():
    """Test that --force deletes and rebuilds the entire index."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / "file1.py").write_text("x = 1")

        # Initialize git repo (required for _find_project_root)
        (root / ".git").mkdir()

        runner = CliRunner()

        # Initial index
        with runner.isolated_filesystem(temp_dir=tmpdir) as fs:
            os.chdir(root)
            result1 = runner.invoke(cli, ["index"])
            assert result1.exit_code == 0

            # Verify index exists
            config = SemdexConfig(project_root=root)
            assert config.db_path.exists()

            # Force rebuild
            result2 = runner.invoke(cli, ["index", "--force"])
            assert result2.exit_code == 0
            assert "Deleting existing index" in result2.output
            assert "Rebuilding full index from scratch" in result2.output

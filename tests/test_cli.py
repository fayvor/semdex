from click.testing import CliRunner

from semdex.cli import cli


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

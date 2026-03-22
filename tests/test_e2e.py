import os
import tempfile
import subprocess
from pathlib import Path


def test_full_workflow():
    """Test: init → index → search → status → forget."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        old_cwd = os.getcwd()
        os.chdir(root)

        # Create a fake git repo
        subprocess.run(["git", "init"], cwd=root, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=root, capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=root, capture_output=True,
        )

        # Create project files
        (root / "auth.py").write_text(
            "def authenticate(user, password):\n"
            "    '''Authenticate a user with credentials.'''\n"
            "    return check_password(user, password)\n"
        )
        (root / "db.py").write_text(
            "def connect_database(url):\n"
            "    '''Connect to the database.'''\n"
            "    return Connection(url)\n"
        )
        (root / "README.md").write_text("# Test Project\nA test project.\n")

        # git add and commit so HEAD exists
        subprocess.run(["git", "add", "."], cwd=root, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "init"],
            cwd=root, capture_output=True,
        )

        from click.testing import CliRunner
        from semdex.cli import cli

        runner = CliRunner()
        os.chdir(root)

        # Init
        result = runner.invoke(cli, ["init"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "Indexed" in result.output
        assert (root / ".claude" / "semdex").is_dir()

        # Status
        result = runner.invoke(cli, ["status"], catch_exceptions=False)
        assert result.exit_code == 0
        assert "Files indexed:" in result.output

        # Search
        result = runner.invoke(
            cli, ["search", "authentication"], catch_exceptions=False
        )
        assert result.exit_code == 0
        assert "auth.py" in result.output

        # Forget
        result = runner.invoke(
            cli, ["forget", "auth.py"], catch_exceptions=False
        )
        assert result.exit_code == 0
        assert "Removed" in result.output

        os.chdir(old_cwd)

import subprocess
import tempfile
from pathlib import Path

import pytest

from semdex.git import (
    GitState,
    get_current_commit,
    is_ancestor,
    get_changed_files,
    is_git_repo,
)


def _init_git_repo(path: Path) -> None:
    """Initialize a git repo with an initial commit."""
    subprocess.run(["git", "init"], cwd=path, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=path, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, capture_output=True)
    (path / "README.md").write_text("# Test")
    subprocess.run(["git", "add", "."], cwd=path, capture_output=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=path, capture_output=True)


class TestGitState:
    def test_load_nonexistent(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = GitState(Path(tmpdir) / "state.json")
            assert state.get_commit() is None
            assert state.get_commit("/some/path") is None

    def test_save_and_load_default(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "state.json"
            state = GitState(state_path)
            state.set_commit("abc123")
            state.save()

            state2 = GitState(state_path)
            assert state2.get_commit() == "abc123"

    def test_save_and_load_per_source(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "state.json"
            state = GitState(state_path)
            state.set_commit("abc123", "/repo/one")
            state.set_commit("def456", "/repo/two")
            state.save()

            state2 = GitState(state_path)
            assert state2.get_commit("/repo/one") == "abc123"
            assert state2.get_commit("/repo/two") == "def456"
            assert state2.get_commit("/repo/three") is None

    def test_clear_commit(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "state.json"
            state = GitState(state_path)
            state.set_commit("abc123", "/repo/one")
            state.save()

            state.set_commit(None, "/repo/one")
            state.save()

            state2 = GitState(state_path)
            assert state2.get_commit("/repo/one") is None

    def test_legacy_property_compat(self):
        """Legacy last_indexed_commit property works with _default key."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "state.json"
            state = GitState(state_path)
            state.last_indexed_commit = "abc123"
            state.save()

            state2 = GitState(state_path)
            assert state2.last_indexed_commit == "abc123"
            assert state2.get_commit() == "abc123"

    def test_migrates_old_format(self):
        """Old single-commit format is migrated to per-source format."""
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "state.json"
            # Write old format directly
            state_path.write_text('{"last_indexed_commit": "old123"}')

            state = GitState(state_path)
            assert state.get_commit() == "old123"
            assert state.last_indexed_commit == "old123"


class TestGitCommands:
    def test_is_git_repo_true(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _init_git_repo(root)
            assert is_git_repo(root) is True

    def test_is_git_repo_false(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            assert is_git_repo(root) is False

    def test_get_current_commit(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _init_git_repo(root)
            commit = get_current_commit(root)
            assert commit is not None
            assert len(commit) == 40  # SHA-1 hex

    def test_get_current_commit_no_repo(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            assert get_current_commit(root) is None

    def test_is_ancestor_true(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _init_git_repo(root)

            first_commit = get_current_commit(root)

            (root / "file.txt").write_text("content")
            subprocess.run(["git", "add", "."], cwd=root, capture_output=True)
            subprocess.run(["git", "commit", "-m", "Second commit"], cwd=root, capture_output=True)

            second_commit = get_current_commit(root)

            assert is_ancestor(root, first_commit, second_commit) is True

    def test_is_ancestor_false(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _init_git_repo(root)

            first_commit = get_current_commit(root)

            (root / "file.txt").write_text("content")
            subprocess.run(["git", "add", "."], cwd=root, capture_output=True)
            subprocess.run(["git", "commit", "-m", "Second commit"], cwd=root, capture_output=True)

            second_commit = get_current_commit(root)

            assert is_ancestor(root, second_commit, first_commit) is False


class TestGetChangedFiles:
    def test_added_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _init_git_repo(root)
            first_commit = get_current_commit(root)

            (root / "new_file.py").write_text("x = 1")
            subprocess.run(["git", "add", "."], cwd=root, capture_output=True)
            subprocess.run(["git", "commit", "-m", "Add file"], cwd=root, capture_output=True)

            modified, deleted = get_changed_files(root, first_commit)
            assert "new_file.py" in modified
            assert deleted == []

    def test_modified_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _init_git_repo(root)
            first_commit = get_current_commit(root)

            (root / "README.md").write_text("# Updated")
            subprocess.run(["git", "add", "."], cwd=root, capture_output=True)
            subprocess.run(["git", "commit", "-m", "Update readme"], cwd=root, capture_output=True)

            modified, deleted = get_changed_files(root, first_commit)
            assert "README.md" in modified
            assert deleted == []

    def test_deleted_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _init_git_repo(root)

            (root / "to_delete.py").write_text("x = 1")
            subprocess.run(["git", "add", "."], cwd=root, capture_output=True)
            subprocess.run(["git", "commit", "-m", "Add file"], cwd=root, capture_output=True)
            first_commit = get_current_commit(root)

            (root / "to_delete.py").unlink()
            subprocess.run(["git", "add", "."], cwd=root, capture_output=True)
            subprocess.run(["git", "commit", "-m", "Delete file"], cwd=root, capture_output=True)

            modified, deleted = get_changed_files(root, first_commit)
            assert "to_delete.py" in deleted
            assert "to_delete.py" not in modified

    def test_renamed_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _init_git_repo(root)

            (root / "old_name.py").write_text("x = 1")
            subprocess.run(["git", "add", "."], cwd=root, capture_output=True)
            subprocess.run(["git", "commit", "-m", "Add file"], cwd=root, capture_output=True)
            first_commit = get_current_commit(root)

            subprocess.run(["git", "mv", "old_name.py", "new_name.py"], cwd=root, capture_output=True)
            subprocess.run(["git", "commit", "-m", "Rename file"], cwd=root, capture_output=True)

            modified, deleted = get_changed_files(root, first_commit)
            assert "new_name.py" in modified

    def test_no_changes(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            _init_git_repo(root)
            commit = get_current_commit(root)

            modified, deleted = get_changed_files(root, commit)
            assert modified == []
            assert deleted == []

from __future__ import annotations

import json
import subprocess
from pathlib import Path


class GitState:
    """Track git state for incremental indexing, per source directory."""

    def __init__(self, state_path: Path):
        self._path = state_path
        self._data: dict = {}
        self._load()

    def _load(self):
        if self._path.exists():
            try:
                self._data = json.loads(self._path.read_text())
            except (json.JSONDecodeError, OSError):
                self._data = {}
        # Migrate old format (single commit) to new format (per-source)
        if "last_indexed_commit" in self._data and "sources" not in self._data:
            old_commit = self._data.pop("last_indexed_commit")
            self._data["sources"] = {"_default": {"commit": old_commit}}

    def save(self):
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(self._data, indent=2))

    def get_commit(self, source_dir: str | None = None) -> str | None:
        """Get last indexed commit for a source directory."""
        key = source_dir or "_default"
        sources = self._data.get("sources", {})
        entry = sources.get(key, {})
        return entry.get("commit")

    def set_commit(self, commit: str | None, source_dir: str | None = None):
        """Set last indexed commit for a source directory."""
        key = source_dir or "_default"
        if "sources" not in self._data:
            self._data["sources"] = {}
        if commit is None:
            self._data["sources"].pop(key, None)
        else:
            self._data["sources"][key] = {"commit": commit}

    # Legacy property for backwards compatibility
    @property
    def last_indexed_commit(self) -> str | None:
        return self.get_commit()

    @last_indexed_commit.setter
    def last_indexed_commit(self, commit: str | None):
        self.set_commit(commit)


def get_current_commit(repo_root: Path) -> str | None:
    """Get the current HEAD commit SHA."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return None


def is_ancestor(repo_root: Path, ancestor: str, descendant: str) -> bool:
    """Check if ancestor is an ancestor of descendant."""
    try:
        result = subprocess.run(
            ["git", "merge-base", "--is-ancestor", ancestor, descendant],
            cwd=repo_root,
            capture_output=True,
            timeout=10,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def get_changed_files(repo_root: Path, from_commit: str, to_commit: str = "HEAD") -> tuple[list[str], list[str]]:
    """Get files changed between two commits.

    Returns:
        (modified_or_added, deleted) - lists of relative file paths
    """
    try:
        result = subprocess.run(
            ["git", "diff", "--name-status", from_commit, to_commit],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return ([], [])

        modified_or_added = []
        deleted = []

        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            parts = line.split("\t", 1)
            if len(parts) != 2:
                continue
            status, file_path = parts

            if status.startswith("D"):
                deleted.append(file_path)
            elif status.startswith(("A", "M", "R", "C", "T")):
                if status.startswith("R") or status.startswith("C"):
                    parts = file_path.split("\t")
                    if len(parts) == 2:
                        file_path = parts[1]
                modified_or_added.append(file_path)

        return (modified_or_added, deleted)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return ([], [])


def is_git_repo(path: Path) -> bool:
    """Check if path is inside a git repository."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--git-dir"],
            cwd=path,
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False

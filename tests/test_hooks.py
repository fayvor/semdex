import tempfile
from pathlib import Path

from semdex.hooks import install_hook, uninstall_hook, HOOK_MARKER


def test_install_hook_creates_file():
    with tempfile.TemporaryDirectory() as tmpdir:
        hooks_dir = Path(tmpdir) / ".git" / "hooks"
        hooks_dir.mkdir(parents=True)
        install_hook(Path(tmpdir))
        hook_file = hooks_dir / "post-commit"
        assert hook_file.exists()
        content = hook_file.read_text()
        assert HOOK_MARKER in content
        assert "semdex" in content


def test_install_hook_preserves_existing():
    with tempfile.TemporaryDirectory() as tmpdir:
        hooks_dir = Path(tmpdir) / ".git" / "hooks"
        hooks_dir.mkdir(parents=True)
        hook_file = hooks_dir / "post-commit"
        hook_file.write_text("#!/bin/sh\necho 'existing'\n")
        hook_file.chmod(0o755)
        install_hook(Path(tmpdir))
        content = hook_file.read_text()
        assert "existing" in content
        assert HOOK_MARKER in content


def test_uninstall_hook_removes_semdex_section():
    with tempfile.TemporaryDirectory() as tmpdir:
        hooks_dir = Path(tmpdir) / ".git" / "hooks"
        hooks_dir.mkdir(parents=True)
        install_hook(Path(tmpdir))
        uninstall_hook(Path(tmpdir))
        hook_file = hooks_dir / "post-commit"
        if hook_file.exists():
            assert HOOK_MARKER not in hook_file.read_text()


def test_install_hook_is_idempotent():
    with tempfile.TemporaryDirectory() as tmpdir:
        hooks_dir = Path(tmpdir) / ".git" / "hooks"
        hooks_dir.mkdir(parents=True)
        install_hook(Path(tmpdir))
        install_hook(Path(tmpdir))
        content = (hooks_dir / "post-commit").read_text()
        assert content.count(HOOK_MARKER) == 2  # start and end markers only


def test_install_hook_for_external_repo():
    """External repo hook calls back to controller project."""
    with tempfile.TemporaryDirectory() as tmpdir:
        controller = Path(tmpdir) / "main-project"
        external = Path(tmpdir) / "external-repo"
        controller.mkdir()
        (external / ".git" / "hooks").mkdir(parents=True)

        install_hook(external, controller_dir=controller)

        hook_file = external / ".git" / "hooks" / "post-commit"
        assert hook_file.exists()
        content = hook_file.read_text()
        assert HOOK_MARKER in content
        assert str(controller.resolve()) in content
        assert "semdex index" in content

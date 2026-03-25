import tempfile
from pathlib import Path

from semdex.hooks import install_hook, uninstall_hook, HOOK_MARKER


def test_install_hook_creates_both_files():
    with tempfile.TemporaryDirectory() as tmpdir:
        hooks_dir = Path(tmpdir) / ".git" / "hooks"
        hooks_dir.mkdir(parents=True)
        install_hook(Path(tmpdir))
        for name in ("post-commit", "post-checkout"):
            hook_file = hooks_dir / name
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
        for name in ("post-commit", "post-checkout"):
            hook_file = hooks_dir / name
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


def test_post_checkout_hook_has_branch_guard():
    with tempfile.TemporaryDirectory() as tmpdir:
        hooks_dir = Path(tmpdir) / ".git" / "hooks"
        hooks_dir.mkdir(parents=True)
        install_hook(Path(tmpdir))
        content = (hooks_dir / "post-checkout").read_text()
        assert '"$3" = "1"' in content  # only runs on branch checkouts

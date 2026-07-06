from __future__ import annotations

import stat
from pathlib import Path

HOOK_MARKER = "# --- semdex ---"
HOOK_END_MARKER = "# --- semdex --- end"


def _make_hook_script(controller_dir: Path | None = None) -> str:
    """Generate hook script content.

    Args:
        controller_dir: If set, this is an external repo that calls back to
                       the controller project's semdex. If None, this is the
                       main project.
    """
    if controller_dir:
        # External repo: call semdex in controller dir, passing this repo's path
        controller = str(controller_dir.resolve())
        return f"""{HOOK_MARKER}
# Re-index this external repo in the controller project's semdex
cd "{controller}" && semdex index "$(pwd)" >> .claude/semdex/hook.log 2>&1 &
{HOOK_END_MARKER}"""
    else:
        # Main project: index changed files
        return f"""{HOOK_MARKER}
# Incremental re-index after commit
semdex index $(git diff HEAD~1 --name-only 2>/dev/null) >> .claude/semdex/hook.log 2>&1 &
{HOOK_END_MARKER}"""


def install_hook(repo_root: Path, controller_dir: Path | None = None) -> None:
    """Install post-commit hook.

    Args:
        repo_root: The git repository to install the hook in
        controller_dir: If set, hook will call back to this project's semdex
    """
    hook_path = repo_root / ".git" / "hooks" / "post-commit"
    hook_script = _make_hook_script(controller_dir)

    if hook_path.exists():
        content = hook_path.read_text()
        if HOOK_MARKER in content:
            # Already installed - update it
            uninstall_hook(repo_root)
            content = hook_path.read_text() if hook_path.exists() else ""

        if content:
            content = content.rstrip() + "\n\n" + hook_script + "\n"
        else:
            content = "#!/bin/sh\n\n" + hook_script + "\n"
    else:
        content = "#!/bin/sh\n\n" + hook_script + "\n"

    hook_path.write_text(content)
    hook_path.chmod(hook_path.stat().st_mode | stat.S_IEXEC)


def uninstall_hook(repo_root: Path) -> None:
    hook_path = repo_root / ".git" / "hooks" / "post-commit"
    if not hook_path.exists():
        return

    content = hook_path.read_text()
    if HOOK_MARKER not in content:
        return

    # Remove the semdex section
    lines = content.splitlines(keepends=True)
    new_lines = []
    in_semdex = False
    for line in lines:
        if HOOK_MARKER in line and HOOK_END_MARKER not in line:
            in_semdex = True
            continue
        if HOOK_END_MARKER in line:
            in_semdex = False
            continue
        if not in_semdex:
            new_lines.append(line)

    remaining = "".join(new_lines).strip()
    if remaining == "#!/bin/sh" or not remaining:
        hook_path.unlink()
    else:
        hook_path.write_text(remaining + "\n")

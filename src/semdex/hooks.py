from __future__ import annotations

import stat
from pathlib import Path

HOOK_MARKER = "# --- semdex ---"
HOOK_END_MARKER = "# --- semdex --- end"

HOOK_SCRIPT = f"""{HOOK_MARKER}
# Incremental re-index after commit
semdex index $(git diff HEAD~1 --name-only 2>/dev/null) >> .claude/semdex/hook.log 2>&1 &
{HOOK_END_MARKER}"""


def install_hook(repo_root: Path) -> None:
    hook_path = repo_root / ".git" / "hooks" / "post-commit"

    if hook_path.exists():
        content = hook_path.read_text()
        if HOOK_MARKER in content:
            return  # Already installed
        content = content.rstrip() + "\n\n" + HOOK_SCRIPT + "\n"
    else:
        content = "#!/bin/sh\n\n" + HOOK_SCRIPT + "\n"

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

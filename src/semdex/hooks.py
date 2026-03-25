from __future__ import annotations

import stat
from pathlib import Path

HOOK_MARKER = "# --- semdex ---"
HOOK_END_MARKER = "# --- semdex --- end"

POST_COMMIT_SCRIPT = f"""{HOOK_MARKER}
# Incremental re-index after commit
semdex index $(git diff HEAD~1 --name-only 2>/dev/null) >> .claude/semdex/hook.log 2>&1 &
{HOOK_END_MARKER}"""

POST_CHECKOUT_SCRIPT = f"""{HOOK_MARKER}
# Re-index files that changed between branches
# $1=old ref, $2=new ref, $3=branch flag (1=branch checkout, 0=file checkout)
if [ "$3" = "1" ]; then
  changed=$(git diff --name-only "$1" "$2" 2>/dev/null)
  if [ -n "$changed" ]; then
    semdex index $changed >> .claude/semdex/hook.log 2>&1 &
  fi
fi
{HOOK_END_MARKER}"""


def _install_hook_file(repo_root: Path, hook_name: str, script: str) -> None:
    hook_path = repo_root / ".git" / "hooks" / hook_name

    if hook_path.exists():
        content = hook_path.read_text()
        if HOOK_MARKER in content:
            return  # Already installed
        content = content.rstrip() + "\n\n" + script + "\n"
    else:
        content = "#!/bin/sh\n\n" + script + "\n"

    hook_path.write_text(content)
    hook_path.chmod(hook_path.stat().st_mode | stat.S_IEXEC)


def _uninstall_hook_file(repo_root: Path, hook_name: str) -> None:
    hook_path = repo_root / ".git" / "hooks" / hook_name
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


def install_hook(repo_root: Path) -> None:
    _install_hook_file(repo_root, "post-commit", POST_COMMIT_SCRIPT)
    _install_hook_file(repo_root, "post-checkout", POST_CHECKOUT_SCRIPT)


def uninstall_hook(repo_root: Path) -> None:
    _uninstall_hook_file(repo_root, "post-commit")
    _uninstall_hook_file(repo_root, "post-checkout")

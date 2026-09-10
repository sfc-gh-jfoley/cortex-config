"""Git pre-commit hook installation for scaffold."""

from __future__ import annotations

import stat
from pathlib import Path

# ---------------------------------------------------------------------------
# Git pre-commit hook
# ---------------------------------------------------------------------------

_PRECOMMIT_HOOK_CONTENT = """\
#!/bin/sh
# Auto-regenerate spec manifest and README tables on commit.
# Installed by: python3 -m specbuilder scaffold
# Safe to remove if you prefer manual generation.

# Locate specbuilder module (may be in .cortex/skills/, project root, or elsewhere)
_SB_FOUND=0
for _dir in .cortex/skills . vendor; do
    if [ -d "$_dir/specbuilder" ]; then
        PYTHONPATH="$_dir:${PYTHONPATH:-}" python3 -m specbuilder generate-manifest 2>/dev/null
        _SB_FOUND=$?
        break
    fi
done

if [ "$_SB_FOUND" -eq 0 ]; then
    # Stage regenerated files so they're included in this commit
    git add spec/manifest.json spec/README.md spec/acceptance-criteria/README.md 2>/dev/null
fi
"""

_PRECOMMIT_MARKER = "specbuilder.generate_manifest"
_PRECOMMIT_MARKER_LEGACY = "specbuilder.generate_index"


def _make_executable(path: Path) -> None:
    """Add the executable bit to *path* for owner/group/other."""
    current = path.stat().st_mode
    path.chmod(current | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _install_git_precommit(
    project_root: Path,
    spec_dir: str,
    dry_run: bool,
    created: list[str],
    skipped: list[str],
) -> None:
    """Install a git pre-commit hook that runs generate-manifest.

    Skips if:
    - No .git/ directory exists (not a git repo)
    - A pre-commit hook already exists and contains our marker

    If an existing hook uses `exec` (e.g., the pre-commit framework),
    we insert our logic before the exec rather than appending (since
    appended code after exec never runs).
    """
    git_dir = project_root / ".git"
    if not git_dir.is_dir():
        return

    hooks_dir = git_dir / "hooks"
    hook_path = hooks_dir / "pre-commit"
    rel = ".git/hooks/pre-commit"

    if hook_path.exists():
        existing = hook_path.read_text(encoding="utf-8")
        if _PRECOMMIT_MARKER in existing or _PRECOMMIT_MARKER_LEGACY in existing:
            skipped.append(rel)
            return
        # Check if the existing hook uses exec (e.g., pre-commit framework)
        # If so, insert before the first exec line; appending won't work.
        if any(line.strip().startswith("exec ") for line in existing.split("\n")):
            if dry_run:
                print(f"[dry-run] insert into {rel} (before exec)")
            else:
                # Insert our hook right after the shebang/header, before exec
                # Find the first exec line and insert before it
                lines = existing.split("\n")
                insert_idx = 0
                for i, line in enumerate(lines):
                    if line.strip().startswith("exec "):
                        insert_idx = i
                        break
                # Walk back to find a good insertion point (before the if block)
                while insert_idx > 0 and lines[insert_idx - 1].strip() not in ("", "fi"):
                    insert_idx -= 1
                # Never insert before the shebang line
                if lines and lines[0].startswith("#!"):
                    insert_idx = max(insert_idx, 1)
                # Build the insertion block (strip shebang from the content)
                hook_body = _PRECOMMIT_HOOK_CONTENT
                # Remove shebang line
                if hook_body.startswith("#!/"):
                    hook_body = hook_body.split("\n", 1)[1]
                insert_block = (
                    "\n# --- SpecBuilder: auto-regenerate manifest ---\n"
                    + hook_body.strip()
                    + "\n# --- End SpecBuilder ---\n\n"
                )
                lines.insert(insert_idx, insert_block)
                hook_path.write_text("\n".join(lines), encoding="utf-8")
            created.append(f"{rel} (inserted before exec)")
        else:
            # No exec — safe to append
            if dry_run:
                print(f"[dry-run] append to {rel}")
            else:
                with open(hook_path, "a", encoding="utf-8") as f:
                    f.write("\n" + _PRECOMMIT_HOOK_CONTENT)
            created.append(f"{rel} (appended)")
    else:
        if dry_run:
            print(f"[dry-run] create {rel}")
        else:
            hooks_dir.mkdir(parents=True, exist_ok=True)
            hook_path.write_text(_PRECOMMIT_HOOK_CONTENT, encoding="utf-8")
            _make_executable(hook_path)
        created.append(rel)

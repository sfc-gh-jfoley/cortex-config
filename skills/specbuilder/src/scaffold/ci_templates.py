"""CI template installation for scaffold (EXT-007)."""

from __future__ import annotations

from pathlib import Path

# ---------------------------------------------------------------------------
# CI template installation (EXT-007)
# ---------------------------------------------------------------------------

_CI_TEMPLATES_DIR = Path(__file__).resolve().parent.parent.parent / "ci-templates"

_CI_TEMPLATE_MAP = {
    "github": ("github-actions.yml", ".github/workflows/spec-drift.yml"),
    "gitlab": ("gitlab-ci.yml", ".gitlab-ci.yml"),
}


def _install_ci_template(
    project_root: Path,
    ci_platform: str,
    dry_run: bool,
    created: list[str],
    skipped: list[str],
) -> None:
    """Copy the appropriate CI template into the project."""
    if ci_platform not in _CI_TEMPLATE_MAP:
        return

    source_name, target_rel = _CI_TEMPLATE_MAP[ci_platform]
    source_path = _CI_TEMPLATES_DIR / source_name
    target_path = project_root / target_rel

    if target_path.exists():
        skipped.append(target_rel)
        return

    if dry_run:
        print(f"[dry-run] create {target_rel}")
    else:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(source_path.read_text(encoding="utf-8"), encoding="utf-8")
    created.append(target_rel)

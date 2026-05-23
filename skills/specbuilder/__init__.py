"""SpecBuilder — Spec-driven development toolkit.

A self-contained skill package that provides project scaffolding,
spec module generation, skill discovery, drift detection, and
acceptance testing for spec-driven development workflows.
"""

import re as _re
from pathlib import Path as _Path


def _resolve_version() -> str:
    """Derive the current version from the latest changelog entry.

    Scans spec/changelog/*.md for the highest version string.
    Falls back to "0.0.0" if no changelog exists (e.g., in consumer projects).
    """
    changelog_dir = _Path(__file__).resolve().parent.parent / "spec" / "changelog"
    if not changelog_dir.exists():
        return "0.0.0"

    latest_version = "0.0.0"
    for f in sorted(changelog_dir.glob("*.md"), reverse=True):
        content = f.read_text(encoding="utf-8")
        match = _re.search(r'^version:\s*"?([^"\n]+)"?', content, _re.MULTILINE)
        if match:
            latest_version = match.group(1).strip()
            break  # Sorted reverse — first match is the latest entry

    return latest_version


__version__ = _resolve_version()

"""Semantic spec diffing (EXT-008).

Compares spec module versions section-by-section and classifies changes
as breaking, additive, or cosmetic.

Usage:
    python3 -m specbuilder diff <module_num> [--from COMMIT] [--to COMMIT]
        [--json] [--breaking-only]

Exit codes:
    0 = success (diff produced)
    1 = breaking changes found (useful for CI gating)
    2 = usage error
"""

import json
import subprocess
import sys
from pathlib import Path

from specbuilder.src.config import DEFAULT_MODULES_DIR, get_project_root
from specbuilder.src.validation import parse_frontmatter

# ---------------------------------------------------------------------------
# Section parsing
# ---------------------------------------------------------------------------


def parse_spec_sections(content: str) -> dict[str, str]:
    """Parse a spec module into named sections by ## headings.

    Returns a dict mapping section name → section body text.
    Frontmatter (before first ##) is stored under key "_frontmatter".
    """
    sections: dict[str, str] = {}
    current: str | None = "_preamble"
    sections["_preamble"] = ""

    for line in content.splitlines(keepends=True):
        if line.startswith("## "):
            current = line[3:].strip()
            sections[current] = ""
        elif current is not None:
            sections[current] += line

    # Remove empty preamble
    if not sections.get("_preamble", "").strip():
        del sections["_preamble"]

    return sections


# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------


def get_spec_at_commit(spec_path: Path, commit: str, project_root: Path) -> str | None:
    """Retrieve file content at a specific git commit.

    Returns None if the file didn't exist at that commit or git fails.
    """
    try:
        rel_path = spec_path.relative_to(project_root)
    except ValueError:
        rel_path = spec_path

    try:
        result = subprocess.run(
            ["git", "-C", str(project_root), "show", f"{commit}:{rel_path}"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return result.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return None


def get_previous_version(spec_path: Path, project_root: Path) -> str | None:
    """Get the last committed version of a spec file (HEAD).

    Returns None if the file has no git history.
    """
    return get_spec_at_commit(spec_path, "HEAD", project_root)


# ---------------------------------------------------------------------------
# Change classification
# ---------------------------------------------------------------------------

# Sections that carry implementation weight (changes here may be breaking/additive)
_STRUCTURAL_SECTIONS = {"Inputs", "Output", "Acceptance Criteria", "Edge Cases"}

# Sections where changes are always cosmetic
_COSMETIC_SECTIONS = {"Executive Summary", "Extension Points"}


def _extract_list_items(text: str) -> list[str]:
    """Extract bullet/checkbox items from section text."""
    items = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(("- ", "* ", "- [ ] ", "- [x] ")):
            # Normalize checkbox prefixes
            item = stripped.lstrip("-* ").lstrip("[ ] ").lstrip("[x] ").strip()
            if item:
                items.append(item)
    return items


def _extract_table_rows(text: str) -> list[str]:
    """Extract non-header table rows."""
    rows = []
    in_table = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|"):
            if "---" in stripped:
                in_table = True
                continue
            if in_table:
                rows.append(stripped)
            elif not in_table and "|" in stripped:
                # Header row — skip
                in_table = False
    return rows


def classify_section_change(section: str, old_text: str, new_text: str) -> dict:
    """Classify the change in a single section.

    Returns:
        {"section": str, "impact": "breaking"|"additive"|"cosmetic", "details": [str]}
    """
    # No change
    if old_text.strip() == new_text.strip():
        return {"section": section, "impact": "none", "details": []}

    # Cosmetic-only sections
    if section in _COSMETIC_SECTIONS:
        return {
            "section": section,
            "impact": "cosmetic",
            "details": [f"Rewording in {section} (no implementation impact)"],
        }

    # Structural sections — analyze item-level changes
    if section in _STRUCTURAL_SECTIONS:
        old_items = _extract_list_items(old_text)
        new_items = _extract_list_items(new_text)

        # Also check table rows for Edge Cases
        if section == "Edge Cases":
            old_items = _extract_table_rows(old_text) or old_items
            new_items = _extract_table_rows(new_text) or new_items

        removed = set(old_items) - set(new_items)
        added = set(new_items) - set(old_items)

        details = []
        impact = "cosmetic"

        if removed:
            impact = "breaking"
            for item in sorted(removed):
                details.append(f"Removed: {item[:80]}")

        if added:
            if impact != "breaking":
                impact = "additive"
            for item in sorted(added):
                details.append(f"Added: {item[:80]}")

        # If items didn't change but text did, it's a reword
        if not details:
            impact = "cosmetic"
            details.append(f"Rewording in {section}")

        return {"section": section, "impact": impact, "details": details}

    # Unknown sections — default to cosmetic
    return {
        "section": section,
        "impact": "cosmetic",
        "details": [f"Changed: {section}"],
    }


# ---------------------------------------------------------------------------
# Diff orchestrator
# ---------------------------------------------------------------------------


def diff_spec(
    module_num: int,
    project_root: Path | None = None,
    from_commit: str | None = None,
    to_commit: str | None = None,
) -> dict:
    """Produce a semantic diff for a spec module.

    Args:
        module_num: Module number to diff.
        project_root: Project root (auto-detected if None).
        from_commit: Base commit (default: HEAD — last committed version).
        to_commit: Target commit (default: None — current working tree).

    Returns:
        Dict with keys: module, version_from, version_to, changes, summary.
    """
    if project_root is None:
        project_root = get_project_root()

    # Find the spec file
    modules_dir = project_root / DEFAULT_MODULES_DIR
    pattern = f"{module_num:02d}-*.md"
    matches = list(modules_dir.glob(pattern))

    if not matches:
        return {"error": f"No spec file matching {pattern} in {modules_dir}"}

    spec_path = matches[0]

    # Get current version (working tree or specific commit)
    if to_commit:
        new_content = get_spec_at_commit(spec_path, to_commit, project_root)
        if not new_content:
            return {"error": f"Cannot read {spec_path.name} at commit {to_commit}"}
    else:
        new_content = spec_path.read_text(encoding="utf-8")

    # Get old version
    base = from_commit or "HEAD"
    old_content = get_spec_at_commit(spec_path, base, project_root)

    # Handle new module (no prior version)
    if old_content is None:
        new_sections = parse_spec_sections(new_content)
        changes = []
        for section, text in new_sections.items():
            if section == "_preamble":
                continue
            items = _extract_list_items(text)
            details = (
                [f"Added: {item[:80]}" for item in items] if items else [f"New section: {section}"]
            )
            changes.append(
                {
                    "section": section,
                    "impact": "additive",
                    "details": details,
                }
            )
        new_fm = parse_frontmatter(spec_path) if not to_commit else {}
        return {
            "module": new_fm.get("id", f"MOD-{module_num:03d}"),
            "version_from": "(none)",
            "version_to": new_fm.get("version", "unknown"),
            "changes": changes,
            "summary": {"breaking": 0, "additive": len(changes), "cosmetic": 0},
        }

    # Parse both versions into sections
    old_sections = parse_spec_sections(old_content)
    new_sections = parse_spec_sections(new_content)

    # Extract version info from frontmatter
    old_fm = parse_frontmatter(spec_path) if not from_commit else {}
    new_fm = parse_frontmatter(spec_path) if not to_commit else {}

    # Quick version extraction from content if we're comparing commits
    if from_commit:
        import re

        m = re.search(r'version:\s*"([^"]+)"', old_content)
        old_version = m.group(1) if m else "unknown"
    else:
        old_version = old_fm.get("version", "unknown")

    if to_commit:
        import re

        m = re.search(r'version:\s*"([^"]+)"', new_content)
        new_version = m.group(1) if m else "unknown"
    else:
        new_version = new_fm.get("version", "unknown")

    # Compare sections
    all_section_names = set(old_sections.keys()) | set(new_sections.keys())
    all_section_names.discard("_preamble")

    changes = []
    for section in sorted(all_section_names):
        old_text = old_sections.get(section, "")
        new_text = new_sections.get(section, "")

        if not old_text and new_text:
            # Entirely new section
            changes.append(
                {
                    "section": section,
                    "impact": "additive",
                    "details": [f"New section added: {section}"],
                }
            )
        elif old_text and not new_text:
            # Section removed
            changes.append(
                {
                    "section": section,
                    "impact": "breaking",
                    "details": [f"Section removed: {section}"],
                }
            )
        else:
            change = classify_section_change(section, old_text, new_text)
            if change["impact"] != "none":
                changes.append(change)

    # Build summary
    summary = {
        "breaking": sum(1 for c in changes if c["impact"] == "breaking"),
        "additive": sum(1 for c in changes if c["impact"] == "additive"),
        "cosmetic": sum(1 for c in changes if c["impact"] == "cosmetic"),
    }

    return {
        "module": new_fm.get("id", f"MOD-{module_num:03d}"),
        "version_from": old_version,
        "version_to": new_version,
        "changes": changes,
        "summary": summary,
    }


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------


def format_diff_report(result: dict) -> str:
    """Format a diff result as a human-readable terminal report."""
    if "error" in result:
        return f"Error: {result['error']}"

    lines = [
        f"Spec Diff: {result['module']}",
        f"Version: {result['version_from']} → {result['version_to']}",
        "",
    ]

    changes = result["changes"]
    if not changes:
        lines.append("No changes detected.")
        return "\n".join(lines)

    # Group by impact
    breaking = [c for c in changes if c["impact"] == "breaking"]
    additive = [c for c in changes if c["impact"] == "additive"]
    cosmetic = [c for c in changes if c["impact"] == "cosmetic"]

    if breaking:
        lines.append(f"BREAKING ({len(breaking)}):")
        for c in breaking:
            for detail in c["details"]:
                lines.append(f"  - [{c['section']}] {detail}")
        lines.append("")

    if additive:
        lines.append(f"ADDITIVE ({len(additive)}):")
        for c in additive:
            for detail in c["details"]:
                lines.append(f"  - [{c['section']}] {detail}")
        lines.append("")

    if cosmetic:
        lines.append(f"COSMETIC ({len(cosmetic)}):")
        for c in cosmetic:
            for detail in c["details"]:
                lines.append(f"  - [{c['section']}] {detail}")
        lines.append("")

    s = result["summary"]
    lines.append(
        f"Summary: {s['breaking']} breaking, {s['additive']} additive, {s['cosmetic']} cosmetic"
    )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """CLI entry point."""
    if len(sys.argv) < 2:
        print(
            "Usage: python3 -m specbuilder diff <module_num> "
            "[--from COMMIT] [--to COMMIT] [--json] [--breaking-only]",
            file=sys.stderr,
        )
        sys.exit(2)

    try:
        module_num = int(sys.argv[1])
    except ValueError:
        print(f"Error: module_num must be an integer, got '{sys.argv[1]}'", file=sys.stderr)
        sys.exit(2)

    # Parse optional flags
    from_commit = None
    to_commit = None
    json_output = "--json" in sys.argv
    breaking_only = "--breaking-only" in sys.argv

    if "--from" in sys.argv:
        idx = sys.argv.index("--from")
        if idx + 1 < len(sys.argv):
            from_commit = sys.argv[idx + 1]

    if "--to" in sys.argv:
        idx = sys.argv.index("--to")
        if idx + 1 < len(sys.argv):
            to_commit = sys.argv[idx + 1]

    result = diff_spec(
        module_num,
        from_commit=from_commit,
        to_commit=to_commit,
    )

    if "error" in result:
        print(f"Error: {result['error']}", file=sys.stderr)
        sys.exit(2)

    # Filter breaking-only if requested
    if breaking_only:
        result["changes"] = [c for c in result["changes"] if c["impact"] == "breaking"]

    if json_output:
        print(json.dumps(result, indent=2))
    else:
        print(format_diff_report(result))

    # Exit 1 if breaking changes found (useful for CI)
    if result["summary"]["breaking"] > 0:
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()

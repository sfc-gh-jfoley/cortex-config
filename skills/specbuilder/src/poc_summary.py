"""POC Summary artifact generator.

Rolls up module statuses, acceptance criteria pass/fail results,
scope exclusions, and production readiness gaps into a single
spec/POC-SUMMARY.md artifact for external audiences.
"""

import re
import sys
from datetime import date
from pathlib import Path

from specbuilder.src.config import (
    DEFAULT_IMPL_DIR,
    DEFAULT_MODULES_DIR,
    DEFAULT_SUMMARY_FILE,
    get_project_root,
    is_poc_mode,
)
from specbuilder.src.validation import parse_frontmatter

# ---------------------------------------------------------------------------
# Module status parsing
# ---------------------------------------------------------------------------


def parse_module_statuses(project_root: Path, modules: list[str] | None = None) -> list[dict]:
    """Read spec/modules/*.md frontmatter + inline AC checkboxes.

    Returns a list of dicts with keys:
        id, title, status, ac_pass, ac_total, ac_items
    """
    modules_dir = project_root / DEFAULT_MODULES_DIR
    if not modules_dir.is_dir():
        return []

    results = []
    for md_file in sorted(modules_dir.glob("[0-9][0-9]-*.md")):
        if md_file.name.startswith("00-"):
            continue

        fm = parse_frontmatter(md_file)
        mod_id = fm.get("id", md_file.stem)

        # Filter by --modules if specified
        if modules and mod_id not in modules:
            continue

        content = md_file.read_text(encoding="utf-8")
        ac_items = _extract_ac_items(content)
        ac_pass = sum(1 for item in ac_items if item["checked"])

        results.append({
            "id": mod_id,
            "title": fm.get("title", md_file.stem),
            "status": fm.get("status", "unknown"),
            "ac_pass": ac_pass,
            "ac_total": len(ac_items),
            "ac_items": ac_items,
        })

    return results


def _extract_ac_items(content: str) -> list[dict]:
    """Extract acceptance criteria checkbox items from markdown content."""
    items = []
    in_ac_section = False
    lines = content.split("\n")

    for line in lines:
        if re.match(r"^##\s+Acceptance Criteria", line):
            in_ac_section = True
            continue
        if in_ac_section and re.match(r"^##\s+", line) and "Acceptance" not in line:
            break
        if in_ac_section:
            match = re.match(r"^\s*-\s+\[([ xX])\]\s*(.*)", line)
            if match:
                checked = match.group(1).lower() == "x"
                text = match.group(2).strip()
                items.append({"checked": checked, "text": text})

    return items


# ---------------------------------------------------------------------------
# Out-of-scope extraction
# ---------------------------------------------------------------------------


def extract_out_of_scope(project_root: Path) -> list[str]:
    """Parse spec/INTAKE.md and module out-of-scope sections for exclusions."""
    exclusions = []

    # Check INTAKE.md
    intake_path = project_root / "spec" / "INTAKE.md"
    if intake_path.is_file():
        content = intake_path.read_text(encoding="utf-8")
        exclusions.extend(_parse_out_of_scope_section(content))

    # Check each module for "Out of scope" subsections
    modules_dir = project_root / DEFAULT_MODULES_DIR
    if modules_dir.is_dir():
        for md_file in sorted(modules_dir.glob("[0-9][0-9]-*.md")):
            if md_file.name.startswith("00-"):
                continue
            content = md_file.read_text(encoding="utf-8")
            exclusions.extend(_parse_out_of_scope_section(content))

    return exclusions


def _parse_out_of_scope_section(content: str) -> list[str]:
    """Extract bullet items from an 'Out of scope' or 'Out of Scope' section."""
    items = []
    in_section = False
    lines = content.split("\n")

    for line in lines:
        if re.match(r"^#{1,3}\s+Out\s+of\s+[Ss]cope", line):
            in_section = True
            continue
        if in_section and re.match(r"^#{1,3}\s+", line):
            break
        if in_section:
            match = re.match(r"^\s*-\s+(.*)", line)
            if match:
                text = match.group(1).strip()
                if text:
                    items.append(text)

    return items


# ---------------------------------------------------------------------------
# Production gap detection
# ---------------------------------------------------------------------------

# Common hardcoded references to flag
_HARDCODED_PATTERNS = [
    (re.compile(r"\b(USE\s+(?:DATABASE|SCHEMA|WAREHOUSE)\s+)([A-Z_][A-Z0-9_]+)", re.IGNORECASE),
     "Hardcoded {0} reference: {1}"),
]

_TODO_PATTERN = re.compile(r"\b(TODO|FIXME)\b", re.IGNORECASE)
_TRY_CATCH_PATTERN = re.compile(
    r"\bBEGIN\b.*\bEXCEPTION\b|\bTRY\b.*\bCATCH\b", re.IGNORECASE | re.DOTALL
)
_GRANT_PATTERN = re.compile(r"\bGRANT\b", re.IGNORECASE)


def detect_production_gaps(impl_dir: Path) -> list[dict]:
    """Heuristic checks on generated SQL/Python files for production gaps."""
    gaps: list[dict[str, str | int | None]] = []
    if not impl_dir.is_dir():
        return gaps

    sql_files = list(impl_dir.rglob("*.sql"))
    py_files = list(impl_dir.rglob("*.py"))
    all_files = sql_files + py_files

    has_grant = False

    for filepath in all_files:
        try:
            content = filepath.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue

        rel_path = str(filepath)

        # Check for TODO/FIXME markers
        for match in _TODO_PATTERN.finditer(content):
            line_num = content[:match.start()].count("\n") + 1
            gaps.append({
                "file": rel_path,
                "gap": f"{match.group(0)} marker",
                "severity": "Medium",
                "recommendation": "Resolve or remove before production",
                "line": line_num,
            })

        # Check for hardcoded DB/schema/warehouse references
        for pattern, msg_template in _HARDCODED_PATTERNS:
            for match in pattern.finditer(content):
                keyword = match.group(1).strip()
                value = match.group(2)
                gaps.append({
                    "file": rel_path,
                    "gap": f"Hardcoded reference: {keyword} {value}",
                    "severity": "Low",
                    "recommendation": "Parameterize via session variable or config",
                    "line": content[:match.start()].count("\n") + 1,
                })

        # Check GRANT presence
        if _GRANT_PATTERN.search(content):
            has_grant = True

    # Check SQL stored procedures for error handling
    for filepath in sql_files:
        try:
            content = filepath.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue

        # If file contains CREATE PROCEDURE but no TRY/CATCH or EXCEPTION
        if re.search(r"\bCREATE\s+(OR\s+REPLACE\s+)?PROCEDURE\b", content, re.IGNORECASE):
            if not _TRY_CATCH_PATTERN.search(content):
                gaps.append({
                    "file": str(filepath),
                    "gap": "Missing error handling in stored procedure",
                    "severity": "Medium",
                    "recommendation": "Add TRY/CATCH or EXCEPTION block",
                    "line": None,
                })

    # If no GRANT found across all files, flag it
    if all_files and not has_grant:
        gaps.append({
            "file": "(project-wide)",
            "gap": "No GRANT statements found",
            "severity": "Low",
            "recommendation": "Add access control grants for production roles",
            "line": None,
        })

    return gaps


# ---------------------------------------------------------------------------
# Summary generation
# ---------------------------------------------------------------------------


def generate_summary(
    project_root: Path,
    output_path: Path | None = None,
    modules: list[str] | None = None,
) -> Path | None:
    """Orchestrate all functions, render markdown, write to output path."""
    if output_path is None:
        output_path = project_root / DEFAULT_SUMMARY_FILE

    # Gather data
    module_statuses = parse_module_statuses(project_root, modules=modules)
    if not module_statuses:
        print("No implemented modules found. Nothing to summarize.", file=sys.stderr)
        return None

    out_of_scope = extract_out_of_scope(project_root)
    impl_dir = project_root / DEFAULT_IMPL_DIR
    production_gaps = detect_production_gaps(impl_dir)

    # Render markdown
    lines = []
    lines.append("# POC Summary")
    lines.append("")
    lines.append(f"**Date:** {date.today().isoformat()}")
    lines.append(f"**Components:** {len(module_statuses)} modules")
    lines.append("")

    # What Was Proven
    lines.append("## What Was Proven")
    lines.append("")
    lines.append("| Component | Status | Acceptance Criteria |")
    lines.append("|-----------|--------|---------------------|")
    for mod in module_statuses:
        status_icon = _status_icon(mod)
        ac_summary = f"{mod['ac_pass']}/{mod['ac_total']} passed"
        lines.append(f"| {mod['title']} | {status_icon} | {ac_summary} |")
    lines.append("")

    # Acceptance Criteria Results
    lines.append("## Acceptance Criteria Results")
    lines.append("")
    for mod in module_statuses:
        if mod["ac_items"]:
            lines.append(f"### {mod['title']}")
            lines.append("")
            for item in mod["ac_items"]:
                check = "x" if item["checked"] else " "
                lines.append(f"- [{check}] {item['text']}")
            lines.append("")

    # Out of Scope
    if out_of_scope:
        lines.append("## Out of Scope (Agreed Exclusions)")
        lines.append("")
        for item in out_of_scope:
            lines.append(f"- {item}")
        lines.append("")

    # Production Readiness Gaps
    if production_gaps:
        lines.append("## Production Readiness Gaps")
        lines.append("")
        lines.append("| Gap | Severity | Recommendation |")
        lines.append("|-----|----------|----------------|")
        for gap in production_gaps:
            lines.append(f"| {gap['gap']} | {gap['severity']} | {gap['recommendation']} |")
        lines.append("")

    # Recommended Next Steps
    lines.append("## Recommended Next Steps")
    lines.append("")
    if production_gaps:
        seen = set()
        for gap in production_gaps:
            rec = gap["recommendation"]
            if rec not in seen:
                lines.append(f"- [ ] {rec}")
                seen.add(rec)
    if out_of_scope:
        lines.append("- [ ] Review out-of-scope items for production roadmap")
    lines.append("")

    # Write output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path


def _status_icon(mod: dict) -> str:
    """Return a status icon string for a module."""
    if mod["ac_total"] == 0:
        return "- No AC"
    ratio = mod["ac_pass"] / mod["ac_total"]
    if ratio == 1.0:
        return "Verified"
    elif ratio >= 0.5:
        return "Partial"
    else:
        return "Failed"


# ---------------------------------------------------------------------------
# CLI entry
# ---------------------------------------------------------------------------


def main() -> None:
    """CLI entry point for POC summary generation."""
    import argparse

    parser = argparse.ArgumentParser(
        prog="specbuilder summary",
        description="Generate a POC summary artifact from spec modules.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output file path (default: spec/POC-SUMMARY.md)",
    )
    parser.add_argument(
        "--modules",
        nargs="*",
        default=None,
        help="Include only specific modules (e.g., MOD-01 MOD-03)",
    )

    args = parser.parse_args()
    project_root = get_project_root()
    if not is_poc_mode(project_root):
        print(
            "Not a POC project (no spec/.poc and no [project] mode = 'poc' in .specbuilder.toml).",
            file=sys.stderr,
        )
        print("Skipping POC summary generation.", file=sys.stderr)
        return
    output = generate_summary(project_root, output_path=args.output, modules=args.modules)
    if output is not None:
        print(f"Summary written to: {output}")

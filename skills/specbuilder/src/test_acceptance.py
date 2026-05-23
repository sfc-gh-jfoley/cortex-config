"""Acceptance criteria test runner (MOD-05 Phase 4).

Loads an acceptance criteria file, runs automated checks where possible,
and produces a PASS/FAIL/MANUAL_REVIEW report.

Usage:
    python3 -m specbuilder.test_acceptance <module_num> [output_file]

Exit codes:
    0 = all automated checks pass
    1 = one or more automated checks fail
    2 = usage error
"""

import re
import sys
from datetime import datetime
from pathlib import Path

from specbuilder.src.config import get_project_root
from specbuilder.src.validation import parse_frontmatter, validate_ac_file, validate_spec_module

# ---------------------------------------------------------------------------
# AC parsing
# ---------------------------------------------------------------------------


def _parse_ac_sections(ac_content: str) -> list[dict]:
    """Parse AC file content into structured sections with criteria."""
    sections = []
    current_section: dict | None = None

    for line in ac_content.split("\n"):
        # Detect AC section headers
        if re.match(r"^## AC-\d+", line):
            if current_section:
                sections.append(current_section)
            current_section = {
                "header": line.strip("# ").strip(),
                "criteria": [],
            }
        elif current_section and "|" in line:
            # Parse table rows (skip header and separator)
            cells = [c.strip() for c in line.split("|")[1:-1]]
            if len(cells) >= 3 and cells[0] and not cells[0].startswith("-"):
                # Skip table header row
                if cells[0] == "#" or cells[0] == "---":
                    continue
                current_section["criteria"].append(
                    {
                        "id": cells[0],
                        "criterion": cells[1] if len(cells) > 1 else "",
                        "pass": cells[2].strip() if len(cells) > 2 else "☐",
                        "notes": cells[3].strip() if len(cells) > 3 else "",
                    }
                )

    if current_section:
        sections.append(current_section)

    return sections


# ---------------------------------------------------------------------------
# Automated checks
# ---------------------------------------------------------------------------


def _check_spec_exists(project_root: Path, module_num: int) -> dict:
    """Check that the spec module file exists and is valid."""
    spec_dir = project_root / "spec" / "modules"
    pattern = f"{module_num:02d}-*.md"
    matches = list(spec_dir.glob(pattern))

    if not matches:
        return {
            "check": "spec_exists",
            "result": "FAIL",
            "detail": f"No spec file matching {pattern}",
        }

    spec_file = matches[0]
    errors = validate_spec_module(spec_file, project_root / "spec" / "acceptance-criteria")
    if errors:
        return {"check": "spec_valid", "result": "FAIL", "detail": "; ".join(errors)}

    return {"check": "spec_exists", "result": "PASS", "detail": str(spec_file.name)}


def _check_ac_exists(project_root: Path, module_num: int) -> dict:
    """Check that the AC file exists and is valid."""
    ac_dir = project_root / "spec" / "acceptance-criteria"
    pattern = f"{module_num:02d}-*.md"
    matches = list(ac_dir.glob(pattern))

    if not matches:
        return {"check": "ac_exists", "result": "FAIL", "detail": f"No AC file matching {pattern}"}

    ac_file = matches[0]
    errors = validate_ac_file(ac_file)
    if errors:
        return {"check": "ac_valid", "result": "FAIL", "detail": "; ".join(errors)}

    return {"check": "ac_exists", "result": "PASS", "detail": str(ac_file.name)}


def _check_frontmatter_alignment(project_root: Path, module_num: int) -> dict:
    """Check that spec and AC file versions/statuses are aligned."""
    spec_dir = project_root / "spec" / "modules"
    ac_dir = project_root / "spec" / "acceptance-criteria"

    spec_files = list(spec_dir.glob(f"{module_num:02d}-*.md"))
    ac_files = list(ac_dir.glob(f"{module_num:02d}-*.md"))

    if not spec_files or not ac_files:
        return {"check": "alignment", "result": "FAIL", "detail": "Missing spec or AC file"}

    spec_fm = parse_frontmatter(spec_files[0])
    ac_fm = parse_frontmatter(ac_files[0])

    issues = []
    if spec_fm.get("version") != ac_fm.get("version"):
        issues.append(
            f"Version mismatch: spec={spec_fm.get('version')} vs ac={ac_fm.get('version')}"
        )

    if issues:
        return {"check": "alignment", "result": "FAIL", "detail": "; ".join(issues)}

    return {"check": "alignment", "result": "PASS", "detail": "Spec and AC aligned"}


def _check_ac_coverage(project_root: Path, module_num: int) -> dict:
    """Check that AC file covers all spec acceptance criteria."""
    spec_dir = project_root / "spec" / "modules"
    ac_dir = project_root / "spec" / "acceptance-criteria"

    spec_files = list(spec_dir.glob(f"{module_num:02d}-*.md"))
    ac_files = list(ac_dir.glob(f"{module_num:02d}-*.md"))

    if not spec_files or not ac_files:
        return {"check": "coverage", "result": "FAIL", "detail": "Missing files"}

    spec_content = spec_files[0].read_text(encoding="utf-8")
    ac_content = ac_files[0].read_text(encoding="utf-8")

    # Count AC sections in spec vs AC file
    spec_ac_count = len(re.findall(r"^### AC-\d+", spec_content, re.MULTILINE))
    ac_ac_count = len(re.findall(r"^## AC-\d+", ac_content, re.MULTILINE))

    if spec_ac_count != ac_ac_count:
        return {
            "check": "coverage",
            "result": "FAIL",
            "detail": f"Spec has {spec_ac_count} AC sections, AC file has {ac_ac_count}",
        }

    return {"check": "coverage", "result": "PASS", "detail": f"{ac_ac_count} sections covered"}


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------


def run_tests(module_num: int, project_root: Path | None = None) -> dict:
    """Run all automated acceptance checks for a module.

    Args:
        module_num: The module number to test (e.g., 1, 2, 3).
        project_root: Project root. Auto-detected if None.

    Returns:
        Dict with: module_num, timestamp, checks (list of results),
        summary (pass/fail/manual counts).
    """
    if project_root is None:
        project_root = get_project_root()

    checks = [
        _check_spec_exists(project_root, module_num),
        _check_ac_exists(project_root, module_num),
        _check_frontmatter_alignment(project_root, module_num),
        _check_ac_coverage(project_root, module_num),
    ]

    # Parse AC file for manual review items
    ac_dir = project_root / "spec" / "acceptance-criteria"
    ac_files = list(ac_dir.glob(f"{module_num:02d}-*.md"))
    manual_items = []
    if ac_files:
        ac_content = ac_files[0].read_text(encoding="utf-8")
        sections = _parse_ac_sections(ac_content)
        for section in sections:
            for criterion in section["criteria"]:
                if criterion["pass"] == "☐":
                    manual_items.append(
                        {
                            "check": f"{section['header']}/{criterion['id']}",
                            "result": "MANUAL_REVIEW",
                            "detail": criterion["criterion"],
                        }
                    )

    all_results = checks + manual_items

    summary = {
        "pass": sum(1 for r in all_results if r["result"] == "PASS"),
        "fail": sum(1 for r in all_results if r["result"] == "FAIL"),
        "manual_review": sum(1 for r in all_results if r["result"] == "MANUAL_REVIEW"),
    }

    return {
        "module_num": module_num,
        "timestamp": datetime.now().isoformat(),
        "checks": all_results,
        "summary": summary,
    }


def format_report(results: dict) -> str:
    """Format test results as a markdown report."""
    lines = [
        f"# Acceptance Test Report — Module {results['module_num']:02d}",
        "",
        f"> Generated: {results['timestamp']}",
        "",
        "---",
        "",
        "## Automated Checks",
        "",
        "| Check | Result | Detail |",
        "|-------|--------|--------|",
    ]

    for check in results["checks"]:
        if check["result"] != "MANUAL_REVIEW":
            icon = "✓" if check["result"] == "PASS" else "✗"
            lines.append(f"| {check['check']} | {icon} {check['result']} | {check['detail']} |")

    lines.extend(["", "---", "", "## Manual Review Required", ""])

    manual = [c for c in results["checks"] if c["result"] == "MANUAL_REVIEW"]
    if manual:
        lines.extend(["| Criterion | Detail |", "|-----------|--------|"])
        for check in manual:
            lines.append(f"| {check['check']} | {check['detail']} |")
    else:
        lines.append("No manual review items.")

    lines.extend(
        [
            "",
            "---",
            "",
            "## Summary",
            "",
            f"- **PASS**: {results['summary']['pass']}",
            f"- **FAIL**: {results['summary']['fail']}",
            f"- **MANUAL_REVIEW**: {results['summary']['manual_review']}",
            "",
        ]
    )

    return "\n".join(lines)


def main() -> None:
    """CLI entry point."""
    if len(sys.argv) < 2:
        print(
            "Usage: python3 -m specbuilder.test_acceptance <module_num> [output_file]",
            file=sys.stderr,
        )
        sys.exit(2)

    try:
        module_num = int(sys.argv[1])
    except ValueError:
        print(f"Error: module_num must be an integer, got '{sys.argv[1]}'", file=sys.stderr)
        sys.exit(2)

    results = run_tests(module_num)
    report = format_report(results)

    if len(sys.argv) >= 3:
        output_path = Path(sys.argv[2])
        output_path.write_text(report, encoding="utf-8")
        print(f"Report written to {output_path}")
    else:
        print(report)

    sys.exit(0 if results["summary"]["fail"] == 0 else 1)


if __name__ == "__main__":
    main()

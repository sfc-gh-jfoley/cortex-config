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

import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from specbuilder.src.config import get_project_root
from specbuilder.src.diagnostic_schema import wrap_findings
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
                criterion_entry = {
                    "id": cells[0],
                    "criterion": cells[1] if len(cells) > 1 else "",
                    "pass": cells[2].strip() if len(cells) > 2 else "☐",
                    "notes": cells[3].strip() if len(cells) > 3 else "",
                }
                if len(cells) > 4 and cells[4].strip() == "manual":
                    criterion_entry["type"] = "manual"
                current_section["criteria"].append(criterion_entry)

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

    spec_status = spec_fm.get("status", "")
    if spec_status not in ("accepted", "implemented"):
        issues.append(
            f"Unexpected spec status '{spec_status}': "
            "expected 'accepted' or 'implemented' when running acceptance tests"
        )

    spec_id = spec_fm.get("id")
    ac_id_val = ac_fm.get("id")
    if spec_id and ac_id_val and spec_id != ac_id_val:
        issues.append(f"ID mismatch: spec={spec_id} vs ac={ac_id_val}")

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

    try:
        spec_content = spec_files[0].read_text(encoding="utf-8")
        ac_content = ac_files[0].read_text(encoding="utf-8")
    except OSError as e:
        return {
            "check": "coverage",
            "result": "FAIL",
            "detail": f"Could not read spec or AC file: {e}",
        }

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
# SQL assertion execution
# ---------------------------------------------------------------------------


def execute_sql_assertion(sql: str) -> tuple[bool, str]:
    """Execute a single SQL assertion block via the cortex CLI.

    Returns (passed: bool, result_text: str).
    A non-zero exit code or an empty result set is treated as a failure.

    Raises:
        RuntimeError: if the cortex CLI binary is not found in PATH.
    """
    try:
        result = subprocess.run(
            ["cortex", "sql", "--format", "csv", "--query", sql],
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        raise RuntimeError(
            "cortex CLI not found in PATH. "
            "Install Cortex CLI or ensure it is on your PATH before using --execute-assertions."
        )
    if result.returncode != 0:
        return False, result.stderr.strip()
    output = result.stdout.strip()
    passed = bool(output) and output not in ("0", "false", "FALSE", "")
    return passed, output


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------


def run_tests(
    module_num: int,
    project_root: Path | None = None,
    schema: str | None = None,
    execute_assertions: bool = False,
) -> dict:
    """Run all automated acceptance checks for a module.

    Args:
        module_num: The module number to test (e.g., 1, 2, 3).
        project_root: Project root. Auto-detected if None.
        schema: Optional fully qualified sandbox schema (e.g. MY_DB.SANDBOX_SCHEMA).
            When provided, translatable ACs are surfaced as AUTOMATED items.
        execute_assertions: When True, SQL assertion blocks are executed against
            the active Snowflake connection via the cortex CLI.

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

    # Parse AC file for criterion pass/fail items
    ac_dir = project_root / "spec" / "acceptance-criteria"
    ac_files = list(ac_dir.glob(f"{module_num:02d}-*.md"))
    passed_items = []
    failed_items: list[dict] = []
    if ac_files:
        try:
            ac_content = ac_files[0].read_text(encoding="utf-8")
        except OSError as e:
            failed_items.append(
                {
                    "check": "AC-READ-ERROR",
                    "result": "FAIL",
                    "detail": f"Could not read AC file: {e}",
                }
            )
            ac_content = ""  # skip section parsing below
        sections = _parse_ac_sections(ac_content)
        for section in sections:
            for criterion in section["criteria"]:
                if criterion.get("type") == "manual" and criterion["pass"] == "☐":
                    passed_items.append(
                        {
                            "check": f"{section['header']}/{criterion['id']}",
                            "result": "MANUAL_REVIEW",
                            "detail": criterion["criterion"],
                        }
                    )
                elif criterion["pass"] == "☐":
                    failed_items.append(
                        {
                            "check": f"{section['header']}/{criterion['id']}",
                            "result": "FAIL",
                            "detail": criterion["criterion"],
                        }
                    )
                elif criterion["pass"] in ("☑", "✓"):
                    passed_items.append(
                        {
                            "check": f"{section['header']}/{criterion['id']}",
                            "result": "PASSED",
                            "detail": criterion["criterion"],
                        }
                    )

    # Tier 4: surface translatable SQL assertions when sandbox schema is provided.
    automated_items: list[dict] = []
    if schema is not None:
        from specbuilder.src.ac_assertions import translate_spec_acs

        spec_dir = project_root / "spec" / "modules"
        spec_files = list(spec_dir.glob(f"{module_num:02d}-*.md"))
        if spec_files:
            try:
                spec_content = spec_files[0].read_text(encoding="utf-8")
            except OSError as e:
                automated_items.append(
                    {
                        "check": "SPEC-READ-ERROR",
                        "result": "FAIL",
                        "detail": f"Could not read spec file: {e}",
                    }
                )
                spec_content = ""  # skip translation below
            for assertion in translate_spec_acs(spec_content, schema):
                if assertion.translatable:
                    item: dict = {
                        "check": assertion.ac_id,
                        "result": "AUTOMATED",
                        "detail": assertion.ac_text,
                        "assertion_sql": assertion.assertion_sql,
                    }
                    if execute_assertions and assertion.assertion_sql:
                        try:
                            passed_exec, exec_output = execute_sql_assertion(
                                assertion.assertion_sql
                            )
                            item["result"] = "PASS" if passed_exec else "FAIL"
                            item["execution_output"] = exec_output
                        except RuntimeError as exc:
                            item["result"] = "FAIL"
                            item["execution_output"] = str(exc)
                    automated_items.append(item)

    all_results = checks + failed_items + automated_items

    summary = {
        "pass": sum(1 for r in all_results if r["result"] == "PASS"),
        "fail": sum(1 for r in all_results if r["result"] == "FAIL"),
        "automated": sum(1 for r in all_results if r["result"] == "AUTOMATED"),
        "passed": sum(1 for r in passed_items if r["result"] == "PASSED"),
        "manual_review": sum(1 for r in passed_items if r["result"] == "MANUAL_REVIEW"),
    }

    return {
        "module_num": module_num,
        "timestamp": datetime.now().isoformat(),
        "checks": all_results,
        "passed": passed_items,
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
        if check["result"] == "PASSED":
            continue
        if check["result"] == "AUTOMATED":
            sql_snippet = (check.get("assertion_sql") or "")[:80]
            lines.append(f"| {check['check']} | → AUTOMATED | `{sql_snippet}` |")
            continue
        icon = "✓" if check["result"] == "PASS" else "✗"
        lines.append(f"| {check['check']} | {icon} {check['result']} | {check['detail']} |")

    lines.extend(["", "---", "", "## Passed Items", ""])

    passed = results.get("passed", [])
    if passed:
        lines.extend(["| Criterion | Detail |", "|-----------|--------|"])
        for check in passed:
            lines.append(f"| {check['check']} | {check['detail']} |")
    else:
        lines.append("No passed items.")

    lines.extend(
        [
            "",
            "---",
            "",
            "## Summary",
            "",
            f"- **PASS**: {results['summary']['pass']}",
            f"- **FAIL**: {results['summary']['fail']}",
            f"- **AUTOMATED**: {results['summary'].get('automated', 0)}",
            f"- **PASSED**: {len(results.get('passed', []))}",
            "",
        ]
    )

    return "\n".join(lines)


def main() -> None:
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        prog="python3 -m specbuilder.test_acceptance",
        description="Run acceptance tests for a spec module.",
    )
    parser.add_argument("module_num", type=int, help="Module number (e.g. 5)")
    parser.add_argument("output_file", nargs="?", help="Optional output file path")
    parser.add_argument(
        "--schema",
        metavar="SCHEMA_FQN",
        help=(
            "Fully qualified sandbox schema (e.g. MY_DB.SANDBOX_SCHEMA). "
            "Translatable ACs are surfaced as AUTOMATED with assertion_sql shown."
        ),
    )
    parser.add_argument(
        "--execute-assertions",
        action="store_true",
        help=(
            "Execute SQL assertion blocks against the active Snowflake connection "
            "via the cortex CLI. Requires an active cortex connection."
        ),
    )
    parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text).",
    )
    args = parser.parse_args()

    results = run_tests(
        args.module_num,
        schema=args.schema,
        execute_assertions=args.execute_assertions,
    )

    if args.format == "json":
        checks_flat = results["checks"] + results.get("passed", [])
        envelope = wrap_findings(
            "test-acceptance",
            checks_flat,
            module=str(results["module_num"]),
        )
        output = json.dumps(envelope, indent=2, default=str)
    else:
        output = format_report(results)

    if args.output_file:
        output_path = Path(args.output_file)
        output_path.write_text(output, encoding="utf-8")
        print(f"Report written to {output_path}")
    else:
        print(output)

    sys.exit(0 if results["summary"]["fail"] == 0 else 1)


if __name__ == "__main__":
    main()

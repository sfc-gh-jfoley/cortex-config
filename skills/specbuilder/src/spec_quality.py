"""Spec quality linting module.

Assesses whether spec modules are *good* — not just structurally valid.
Checks for vague criteria, testability, edge case sufficiency,
input completeness, and output specificity.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from specbuilder.src.config import (
    DEFAULT_MODULES_DIR,
    QUALITY_GATE_THRESHOLD,
    QUALITY_PROFILES,
    get_active_profile,
    get_project_root,
)

# ---------------------------------------------------------------------------
# Scoring constants
# ---------------------------------------------------------------------------

TESTABILITY_MAX_PENALTY = 10  # Maximum points deducted for zero testability score

# ---------------------------------------------------------------------------
# Weak words that indicate vague acceptance criteria
# ---------------------------------------------------------------------------

VAGUE_WORDS = [
    "works correctly",
    "appropriate",
    "reasonable",
    "properly",
    "as expected",
    "handles well",
    "efficient",
]

# ---------------------------------------------------------------------------
# Quality checks
# ---------------------------------------------------------------------------


def check_vague_criteria(content: str) -> list[dict]:
    """Flag acceptance criteria containing weak/vague words."""
    findings = []
    in_ac_section = False
    lines = content.split("\n")

    for i, line in enumerate(lines, start=1):
        if re.match(r"^##\s+Acceptance Criteria", line):
            in_ac_section = True
            continue
        if in_ac_section and re.match(r"^##\s+", line) and "Acceptance" not in line:
            break
        if in_ac_section:
            lower = line.lower()
            for word in VAGUE_WORDS:
                if word in lower:
                    findings.append(
                        {
                            "severity": "error",
                            "check": "vague_criteria",
                            "message": f"Vague language '{word}' in acceptance criteria",
                            "line": i,
                        }
                    )
    return findings


def check_testability(content: str) -> tuple[float, list[dict]]:
    """Score testability of acceptance criteria items.

    A testable AC item contains a measurable assertion: numeric threshold,
    boolean condition, specific output, or checkbox-style criterion.

    Returns (score, findings) where score = testable_items / total_items.
    """
    findings = []
    in_ac_section = False
    total_items = 0
    testable_items = 0
    lines = content.split("\n")

    # Patterns indicating testable criteria (applied to content after checkbox)
    testable_patterns = [
        r"\d+",  # numeric threshold
        r"\b(true|false)\b",  # boolean condition
        r"`[^`]+`",  # specific output/code reference
        r"\b(must|shall|returns?|produces?|outputs?|generates?|creates?|fails?|raises?)\b",
    ]

    for i, line in enumerate(lines, start=1):
        if re.match(r"^##\s+Acceptance Criteria", line):
            in_ac_section = True
            continue
        if in_ac_section and re.match(r"^##\s+", line) and "Acceptance" not in line:
            break
        if in_ac_section and re.match(r"^\s*-\s+", line):
            total_items += 1
            # Strip checkbox prefix before checking testability
            text = re.sub(r"^\s*-\s+\[[ x]\]\s*", "", line)
            is_testable = any(re.search(p, text, re.IGNORECASE) for p in testable_patterns)
            if is_testable:
                testable_items += 1

    if total_items == 0:
        findings.append(
            {
                "severity": "warning",
                "check": "testability",
                "message": "No acceptance criteria items found",
                "line": None,
            }
        )
        return (0.0, findings)

    score = testable_items / total_items
    if score < 0.7:
        findings.append(
            {
                "severity": "warning",
                "check": "testability",
                "message": (
                    f"Only {testable_items}/{total_items} AC items appear testable "
                    f"(score: {score:.0%}). Add measurable assertions."
                ),
                "line": None,
            }
        )
    return (score, findings)


def check_edge_case_sufficiency(content: str) -> list[dict]:
    """Flag if Edge Cases table has fewer than 5 rows."""
    findings = []
    in_edge_section = False
    table_rows = 0
    lines = content.split("\n")

    for i, line in enumerate(lines, start=1):
        if re.match(r"^##\s+Edge Cases", line):
            in_edge_section = True
            continue
        if in_edge_section and re.match(r"^##\s+", line) and "Edge" not in line:
            break
        if in_edge_section and line.strip().startswith("|"):
            # Skip header and separator rows
            stripped = line.strip()
            if re.match(r"^\|[-\s|]+\|$", stripped):
                continue
            if table_rows == 0:
                # First row is the header
                table_rows += 1
                continue
            table_rows += 1

    # table_rows includes the header row, so data rows = table_rows - 1
    data_rows = max(0, table_rows - 1)
    if data_rows < 5:
        findings.append(
            {
                "severity": "warning",
                "check": "edge_case_sufficiency",
                "message": (f"Edge Cases table has only {data_rows} rows (minimum recommended: 5)"),
                "line": None,
            }
        )
    return findings


def check_input_completeness(content: str) -> list[dict]:
    """Flag if Inputs section has no field table."""
    findings = []
    in_inputs_section = False
    has_table = False
    lines = content.split("\n")

    for line in lines:
        if re.match(r"^##\s+Inputs", line):
            in_inputs_section = True
            continue
        if in_inputs_section and re.match(r"^##\s+", line) and "Input" not in line:
            break
        if in_inputs_section and line.strip().startswith("|"):
            has_table = True
            break

    if not has_table:
        findings.append(
            {
                "severity": "warning",
                "check": "input_completeness",
                "message": "Inputs section has no field table (no | table rows found)",
                "line": None,
            }
        )
    return findings


def check_output_specificity(content: str) -> list[dict]:
    """Flag if Output section contains no backtick-quoted file paths or code blocks."""
    findings = []
    in_output_section = False
    has_specifics = False
    lines = content.split("\n")

    for line in lines:
        if re.match(r"^##\s+Output", line):
            in_output_section = True
            continue
        if in_output_section and re.match(r"^##\s+", line) and "Output" not in line:
            break
        if in_output_section:
            # Check for backtick-quoted paths or code blocks
            if re.search(r"`[^`]+`", line) or line.strip().startswith("```"):
                has_specifics = True
                break

    if not has_specifics:
        findings.append(
            {
                "severity": "warning",
                "check": "output_specificity",
                "message": ("Output section contains no backtick-quoted file paths or code blocks"),
                "line": None,
            }
        )
    return findings


# ---------------------------------------------------------------------------
# Cross-referencing checks (EXT-046)
# ---------------------------------------------------------------------------


def _extract_section(content: str, heading: str) -> str:
    """Extract text between a ## heading and the next ## heading."""
    pattern = rf"^##\s+{re.escape(heading)}\b(.*?)(?=\n##\s|\Z)"
    match = re.search(pattern, content, re.DOTALL | re.MULTILINE)
    return match.group(1) if match else ""


def _extract_backtick_paths(text: str) -> list[str]:
    """Extract backtick-quoted file paths from text, skipping glob patterns."""
    paths = re.findall(r"`([^`]+\.[a-zA-Z0-9]+)`", text)
    return [p for p in paths if not any(c in p for c in "*?[")]


def check_ac_coverage_of_outputs(content: str) -> list[dict]:
    """Flag output artifacts that have no corresponding acceptance criteria."""
    findings: list[dict] = []

    output_section = _extract_section(content, "Output")
    ac_section = _extract_section(content, "Acceptance Criteria")

    if not output_section or not ac_section:
        return findings

    # Extract backtick-quoted paths from Output section
    output_paths = _extract_backtick_paths(output_section)
    if not output_paths:
        return findings

    ac_lower = ac_section.lower()

    for path in output_paths:
        # Check if the path stem or full path appears in AC section
        stem = path.rsplit("/", 1)[-1].rsplit(".", 1)[0].lower()
        full_lower = path.lower()

        # Check stem (e.g., "users" from "sql/tables/users.sql")
        # and full path reference
        if stem not in ac_lower and full_lower not in ac_lower:
            findings.append(
                {
                    "severity": "warning",
                    "check": "ac_coverage_of_outputs",
                    "message": (
                        f"Output artifact `{path}` has no reference "
                        f"in Acceptance Criteria"
                    ),
                    "line": None,
                }
            )

    return findings


def check_edge_case_traceability(content: str) -> list[dict]:
    """Flag edge cases that have no related acceptance criteria."""
    findings: list[dict] = []

    edge_section = _extract_section(content, "Edge Cases")
    ac_section = _extract_section(content, "Acceptance Criteria")

    if not edge_section or not ac_section:
        return findings

    ac_lower = ac_section.lower()

    # Parse edge case table rows (skip header and separator)
    rows = []
    in_table = False
    header_seen = False
    for line in edge_section.split("\n"):
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        # Skip separator row
        if re.match(r"^\|[-\s|]+\|$", stripped):
            in_table = True
            continue
        if not in_table:
            # This is the header row
            header_seen = True
            continue
        if not header_seen:
            header_seen = True
            in_table = True
            continue
        # Data row — extract first content cell (scenario)
        cells = [c.strip() for c in stripped.split("|")]
        # After split: ['', 'Scenario text', 'Expected behavior', '']
        cells = [c for c in cells if c]
        if cells:
            rows.append(cells[0])

    # For each edge case scenario, extract keywords and check AC coverage
    for scenario in rows:
        # Extract meaningful words (3+ chars, not stop words)
        words = re.findall(r"[a-z][a-z0-9_]+", scenario.lower())
        keywords = {
            w for w in words
            if len(w) >= 3 and w not in {
                "with", "when", "then", "that", "this", "from",
                "have", "has", "does", "should", "must", "will", "each",
                "already", "exists", "expected", "section", "not", "the",
            }
        }

        if not keywords:
            continue

        # Scale hit threshold: require 1 hit for small keyword sets, 2 for larger
        min_hits = 1 if len(keywords) <= 2 else 2
        hits = sum(1 for kw in keywords if kw in ac_lower)
        if hits < min_hits:
            short_scenario = scenario[:60] + "..." if len(scenario) > 60 else scenario
            findings.append(
                {
                    "severity": "warning",
                    "check": "edge_case_traceability",
                    "message": (
                        f"Edge case \"{short_scenario}\" has weak traceability "
                        f"to acceptance criteria ({hits}/{len(keywords)} keywords)"
                    ),
                    "line": None,
                }
            )

    return findings


def check_input_output_traceability(content: str) -> list[dict]:
    """Flag inputs that are never referenced in Output or Acceptance Criteria."""
    findings: list[dict] = []

    input_section = _extract_section(content, "Inputs")
    output_section = _extract_section(content, "Output")
    ac_section = _extract_section(content, "Acceptance Criteria")

    if not input_section:
        return findings

    downstream = (output_section + "\n" + ac_section).lower()
    if not downstream.strip():
        return findings

    # Extract input field names from table rows (backtick-quoted in first column)
    input_fields: list[str] = []

    # Pattern 1: table rows — extract only the FIRST backtick-quoted value per row
    # (the field name column, not Default/Description columns)
    for line in input_section.split("\n"):
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        # Skip separator rows
        if re.match(r"^\|[-\s|:]+\|$", stripped):
            continue
        # Find first backtick-quoted value in the row
        match = re.search(r"`([^`]+)`", stripped)
        if match:
            value = match.group(1)
            # Skip common non-field values (booleans, paths, placeholders)
            if value.lower() in ("true", "false", "none", "—", "-", "auto-detected"):
                continue
            # Skip if it looks like a CLI flag without a name component
            if value.startswith("--"):
                # Extract the meaningful part: "--stubs-only" → "stubs"
                flag_name = value.lstrip("-").replace("-", "_").split("_")[0]
                if len(flag_name) > 3:
                    input_fields.append(flag_name)
            else:
                input_fields.append(value)

    # Check each input field for downstream reference
    for field in input_fields:
        field_lower = field.lower()
        # For compound names like "source_type", also check without underscores
        variants = {field_lower, field_lower.replace("_", " "), field_lower.replace("-", " ")}
        # Also check the last word (e.g., "type" from "source_type")
        parts = re.split(r"[_\-\s]+", field_lower)
        if len(parts) > 1:
            variants.add(parts[-1])

        found = any(v in downstream for v in variants if len(v) >= 3)
        if not found:
            findings.append(
                {
                    "severity": "warning",
                    "check": "input_output_traceability",
                    "message": (
                        f"Input `{field}` is not referenced in "
                        f"Output or Acceptance Criteria"
                    ),
                    "line": None,
                }
            )

    return findings


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

# Map check names to their functions for skip_checks filtering.
# Each value is a callable(content) -> list[dict] (findings).
# testability is special: returns (score, findings).
_CHECK_REGISTRY: dict[str, str] = {
    "vague_criteria": "check_vague_criteria",
    "testability": "check_testability",
    "edge_case_sufficiency": "check_edge_case_sufficiency",
    "input_completeness": "check_input_completeness",
    "output_specificity": "check_output_specificity",
    "ac_coverage_of_outputs": "check_ac_coverage_of_outputs",
    "edge_case_traceability": "check_edge_case_traceability",
    "input_output_traceability": "check_input_output_traceability",
}


def assess_quality(spec_path: Path, skip_checks: list[str] | None = None) -> dict:
    """Run all quality checks and return a structured report.

    Parameters
    ----------
    spec_path:
        Path to the spec markdown file to assess.
    skip_checks:
        Optional list of check names to skip. Skipped checks are excluded
        from the score calculation entirely (not scored as zero).
    """
    content = spec_path.read_text(encoding="utf-8")
    findings = []
    checks_to_skip = set(skip_checks) if skip_checks else set()

    if "vague_criteria" not in checks_to_skip:
        findings.extend(check_vague_criteria(content))

    if "testability" not in checks_to_skip:
        testability_score, testability_findings = check_testability(content)
        findings.extend(testability_findings)

    if "edge_case_sufficiency" not in checks_to_skip:
        findings.extend(check_edge_case_sufficiency(content))

    if "input_completeness" not in checks_to_skip:
        findings.extend(check_input_completeness(content))

    if "output_specificity" not in checks_to_skip:
        findings.extend(check_output_specificity(content))

    if "ac_coverage_of_outputs" not in checks_to_skip:
        findings.extend(check_ac_coverage_of_outputs(content))

    if "edge_case_traceability" not in checks_to_skip:
        findings.extend(check_edge_case_traceability(content))

    if "input_output_traceability" not in checks_to_skip:
        findings.extend(check_input_output_traceability(content))

    # Score calculation: start at 100, subtract per finding
    score: float = 100
    for f in findings:
        if f["severity"] == "error":
            score -= 15
        else:
            score -= 5

    # Incorporate testability dimension (penalty-based to avoid double-counting findings)
    if "testability" not in checks_to_skip:
        score -= (1 - testability_score) * TESTABILITY_MAX_PENALTY

    score = max(0, min(100, score))

    summary_parts = []
    errors = sum(1 for f in findings if f["severity"] == "error")
    warnings = sum(1 for f in findings if f["severity"] == "warning")
    if errors:
        summary_parts.append(f"{errors} error(s)")
    if warnings:
        summary_parts.append(f"{warnings} warning(s)")
    summary = ", ".join(summary_parts) if summary_parts else "No issues found"

    return {
        "path": str(spec_path),
        "score": score,
        "findings": findings,
        "summary": summary,
    }


def check_spec_quality(spec_content: str, profile: dict) -> dict:
    """Run all quality checks on a spec content string and return a structured result.

    Parameters
    ----------
    spec_content:
        Spec markdown content as a string.
    profile:
        Quality profile dict with at least a ``name`` key; skip_checks respected.

    Returns
    -------
    dict with keys: score (float), threshold (int), findings (list[dict])
    """
    findings: list[dict] = []
    checks_to_skip = set(profile.get("skip_checks", []))

    if "vague_criteria" not in checks_to_skip:
        findings.extend(check_vague_criteria(spec_content))

    testability_score = 1.0
    if "testability" not in checks_to_skip:
        testability_score, testability_findings = check_testability(spec_content)
        findings.extend(testability_findings)

    if "edge_case_sufficiency" not in checks_to_skip:
        findings.extend(check_edge_case_sufficiency(spec_content))

    if "input_completeness" not in checks_to_skip:
        findings.extend(check_input_completeness(spec_content))

    if "output_specificity" not in checks_to_skip:
        findings.extend(check_output_specificity(spec_content))

    if "ac_coverage_of_outputs" not in checks_to_skip:
        findings.extend(check_ac_coverage_of_outputs(spec_content))

    if "edge_case_traceability" not in checks_to_skip:
        findings.extend(check_edge_case_traceability(spec_content))

    if "input_output_traceability" not in checks_to_skip:
        findings.extend(check_input_output_traceability(spec_content))

    # Score calculation: same as assess_quality
    score: float = 100
    for f in findings:
        if f["severity"] == "error":
            score -= 15
        else:
            score -= 5

    if "testability" not in checks_to_skip:
        score -= (1 - testability_score) * TESTABILITY_MAX_PENALTY

    score = max(0, min(100, score))

    profile_name = profile.get("name", "full")
    threshold: int = QUALITY_PROFILES.get(profile_name, {}).get("threshold", 75)

    return {"score": score, "threshold": threshold, "findings": findings}


def _format_report(result: dict, profile: dict | None = None) -> str:
    """Format quality report as markdown."""
    lines = []
    lines.append("# Spec Quality Report")
    lines.append("")
    lines.append(f"**File:** `{result['path']}`")
    if profile:
        skips = ", ".join(profile.get("skip_checks", [])) or "none"
        lines.append(
            f"**Profile:** {profile['name']} "
            f"(threshold: {profile['threshold']}, skips: {skips})"
        )
    lines.append(f"**Score:** {result['score']}/100")
    lines.append(f"**Summary:** {result['summary']}")
    lines.append("")

    if result["findings"]:
        lines.append("## Findings")
        lines.append("")
        for f in result["findings"]:
            icon = "X" if f["severity"] == "error" else "!"
            loc = f" (line {f['line']})" if f["line"] else ""
            lines.append(f"- [{icon}] **{f['check']}**{loc}: {f['message']}")
        lines.append("")
    else:
        lines.append("No quality issues found.")
        lines.append("")

    return "\n".join(lines)


def _resolve_spec_path(arg: str) -> Path:
    """Resolve a module number or path to a spec file path."""
    # If it's a path that exists, use it directly
    path = Path(arg)
    if path.exists():
        return path

    # Try to interpret as module number
    try:
        module_num = int(arg)
    except ValueError:
        print(f"Error: '{arg}' is not a valid path or module number", file=sys.stderr)
        sys.exit(2)

    root = get_project_root()
    modules_dir = root / DEFAULT_MODULES_DIR
    pattern = f"{module_num:02d}-*.md"
    matches = list(modules_dir.glob(pattern))
    if not matches:
        print(
            f"Error: No module found matching '{pattern}' in {modules_dir}",
            file=sys.stderr,
        )
        sys.exit(2)
    return matches[0]


# ---------------------------------------------------------------------------
# CLI entry
# ---------------------------------------------------------------------------


def main() -> None:
    """CLI entry point for spec quality assessment."""
    if len(sys.argv) < 2 or sys.argv[1] in ("--help", "-h"):
        print(
            "Usage: python3 -m specbuilder quality <module_num|path> "
            "[--threshold N] [--profile <name>]"
        )
        print("")
        print("Assess the quality of a spec module.")
        print(
            "Exit code 0 if score >= threshold"
            f" (default: {QUALITY_GATE_THRESHOLD}),"
            " exit code 1 otherwise."
        )
        print("")
        print(f"Available profiles: {', '.join(sorted(QUALITY_PROFILES.keys()))}")
        sys.exit(0)

    # Parse flags
    threshold_override: int | None = None
    profile_flag: str | None = None
    output_format = "text"
    args = sys.argv[1:]

    # Parse --threshold flag
    if "--threshold" in args:
        idx = args.index("--threshold")
        if idx + 1 < len(args):
            try:
                threshold_override = int(args[idx + 1])
            except ValueError:
                print(
                    f"Error: --threshold requires an integer, got '{args[idx + 1]}'",
                    file=sys.stderr,
                )
                sys.exit(2)
            args = args[:idx] + args[idx + 2:]
        else:
            print("Error: --threshold requires a value", file=sys.stderr)
            sys.exit(2)

    # Parse --profile flag
    if "--profile" in args:
        idx = args.index("--profile")
        if idx + 1 < len(args):
            profile_flag = args[idx + 1]
            if profile_flag not in QUALITY_PROFILES:
                valid = ", ".join(sorted(QUALITY_PROFILES.keys()))
                print(
                    f"Error: invalid profile '{profile_flag}'. "
                    f"Valid profiles: {valid}",
                    file=sys.stderr,
                )
                sys.exit(2)
            args = args[:idx] + args[idx + 2:]
        else:
            print("Error: --profile requires a value", file=sys.stderr)
            sys.exit(2)

    # Parse --format flag
    if "--format" in args:
        idx = args.index("--format")
        if idx + 1 < len(args):
            fmt = args[idx + 1]
            if fmt not in ("text", "json"):
                print(
                    f"Error: invalid --format '{fmt}'. Valid: text, json",
                    file=sys.stderr,
                )
                sys.exit(2)
            output_format = fmt
            args = args[:idx] + args[idx + 2:]
        else:
            print("Error: --format requires a value", file=sys.stderr)
            sys.exit(2)

    if not args:
        print("Error: no module number or path provided", file=sys.stderr)
        sys.exit(2)

    spec_path = _resolve_spec_path(args[0])

    # Resolve profile: --profile flag > get_active_profile()
    root = get_project_root()
    if profile_flag:
        profile = {"name": profile_flag, **QUALITY_PROFILES[profile_flag]}
    else:
        profile = get_active_profile(root)

    # Resolve threshold: --threshold > profile threshold
    if threshold_override is not None:
        threshold = threshold_override
    else:
        threshold = profile["threshold"]

    # Run assessment with profile's skip_checks
    skip_checks = profile.get("skip_checks", [])
    result = assess_quality(spec_path, skip_checks=skip_checks if skip_checks else None)

    if output_format == "json":
        import json

        from specbuilder.src.diagnostic_schema import wrap_findings
        envelope = wrap_findings("spec-quality", result["findings"])
        output: dict = {**envelope, "score": result["score"]}
        print(json.dumps(output, indent=2))
    else:
        print(_format_report(result, profile=profile))

    sys.exit(0 if result["score"] >= threshold else 1)

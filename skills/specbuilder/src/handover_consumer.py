"""Handover consumption path (EXT-049).

Parses a handover module and triggers a guided intake to scaffold
a customer POC with pre-validated acceptance criteria.
"""

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from specbuilder.src.config import (
    SPECBUILDER_TOML_FILE,
    get_project_root,
)
from specbuilder.src.validation import parse_frontmatter

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class HandoverContext:
    """Parsed content from a handover module."""

    source_demo_id: str = ""
    title: str = ""
    handover_version: int = 1
    validated_acs: list[dict[str, str]] = field(default_factory=list)
    manual_acs: list[dict[str, str]] = field(default_factory=list)
    privilege_manifest: list[dict[str, str]] = field(default_factory=list)
    artifact_manifest: list[dict[str, str]] = field(default_factory=list)
    source_data_refs: list[str] = field(default_factory=list)


@dataclass
class IntakeResponses:
    """Collected responses from the guided intake questionnaire."""

    source_data_exists: bool = False
    source_table_paths: list[str] = field(default_factory=list)
    use_synthetic_data: bool = False
    target_database: str = ""
    target_schema: str = ""
    poc_role: str = ""
    additional_roles: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Handover parsing
# ---------------------------------------------------------------------------


def parse_handover(handover_path: Path) -> HandoverContext | None:
    """Parse a handover module into structured context.

    Returns None if the file is not a valid handover module.
    """
    if not handover_path.exists():
        return None

    fm = parse_frontmatter(handover_path)
    if fm.get("type") != "handover":
        return None

    content = handover_path.read_text(encoding="utf-8")
    ctx = HandoverContext(
        source_demo_id=fm.get("source_demo", ""),
        title=fm.get("title", ""),
        handover_version=int(fm.get("handover_version", 1)),
    )

    # Parse Validated AC table
    ac_section = _extract_section(content, "Validated Acceptance Criteria")
    if ac_section:
        for row in _parse_table_rows(ac_section):
            if len(row) >= 2:
                status = row[1].strip().upper()
                ac_entry = {"ac_id": row[0].strip(), "status": status}
                if len(row) >= 3:
                    ac_entry["assertion"] = row[2].strip()
                if status == "PASS":
                    ctx.validated_acs.append(ac_entry)
                else:
                    ctx.manual_acs.append(ac_entry)

    # Parse Deployment Requirements table
    priv_section = _extract_section(content, "Deployment Requirements")
    if priv_section:
        for row in _parse_table_rows(priv_section):
            if len(row) >= 2:
                ctx.privilege_manifest.append({
                    "privilege": row[0].strip(),
                    "on": row[1].strip(),
                    "notes": row[2].strip() if len(row) >= 3 else "",
                })

    # Parse Artifact Manifest table
    art_section = _extract_section(content, "Artifact Manifest")
    if art_section:
        for row in _parse_table_rows(art_section):
            if len(row) >= 2:
                ctx.artifact_manifest.append({
                    "file": row[0].strip().strip("`"),
                    "tier": row[1].strip() if len(row) >= 2 else "",
                    "status": row[2].strip() if len(row) >= 3 else "",
                })

    return ctx


def _extract_section(content: str, heading: str) -> str:
    """Extract text between a ## heading and the next ## heading."""
    pattern = rf"^##\s+{re.escape(heading)}\b(.*?)(?=\n##\s|\Z)"
    match = re.search(pattern, content, re.DOTALL | re.MULTILINE)
    return match.group(1) if match else ""


def _parse_table_rows(text: str) -> list[list[str]]:
    """Parse markdown table rows (skip header and separator)."""
    rows: list[list[str]] = []
    header_seen = False
    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        if re.match(r"^\|[-\s:|]+\|$", stripped):
            header_seen = True
            continue
        if not header_seen:
            header_seen = True  # first | row is header
            continue
        cells = [c.strip() for c in stripped.split("|")]
        cells = [c for c in cells if c]
        if cells and not all(c == "(none)" or c == "(none discovered)" for c in cells):
            rows.append(cells)
    return rows


# ---------------------------------------------------------------------------
# Security posture engine
# ---------------------------------------------------------------------------

_BLOCKED_ROLES = {"ACCOUNTADMIN", "SECURITYADMIN", "SYSADMIN"}
_PRODUCTION_INDICATORS = {"PROD", "PRODUCTION", "LIVE", "MAIN"}


def check_security_posture(responses: IntakeResponses) -> list[dict[str, str]]:
    """Apply security rules to intake responses.

    Returns list of warnings/blocks with severity and message.
    """
    findings: list[dict[str, str]] = []

    # Rule: Block privileged roles
    if responses.poc_role.upper() in _BLOCKED_ROLES:
        findings.append({
            "severity": "block",
            "message": (
                f"Role '{responses.poc_role}' is too privileged for a POC. "
                "Use a dedicated least-privilege role instead."
            ),
        })

    # Rule: Warn on production schema indicators
    schema_upper = responses.target_schema.upper()
    for indicator in _PRODUCTION_INDICATORS:
        if indicator in schema_upper and "_POC" not in schema_upper:
            findings.append({
                "severity": "warn",
                "message": (
                    f"Target schema '{responses.target_schema}' appears "
                    "to be a production schema. Consider using an isolated "
                    "schema with a _POC prefix."
                ),
            })
            break

    # Rule: Warn if target and source in same schema
    if responses.source_table_paths:
        for table_path in responses.source_table_paths:
            parts = table_path.upper().split(".")
            if len(parts) >= 2:
                source_schema = ".".join(parts[:2])
                target_fqn = f"{responses.target_database}.{responses.target_schema}".upper()
                if source_schema == target_fqn:
                    findings.append({
                        "severity": "warn",
                        "message": (
                            "Source data and target schema are in the same "
                            "location. Recommend schema separation for safety."
                        ),
                    })
                    break

    return findings


# ---------------------------------------------------------------------------
# Guided intake
# ---------------------------------------------------------------------------


def build_intake_prompts(ctx: HandoverContext) -> list[dict[str, Any]]:
    """Build the guided intake questionnaire prompts.

    Returns a list of prompt dicts suitable for display/processing.
    This is the data model — actual interaction is handled by the caller
    (CoCo ask_user_question or CLI stdin).
    """
    prompts: list[dict[str, Any]] = []

    # Step 1: Source data
    source_refs = [
        g["on"] for g in ctx.privilege_manifest
        if "SELECT" in g.get("privilege", "").upper()
    ]
    if source_refs:
        prompts.append({
            "step": 1,
            "question": "Do the source tables exist in your environment?",
            "context": source_refs,
            "options": [
                "Yes, at the same paths",
                "Yes, but at different paths",
                "No — generate synthetic data",
            ],
        })

    # Step 2: Target location
    prompts.append({
        "step": 2,
        "question": "Where should the POC artifacts be created?",
        "recommendation": "An isolated schema with _POC prefix",
        "options": [
            "Accept recommendation",
            "Specify a different database/schema",
        ],
    })

    # Step 3: Role
    prompts.append({
        "step": 3,
        "question": "What role should own the POC?",
        "recommendation": "A dedicated role with minimal privileges",
        "options": [
            "Create new dedicated role",
            "Use existing role",
        ],
    })

    return prompts


# ---------------------------------------------------------------------------
# POC scaffolding from handover
# ---------------------------------------------------------------------------


def scaffold_from_handover(
    handover_path: Path,
    responses: IntakeResponses,
    project_root: Path,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Scaffold a POC project from a handover module + intake responses.

    Creates:
    - POC scaffold structure (via scaffold_poc)
    - Pre-populated spec module with validated ACs
    - .specbuilder.toml with environment configuration
    """
    from specbuilder.src.scaffold import scaffold_poc

    ctx = parse_handover(handover_path)
    if ctx is None:
        return {"error": "Not a valid handover module"}

    # Scaffold base POC
    project_name = ctx.title.replace("Handover: ", "").strip() or "poc-from-handover"
    result = scaffold_poc(
        project_root=project_root,
        project_name=project_name,
        dry_run=dry_run,
    )

    if result.get("message"):
        return result

    project_root = project_root.resolve()

    # Write environment config to .specbuilder.toml
    toml_path = project_root / SPECBUILDER_TOML_FILE
    toml_content = (
        "# SpecBuilder project configuration (from handover)\n"
        "\n"
        "[project]\n"
        f'name = "{project_name}"\n'
        'mode = "poc"\n'
        f'from_handover = "{handover_path.name}"\n'
        "\n"
        "[quality]\n"
        'profile = "poc"\n'
        "\n"
        "[environment]\n"
        f'target_database = "{responses.target_database}"\n'
        f'target_schema = "{responses.target_schema}"\n'
        f'poc_role = "{responses.poc_role}"\n'
        f'synthetic_data = {"true" if responses.use_synthetic_data else "false"}\n'
    )
    if responses.source_table_paths:
        tables_str = ", ".join(f'"{t}"' for t in responses.source_table_paths)
        toml_content += f"source_tables = [{tables_str}]\n"

    if not dry_run:
        toml_path.write_text(toml_content, encoding="utf-8")
    result["created"].append(f"{SPECBUILDER_TOML_FILE} (from handover)")

    # Generate pre-populated spec module with validated ACs
    modules_dir = project_root / "spec" / "modules"
    spec_content = _generate_spec_from_handover(ctx, responses)
    spec_path = modules_dir / "01-poc-module.md"
    if not dry_run:
        modules_dir.mkdir(parents=True, exist_ok=True)
        spec_path.write_text(spec_content, encoding="utf-8")
    result["created"].append("spec/modules/01-poc-module.md")

    return result


def _generate_spec_from_handover(
    ctx: HandoverContext, responses: IntakeResponses
) -> str:
    """Generate a spec module from handover context."""
    from datetime import date

    ac_lines = []
    for ac in ctx.validated_acs:
        ac_lines.append(f"- [ ] {ac.get('ac_id', '?')}: (validated_in_demo: true)")
    for ac in ctx.manual_acs:
        ac_lines.append(
            f"- [ ] {ac.get('ac_id', '?')}: (requires manual verification)"
        )

    return f"""---
id: MOD-01
title: "{ctx.title.replace('Handover: ', '')}"
status: draft
version: "0.1.0"
last_updated: "{date.today().isoformat()}"
from_handover: "{ctx.source_demo_id}"
---

## Executive Summary

POC scaffolded from demo handover ({ctx.source_demo_id}).
Acceptance criteria pre-validated during demo deployment.

## Inputs

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| target_schema | str | yes | {responses.target_database}.{responses.target_schema} |
| poc_role | str | yes | {responses.poc_role} |

## Output

Reproduces the demo artifacts in the customer environment.

## Acceptance Criteria

### AC-1: Pre-Validated (from demo)

{chr(10).join(ac_lines) if ac_lines else "- [ ] (no ACs from handover)"}

## Edge Cases

| Scenario | Expected Behavior |
|----------|-------------------|
| Source data unavailable | Graceful error with instructions |
| Insufficient privileges | Report required grants |
"""


# ---------------------------------------------------------------------------
# Handover detection
# ---------------------------------------------------------------------------


def detect_handover_files(directory: Path) -> list[Path]:
    """Find handover modules in a directory."""
    handovers: list[Path] = []
    for md_file in directory.glob("**/*.md"):
        try:
            fm = parse_frontmatter(md_file)
            if fm.get("type") == "handover":
                handovers.append(md_file)
        except Exception:
            continue
    return handovers


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="specbuilder scaffold --from-handover",
        description="Scaffold a POC from a demo handover module.",
    )
    parser.add_argument(
        "handover_path",
        help="Path to the handover module (.md file with type: handover).",
    )
    parser.add_argument(
        "--database", default="",
        help="Target database for the POC.",
    )
    parser.add_argument(
        "--schema", default="",
        help="Target schema for the POC.",
    )
    parser.add_argument(
        "--role", default="",
        help="POC role name.",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would be created without writing files.",
    )

    args = parser.parse_args(argv)

    handover_path = Path(args.handover_path)
    if not handover_path.exists():
        print(f"Error: Handover file not found: {handover_path}", file=sys.stderr)
        sys.exit(2)

    # Parse handover
    ctx = parse_handover(handover_path)
    if ctx is None:
        print(
            "Error: File is not a valid handover module "
            "(missing 'type: handover' in frontmatter).",
            file=sys.stderr,
        )
        sys.exit(2)

    print(f"Handover detected: {ctx.title}")
    print(f"  Source demo: {ctx.source_demo_id}")
    print(f"  Validated ACs: {len(ctx.validated_acs)}")
    print(f"  Manual ACs: {len(ctx.manual_acs)}")
    print()

    # Build responses (from CLI args or defaults)
    responses = IntakeResponses(
        target_database=args.database or "POC_DB",
        target_schema=args.schema or f"_POC_{ctx.source_demo_id.replace('-', '_')}",
        poc_role=args.role or f"POC_{ctx.source_demo_id.replace('-', '_')}_ROLE",
        source_data_exists=False,
        use_synthetic_data=True,
    )

    # Security check
    findings = check_security_posture(responses)
    for f in findings:
        severity = f["severity"].upper()
        print(f"  [{severity}] {f['message']}")
        if f["severity"] == "block":
            print("Error: Security check failed. Fix the issues above.")
            sys.exit(1)

    # Scaffold
    project_root = get_project_root()
    result = scaffold_from_handover(
        handover_path, responses, project_root, dry_run=args.dry_run
    )

    if "error" in result:
        print(f"Error: {result['error']}", file=sys.stderr)
        sys.exit(1)

    print("POC scaffolded from handover:")
    for item in result.get("created", []):
        print(f"  + {item}")


if __name__ == "__main__":
    main()

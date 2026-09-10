"""Handover consumption path (EXT-049, EXT-071).

Parses a handover module and triggers a guided intake to scaffold
a customer POC with pre-validated acceptance criteria.

EXT-071: Adds `env_placeholders` parsing from `## Environment Placeholders`
and dynamic substitution throughout all content when placeholders are present.
Backward compatible: old handovers without the section use fixed prompts.
"""

import argparse
import logging
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from specbuilder.src.config import (
    HANDOVER_SPEC_FIELDS,
    QUALITY_PROFILES,
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
    # EXT-071: dynamic per-placeholder intake (absent in old handovers)
    env_placeholders: list[dict[str, str]] = field(default_factory=list)


@dataclass
class IntakeResponses:
    """Collected responses from the guided intake questionnaire."""

    source_data_exists: bool = False
    source_table_paths: list[str] = field(default_factory=list)
    use_synthetic_data: bool = False
    target_database: str = ""
    target_schema: str = ""
    poc_role: str = ""


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

    # Parse Environment Placeholders (EXT-071 — new section)
    env_section = _extract_section(content, "Environment Placeholders")
    if env_section:
        for row in _parse_table_rows(env_section):
            if len(row) >= 2:
                ctx.env_placeholders.append({
                    "placeholder": row[0].strip(),
                    "description": row[1].strip() if len(row) > 1 else "",
                    "example": row[2].strip() if len(row) > 2 else "",
                })

    # Parse Validated AC table
    ac_section = _extract_section(content, "Validated Acceptance Criteria")
    if ac_section:
        for row in _parse_table_rows(ac_section):
            if len(row) >= 2:
                # New format: AC | Assertion SQL | Status
                # Old format: AC | Status | Assertion
                # Detect by checking if second column looks like SQL or a status word
                if len(row) >= 3:
                    second = row[1].strip().strip("`")
                    third = row[2].strip().upper()
                    # New format: col2 is SQL, col3 is STATUS
                    if third in ("PASS", "FAIL", "MANUAL", "UNKNOWN"):
                        ac_entry = {
                            "ac_id": row[0].strip(),
                            "status": third,
                            "assertion": second,
                        }
                    else:
                        # Old format: col2 is STATUS, col3 is assertion
                        status = second.upper()
                        ac_entry = {
                            "ac_id": row[0].strip(),
                            "status": status,
                            "assertion": row[2].strip(),
                        }
                else:
                    status = row[1].strip().upper()
                    ac_entry = {"ac_id": row[0].strip(), "status": status}

                if ac_entry["status"] == "PASS":
                    ctx.validated_acs.append(ac_entry)
                else:
                    ctx.manual_acs.append(ac_entry)

    # Parse privilege/grants section — try new name first, fall back to old name
    priv_section = _extract_section(content, "Required Grants") or _extract_section(
        content, "Deployment Requirements"
    )
    if priv_section:
        for row in _parse_table_rows(priv_section):
            if len(row) >= 2:
                ctx.privilege_manifest.append({
                    "privilege": row[0].strip(),
                    "on": row[1].strip(),
                    "notes": row[2].strip() if len(row) >= 3 else "",
                    "grantee": row[3].strip() if len(row) > 3 else "",
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


def check_security_posture(
    responses: IntakeResponses,
    privilege_manifest: list[dict[str, str]] | None = None,
) -> list[dict[str, str]]:
    """Apply security rules to intake responses.

    Returns list of warnings/blocks with severity and message.
    """
    findings: list[dict[str, str]] = []

    # Rule: Block privileged roles
    poc_upper = responses.poc_role.upper()
    if poc_upper in _BLOCKED_ROLES or any(b in poc_upper for b in _BLOCKED_ROLES):
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

    # Rule: Warn on over-privileged grants in the handover manifest
    if privilege_manifest:
        for grant in privilege_manifest:
            grantee = grant.get("grantee", "").upper()
            if not grantee:
                findings.append({
                    "severity": "warn",
                    "message": (
                        f"Grant row has empty grantee: {grant.get('privilege')} "
                        f"on {grant.get('on', '?')}"
                    ),
                })
                continue
            if grantee in _BLOCKED_ROLES or any(b in grantee for b in _BLOCKED_ROLES):
                findings.append({
                    "severity": "warn",
                    "message": (
                        f"Handover manifest requires privilege '{grant.get('privilege')}' "
                        f"on '{grant.get('on', '?')}'. "
                        "This privilege is too elevated for a POC environment."
                    ),
                })

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
# Placeholder substitution (EXT-071)
# ---------------------------------------------------------------------------


def _substitute_placeholders(content: str, substitutions: dict[str, str]) -> str:
    """Replace {{PLACEHOLDER}} tokens with their resolved values.

    substitutions maps placeholder token (e.g. "{{TARGET_DATABASE}}") to
    the actual customer value.
    """
    for token, value in substitutions.items():
        content = content.replace(token, value)
    return content


def _collect_placeholder_values_cli(
    env_placeholders: list[dict[str, str]],
) -> dict[str, str]:
    """Prompt user via stdin for each placeholder and return a substitution map.

    Falls back to example values when stdin is not interactive.
    """
    substitutions: dict[str, str] = {}
    is_interactive = sys.stdin.isatty()

    for ph in env_placeholders:
        token = ph.get("placeholder", "")
        description = ph.get("description", token)
        example = ph.get("example", "")

        if not token:
            continue

        if is_interactive:
            prompt = f"  {description}"
            if example:
                prompt += f" (example: {example})"
            prompt += ": "
            value = _safe_input(prompt)
            substitutions[token] = value if value else example
        else:
            # Non-interactive: use example value as default
            sys.stderr.write(
                f"Warning: non-interactive mode — using example value for '{token}': '{example}'\n"
            )
            substitutions[token] = example

    return substitutions


# ---------------------------------------------------------------------------
# POC scaffolding from handover
# ---------------------------------------------------------------------------


def scaffold_from_handover(
    handover_path: Path,
    responses: IntakeResponses,
    project_root: Path,
    dry_run: bool = False,
    quality_profile: str = "poc",
    substitutions: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Scaffold a POC project from a handover module + intake responses.

    EXT-071: When the handover contains `## Environment Placeholders`,
    prompts for each value and substitutes throughout all generated content.
    Falls back to fixed target_database/target_schema/poc_role prompts when
    the section is absent (backward compatible with pre-EXT-071 handovers).

    Creates:
    - POC scaffold structure (via scaffold_poc)
    - Pre-populated spec module with validated ACs
    - .specbuilder.toml with environment configuration
    """
    from specbuilder.src.scaffold import scaffold_poc

    ctx = parse_handover(handover_path)
    if ctx is None:
        return {"error": "Not a valid handover module"}

    # Build placeholder substitution map from env_placeholders (EXT-071 path)
    if substitutions is None:
        substitutions = {}
        if ctx.env_placeholders:
            substitutions = _collect_placeholder_values_cli(ctx.env_placeholders)

            # Derive target_database / target_schema / poc_role from substitutions
            # for backward-compatible downstream use
            db_token = next(
                (ph["placeholder"] for ph in ctx.env_placeholders
                 if "DATABASE" in ph.get("placeholder", "").upper()),
                None,
            )
            schema_token = next(
                (ph["placeholder"] for ph in ctx.env_placeholders
                 if "SCHEMA" in ph.get("placeholder", "").upper()),
                None,
            )
            role_token = next(
                (ph["placeholder"] for ph in ctx.env_placeholders
                 if "ROLE" in ph.get("placeholder", "").upper()),
                None,
            )
            if db_token and substitutions.get(db_token):
                responses.target_database = substitutions[db_token]
            if schema_token and substitutions.get(schema_token):
                responses.target_schema = substitutions[schema_token]
            if role_token and substitutions.get(role_token):
                responses.poc_role = substitutions[role_token]

    # Scaffold base POC
    project_name = ctx.title.replace("Handover: ", "").strip() or "poc-from-handover"

    project_root = project_root.resolve()

    # Write environment config to .specbuilder.toml
    toml_path = project_root / SPECBUILDER_TOML_FILE
    toml_content = (
        "# SpecBuilder project configuration (from handover)\n"
        "\n"
        "[project]\n"
        f'name = "{project_name}"\n'
        f'mode = "{quality_profile}"\n'
        f'from_handover = "{handover_path.name}"\n'
        "\n"
        "[quality]\n"
        f'profile = "{quality_profile}"\n'
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

    # Apply substitutions to toml content
    if substitutions:
        toml_content = _substitute_placeholders(toml_content, substitutions)

    # Generate pre-populated spec module with validated ACs
    modules_dir = project_root / "spec" / "modules"
    spec_content = _generate_spec_from_handover(ctx, responses)

    # Validate HANDOVER_SPEC_FIELDS are present in generated spec frontmatter
    fm_match = re.match(r"^---\n(.*?)\n---", spec_content, re.DOTALL)
    if fm_match:
        fm_keys = {
            line.split(":")[0].strip()
            for line in fm_match.group(1).splitlines()
            if ":" in line
        }
        missing_handover_fields = HANDOVER_SPEC_FIELDS - fm_keys
        if missing_handover_fields:
            return {
                "error": (
                    "Generated spec missing required handover fields: "
                    f"{sorted(missing_handover_fields)}"
                )
            }

    # Apply substitutions to spec content
    if substitutions:
        spec_content = _substitute_placeholders(spec_content, substitutions)

    # Warn on any unresolved {{PLACEHOLDER}} tokens remaining after substitution
    unresolved = list(dict.fromkeys(re.findall(r"\{\{[A-Z_]+\}\}", toml_content + spec_content)))
    if unresolved:
        sys.stderr.write(f"Warning: unresolved placeholder(s): {unresolved}\n")

    spec_path = modules_dir / "01-poc-module.md"
    spec_collision = spec_path.exists()
    created_paths: list[Path] = []
    try:
        try:
            result = scaffold_poc(
                project_root=project_root,
                project_name=project_name,
                dry_run=dry_run,
            )
        except OSError:
            raise
        except Exception as e:
            return {"error": str(e)}
        created_paths.extend(result.pop("created_paths", []))
        if "error" in result:
            return result
        if "message" in result:
            return {"error": f"Project already exists: {result['message']}"}

        if not dry_run:
            toml_path.write_text(toml_content, encoding="utf-8")
            created_paths.append(toml_path)
        result["created"].append(f"{SPECBUILDER_TOML_FILE} (from handover)")

        if not dry_run:
            modules_dir.mkdir(parents=True, exist_ok=True)
            spec_path.write_text(spec_content, encoding="utf-8")
            created_paths.append(spec_path)
        spec_label = "spec/modules/01-poc-module.md"
        if spec_collision:
            spec_label += " (overwritten)"
        result["created"].append(spec_label)

    except OSError as exc:
        for p in reversed(created_paths):
            try:
                p.unlink(missing_ok=True)
            except OSError:
                pass
        return {"error": f"Scaffold write failed: {exc}"}

    return result


def _build_output_section(ctx: HandoverContext) -> str:
    """Build the ## Output body from artifact_manifest."""
    if not ctx.artifact_manifest:
        return "See handover artifact manifest."
    lines = "\n".join(f"- `{a['file']}`" for a in ctx.artifact_manifest)
    return lines


def _generate_spec_from_handover(
    ctx: HandoverContext, responses: IntakeResponses
) -> str:
    """Generate a spec module from handover context."""
    from datetime import date

    # Build AC table rows using canonical 4-column format
    ac_table_rows = []
    for i, ac in enumerate(ctx.validated_acs, 1):
        ac_table_rows.append(
            f"| {i} | {ac.get('ac_id', '?')}: validated in demo"
            f" | \u2610 | validated_in_demo: true |"
        )
    offset = len(ctx.validated_acs)
    for i, ac in enumerate(ctx.manual_acs, 1):
        ac_table_rows.append(
            f"| {offset + i} | {ac.get('ac_id', '?')}: requires manual verification | \u2610 | |"
        )

    if ac_table_rows:
        ac_table = (
            "| # | Criterion | Pass | Notes |\n"
            "|---|-----------|------|-------|\n"
            + "\n".join(ac_table_rows)
        )
    else:
        ac_table = (
            "| # | Criterion | Pass | Notes |\n"
            "|---|-----------|------|-------|\n"
            "| 1 | (no ACs from handover) | \u2610 | |"
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

{_build_output_section(ctx)}

## Acceptance Criteria

### AC-1: Pre-Validated (from demo)

{ac_table}

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
        except Exception as exc:
            logging.warning("Could not parse %s: %s", md_file, exc)
            continue
    return handovers


# ---------------------------------------------------------------------------
# CLI helpers
# ---------------------------------------------------------------------------


def _safe_input(prompt: str, default: str = "") -> str:
    """Wrapper around input() that handles EOFError cleanly."""
    try:
        return input(prompt).strip()
    except EOFError:
        return default


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="specbuilder handover-consumer",
        description="Scaffold a POC from a demo handover module.",
    )
    parser.add_argument(
        "handover_path",
        help="Path to the handover module (.md file with type: handover).",
    )
    parser.add_argument(
        "--database", default="POC_DB",
        help="Target database for the POC. Default: POC_DB.",
    )
    parser.add_argument(
        "--schema", default="",
        help="Target schema for the POC. Default: _POC_<demo_id>.",
    )
    parser.add_argument(
        "--role", default="",
        help="POC role name. Default: POC_<demo_id>_ROLE.",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would be created without writing files.",
    )
    parser.add_argument(
        "--quality-profile",
        default="poc",
        dest="quality_profile",
        help="Quality profile written to the scaffolded .specbuilder.toml (default: poc).",
    )

    args = parser.parse_args(argv)

    if args.quality_profile not in QUALITY_PROFILES:
        print(
            f"ERROR: invalid quality profile '{args.quality_profile}'. "
            f"Valid profiles: {', '.join(sorted(QUALITY_PROFILES.keys()))}",
            file=sys.stderr,
        )
        sys.exit(2)

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
    if ctx.env_placeholders:
        print(f"  Environment placeholders: {len(ctx.env_placeholders)}")
        print("\nProvide your environment values:")
    print()

    # Build responses via questionnaire or CLI args / defaults
    prompts = build_intake_prompts(ctx)

    if sys.stdin.isatty():
        # Interactive mode: present prompts and collect answers
        collected: dict[str, Any] = {
            "source_data_exists": False,
            "use_synthetic_data": True,
            "target_database": args.database or "POC_DB",
            "target_schema": args.schema or f"_POC_{ctx.source_demo_id.replace('-', '_')}",
            "poc_role": args.role or f"POC_{ctx.source_demo_id.replace('-', '_')}_ROLE",
        }
        for prompt_item in prompts:
            step = prompt_item.get("step", 0)
            question = prompt_item.get("question", "")
            options = prompt_item.get("options", [])
            recommendation = prompt_item.get("recommendation", "")
            context = prompt_item.get("context", [])

            print(f"\nStep {step}: {question}")
            if context:
                print("  Referenced tables: " + ", ".join(str(r) for r in context))
            if recommendation:
                print(f"  Recommendation: {recommendation}")
            for i, opt in enumerate(options, 1):
                print(f"  {i}. {opt}")

            choice_str = _safe_input("Choose [1]: ")
            try:
                choice = int(choice_str) if choice_str else 1
            except ValueError:
                choice = 1

            if step == 1:
                # Source data step
                if choice == 3:
                    collected["source_data_exists"] = False
                    collected["use_synthetic_data"] = True
                    collected["source_table_paths"] = []
                elif choice == 1:
                    # Option 1: same paths — auto-populate from manifest context
                    collected["source_data_exists"] = True
                    collected["use_synthetic_data"] = False
                    # context = source_refs from manifest
                    collected["source_table_paths"] = list(context)
                else:
                    # Option 2: different paths — collect from user
                    collected["source_data_exists"] = True
                    collected["use_synthetic_data"] = False
                    raw = _safe_input(
                        "  Enter source table paths (comma-separated DB.SCHEMA.TABLE): "
                    )
                    collected["source_table_paths"] = [
                        p.strip() for p in raw.split(",") if p.strip()
                    ]
            elif step == 2:
                # Target location step: option 2 = custom database/schema
                if choice == 2:
                    db = _safe_input(f"  Target database [{collected['target_database']}]: ")
                    if db:
                        collected["target_database"] = db
                    schema = _safe_input(f"  Target schema [{collected['target_schema']}]: ")
                    if schema:
                        collected["target_schema"] = schema
            elif step == 3:
                # Role step: option 2 = use existing role
                if choice == 2:
                    role = _safe_input(f"  Role name [{collected['poc_role']}]: ")
                    if role:
                        collected["poc_role"] = role

        responses = IntakeResponses(
            target_database=collected["target_database"],
            target_schema=collected["target_schema"],
            poc_role=collected["poc_role"],
            source_data_exists=bool(collected["source_data_exists"]),
            use_synthetic_data=bool(collected["use_synthetic_data"]),
            source_table_paths=collected.get("source_table_paths", []),
        )
    else:
        # Non-interactive mode: fall back to CLI args / defaults
        has_real_data = bool(args.database and args.schema)
        responses = IntakeResponses(
            target_database=args.database or "POC_DB",
            target_schema=args.schema or f"_POC_{ctx.source_demo_id.replace('-', '_')}",
            poc_role=args.role or f"POC_{ctx.source_demo_id.replace('-', '_')}_ROLE",
            source_data_exists=has_real_data,
            use_synthetic_data=not has_real_data,
        )

    # Collect placeholder values before showing confirmation summary (Fix 4)
    substitutions: dict[str, str] = {}
    if ctx.env_placeholders:
        substitutions = _collect_placeholder_values_cli(ctx.env_placeholders)
        # Backfill responses from substitutions so confirmation summary is accurate
        db_token = next(
            (ph["placeholder"] for ph in ctx.env_placeholders
             if "DATABASE" in ph.get("placeholder", "").upper()), None,
        )
        schema_token = next(
            (ph["placeholder"] for ph in ctx.env_placeholders
             if "SCHEMA" in ph.get("placeholder", "").upper()), None,
        )
        role_token = next(
            (ph["placeholder"] for ph in ctx.env_placeholders
             if "ROLE" in ph.get("placeholder", "").upper()), None,
        )
        if db_token and substitutions.get(db_token):
            responses.target_database = substitutions[db_token]
        if schema_token and substitutions.get(schema_token):
            responses.target_schema = substitutions[schema_token]
        if role_token and substitutions.get(role_token):
            responses.poc_role = substitutions[role_token]

    # Security check
    findings = check_security_posture(responses, privilege_manifest=ctx.privilege_manifest)
    has_block = False
    for f in findings:
        severity = f["severity"].upper()
        print(f"  [{severity}] {f['message']}")
        if f["severity"] == "block":
            has_block = True
    if has_block:
        print("Error: Security check failed. Fix the issues above.")
        sys.exit(1)

    # Confirmation gate (interactive mode only)
    project_root = get_project_root()
    spec_path = project_root / "spec" / "modules" / "01-poc-module.md"
    spec_will_overwrite = spec_path.exists()
    if sys.stdin.isatty():
        print("\nConfiguration summary:")
        print(f"  Database : {responses.target_database}")
        print(f"  Schema   : {responses.target_schema}")
        print(f"  Role     : {responses.poc_role}")
        print(f"  Source data exists: {responses.source_data_exists}")
        if spec_will_overwrite:
            print(
                f"  WARNING: {spec_path} already exists and will be overwritten."
            )
        confirm = _safe_input("\nProceed with scaffolding? [y/N]: ").lower()
        if confirm not in ("y", "yes"):
            print("Aborted.")
            sys.exit(0)
    else:
        if spec_will_overwrite:
            print(
                "WARNING: overwriting existing spec module in non-interactive mode.",
                file=sys.stderr,
            )

    # Scaffold
    result = scaffold_from_handover(
        handover_path, responses, project_root,
        dry_run=args.dry_run,
        quality_profile=args.quality_profile,
        substitutions=substitutions,
    )

    if "error" in result:
        print(f"Error: {result['error']}", file=sys.stderr)
        sys.exit(1)

    print("POC scaffolded from handover:")
    for item in result.get("created", []):
        print(f"  + {item}")

    print(
        "\nNext step: run 'python3 -m specbuilder generate-manifest'"
        " to update the project index."
    )


if __name__ == "__main__":
    main()

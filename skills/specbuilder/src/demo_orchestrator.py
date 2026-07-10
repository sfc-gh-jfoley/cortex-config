"""Demo orchestrator for EXT-071.

Implements the sanitized handover workflow:
  implement-spec → demo-handover (validate + grant-test + sanitize + write)

`demo-run` is a convenience wrapper: implement → demo-handover.
`demo-handover` is a four-phase orchestrator that can skip completed phases.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from specbuilder.src.config import (
    DEFAULT_IMPL_DIR,
    DEFAULT_SPECBUILDER_META_DIR,
    get_project_root,
)

# ---------------------------------------------------------------------------
# State management for resumability
# ---------------------------------------------------------------------------

_STATE_FILE = "demo-state.json"


def _read_state(meta_dir: Path) -> dict[str, Any]:
    """Read demo-run state file for resumability."""
    state_path = meta_dir / _STATE_FILE
    if state_path.exists():
        result: dict[str, Any] = json.loads(state_path.read_text(encoding="utf-8"))
        return result
    return {"phase": "init", "module_num": None, "timestamp": None}


def _write_state(meta_dir: Path, state: dict[str, Any]) -> None:
    """Write demo-run state file."""
    meta_dir.mkdir(parents=True, exist_ok=True)
    state_path = meta_dir / _STATE_FILE
    state_path.write_text(json.dumps(state, indent=2, default=str), encoding="utf-8")


# ---------------------------------------------------------------------------
# Sanitization helpers
# ---------------------------------------------------------------------------


def _build_value_map(project_root: Path) -> dict[str, str]:
    """Build a {actual_value: "{{PLACEHOLDER}}"} map from spec/metadata.yaml.

    Falls back to .specbuilder.toml [demo].database when metadata.yaml is absent.
    Entries are sorted longest-first so partial substitutions are avoided.
    """
    metadata_path = project_root / "spec" / "metadata.yaml"
    value_map: dict[str, str] = {}

    if metadata_path.exists():
        try:
            data: dict[str, Any] = yaml.safe_load(
                metadata_path.read_text(encoding="utf-8")
            ) or {}
            for key, value in data.items():
                if value and isinstance(value, str):
                    placeholder = "{{" + key.upper() + "}}"
                    value_map[value] = placeholder
        except Exception as e:
            print(
                f"Warning: could not parse spec/metadata.yaml: {e}",
                file=sys.stderr,
            )
    else:
        # Minimal fallback: read [demo] section from .specbuilder.toml
        try:
            try:
                import tomllib  # Python 3.11+
            except ImportError:
                import tomli as tomllib  # type: ignore[no-redef]

            toml_path = project_root / ".specbuilder.toml"
            if toml_path.exists():
                config = tomllib.loads(toml_path.read_text(encoding="utf-8"))
                demo_cfg = config.get("demo", {})
                if demo_cfg.get("database"):
                    value_map[demo_cfg["database"]] = "{{TARGET_DATABASE}}"
                if demo_cfg.get("warehouse"):
                    value_map[demo_cfg["warehouse"]] = "{{WAREHOUSE}}"
        except Exception:
            pass

    # Sort longest-first to avoid partial substitutions
    return dict(sorted(value_map.items(), key=lambda kv: len(kv[0]), reverse=True))


def sanitize(content: str, value_map: dict[str, str]) -> str:
    """Replace all provider-specific values with {{PLACEHOLDER}} tokens.

    Replacement is longest-match-first (guaranteed by value_map ordering).
    """
    for actual_value, placeholder in value_map.items():
        if actual_value:
            content = content.replace(actual_value, placeholder)
    return content


# ---------------------------------------------------------------------------
# Handover generation helpers
# ---------------------------------------------------------------------------


def _find_grants_module(project_root: Path) -> Path | None:
    """Return the grants module path if one exists, else None."""
    modules_dir = project_root / "spec" / "modules"
    if not modules_dir.exists():
        return None
    matches = sorted(modules_dir.glob("[0-9][0-9]-grants-*.md"))
    return matches[0] if matches else None


def _load_validation_report(meta_dir: Path) -> dict[str, Any] | None:
    """Load validation-report.json if present, else return None."""
    report_path = meta_dir / "validation-report.json"
    if not report_path.exists():
        return None
    return json.loads(report_path.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def _is_degraded_report(report: dict[str, Any]) -> bool:
    """Return True if the report is a degraded compile check standing in for verify."""
    return (
        report.get("tier") != "verify"
        and report.get("degraded_from") == "verify"
    )


# ---------------------------------------------------------------------------
# Four-phase demo_handover() orchestrator
# ---------------------------------------------------------------------------


def demo_handover(
    module_num: str,
    project_root: Path,
    force_validate: bool = False,
    force_grant_test: bool = False,
    tester_role: str = "SPECBUILDER_TESTER_ROLE",
    sql_execute_fn: Any = None,
) -> int:
    """Generate a sanitized, executable handover.md.

    Four phases (each skippable if outputs already exist):
      Phase 1: validate-artifacts --tier verify
      Phase 2: grant-test loop
      Phase 3: build value_map from spec/metadata.yaml
      Phase 4: sanitize all content and write handover.md

    Returns 0 on success, 1 on failure.
    """
    meta_dir = project_root / DEFAULT_SPECBUILDER_META_DIR
    impl_dir = project_root / DEFAULT_IMPL_DIR
    modules_dir = project_root / "spec" / "modules"

    # -------------------------------------------------------------------------
    # Phase 1: Validation
    # -------------------------------------------------------------------------
    validation_report = _load_validation_report(meta_dir)

    if force_validate or validation_report is None or _is_degraded_report(validation_report):
        if validation_report is not None and _is_degraded_report(validation_report):
            print(
                "Warning: existing validation-report.json is a degraded compile check\n"
                f"(degraded_from: verify — no database was provided when validate-artifacts ran).\n"
                "Re-running Tier 4. To avoid this, run:\n"
                f"  python3 -m specbuilder validate-artifacts {module_num}"
                " --tier verify --database <db>",
                file=sys.stderr,
            )
        elif force_validate:
            print("Phase 1/4: Re-running validation (--force-validate)...")
        else:
            print("Phase 1/4: Running Tier 1 compile check (no existing report)...")

        # Run Tier 1 compile as the offline fallback; Tier 4 requires sql_execute_fn
        from specbuilder.src.validate_artifacts import run_tier1

        results = run_tier1(impl_dir)
        failures = [r for r in results if r["status"] == "fail"]
        validation_report = {
            "tier": "compile",
            "timestamp": datetime.now().isoformat(),
            "artifact_results": results,
            "ac_results": [],
            "privilege_manifest": [],
            "teardown_path": None,
            "status": "fail" if failures else "pass",
            "summary": f"Artifacts: {len(results) - len(failures)} pass, {len(failures)} fail",
        }
        meta_dir.mkdir(parents=True, exist_ok=True)
        (meta_dir / "validation-report.json").write_text(
            json.dumps(validation_report, indent=2, default=str), encoding="utf-8"
        )
        if failures:
            print(f"  {len(failures)} artifact(s) failed validation.")
            for r in failures:
                print(f"    ✗ {r['path']}: {r.get('error', 'unknown')}")
        else:
            print(f"  All {len(results)} artifact(s) passed.")
    else:
        print(
            f"Phase 1/4: Validation skipped (existing report tier={validation_report.get('tier')})."
        )

    # -------------------------------------------------------------------------
    # Phase 2: Grant-test
    # -------------------------------------------------------------------------
    grants_module = _find_grants_module(project_root)

    if force_grant_test or grants_module is None:
        if force_grant_test:
            print("Phase 2/4: Re-running grant-test (--force-grant-test)...")
        else:
            print("Phase 2/4: Running grant-test...")
        from specbuilder.src.grant_validator import run_grant_test

        database = ""
        try:
            try:
                import tomllib  # Python 3.11+
            except ImportError:
                import tomli as tomllib  # type: ignore[no-redef]
            toml_path = project_root / ".specbuilder.toml"
            if toml_path.exists():
                cfg = tomllib.loads(toml_path.read_text(encoding="utf-8"))
                database = cfg.get("demo", {}).get("database", "")
        except Exception:
            pass

        grants_module = run_grant_test(
            module_num=module_num,
            project_root=project_root,
            tester_role=tester_role,
            sql_execute_fn=sql_execute_fn,
            database=database,
        )
        if grants_module is None:
            print(
                "Phase 2/4: grant-test skipped (no live Snowflake connection). "
                "Falling back to privilege-manifest.json if available."
            )
    else:
        print(f"Phase 2/4: Grant-test skipped (grants module exists: {grants_module.name}).")

    # -------------------------------------------------------------------------
    # Phase 3: Build value_map
    # -------------------------------------------------------------------------
    print("Phase 3/4: Building sanitization value_map from spec/metadata.yaml...")
    value_map = _build_value_map(project_root)
    if value_map:
        print(f"  {len(value_map)} placeholder(s) defined.")
    else:
        print(
            "  No spec/metadata.yaml found — handover will not be sanitized. "
            "Create spec/metadata.yaml with your environment values to enable sanitization."
        )

    # -------------------------------------------------------------------------
    # Phase 4: Sanitize + write handover.md
    # -------------------------------------------------------------------------
    print("Phase 4/4: Sanitizing content and writing handover.md...")

    # Determine source module info
    spec_files = list(modules_dir.glob(f"{module_num.zfill(2)}-*.md"))
    source_title = "Demo Module"
    source_id = f"MOD-{module_num.zfill(2)}"
    if spec_files:
        source_title = spec_files[0].stem.split("-", 1)[-1].replace("-", " ").title()

    # Determine next module number for handover file
    existing_modules = sorted(modules_dir.glob("[0-9][0-9]-*.md"))
    next_num = 1
    if existing_modules:
        last_name = existing_modules[-1].name
        match = re.match(r"(\d+)-", last_name)
        if match:
            next_num = int(match.group(1)) + 1
    handover_num = f"{next_num:02d}"

    grants_module_id = ""
    if grants_module:
        m = re.match(r"(\d+)-", grants_module.name)
        if m:
            grants_module_id = f"MOD-{m.group(1).zfill(2)}"

    # Build ## Environment Placeholders table from value_map
    placeholder_rows = []
    for actual_value, placeholder in value_map.items():
        key = placeholder.strip("{}").title().replace("_", " ")
        placeholder_rows.append(
            f"| {placeholder} | {key} | [redacted] |"
        )
    placeholder_table = (
        "\n".join(placeholder_rows)
        if placeholder_rows
        else "| (none — create spec/metadata.yaml) | | |"
    )

    # Build ## Required Grants table
    priv_manifest: list[dict[str, str]] = []
    # Load from grants module content if available
    if grants_module and grants_module.exists():
        grants_content = grants_module.read_text(encoding="utf-8")
        gm = re.search(
            r"^##\s+Grant Manifest\b(.*?)(?=\n##\s|\Z)",
            grants_content,
            re.DOTALL | re.MULTILINE,
        )
        if gm:
            header_seen = False
            for line in gm.group(1).split("\n"):
                stripped = line.strip()
                if not stripped.startswith("|"):
                    continue
                if re.match(r"^\|[-\s:|]+\|$", stripped):
                    header_seen = True
                    continue
                if not header_seen:
                    header_seen = True
                    continue
                cells = [c.strip() for c in stripped.split("|")]
                cells = [c for c in cells if c]
                if cells and not all(c.startswith("(none") for c in cells):
                    priv_manifest.append({
                        "privilege": cells[0] if cells else "",
                        "object_type": cells[1] if len(cells) > 1 else "",
                        "on": cells[2] if len(cells) > 2 else "",
                    })
    else:
        # Fallback to privilege-manifest.json
        priv_path = project_root / DEFAULT_IMPL_DIR / "privilege-manifest.json"
        if not priv_path.exists():
            priv_path = project_root / DEFAULT_SPECBUILDER_META_DIR / "privilege-manifest.json"
        if priv_path.exists():
            data = json.loads(priv_path.read_text(encoding="utf-8"))
            for g in data.get("minimum_grants", []):
                priv_manifest.append({
                    "privilege": g.get("privilege", ""),
                    "object_type": "",
                    "on": g.get("on", ""),
                })

    grant_rows = []
    for g in priv_manifest:
        obj = g.get("on") or f"{g.get('object_type', '')} {g.get('object_name', '')}".strip()
        grantee = g.get("grantee", "")
        raw_row = f"| {g['privilege']} | {obj} | {g.get('notes', '')} | {grantee} |"
        grant_rows.append(sanitize(raw_row, value_map))
    grants_table = (
        "\n".join(grant_rows) if grant_rows else "| (none discovered) | | | |"
    )

    # Build ## Validated Acceptance Criteria table
    ac_results = (validation_report or {}).get("ac_results", [])
    ac_rows = []
    for ac in ac_results:
        status = ac.get("status", "unknown").upper()
        sql = ac.get("assertion_sql", "N/A") or "N/A"
        if len(sql) > 80:
            sql = sql[:77] + "..."
        raw_row = f"| {ac.get('ac_id', '?')} | `{sql}` | {status} |"
        ac_rows.append(sanitize(raw_row, value_map))
    ac_table = "\n".join(ac_rows) if ac_rows else "| (none) | | |"

    # Build ## Artifact Manifest table
    artifact_results = (validation_report or {}).get("artifact_results", [])
    artifact_rows = []
    for art in artifact_results:
        path = art.get("path", "?")
        status = art.get("status", "?").upper()
        raw_row = f"| `{path}` | artifact | {sanitize(status, value_map)} |"
        artifact_rows.append(raw_row)
    artifact_table = (
        "\n".join(artifact_rows) if artifact_rows else "| (none) | | |"
    )

    # Build teardown note
    teardown_path = (validation_report or {}).get("teardown_path")
    raw_teardown = (
        f"Execute `{teardown_path}` to remove all deployed objects."
        if teardown_path
        else "No teardown script generated."
    )
    teardown_note = sanitize(raw_teardown, value_map)

    # Assemble handover.md content — every string already sanitized
    summary_line = sanitize(
        f"This handover drives full POC replication of {source_title} "
        "through CoCo with no manual configuration.",
        value_map,
    )

    handover_content = f"""---
id: MOD-{handover_num}
title: "Handover: {sanitize(source_title, value_map)}"
status: implemented
type: handover
source_demo: {source_id}
grants_module: {grants_module_id or "none"}
handover_version: 1
last_updated: "{datetime.now().strftime('%Y-%m-%d')}"
---

# Handover: {sanitize(source_title, value_map)}

{summary_line}

## Environment Placeholders

Provide these values when prompted. Every occurrence in the artifact
files, SQL assertions, and metadata will be substituted automatically.

| Placeholder | Description | Example |
|---|---|---|
{placeholder_table}

## Required Grants

Have your Snowflake admin run `impl/grants/setup_grants.sql` before starting.
Verified by the `grant-test` loop — nothing more, nothing less.

| Privilege | Object | Notes | Grantee |
|---|---|---|---|
{grants_table}

## Validated Acceptance Criteria

Verified against a live Snowflake deployment. Pre-seeded into your POC.

| AC | Assertion SQL | Status |
|---|---|---|
{ac_table}

## Artifact Manifest

| File | Type | Description |
|---|---|---|
{artifact_table}

## Deployment Instructions

1. Have your admin run `impl/grants/setup_grants.sql`
2. Run: `python3 -m specbuilder handover-consumer spec/modules/{handover_num}-handover.md`
3. Provide your environment values when prompted — all placeholders
   above will be substituted throughout every artifact and assertion
4. CoCo implements all artifacts, validates in your environment, signs off

## Cleanup

{teardown_note}
"""

    # Write handover module
    modules_dir.mkdir(parents=True, exist_ok=True)
    handover_path = modules_dir / f"{handover_num}-handover.md"
    handover_path.write_text(handover_content, encoding="utf-8")
    print(f"Handover module written: {handover_path}")

    return 0


# ---------------------------------------------------------------------------
# Demo orchestrator (simplified 2-phase wrapper)
# ---------------------------------------------------------------------------


def demo_run(module_num: str, project_root: Path) -> int:
    """Execute the full demo lifecycle: implement → demo-handover.

    Returns exit code (0 = success, 1 = partial failure).
    """
    meta_dir = project_root / DEFAULT_SPECBUILDER_META_DIR
    impl_dir = project_root / DEFAULT_IMPL_DIR

    state = _read_state(meta_dir)

    # Migration guard: old 3-phase state had "validate" — treat as "handover"
    if state.get("phase") == "validate":
        state["phase"] = "handover"

    # Phase 1: Implement (skip if impl/ exists)
    if state.get("phase") in ("init", "implement"):
        if not impl_dir.is_dir():
            print("Phase 1/2: Generating implementation artifacts...")
            from specbuilder.src.implement import implement

            exit_code = implement(int(module_num), project_root=project_root)
            if exit_code != 0:
                print("Error: Implementation failed.", file=sys.stderr)
                _write_state(
                    meta_dir,
                    {
                        "phase": "implement",
                        "module_num": module_num,
                        "timestamp": datetime.now().isoformat(),
                        "error": "implement failed",
                    },
                )
                return 1
        else:
            print("Phase 1/2: Implementation artifacts already exist. Skipping.")

        _write_state(
            meta_dir,
            {
                "phase": "handover",
                "module_num": module_num,
                "timestamp": datetime.now().isoformat(),
            },
        )

    # Phase 2: demo-handover (handles Tier 4 + grant-test + sanitize + write)
    print("Phase 2/2: Running demo-handover...")
    exit_code = demo_handover(module_num, project_root)

    state_path = meta_dir / _STATE_FILE
    if exit_code == 0:
        # Clear state only on success; preserve checkpoint for resumption on failure
        if state_path.exists():
            state_path.unlink()
        print("\nDemo run complete.")
    else:
        print(
            f"\nDemo run failed (exit code {exit_code}). "
            "State file preserved for resumption.",
            file=sys.stderr,
        )
    return exit_code


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> None:
    # Build a unified parser that handles both demo-run and demo-handover
    parser = argparse.ArgumentParser(
        prog="specbuilder demo",
        description="Demo orchestration commands.",
    )
    subparsers = parser.add_subparsers(dest="subcommand")

    # demo-run subcommand
    run_parser = subparsers.add_parser(
        "run", help="Execute full demo lifecycle: implement → demo-handover"
    )
    run_parser.add_argument("module_num", help="Module number (e.g., 01)")

    # demo-handover subcommand
    handover_parser = subparsers.add_parser(
        "handover",
        help="Generate sanitized handover.md from existing artifacts",
    )
    handover_parser.add_argument("module_num", help="Module number (e.g., 01)")
    handover_parser.add_argument(
        "--force-validate",
        action="store_true",
        help="Re-run validation even if a report already exists.",
    )
    handover_parser.add_argument(
        "--force-grant-test",
        action="store_true",
        help="Re-run grant-test even if a grants module already exists.",
    )
    handover_parser.add_argument(
        "--tester-role",
        default="SPECBUILDER_TESTER_ROLE",
        help="Tester role name for grant-test (default: SPECBUILDER_TESTER_ROLE)",
    )

    args = parser.parse_args(argv)

    if not args.subcommand:
        # When invoked as `specbuilder demo-run <N>` or `specbuilder demo-handover <N>`,
        # sys.argv[0] is "specbuilder demo-run" / "specbuilder demo-handover".
        # Re-parse treating the first positional as module_num.
        cmd_name = sys.argv[0] if not argv else argv[0] if argv else ""
        if "handover" in cmd_name:
            handover_parser2 = argparse.ArgumentParser(prog="specbuilder demo-handover")
            handover_parser2.add_argument("module_num")
            handover_parser2.add_argument("--force-validate", action="store_true")
            handover_parser2.add_argument("--force-grant-test", action="store_true")
            handover_parser2.add_argument(
                "--tester-role", default="SPECBUILDER_TESTER_ROLE"
            )
            args2 = handover_parser2.parse_args(argv)
            args2.subcommand = "handover"
            args = args2
        else:
            run_parser2 = argparse.ArgumentParser(prog="specbuilder demo-run")
            run_parser2.add_argument("module_num")
            args2 = run_parser2.parse_args(argv)
            args2.subcommand = "run"
            args = args2

    project_root = get_project_root()

    if args.subcommand == "run":
        exit_code = demo_run(args.module_num, project_root)
        sys.exit(exit_code)
    elif args.subcommand == "handover":
        exit_code = demo_handover(
            module_num=args.module_num,
            project_root=project_root,
            force_validate=getattr(args, "force_validate", False),
            force_grant_test=getattr(args, "force_grant_test", False),
            tester_role=getattr(args, "tester_role", "SPECBUILDER_TESTER_ROLE"),
        )
        sys.exit(exit_code)
    else:
        parser.print_help()
        sys.exit(2)


if __name__ == "__main__":
    main()

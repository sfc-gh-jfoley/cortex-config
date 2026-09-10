"""Implementation orchestrator for SpecBuilder.

Reads an accepted spec's Output section, generates file stubs, dispatches
domain agents, and runs cross-reference validation.

Usage:
    python3 -m specbuilder implement <module_num> [--stubs-only] [--validate-only]

Exit codes:
    0 = success
    1 = validation failure
    2 = usage error
    3 = gate-blocked — awaiting stub review confirmation via --confirm
"""

import json
import sys
import time
from pathlib import Path

# Re-export all public functions for backward compatibility
from specbuilder.src.artifact_parser import _infer_type, parse_output_section  # noqa: F401
from specbuilder.src.config import (
    DEFAULT_IMPL_DIR,
    DEFAULT_MODULES_DIR,
    DEFAULT_SPECBUILDER_META_DIR,
    GATE_SENTINEL_MAX_AGE_SECONDS,
    get_effective_profile,
    get_project_root,
)
from specbuilder.src.dispatch import prepare_dispatch_plan, topological_sort  # noqa: F401
from specbuilder.src.validation import parse_frontmatter
from specbuilder.src.workspace import (  # noqa: F401
    check_dispatch_status,
    generate_stubs,
    prepare_validation,
    reconcile_status_files,
    skip_dependents,
    write_artifact_status,
)

# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------


def implement(
    module_num: int,
    project_root: Path | None = None,
    stubs_only: bool = False,
    validate_only: bool = False,
    confirm: bool = False,
) -> int:
    """Run implementation orchestration for a module.

    Args:
        module_num: Module number to implement.
        project_root: Project root (auto-detected if None).
        stubs_only: If True, only generate stubs (no agent dispatch).
        validate_only: If True, only run validation on existing impl.
        confirm: If True, confirms stub review and allows dispatch to proceed.

    Returns:
        Exit code (0=success, 1=failure, 2=error, 3=gate-blocked).
    """
    if project_root is None:
        project_root = get_project_root()

    profile = get_effective_profile(project_root)
    print(f"Quality profile: {profile['name']} "
          f"(validation_tier={profile['validation_tier']}, "
          f"self_correct={profile['self_correct']}, "
          f"max_retries={profile['max_retries']})")

    # Find the spec file
    modules_dir = project_root / DEFAULT_MODULES_DIR
    if not modules_dir.exists():
        print(
            f"Error: {modules_dir} not found. Run scaffold-spec to initialize.",
            file=sys.stderr,
        )
        return 2

    if not any(modules_dir.iterdir()):
        print(
            f"Error: {modules_dir} is empty. "
            "Run scaffold-spec to create the module structure, "
            "then run generate-spec to populate it.",
            file=sys.stderr,
        )
        return 2

    pattern = f"{module_num:02d}-*.md"
    matches = list(modules_dir.glob(pattern))

    if not matches:
        print(
            f"Error: No spec file matching {pattern} in {modules_dir}",
            file=sys.stderr,
        )
        return 2

    spec_path = matches[0]

    # Check spec status
    fm = parse_frontmatter(spec_path)
    if fm.get("status") not in ("accepted", "implemented"):
        print(
            f"Error: Spec must be accepted before implementation. "
            f"Current status: {fm.get('status', 'unknown')}",
            file=sys.stderr,
        )
        return 2

    module_id = fm.get("id", f"MOD-{module_num:02d}")
    impl_dir = project_root / DEFAULT_IMPL_DIR
    metadata_dir = project_root / DEFAULT_SPECBUILDER_META_DIR

    # Validate-only mode
    if validate_only:
        manifest_path = metadata_dir / "impl-status.json"
        if not manifest_path.exists():
            print(
                "Error: No implementation status found. "
                "Run implementation first.",
                file=sys.stderr,
            )
            return 2
        validation = prepare_validation(impl_dir, metadata_dir, tier=profile['validation_tier'])
        if "error" in validation:
            print(f"Error: {validation['error']}", file=sys.stderr)
            return 2
        if not validation.get("artifacts"):
            print(
                "Error: Manifest contains no artifacts — all may have been blocked by "
                "conflicts during stub generation. Run 'implement <module_num>' first "
                "or inspect .specbuilder/.status/*.json for conflict entries.",
                file=sys.stderr,
            )
            return 1
        print(json.dumps(validation, indent=2))
        failed = [
            a for a in validation.get("artifacts", [])
            if a.get("status") in ("failed", "stub") or a.get("is_stub")
        ]
        active_tier = profile['validation_tier']
        from specbuilder.src.validate_artifacts import run_tier1
        if active_tier != "compile":
            print(
                f"Warning: active profile '{profile['name']}' requires validation "
                f"tier '{active_tier}'; only Tier 1 (compile) is available in this "
                "version. Running compile check only.",
                file=sys.stderr,
            )
        tier1_results = run_tier1(impl_dir)
        sql_files = list(impl_dir.rglob("*.sql"))
        if sql_files:
            print(
                f"Warning: {len(sql_files)} .sql file(s) validated with heuristics only "
                "(no SQL executor). Compile errors may be missed.",
                file=sys.stderr,
            )
        tier1_failed = [r for r in tier1_results if r.get("status") == "fail"]
        if tier1_failed:
            failed = failed + tier1_failed
        if failed:
            return 1
        spec_content = spec_path.read_text(encoding="utf-8")
        updated = spec_content.replace("status: accepted", "status: implemented", 1)
        spec_path.write_text(updated, encoding="utf-8")
        return 0

    # Parse artifacts from spec Output section
    artifacts = parse_output_section(spec_path)

    if not artifacts:
        print(
            f"Error: No artifacts defined in Output section of {spec_path.name}",
            file=sys.stderr,
        )
        print(
            "Add file paths (backtick-quoted) to the Output section "
            "to enable orchestration.",
            file=sys.stderr,
        )
        return 2

    print(f"Found {len(artifacts)} artifact(s) in {spec_path.name}:")
    for art in artifacts:
        print(f"  [{art['domain']}] {art['path']} ({art['type']})")

    # Generate stubs
    print("\nGenerating stubs in impl/...")
    manifest = generate_stubs(artifacts, impl_dir, metadata_dir, module_id)
    print(f"Created {len(manifest['artifacts'])} stub(s)")
    print("Implementation status: .specbuilder/impl-status.json")

    if stubs_only:
        sentinel = metadata_dir / ".stub-review-pending"
        sentinel.parent.mkdir(parents=True, exist_ok=True)
        sentinel.write_text("", encoding="utf-8")
        print("\n--stubs-only: Stopping after stub generation.")
        print("  Sentinel written. Re-run with --confirm to proceed to dispatch.")
        return 0

    if not confirm:
        sentinel = metadata_dir / ".stub-review-pending"
        sentinel.parent.mkdir(parents=True, exist_ok=True)
        sentinel.write_text("", encoding="utf-8")
        print(
            "Stub review gate: inspect generated stubs, then re-run with --confirm to dispatch.",
            file=sys.stderr,
        )
        print("  python3 -m specbuilder implement <module> --confirm")
        return 3

    sentinel = metadata_dir / ".stub-review-pending"
    if not sentinel.exists():
        print(
            "Error: stub-review sentinel not found. "
            "Run 'implement <module>' without --confirm first to generate stubs and enter review.",
            file=sys.stderr,
        )
        return 2
    sentinel_age = time.time() - sentinel.stat().st_mtime
    if sentinel_age > GATE_SENTINEL_MAX_AGE_SECONDS:
        print(
            f"Error: stub-review sentinel is {int(sentinel_age)}s old "
            f"(max {GATE_SENTINEL_MAX_AGE_SECONDS}s). Re-run without --confirm to refresh.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Prepare dispatch plan
    try:
        dispatch = prepare_dispatch_plan(
            artifacts, module_id, spec_path, metadata_dir,
            quality_profile=profile,
        )
        sentinel.unlink()
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 2

    # Write dispatch manifest
    dispatch_path = metadata_dir / "dispatch.json"
    dispatch_path.parent.mkdir(parents=True, exist_ok=True)
    dispatch_path.write_text(
        json.dumps(dispatch, indent=2, default=str) + "\n",
        encoding="utf-8",
    )

    print("\nDispatch plan: .specbuilder/dispatch.json")
    print(f"Execution order ({len(dispatch['execution_order'])} batch(es)):")
    for batch in dispatch["execution_order"]:
        print(f"  Batch {batch['batch']}:")
        for art in batch["artifacts"]:
            print(
                f"    [{art['domain']}] {art['path']} \u2192 skills: "
                f"{', '.join(art['skills']) or 'none'}"
            )

    print("\nProtocol for CoCo:")
    print("  1. Review stubs with the user")
    print(
        "  2. For each batch in dispatch.json, "
        "implement artifacts using listed skills"
    )
    print("  3. Write artifact status to isolated .specbuilder/.status/<slug>.json files "
          "using write_artifact_status() — do NOT write to impl-status.json directly")
    print(
        f"  4. Run: python3 -m specbuilder implement {module_num}"
        " --validate-only"
    )
    print(
        "  5. Rebuild manifest and sync AC files: "
        "python3 -m specbuilder generate-manifest && "
        "python3 -m specbuilder sync-ac-files"
    )

    return 0


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """CLI entry point."""
    if len(sys.argv) < 2:
        print(
            "Usage: python3 -m specbuilder implement <module_num> "
            "[--stubs-only] [--validate-only] [--status]",
            file=sys.stderr,
        )
        sys.exit(2)

    # Handle --status without module_num
    if "--status" in sys.argv:
        project_root = get_project_root()
        metadata_dir = project_root / DEFAULT_SPECBUILDER_META_DIR
        status = check_dispatch_status(metadata_dir)
        if "error" in status:
            print(f"Error: {status['error']}", file=sys.stderr)
            sys.exit(2)
        print(json.dumps(status, indent=2))
        sys.exit(0)

    try:
        module_num = int(sys.argv[1])
    except ValueError:
        print(
            f"Error: module_num must be an integer, got '{sys.argv[1]}'",
            file=sys.stderr,
        )
        sys.exit(2)

    stubs_only = "--stubs-only" in sys.argv
    validate_only = "--validate-only" in sys.argv
    confirm = "--confirm" in sys.argv

    exit_code = implement(
        module_num, stubs_only=stubs_only, validate_only=validate_only, confirm=confirm
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    main()

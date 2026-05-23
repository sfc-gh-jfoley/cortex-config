"""Implementation orchestrator for SpecBuilder.

Reads an accepted spec's Output section, generates file stubs, dispatches
domain agents, and runs cross-reference validation.

Usage:
    python3 -m specbuilder.implement <module_num> [--stubs-only] [--validate-only]

Exit codes:
    0 = success
    1 = validation failure
    2 = usage error
"""

import json
import sys
from pathlib import Path

# Re-export all public functions for backward compatibility
from specbuilder.src.artifact_parser import _infer_type, parse_output_section  # noqa: F401
from specbuilder.src.config import (
    DEFAULT_IMPL_DIR,
    DEFAULT_MODULES_DIR,
    DEFAULT_SPECBUILDER_META_DIR,
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
    update_artifact_status,
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
) -> int:
    """Run implementation orchestration for a module.

    Args:
        module_num: Module number to implement.
        project_root: Project root (auto-detected if None).
        stubs_only: If True, only generate stubs (no agent dispatch).
        validate_only: If True, only run validation on existing impl.

    Returns:
        Exit code (0=success, 1=failure, 2=error).
    """
    if project_root is None:
        project_root = get_project_root()

    # Find the spec file
    modules_dir = project_root / DEFAULT_MODULES_DIR
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
        validation = prepare_validation(impl_dir, metadata_dir)
        if "error" in validation:
            print(f"Error: {validation['error']}", file=sys.stderr)
            return 2
        print(json.dumps(validation, indent=2))
        return 0

    # Parse artifacts from spec Output section
    artifacts = parse_output_section(spec_path)

    if not artifacts:
        print(
            f"No artifacts defined in Output section of {spec_path.name}"
        )
        print(
            "Add file paths (backtick-quoted) to the Output section "
            "to enable orchestration."
        )
        return 0

    print(f"Found {len(artifacts)} artifact(s) in {spec_path.name}:")
    for art in artifacts:
        print(f"  [{art['domain']}] {art['path']} ({art['type']})")

    # Generate stubs
    print("\nGenerating stubs in impl/...")
    manifest = generate_stubs(artifacts, impl_dir, metadata_dir, module_id)
    print(f"Created {len(manifest['artifacts'])} stub(s)")
    print("Implementation status: .specbuilder/impl-status.json")

    if stubs_only:
        print("\n--stubs-only: Stopping after stub generation.")
        return 0

    # Prepare dispatch plan
    dispatch = prepare_dispatch_plan(artifacts, module_id, spec_path)

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
    print("  3. Update .specbuilder/impl-status.json status per artifact")
    print(
        f"  4. Run: python3 -m specbuilder.implement {module_num}"
        " --validate-only"
    )

    return 0


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """CLI entry point."""
    if len(sys.argv) < 2:
        print(
            "Usage: python3 -m specbuilder.implement <module_num> "
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

    exit_code = implement(
        module_num, stubs_only=stubs_only, validate_only=validate_only
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    main()

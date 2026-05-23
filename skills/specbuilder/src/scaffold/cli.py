"""CLI entry point for the scaffold command."""

from __future__ import annotations

import argparse
from pathlib import Path

from specbuilder.src.config import DEFAULT_TEMPLATE_STYLE

from .modes import (
    _VALID_TEMPLATE_STYLES,
    scaffold_demo,
    scaffold_lite,
    scaffold_poc,
    scaffold_project,
)
from .prototype import end_prototype, start_prototype
from .upgrade import upgrade_project


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Scaffold a spec-driven project structure.",
    )
    parser.add_argument(
        "--project-name",
        default=None,
        help="Human-readable project name.",
    )
    parser.add_argument(
        "--protected-dirs",
        nargs="*",
        default=None,
        help="Directories protected by the change-control hook.",
    )
    parser.add_argument(
        "--spec-dir",
        default="spec",
        help="Name of the spec directory (default: spec).",
    )
    parser.add_argument(
        "--template-style",
        default=DEFAULT_TEMPLATE_STYLE,
        choices=sorted(_VALID_TEMPLATE_STYLES),
        help="Template variant (default: standard).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be created without writing files.",
    )
    # Prototype mode (EXT-004)
    parser.add_argument(
        "--prototype",
        action="store_true",
        help="Activate prototype mode (suspends change-control enforcement).",
    )
    parser.add_argument(
        "--end-prototype",
        action="store_true",
        help="End prototype mode and audit modified files.",
    )
    parser.add_argument(
        "--expires-in",
        default=None,
        help="Prototype expiry duration (e.g., '4h', '30m', '2d'). Default: 24h.",
    )
    parser.add_argument(
        "--reason",
        default="",
        help="Reason for activating prototype mode.",
    )
    # CI integration (EXT-007)
    parser.add_argument(
        "--ci",
        choices=["none", "github", "gitlab"],
        default=None,
        help="Install CI workflow template for spec drift checks (none/github/gitlab).",
    )
    # Lite mode (EXT-003)
    parser.add_argument(
        "--lite",
        action="store_true",
        help="Produce minimal spec structure (spec/modules/, INTAKE.md, hook only).",
    )
    parser.add_argument(
        "--upgrade",
        action="store_true",
        help="Convert a lite project to full mode without overwriting existing specs.",
    )
    # POC mode (EXT-037)
    parser.add_argument(
        "--poc",
        action="store_true",
        help="Scaffold in POC mode (lite structure + collapsed workflow + relaxed quality gate).",
    )
    # Demo mode (EXT-048)
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Scaffold in demo mode (POC + auto-deploy/verify + handover generation).",
    )
    # Handover consumption (EXT-049)
    parser.add_argument(
        "--from-handover",
        metavar="PATH",
        default=None,
        help="Scaffold POC from a demo handover module.",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)

    project_root = Path.cwd()

    # Handle prototype mode commands
    if args.end_prototype:
        result = end_prototype(project_root, spec_dir=args.spec_dir)
        if not result.get("active"):
            print(result.get("message", "Prototype mode is not active."))
        else:
            print("Prototype mode ended.")
            if result.get("files_modified"):
                print("\nFiles modified during prototype mode:")
                for f in result["files_modified"]:
                    print(f"  {f}")
                print("\nAction required:")
                print("  - If keeping these changes: create/update specs for affected modules")
                print("  - If discarding: git checkout the modified files")
            else:
                print("No files were modified during prototype mode.")
        return

    if args.prototype:
        # Mutual exclusion: --poc and --prototype cannot be combined (EXT-037)
        if args.poc:
            parser.error(
                "--poc and --prototype are mutually exclusive."
                " POC mode relaxes ceremony; prototype mode suspends"
                " enforcement. Pick one."
            )
        result = start_prototype(
            project_root,
            spec_dir=args.spec_dir,
            expires_in=args.expires_in,
            reason=args.reason,
        )
        print("Prototype mode activated.")
        print(f"  Expires: {result['expires']}")
        print(f"  Reason: {result['reason']}")
        print("\nChange-control hook will allow edits with a reminder.")
        print("Run `python3 -m specbuilder scaffold --end-prototype` when done.")
        return

    # Normal scaffold — project-name is required
    # Auto-detect handover files (EXT-049) when no specific mode is selected
    if not any([args.upgrade, args.demo, args.poc, args.lite, args.from_handover]):
        from specbuilder.src.handover_consumer import detect_handover_files

        handovers = detect_handover_files(project_root)
        if handovers:
            print("Detected handover module(s):")
            for h in handovers:
                print(f"  - {h.relative_to(project_root)}")
            print(
                "\nTo scaffold from a handover, use:"
                f"\n  python3 -m specbuilder scaffold "
                f"--from-handover {handovers[0].relative_to(project_root)}"
                "\n"
            )

    if args.upgrade:
        result = upgrade_project(
            project_root=project_root,
            project_name=args.project_name,
            spec_dir=args.spec_dir,
            dry_run=args.dry_run,
        )
    elif args.from_handover:
        from specbuilder.src.handover_consumer import main as handover_main

        handover_main([args.from_handover] + (["--dry-run"] if args.dry_run else []))
        return
    elif args.demo:
        if args.prototype:
            parser.error("--demo and --prototype are mutually exclusive.")
        if not args.project_name:
            parser.error("--project-name is required for scaffolding")
        result = scaffold_demo(
            project_root=project_root,
            project_name=args.project_name,
            protected_dirs=args.protected_dirs,
            spec_dir=args.spec_dir,
            reason=args.reason,
            dry_run=args.dry_run,
        )
    elif args.poc:
        if not args.project_name:
            parser.error("--project-name is required for scaffolding")
        result = scaffold_poc(
            project_root=project_root,
            project_name=args.project_name,
            protected_dirs=args.protected_dirs,
            spec_dir=args.spec_dir,
            reason=args.reason,
            dry_run=args.dry_run,
        )
    elif args.lite:
        if not args.project_name:
            parser.error("--project-name is required for scaffolding")
        result = scaffold_lite(
            project_root=project_root,
            project_name=args.project_name,
            protected_dirs=args.protected_dirs,
            spec_dir=args.spec_dir,
            dry_run=args.dry_run,
        )
    else:
        if not args.project_name:
            parser.error("--project-name is required for scaffolding")
        result = scaffold_project(
            project_root=project_root,
            project_name=args.project_name,
            protected_dirs=args.protected_dirs,
            spec_dir=args.spec_dir,
            template_style=args.template_style,
            ci_platform=args.ci,
            dry_run=args.dry_run,
        )

    # Print summary
    if result.get("message"):
        print(result["message"])
        return

    if args.dry_run:
        print("\n--- Dry run complete (no files written) ---")

    if result["created"]:
        print(f"\nCreated ({len(result['created'])}):")
        for f in result["created"]:
            print(f"  + {f}")

    if result["skipped"]:
        print(f"\nSkipped ({len(result['skipped'])}):")
        for f in result["skipped"]:
            print(f"  ~ {f}")

    if result["merged"]:
        print(f"\nMerged ({len(result['merged'])}):")
        for f in result["merged"]:
            print(f"  * {f}")

    total = len(result["created"]) + len(result["merged"])
    print(f"\nDone. {total} file(s) written.")


if __name__ == "__main__":
    main()

"""CLI entry point for the scaffold command."""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

from specbuilder.src.config import DEFAULT_TEMPLATE_STYLE, POC_SENTINEL, SPECBUILDER_TOML_FILE

from .modes import (
    _VALID_TEMPLATE_STYLES,
    _detect_ci_platform,
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
    parser.add_argument(
        "--upgrade",
        action="store_true",
        help="Convert a poc/minimal project to full mode without overwriting existing specs.",
    )
    parser.add_argument(
        "--upgrade-from-poc",
        action="store_true",
        help=(
            "Graduate a POC project to full mode"
            " (removes spec/.poc, updates toml mode, adds missing structure)."
        ),
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        default=False,
        help="Confirm irreversible operations (required for --upgrade-from-poc).",
    )
    # POC mode (EXT-037)
    parser.add_argument(
        "--poc",
        action="store_true",
        help="Scaffold in POC mode (lite structure + collapsed workflow + relaxed quality gate).",
    )
    # Lite mode (EXT-227)
    parser.add_argument(
        "--lite",
        action="store_true",
        help="Minimal file footprint: spec governance only, no CI templates.",
    )
    # Handover flag (EXT-193) — only valid with --poc
    parser.add_argument(
        "--handover",
        action="store_true",
        help="Enable handover artifact generation (requires --poc).",
    )
    # --demo is a deprecated alias for --poc --handover (EXT-193)
    parser.add_argument(
        "--demo",
        action="store_true",
        help="[Deprecated] Use --poc --handover instead.",
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

    # F2: CI auto-detection — apply before any branch reads args.ci (EXT-163)
    if args.ci is None:
        args.ci = _detect_ci_platform(project_root)

    # EXT-193: --demo is a deprecated alias for --poc --handover
    if args.demo:
        import warnings
        warnings.warn(
            "--demo is deprecated. Use --poc --handover instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        args.poc = True
        args.handover = True

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
        if args.poc or args.handover:
            parser.error(
                "--prototype cannot be combined with --poc or --handover."
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
    if not any([args.upgrade, args.upgrade_from_poc, args.poc,
                args.from_handover, args.lite]):
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

    if args.upgrade_from_poc:
        if not args.confirm:
            print(
                "ERROR: --upgrade-from-poc is irreversible.\n"
                "  Deleting spec/.poc and changing the mode in .specbuilder.toml"
                " cannot be undone.\n"
                "  Re-run with --confirm to proceed:\n"
                "\n"
                "    python3 -m specbuilder scaffold --upgrade-from-poc --confirm"
            )
            sys.exit(1)
        poc_path = project_root / POC_SENTINEL
        if not poc_path.exists():
            print(
                f"Warning: {POC_SENTINEL} not found — project may not be in POC mode."
                " Proceeding with upgrade."
            )
        if args.dry_run:
            print(f"[dry-run] delete {POC_SENTINEL}")
            print(f"[dry-run] update {SPECBUILDER_TOML_FILE}: mode = \"poc\" → mode = \"full\"")
        else:
            toml_path = project_root / SPECBUILDER_TOML_FILE
            if toml_path.exists():
                try:
                    import tomllib
                except ImportError:
                    import tomli as tomllib  # type: ignore[no-redef]
                import re as _re
                raw = toml_path.read_text(encoding="utf-8")
                try:
                    toml_data = tomllib.loads(raw)
                    toml_data.setdefault("project", {})["mode"] = "full"
                    try:
                        import tomli_w
                        toml_content = tomli_w.dumps(toml_data)
                    except ImportError:
                        # Fallback: regex replacement — resilient to whitespace variations
                        toml_content = _re.sub(
                            r'(?m)^(\s*mode\s*=\s*)"poc"',
                            r'\1"full"',
                            raw,
                        )
                        if 'mode = "full"' not in toml_content:
                            raise RuntimeError(
                                "Could not locate 'mode = \"poc\"' in .specbuilder.toml"
                                " — upgrade aborted."
                            )
                except Exception as parse_exc:
                    raise RuntimeError(
                        f"Failed to parse .specbuilder.toml — upgrade aborted: {parse_exc}"
                    ) from parse_exc
                tmp_fd, tmp_path = tempfile.mkstemp(
                    dir=toml_path.parent,
                    suffix=".tmp",
                    prefix=".specbuilder.toml.",
                )
                try:
                    with os.fdopen(tmp_fd, "w", encoding="utf-8") as fh:
                        fh.write(toml_content)
                    Path(tmp_path).replace(toml_path)  # atomic on POSIX; consistent on Windows
                except OSError as e:
                    try:
                        os.unlink(tmp_path)
                    except OSError:
                        pass
                    raise RuntimeError(
                        f"Failed to write upgraded TOML — upgrade aborted, "
                        f"POC sentinel preserved: {e}"
                    ) from e
            # Sentinel deleted only after the TOML write is fully committed
            if poc_path.exists():
                try:
                    poc_path.unlink()
                except OSError as e:
                    print(
                        f"Error: Could not remove POC sentinel {poc_path}: {e}\n"
                        "The project is in a split-mode state: mode='full' in .specbuilder.toml "
                        "but spec/.poc still on disk.\n"
                        "Remove spec/.poc manually to complete the upgrade.",
                        file=sys.stderr,
                    )
                    sys.exit(1)
        result = upgrade_project(
            project_root=project_root,
            project_name=args.project_name,
            spec_dir=args.spec_dir,
            dry_run=args.dry_run,
        )
    elif args.upgrade:
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
    elif args.poc:
        if not args.project_name:
            parser.error("--project-name is required for scaffolding")
        if not args.confirm and not args.dry_run:
            print(
                "ERROR: --poc creates a divergent lightweight structure.\n"
                "  Re-run with --confirm to proceed:\n"
                "\n"
                "    python3 -m specbuilder scaffold --poc"
                f" --project-name \"{args.project_name}\" --confirm"
            )
            sys.exit(1)
        if args.handover:
            if getattr(args, 'ci', None) and args.ci != "none":
                print(
                    f"Warning: --ci {args.ci!r} was specified but "
                    "CI template installation is skipped for handover mode "
                    "(handover projects are not connected to CI).",
                    file=sys.stderr,
                )
        result = scaffold_poc(
            project_root=project_root,
            project_name=args.project_name,
            protected_dirs=args.protected_dirs,
            spec_dir=args.spec_dir,
            ci_platform=args.ci,
            reason=args.reason,
            handover=args.handover,
            dry_run=args.dry_run,
        )
    elif args.lite:
        if not args.project_name:
            parser.error("--project-name is required for scaffolding")
        scaffold_lite(project_root, project_name=args.project_name)
        return
    else:
        if not args.project_name:
            parser.error("--project-name is required for scaffolding")
        if getattr(args, 'handover', False):
            parser.error("--handover requires --poc")
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

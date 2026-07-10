"""Propose-spec backing module: pre-write validation and collision detection."""
from __future__ import annotations

import argparse
import re as _re
import sys
from pathlib import Path

from specbuilder.src.config import (
    ARCH_FILE_PATTERN,
    PROMOTED_TO_PATTERN,
    REQUIRED_PROPOSAL_FIELDS,
    VALID_PROPOSAL_STATUSES,
    get_effective_profile,
    get_project_root,
)
from specbuilder.src.validation import (
    parse_frontmatter,
)
from specbuilder.src.validation import (
    validate_proposal as validate_proposal_file,
)

# YAMLError excluded: parse_frontmatter() catches all exceptions internally
# (validation.py:74), so YAMLError never propagates to this handler.
_RECOVERABLE_ERRORS: tuple[type[Exception], ...] = (
    FileNotFoundError, UnicodeDecodeError, PermissionError
)


def validate_proposal(frontmatter: dict, is_new: bool = False) -> list[str]:
    """Validate in-memory proposal frontmatter before writing to disk.

    Returns a list of error strings; empty list means valid.
    Complements validation.validate_proposal(filepath) which operates on files.
    """
    errors: list[str] = []
    if is_new and frontmatter.get("status") != "planned":
        errors.append(
            f"New proposals must have status 'planned', got '{frontmatter.get('status')}'"
        )
    for key in REQUIRED_PROPOSAL_FIELDS:
        if key not in frontmatter:
            errors.append(f"Missing required field: '{key}'")
    if "status" in frontmatter and frontmatter["status"] not in VALID_PROPOSAL_STATUSES:
        errors.append(
            f"Invalid status '{frontmatter['status']}'; "
            f"must be one of: {sorted(VALID_PROPOSAL_STATUSES)}"
        )
    if "id" in frontmatter and not _re.fullmatch(r"EXT-\d{3,}", str(frontmatter["id"])):
        errors.append(
            f"'id' value '{frontmatter['id']}' does not match required format EXT-NNN "
            "(e.g. EXT-001, EXT-209)"
        )
    if "promoted_to" in frontmatter:
        if not PROMOTED_TO_PATTERN.match(str(frontmatter["promoted_to"])):
            errors.append(
                f"'promoted_to' value '{frontmatter['promoted_to']}' "
                "does not match required pattern MOD-NN (e.g. MOD-01)"
            )
    if "phase" in frontmatter:
        phase = frontmatter["phase"]
        if not isinstance(phase, int) or phase <= 0:
            errors.append(f"'phase' must be a positive integer, got: {phase!r}")
    return errors


def check_ext_collision(proposals_root: Path, proposed_id: str) -> bool:
    """Return True if proposed_id already exists in any proposal directory.

    Scans proposals_root/*.md, proposals_root/implemented/*.md,
    and proposals_root/parked/*.md.
    """
    numeric = proposed_id.split("-")[-1].zfill(3)
    subdirs = [proposals_root, proposals_root / "implemented", proposals_root / "parked"]
    for d in subdirs:
        try:
            md_files = list(d.glob("*.md"))
        except FileNotFoundError:
            continue
        except PermissionError as e:
            print(
                f"Warning: skipping {d} during collision check — PermissionError: {e}",
                file=sys.stderr,
            )
            continue
        for f in md_files:
            if ARCH_FILE_PATTERN.match(f.name):
                prefix = f.name.split("-")[0]
                if prefix == numeric:
                    return True
    return False


def check_scope_overlap(proposals_root: Path, proposed_modules: list[str]) -> list[str]:
    """Return EXT IDs of existing proposals whose impacts_modules overlaps proposed_modules.

    Performs structural set-intersection on module IDs (e.g., 'MOD-04').
    Does not perform semantic/NLP title comparison — see spec/manifest.json for that.
    """
    proposed_set = set(proposed_modules)
    colliding: list[str] = []
    subdirs = [proposals_root, proposals_root / "implemented", proposals_root / "parked"]
    for d in subdirs:
        try:
            md_files = list(d.glob("*.md"))
        except (FileNotFoundError, PermissionError):
            continue
        for f in md_files:
            try:
                fm = parse_frontmatter(f)
                ext_id = fm.get("id", "")
                existing = fm.get("impacts_modules", [])
                if isinstance(existing, list) and proposed_set & set(existing):
                    colliding.append(ext_id)
            except _RECOVERABLE_ERRORS as e:
                print(
                    f"Warning: skipping {f} during overlap check — "
                    f"{type(e).__name__}: {e}",
                    file=sys.stderr,
                )
    return colliding


def main() -> None:
    """CLI entry point for propose subcommands."""
    try:
        project_root = get_project_root()
        profile = get_effective_profile(project_root)
        profile_name = profile["name"]  # "poc", "prototype", "full", or "strict"
    except Exception:
        profile_name = "full"  # fallback: assume full profile outside a project root

    parser = argparse.ArgumentParser(
        prog="specbuilder propose",
        description="Propose-spec pre-flight checks.",
    )
    sub = parser.add_subparsers(dest="subcmd", required=True)

    p_validate = sub.add_parser(
        "validate", help="Validate a proposal file's frontmatter and required sections."
    )
    p_validate.add_argument(
        "file", type=Path, nargs="?", default=None,
        help="Path to proposal .md file (omit when using --pre-write with stdin).",
    )
    p_validate.add_argument(
        "--pre-write",
        metavar="FRONTMATTER_JSON",
        help=(
            "Validate frontmatter before writing to disk. "
            "Pass a JSON string or '-' to read from stdin. "
            "Invokes the in-memory validator (propose.validate_proposal())."
        ),
    )

    p_collision = sub.add_parser("check-collision", help="Check if an EXT number is already taken.")
    p_collision.add_argument("root", type=Path, help="Proposals root directory.")
    p_collision.add_argument("ext_id", metavar="ext-id", help="Proposed EXT ID, e.g. EXT-199.")

    p_overlap = sub.add_parser(
        "check-overlap", help="Find proposals that touch any of the given module IDs."
    )
    p_overlap.add_argument("root", type=Path, help="Proposals root directory.")
    p_overlap.add_argument(
        "modules", nargs="+", help="Module IDs to check for overlap (e.g. MOD-04)."
    )

    p_range = sub.add_parser(
        "check-range",
        help="Validate a range of EXT IDs against the proposals directory.",
    )
    p_range.add_argument("root", type=Path, help="Proposals root directory.")
    p_range.add_argument(
        "start_id", metavar="start-id", help="Start of the EXT ID range, e.g. EXT-022."
    )
    p_range.add_argument(
        "end_id",
        metavar="end-id",
        nargs="?",
        help="End of the EXT ID range (inclusive). If omitted, validates a single ID.",
    )

    args = parser.parse_args()

    if args.subcmd == "validate":
        if getattr(args, "pre_write", None):
            import json
            raw = sys.stdin.read() if args.pre_write == "-" else args.pre_write
            try:
                frontmatter = json.loads(raw)
            except json.JSONDecodeError as exc:
                print(f"ERROR: cannot parse frontmatter JSON: {exc}")
                sys.exit(1)
            errors = validate_proposal(frontmatter)  # in-memory validator (propose.py:29)
            if errors:
                for e in errors:
                    print(f"  ERROR: {e}")
                sys.exit(1)
            print("OK (pre-write check)")
        else:
            errors = validate_proposal_file(args.file)
            if errors:
                for e in errors:
                    print(f"  ERROR: {e}")
                sys.exit(1)
            print("OK")
            if profile_name in ("poc", "prototype"):
                print("Note: propose validate is optional in poc/prototype mode.")

    elif args.subcmd == "check-collision":
        if check_ext_collision(args.root, args.ext_id):
            print(f"COLLISION: {args.ext_id} already exists.")
            sys.exit(1)
        print(f"OK: {args.ext_id} is available.")

    elif args.subcmd == "check-overlap":
        colliding = check_scope_overlap(args.root, args.modules)
        if colliding:
            print(f"OVERLAP: {', '.join(colliding)}")
            sys.exit(1)
        print("OK: no scope overlap.")

    elif args.subcmd == "check-range":
        _id_pattern = _re.compile(r"^EXT-(\d+)$")
        start_match = _id_pattern.match(args.start_id)
        if not start_match:
            print(f"ERROR: '{args.start_id}' is not a valid EXT ID (expected EXT-NNN)")
            sys.exit(1)
        start_num = int(start_match.group(1))

        if args.end_id is not None:
            end_match = _id_pattern.match(args.end_id)
            if not end_match:
                print(f"ERROR: '{args.end_id}' is not a valid EXT ID (expected EXT-NNN)")
                sys.exit(1)
            end_num = int(end_match.group(1))
        else:
            end_num = start_num

        if end_num < start_num:
            print(f"ERROR: end ID '{args.end_id}' must be >= start ID '{args.start_id}'")
            sys.exit(1)

        any_collision = False
        for num in range(start_num, end_num + 1):
            ext_id = f"EXT-{num:03d}"
            if check_ext_collision(args.root, ext_id):
                print(f"COLLISION: {ext_id} already exists.")
                any_collision = True
            else:
                print(f"OK: {ext_id} is available.")

        if any_collision:
            sys.exit(1)


if __name__ == "__main__":
    main()

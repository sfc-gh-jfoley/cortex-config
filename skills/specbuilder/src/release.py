"""Release helper for SpecBuilder — automates version bumping and changelog creation.

Determines the next version based on semver rules and the changelog entry type,
creates a new changelog entry template, and optionally runs generate_index to
propagate the version everywhere.

Usage:
    python3 -m specbuilder.release bump [major|minor|patch]
    python3 -m specbuilder.release bump --type feature   # auto: minor
    python3 -m specbuilder.release bump --type fix       # auto: patch
    python3 -m specbuilder.release current               # print current version
    python3 -m specbuilder.release next --type feature   # print what next would be

Semver rules by changelog type:
    feature    → minor bump (1.1.0 → 1.2.0)
    fix        → patch bump (1.1.0 → 1.1.1)
    pattern    → patch bump (1.1.0 → 1.1.1)
    governance → patch bump (1.1.0 → 1.1.1)
"""

import argparse
import sys
from datetime import date
from pathlib import Path

from specbuilder.src.config import get_project_root

# ---------------------------------------------------------------------------
# Version resolution
# ---------------------------------------------------------------------------

# Semver bump rules per changelog type
TYPE_BUMP_MAP = {
    "feature": "minor",
    "fix": "patch",
    "pattern": "patch",
    "governance": "patch",
}


def get_current_version(project_root: Path | None = None) -> str:
    """Get the current version from the latest changelog entry.

    Returns:
        Version string (e.g., "1.1.0"). Returns "0.0.0" if no changelog.
    """
    if project_root is None:
        project_root = get_project_root()

    import re

    changelog_dir = project_root / "spec" / "changelog"
    if not changelog_dir.exists():
        return "0.0.0"

    for f in sorted(changelog_dir.glob("*.md"), reverse=True):
        content = f.read_text(encoding="utf-8")
        match = re.search(r'^version:\s*"?([^"\n]+)"?', content, re.MULTILINE)
        if match:
            return match.group(1).strip()

    return "0.0.0"


def bump_version(version: str, bump_type: str) -> str:
    """Apply a semver bump to a version string.

    Args:
        version: Current version (e.g., "1.1.0")
        bump_type: One of "major", "minor", "patch"

    Returns:
        New version string.
    """
    parts = version.split(".")
    if len(parts) != 3:
        parts = ["0", "0", "0"]

    major, minor, patch = int(parts[0]), int(parts[1]), int(parts[2])

    if bump_type == "major":
        return f"{major + 1}.0.0"
    elif bump_type == "minor":
        return f"{major}.{minor + 1}.0"
    elif bump_type == "patch":
        return f"{major}.{minor}.{patch + 1}"
    else:
        raise ValueError(f"Invalid bump_type: {bump_type}. Must be major/minor/patch.")


def get_next_changelog_number(project_root: Path) -> int:
    """Determine the next changelog entry number."""
    changelog_dir = project_root / "spec" / "changelog"
    if not changelog_dir.exists():
        return 1

    existing = sorted(changelog_dir.glob("*.md"))
    if not existing:
        return 1

    # Extract number from last file: "014-foo.md" → 14
    last = existing[-1].stem
    try:
        num = int(last.split("-")[0])
        return num + 1
    except (ValueError, IndexError):
        return len(existing) + 1


# ---------------------------------------------------------------------------
# Changelog entry creation
# ---------------------------------------------------------------------------

_CHANGELOG_TEMPLATE = """---
id: CLG-{num:03d}
title: "{title}"
version: "{version}"
date: {date}
affected_modules: [{modules}]
type: {type}
---

## Context

{context}

## Changes

- TODO: List specific changes

## Reasoning

TODO: Explain why this approach was chosen.
"""


def create_changelog_entry(
    project_root: Path,
    title: str,
    entry_type: str,
    version: str,
    affected_modules: list[str] | None = None,
    context: str = "TODO: Describe what prompted this change.",
) -> Path:
    """Create a new changelog entry file.

    Args:
        project_root: Project root directory.
        title: Short description of the change.
        entry_type: One of: feature, fix, pattern, governance.
        version: Version string for this entry.
        affected_modules: List of module IDs affected (e.g., ["MOD-01", "SKILL"]).
        context: Context paragraph for the entry.

    Returns:
        Path to the created changelog file.
    """
    changelog_dir = project_root / "spec" / "changelog"
    changelog_dir.mkdir(parents=True, exist_ok=True)

    import re as _re_slug

    num = get_next_changelog_number(project_root)
    # Strip to ASCII lowercase + digits + hyphens only (matches ARCH_FILE_PATTERN)
    slug = _re_slug.sub(r"[^a-z0-9-]", "", title.lower().replace(" ", "-"))
    slug = _re_slug.sub(r"-+", "-", slug)[:40].strip("-")
    filename = f"{num:03d}-{slug}.md"
    filepath = changelog_dir / filename

    modules_str = ", ".join(affected_modules) if affected_modules else "SKILL"

    content = _CHANGELOG_TEMPLATE.format(
        num=num,
        title=title,
        version=version,
        date=date.today().isoformat(),
        modules=modules_str,
        type=entry_type,
        context=context,
    )

    filepath.write_text(content, encoding="utf-8")
    return filepath


# ---------------------------------------------------------------------------
# Sign-off automation
# ---------------------------------------------------------------------------


def sign_off(
    module_num: int,
    project_root: Path | None = None,
    entry_type: str = "feature",
    dry_run: bool = False,
    confirm: bool = False,
) -> Path | None:
    """Transition a module to 'implemented' and create a changelog entry.

    This is the automated counterpart to the manual `bump` command. It reads
    the module's spec to derive the changelog title and context, bumps the
    version, creates the changelog entry, and updates the spec frontmatter
    status to 'implemented'.

    Args:
        module_num: Module number (e.g., 1 for MOD-01).
        project_root: Project root directory (auto-detected if None).
        entry_type: Changelog type (feature, fix, pattern, governance).
        dry_run: If True, print what would happen without writing files.
        confirm: Must be True for live sign-off (required unless dry_run is True).

    Returns:
        Path to the created changelog file, or None if dry_run.
        Exits with code 1 if confirm is False and dry_run is False.
    """
    if not dry_run and not confirm:
        print(
            "sign-off blocked: pass --confirm to attest that you have reviewed "
            "the test report and approve this sign-off.",
            file=sys.stderr,
        )
        sys.exit(1)

    import re as _re

    if project_root is None:
        project_root = get_project_root()

    from specbuilder.src.config import DEFAULT_MODULES_DIR, is_poc_mode
    from specbuilder.src.validation import parse_frontmatter

    # Find the spec file
    modules_dir = project_root / DEFAULT_MODULES_DIR
    pattern = f"{module_num:02d}-*.md"
    matches = list(modules_dir.glob(pattern))

    if not matches:
        print(f"Error: No spec file matching {pattern} in {modules_dir}", file=sys.stderr)
        return None

    spec_path = matches[0]
    fm = parse_frontmatter(spec_path)

    if not fm:
        print(f"Error: Could not parse frontmatter from {spec_path}", file=sys.stderr)
        return None

    module_id = fm.get("id", f"MOD-{module_num:02d}")
    title = fm.get("title", spec_path.stem)
    status = fm.get("status", "")

    if status == "implemented":
        print(f"Module {module_id} is already implemented.", file=sys.stderr)
        return None

    allowed_statuses = {"accepted", "in-review"} if is_poc_mode(project_root) else {"accepted"}
    if status not in allowed_statuses:
        if status == "in-review" and not is_poc_mode(project_root):
            print(
                "Cannot sign off module with status 'in-review' in non-POC mode. "
                "Module must be in 'accepted' status. Run 'release accept <module>' first, "
                "or use POC mode for the collapsed lifecycle."
            )
        else:
            print(f"Cannot sign off module with status '{status}'.")
        return None

    # Determine version bump
    current = get_current_version(project_root)
    bump_level = TYPE_BUMP_MAP.get(entry_type, "minor")
    next_ver = bump_version(current, bump_level)

    # Derive context from spec's Executive Summary (first paragraph after the heading)
    spec_content = spec_path.read_text(encoding="utf-8")
    summary_match = _re.search(
        r"## Executive Summary\s*\n+(.*?)(?=\n##|\Z)", spec_content, _re.DOTALL
    )
    context = (
        summary_match.group(1).strip()
        if summary_match
        else f"Implementation of {title} ({module_id})."
    )
    # Truncate overly long context
    if len(context) > 300:
        context = context[:297] + "..."

    changelog_title = f"{title} ({module_id})"

    # Step 0: breaking-drift gate (SKILL.md:146–150)
    from specbuilder.src.diff import diff_spec
    drift_result = diff_spec(module_num, project_root)
    if drift_result.get("summary", {}).get("breaking", 0) > 0:
        breaking_count = drift_result["summary"]["breaking"]
        print(
            f"sign-off blocked: {breaking_count} breaking spec change(s) detected. "
            "Resolve or document all breaking changes before signing off.",
            file=sys.stderr,
        )
        return None

    # Pre-flight: AC gate
    from specbuilder.src.test_acceptance import run_tests
    test_summary = run_tests(module_num, project_root)
    if test_summary.get("summary", {}).get("fail", 0) > 0:
        fail_count = test_summary["summary"]["fail"]
        print(
            f"sign-off blocked: {fail_count} acceptance test(s) failing. "
            "Fix all ACs before signing off.",
            file=sys.stderr,
        )
        return None

    # Pre-flight: quality gate
    from specbuilder.src.config import (
        QUALITY_GATE_THRESHOLD,
        QUALITY_PROFILES,
        get_effective_profile,
    )
    from specbuilder.src.spec_quality import assess_quality
    quality_result = assess_quality(spec_path)
    profile = get_effective_profile(project_root)
    threshold = profile.get(
        "threshold",
        QUALITY_PROFILES.get(profile.get("name", "full"), {}).get(
            "threshold", QUALITY_GATE_THRESHOLD
        ),
    )
    if quality_result.get("score", 0) < threshold:
        print(
            f"sign-off blocked: quality score {quality_result['score']:.0f} below "
            f"threshold {threshold}. Resolve quality findings before signing off.",
            file=sys.stderr,
        )
        return None

    if dry_run:
        print(f"[dry-run] Would sign off {module_id}: '{title}'")
        print(f"[dry-run] Version: {current} → {next_ver} ({bump_level} from --type={entry_type})")
        print(f"[dry-run] Changelog: CLG-{get_next_changelog_number(project_root):03d}")
        print(f"[dry-run] Context: {context[:80]}...")
        return None

    # Create changelog entry
    filepath = create_changelog_entry(
        project_root=project_root,
        title=changelog_title,
        entry_type=entry_type,
        version=next_ver,
        affected_modules=[module_id],
        context=context,
    )

    # Atomically update spec frontmatter; rollback changelog on any failure
    try:
        fm_match = _re.match(r'^(---[\r\n]+.*?[\r\n]+---[\r\n]+)', spec_content, _re.DOTALL)
        if not fm_match:
            raise ValueError(
                f"Cannot update status: no YAML frontmatter found in {spec_path}. "
                "Expected file to begin with '---'."
            )
        old_fm = fm_match.group(1)
        new_fm = _re.sub(
            r'^(status:\s*).*$', r'\g<1>implemented', old_fm,
            count=1, flags=_re.MULTILINE
        )
        today = str(date.today())
        if _re.search(r'^last_updated:\s*', new_fm, _re.MULTILINE):
            new_fm = _re.sub(
                r'^(last_updated:\s*).*$',
                f'\\g<1>{today}',
                new_fm,
                flags=_re.MULTILINE,
            )
        else:
            # Insert last_updated immediately after the status line
            new_fm = _re.sub(
                r'^(status:\s*implemented.*)$',
                f'\\g<1>\nlast_updated: {today}',
                new_fm,
                flags=_re.MULTILINE,
            )
        updated_content = new_fm + spec_content[len(old_fm):]
        spec_path.write_text(updated_content, encoding="utf-8")
    except Exception:
        if filepath.exists():
            filepath.unlink()
        raise

    # Regenerate index — isolated so a failure here does not roll back a completed sign-off
    try:
        from specbuilder.src.generate_index import generate
        generate(project_root=project_root)
    except Exception as exc:
        print(f"Warning: manifest index not updated — {exc}", file=sys.stderr)

    # POC mode: auto-generate summary artifact (EXT-037)
    from specbuilder.src.config import get_handover_flag

    if is_poc_mode(project_root):
        from specbuilder.src.poc_summary import generate_summary

        result = generate_summary(project_root)
        if result is not None:
            print("POC Summary generated: spec/POC-SUMMARY.md")

    # Handover flag: auto-generate handover module (EXT-071 / EXT-193)
    if get_handover_flag(project_root):
        from specbuilder.src.demo_orchestrator import demo_handover

        exit_code = demo_handover(str(module_num), project_root)
        if exit_code == 0:
            print("Demo handover generated.")
        else:
            print(
                f"Warning: demo handover generation failed (exit code {exit_code}).",
                file=sys.stderr,
            )
            # Sign-off itself succeeded — emit confirmation before returning
            print(f"Signed off {module_id}: '{title}'")
            print(f"  Version: {current} → {next_ver}")
            print(f"  Changelog: {filepath.relative_to(project_root)}")
            print("  Spec status: → implemented")
            return filepath              # return filepath even when handover step failed

    print(f"Signed off {module_id}: '{title}'")
    print(f"  Version: {current} → {next_ver}")
    print(f"  Changelog: {filepath.relative_to(project_root)}")
    print("  Spec status: → implemented")

    return filepath


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="SpecBuilder release helper — version bumping and changelog creation.",
    )
    subparsers = parser.add_subparsers(dest="command")

    # current
    subparsers.add_parser("current", help="Print the current version")

    # next
    next_p = subparsers.add_parser("next", help="Print what the next version would be")
    next_p.add_argument(
        "--type", choices=TYPE_BUMP_MAP.keys(), help="Changelog entry type (determines bump)"
    )
    next_p.add_argument(
        "bump_level",
        nargs="?",
        choices=["major", "minor", "patch"],
        help="Explicit bump level (overrides --type)",
    )

    # bump
    bump_p = subparsers.add_parser("bump", help="Bump version and create changelog entry")
    bump_p.add_argument(
        "bump_level",
        nargs="?",
        choices=["major", "minor", "patch"],
        help="Explicit bump level (overrides --type)",
    )
    bump_p.add_argument(
        "--type",
        choices=TYPE_BUMP_MAP.keys(),
        default="feature",
        help="Changelog entry type (default: feature)",
    )
    bump_p.add_argument("--title", required=True, help="Short description of the change")
    bump_p.add_argument("--modules", nargs="*", help="Affected module IDs (e.g., MOD-01 SKILL)")
    bump_p.add_argument("--context", default=None, help="Context paragraph for the changelog entry")
    bump_p.add_argument(
        "--no-generate", action="store_true", help="Skip running generate_index after bump"
    )

    # sign-off
    so_p = subparsers.add_parser(
        "sign-off", help="Sign off a module and auto-create changelog entry"
    )
    so_p.add_argument("module_num", type=int, help="Module number to sign off (e.g., 1 for MOD-01)")
    so_p.add_argument(
        "--type",
        choices=TYPE_BUMP_MAP.keys(),
        default="feature",
        help="Changelog entry type (default: feature)",
    )
    so_p.add_argument(
        "--dry-run", action="store_true", help="Show what would happen without writing files"
    )
    so_p.add_argument(
        "--confirm",
        action="store_true",
        help=(
            "Confirm that you have reviewed the test report and approve sign-off. "
            "Required unless --dry-run is set."
        ),
    )

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)

    project_root = get_project_root()
    current = get_current_version(project_root)

    if args.command == "current":
        print(current)
        return

    if args.command == "next":
        level = args.bump_level or TYPE_BUMP_MAP.get(
            getattr(args, "type", None) or "feature", "minor"
        )
        next_ver = bump_version(current, level)
        print(next_ver)
        return

    if args.command == "bump":
        level = args.bump_level or TYPE_BUMP_MAP.get(args.type, "minor")
        next_ver = bump_version(current, level)

        print(f"Current version: {current}")
        print(f"Bump type: {level} (from --type={args.type})")
        print(f"New version: {next_ver}")
        print()

        context = args.context or "TODO: Describe what prompted this change."
        filepath = create_changelog_entry(
            project_root=project_root,
            title=args.title,
            entry_type=args.type,
            version=next_ver,
            affected_modules=args.modules,
            context=context,
        )

        print(f"Created: {filepath.relative_to(project_root)}")

        if not args.no_generate:
            print("\nRunning generate_index to propagate version...")
            from specbuilder.src.generate_index import generate

            exit_code = generate(project_root=project_root)
            if exit_code == 0:
                print(f"\nVersion {next_ver} propagated to SKILL.md and manifest.")
            else:
                print("Warning: generate_index reported errors.", file=sys.stderr)
        else:
            print(f"\nSkipped generate_index. Run manually to propagate version {next_ver}.")

        return

    if args.command == "sign-off":
        sign_off(
            module_num=args.module_num,
            project_root=project_root,
            entry_type=args.type,
            dry_run=args.dry_run,
            confirm=args.confirm,
        )
        return

    parser.print_help()


if __name__ == "__main__":
    main()

"""CI integration for SpecBuilder — vendor-agnostic git-based drift checks.

Provides three subcommands:
- --check-drift: Compare branch changes against spec state (exit 1 if drift)
- --promote-merged: Transition draft specs to accepted after merge
- --pr-context: Output markdown summary of affected specs for PR descriptions

All operations use git subprocess calls only — no vendor SDK dependencies.

Usage:
    python3 -m specbuilder ci --check-drift --base=main [--head=HEAD] [--format=plain|github|gitlab]
    python3 -m specbuilder ci --promote-merged [--no-commit] [--base=main]
    python3 -m specbuilder ci --pr-context [--base=main] [--head=HEAD]
"""

import argparse
import subprocess
import sys
from pathlib import Path

from specbuilder.src.config import (
    CI_ANNOTATION_FORMAT,
    DEFAULT_MODULES_DIR,
    DEFAULT_PROTECTED_DIRS,
    DEFAULT_SPEC_DIR,
    get_project_root,
)
from specbuilder.src.validation import parse_frontmatter

# ---------------------------------------------------------------------------
# Git helpers
# ---------------------------------------------------------------------------


def _git(args: list[str], project_root: Path) -> subprocess.CompletedProcess:
    """Run a git command and return the result."""
    return subprocess.run(
        ["git", "-C", str(project_root)] + args,
        capture_output=True,
        text=True,
        timeout=30,
    )


def _get_changed_files(base: str, head: str, project_root: Path) -> list[str]:
    """Get list of files changed between base and head using three-dot diff.

    Returns relative paths as strings. Returns empty list if git is unavailable
    or times out.
    """
    try:
        result = _git(["diff", "--name-only", f"{base}...{head}"], project_root)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []
    if result.returncode != 0:
        # Fallback to two-dot diff if three-dot fails (e.g., no common ancestor)
        try:
            result = _git(["diff", "--name-only", base, head], project_root)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return []
        if result.returncode != 0:
            print(f"Error: git diff failed: {result.stderr.strip()}", file=sys.stderr)
            return []
    return [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]


def _is_protected_file(filepath: str) -> bool:
    """Check if a file is in a protected (implementation) directory."""
    for protected in DEFAULT_PROTECTED_DIRS:
        if filepath.startswith(protected):
            return True
    return False


def _is_spec_file(filepath: str) -> bool:
    """Check if a file is in the spec directory."""
    return filepath.startswith(DEFAULT_SPEC_DIR + "/")


def _is_non_behavioral(filepath: str) -> bool:
    """Check if a file change is non-behavioral (should not trigger drift).

    Non-behavioral: READMEs, comments-only, formatting, docs, config that
    doesn't affect runtime behavior.
    """
    name = Path(filepath).name.lower()
    non_behavioral_patterns = [
        "readme",
        "changelog",
        "license",
        ".gitignore",
        ".pre-commit",
        "pyproject.toml",  # dependency changes, not logic
    ]
    return any(pattern in name for pattern in non_behavioral_patterns)


# ---------------------------------------------------------------------------
# Spec ↔ implementation mapping
# ---------------------------------------------------------------------------


def _get_spec_modules(project_root: Path) -> list[dict]:
    """Load all spec modules with frontmatter metadata."""
    modules_dir = project_root / DEFAULT_MODULES_DIR
    if not modules_dir.is_dir():
        return []

    modules = []
    for filepath in sorted(modules_dir.glob("[0-9][0-9]-*.md")):
        if filepath.name.startswith("00-"):
            continue
        fm = parse_frontmatter(filepath)
        stem = filepath.stem
        number = stem.split("-", 1)[0]
        slug = stem.split("-", 1)[1] if "-" in stem else stem

        modules.append(
            {
                "number": number,
                "slug": slug,
                "title": fm.get("title", stem),
                "status": fm.get("status", "unknown"),
                "version": fm.get("version", "0.0.0"),
                "file_path": filepath,
                "rel_path": str(filepath.relative_to(project_root)),
            }
        )
    return modules


def _match_impl_to_spec(impl_file: str, modules: list[dict]) -> dict | None:
    """Find which spec module owns an implementation file (by slug convention).

    Module slug "detect-drift" matches files containing "detect_drift".
    """
    for mod in modules:
        normalized_slug = mod["slug"].replace("-", "_")
        normalized_file = Path(impl_file).stem.replace("-", "_")
        if normalized_slug in normalized_file:
            return mod
    return None


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------


def check_drift(
    base: str,
    head: str,
    project_root: Path,
    annotation_format: str = "plain",
) -> int:
    """Check if implementation changed without corresponding spec updates.

    Returns exit code: 0 = no drift, 1 = drift detected.
    """
    changed_files = _get_changed_files(base, head, project_root)
    if not changed_files:
        print("No files changed between base and head.")
        return 0

    # Separate into spec files and implementation files
    spec_changes = [f for f in changed_files if _is_spec_file(f)]
    impl_changes = [f for f in changed_files if _is_protected_file(f) and not _is_non_behavioral(f)]

    if not impl_changes:
        print("No implementation files changed. No drift possible.")
        return 0

    # Load spec modules
    modules = _get_spec_modules(project_root)
    spec_slugs_changed = set()
    for sf in spec_changes:
        stem = Path(sf).stem
        if "-" in stem:
            slug = stem.split("-", 1)[1]
            spec_slugs_changed.add(slug.replace("-", "_"))

    # Check each impl change for a corresponding spec change
    drift_findings = []
    for impl_file in impl_changes:
        owning_module = _match_impl_to_spec(impl_file, modules)
        if owning_module is None:
            # No spec owns this file — that's a coverage gap, not drift
            continue

        # Check if the owning spec was also modified in this branch
        mod_slug_normalized = owning_module["slug"].replace("-", "_")
        if mod_slug_normalized not in spec_slugs_changed:
            drift_findings.append(
                {
                    "impl_file": impl_file,
                    "module": owning_module,
                    "reason": "Implementation changed without spec update",
                }
            )

    if not drift_findings:
        print(f"No drift detected. ({len(impl_changes)} impl file(s) checked)")
        return 0

    # Report findings
    print(f"Drift detected: {len(drift_findings)} file(s) changed without spec updates\n")
    for finding in drift_findings:
        mod = finding["module"]  # type: ignore[index]
        msg = f"{mod['rel_path']} → {finding['impl_file']} changed without spec update"  # type: ignore[index]

        if annotation_format == "github":
            print(f"::error file={finding['impl_file']}::{msg}")
        elif annotation_format == "gitlab":
            print(f"ERROR: {msg}")
        else:
            print(f"[DRIFT] {msg}")

    return 1


def promote_merged(
    base: str,
    project_root: Path,
    no_commit: bool = False,
    use_branch: bool = False,
) -> int:
    """Promote draft specs that were merged to base branch to 'accepted'.

    Looks for spec/modules/*.md files with status: draft on the current HEAD
    that don't exist on the base branch (i.e., newly added in this merge).

    Returns exit code: 0 = success, 1 = error.
    """
    import re

    modules = _get_spec_modules(project_root)
    promoted = []

    for mod in modules:
        if mod["status"] != "draft":
            continue

        # Check if this file existed on the base branch
        rel_path = mod["rel_path"]
        result = _git(["cat-file", "-e", f"{base}:{rel_path}"], project_root)
        if result.returncode == 0:
            # File existed on base — not newly merged, skip
            continue

        # This is a new draft spec not on base → promote to accepted
        spec_path = mod["file_path"]
        content = spec_path.read_text(encoding="utf-8")
        updated = re.sub(
            r"^(status:\s*)draft\s*$",
            r"\1accepted",
            content,
            count=1,
            flags=re.MULTILINE,
        )

        if updated == content:
            print(f"Warning: Could not find 'status: draft' in {rel_path}", file=sys.stderr)
            continue

        spec_path.write_text(updated, encoding="utf-8")
        promoted.append(mod)
        print(f"Promoted: {mod['title']} ({rel_path}) → accepted")

    if not promoted:
        print("No draft specs to promote.")
        return 0

    if no_commit:
        print(f"\n{len(promoted)} spec(s) promoted. --no-commit: skipping git commit.")
        return 0

    # Create a branch if requested (respects branch protection)
    branch_name = None
    if use_branch:
        from datetime import datetime

        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        branch_name = f"specbuilder/promote-{timestamp}"
        result = _git(["checkout", "-b", branch_name], project_root)
        if result.returncode != 0:
            print(
                f"Error: could not create branch '{branch_name}': {result.stderr.strip()}",
                file=sys.stderr,
            )
            return 1

    # Commit the changes
    for mod in promoted:
        _git(["add", mod["rel_path"]], project_root)

    commit_msg = f"chore(spec): promote {len(promoted)} spec(s) to accepted after merge"
    result = _git(["commit", "-m", commit_msg], project_root)
    if result.returncode != 0:
        print(f"Error: git commit failed: {result.stderr.strip()}", file=sys.stderr)
        return 1

    if branch_name:
        print(f"\n{len(promoted)} spec(s) promoted on branch '{branch_name}'.")
        print(f"Push and open a PR to complete: git push -u origin {branch_name}")
    else:
        print(f"\n{len(promoted)} spec(s) promoted and committed. Push to complete.")
    return 0


def pr_context(
    base: str,
    head: str,
    project_root: Path,
) -> int:
    """Output markdown summary of specs affected by this branch.

    Suitable for inclusion in a PR description.

    Returns exit code: 0 always.
    """
    changed_files = _get_changed_files(base, head, project_root)
    modules = _get_spec_modules(project_root)

    # Find directly modified specs
    modified_specs = set()
    for f in changed_files:
        if _is_spec_file(f) and f.startswith(DEFAULT_MODULES_DIR):
            stem = Path(f).stem
            if "-" in stem:
                slug = stem.split("-", 1)[1]
                modified_specs.add(slug)

    # Find referenced specs (impl files that map to a spec)
    referenced_specs = set()
    impl_changes = [f for f in changed_files if _is_protected_file(f)]
    for impl_file in impl_changes:
        owning = _match_impl_to_spec(impl_file, modules)
        if owning and owning["slug"] not in modified_specs:
            referenced_specs.add(owning["slug"])

    # Check drift status
    has_drift = False
    for impl_file in impl_changes:
        if _is_non_behavioral(impl_file):
            continue
        owning = _match_impl_to_spec(impl_file, modules)
        if owning:
            slug_norm = owning["slug"].replace("-", "_")
            spec_slugs = {s.replace("-", "_") for s in modified_specs}
            if slug_norm not in spec_slugs:
                has_drift = True
                break

    # Output markdown
    print("## Affected Specs\n")
    if not modified_specs and not referenced_specs:
        print("_No spec modules affected by this branch._\n")
    else:
        for mod in modules:
            if mod["slug"] in modified_specs:
                print(f"- {mod['title']} (v{mod['version']}) — **modified**")
            elif mod["slug"] in referenced_specs:
                print(f"- {mod['title']} (v{mod['version']}) — referenced")

    print("\n## Drift Status\n")
    if has_drift:
        print("⚠ Implementation changes detected without corresponding spec updates")
    else:
        print("✓ All implementation changes have corresponding spec updates")

    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "SpecBuilder CI integration — vendor-agnostic"
            " drift detection and spec lifecycle."
        ),
    )
    parser.add_argument(
        "--check-drift",
        action="store_true",
        help="Check for implementation drift (exit 1 if found)",
    )
    parser.add_argument(
        "--promote-merged",
        action="store_true",
        help="Promote draft specs to accepted after merge",
    )
    parser.add_argument(
        "--pr-context",
        action="store_true",
        help="Output affected-specs markdown for PR descriptions",
    )
    parser.add_argument(
        "--base",
        default="main",
        help="Base branch for comparison (default: main)",
    )
    parser.add_argument(
        "--head",
        default="HEAD",
        help="Head ref for comparison (default: HEAD)",
    )
    parser.add_argument(
        "--format",
        choices=["plain", "github", "gitlab"],
        default=None,
        help=f"Annotation format (default: from config, currently '{CI_ANNOTATION_FORMAT}')",
    )
    parser.add_argument(
        "--no-commit",
        action="store_true",
        help="For --promote-merged: edit files but skip git commit",
    )
    parser.add_argument(
        "--branch",
        action="store_true",
        help=(
            "For --promote-merged: create a new branch for the"
            " promotion commit (respects branch protection)"
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    """CLI entry point."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    if not (args.check_drift or args.promote_merged or args.pr_context):
        parser.print_help()
        sys.exit(0)

    project_root = get_project_root()
    fmt = args.format or CI_ANNOTATION_FORMAT

    if args.check_drift:
        exit_code = check_drift(args.base, args.head, project_root, fmt)
        sys.exit(exit_code)
    elif args.promote_merged:
        exit_code = promote_merged(args.base, project_root, args.no_commit, args.branch)
        sys.exit(exit_code)
    elif args.pr_context:
        exit_code = pr_context(args.base, args.head, project_root)
        sys.exit(exit_code)


if __name__ == "__main__":
    main()

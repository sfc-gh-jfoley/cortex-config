"""Drift detection between specs and their implementations (MOD-06).

Compares spec state against implementation reality and produces an
actionable report identifying divergence, staleness, and coverage gaps.
"""

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from specbuilder.src.config import (
    DEFAULT_AC_DIR,
    DEFAULT_MODULES_DIR,
    DEFAULT_PROTECTED_DIRS,
    DRIFT_STALENESS_DAYS,
    SPEC_FILE_PATTERN,
    get_project_root,
)
from specbuilder.src.validation import parse_frontmatter

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get_spec_modules(project_root: Path) -> list[dict]:
    """Load all spec/NN-*.md (excluding 00) frontmatter and metadata.

    Returns a list of dicts with keys:
        number, slug, title, status, last_updated, file_path
    """
    spec_dir = project_root / DEFAULT_MODULES_DIR
    if not spec_dir.is_dir():
        return []

    modules: list[dict] = []
    for filepath in sorted(spec_dir.glob("[0-9][0-9]-*.md")):
        if filepath.name.startswith("00-"):
            continue
        if not SPEC_FILE_PATTERN.match(filepath.name):
            continue

        fm = parse_frontmatter(filepath)
        stem = filepath.stem  # e.g. "01-scaffold"
        number = stem.split("-", 1)[0]
        slug = stem.split("-", 1)[1] if "-" in stem else stem

        modules.append(
            {
                "number": number,
                "slug": slug,
                "title": fm.get("title", stem),
                "status": fm.get("status", "unknown"),
                "last_updated": fm.get("last_updated", ""),
                "file_path": filepath,
            }
        )
    return modules


_IMPL_EXTENSIONS = {".py", ".sql", ".yaml", ".yml", ".js", ".ts"}


def _get_implementation_files(project_root: Path) -> list[Path]:
    """Scan protected directories for implementation files.

    Recognised extensions: .py, .sql, .yaml, .yml, .js, .ts (per EXT-126 ratified scope).
    Returns all matching files found under the configured protected directories.
    """
    impl_files: list[Path] = []
    for dirname in DEFAULT_PROTECTED_DIRS:
        search_dir = project_root / dirname
        if search_dir.is_dir():
            for filepath in sorted(search_dir.rglob("*")):
                if filepath.is_file() and filepath.suffix in _IMPL_EXTENSIONS:
                    if not filepath.name.startswith("__"):
                        impl_files.append(filepath)
    return impl_files


def _module_matches_file(slug: str, filepath: Path) -> bool:
    """Check if a module slug matches an implementation file by convention.

    Module "01-scaffold" maps to files containing "scaffold" in their name.
    Multi-word slugs like "detect-drift" match "detect_drift" (hyphen/underscore).
    """
    normalized_slug = slug.replace("-", "_")
    normalized_name = filepath.stem.replace("-", "_")
    return normalized_slug in normalized_name


def _check_post_signoff_changes(
    project_root: Path,
    impl_files: list[Path],
    signoff_date: str,
) -> list[dict]:
    """Check if implementation files were modified after a signoff date.

    Uses ``git log`` to find commits touching *impl_files* after
    *signoff_date*. Returns a list of dicts with ``file`` and
    ``last_modified`` keys for each file changed post-signoff.

    Returns an empty list when git is unavailable or errors out.
    """
    if not impl_files or not signoff_date:
        return []

    changed: list[dict] = []
    for filepath in impl_files:
        try:
            rel_path = filepath.relative_to(project_root)
        except ValueError:
            rel_path = filepath

        try:
            result = subprocess.run(
                [
                    "git",
                    "-C",
                    str(project_root),
                    "log",
                    "--oneline",
                    f"--since={signoff_date}",
                    "--",
                    str(rel_path),
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0 and result.stdout.strip():
                # Get the actual last-modified date
                date_result = subprocess.run(
                    [
                        "git",
                        "-C",
                        str(project_root),
                        "log",
                        "-1",
                        "--format=%aI",
                        "--",
                        str(rel_path),
                    ],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                last_mod = date_result.stdout.strip() if date_result.returncode == 0 else "unknown"
                changed.append({"file": str(rel_path), "last_modified": last_mod})
        except FileNotFoundError:
            return []  # git not installed; no point continuing
        except subprocess.TimeoutExpired:
            print(
                f"Warning: git log timed out for {rel_path}; "
                "post-signoff drift check skipped for this file.",
                file=sys.stderr,
            )
            continue
        except OSError as exc:
            print(
                f"Warning: OS error checking {rel_path} for post-signoff drift ({exc}); skipping.",
                file=sys.stderr,
            )
            continue

    return changed


# ---------------------------------------------------------------------------
# Report formatters
# ---------------------------------------------------------------------------


def _format_report_markdown(
    divergences: list[dict],
    staleness: list[dict],
    gaps: list[dict],
) -> str:
    """Format drift findings as a markdown report with tables."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    lines: list[str] = []

    lines.append("# Spec Drift Report")
    lines.append("")
    lines.append(f"Generated: {now}")
    lines.append("")

    # -- Divergence --
    lines.append("## Divergence Issues (action required)")
    lines.append("")
    if divergences:
        lines.append("| Module | Issue | Severity | Action |")
        lines.append("|--------|-------|----------|--------|")
        for d in divergences:
            lines.append(f"| {d['module']} | {d['issue']} | {d['severity']} | {d['action']} |")
    else:
        lines.append("No divergence issues detected.")
    lines.append("")

    # -- Staleness --
    lines.append("## Staleness Warnings")
    lines.append("")
    if staleness:
        lines.append("| Module | Last Updated | Status | Days Stale |")
        lines.append("|--------|-------------|--------|------------|")
        for s in staleness:
            lines.append(
                f"| {s['module']} | {s['last_updated']} "
                f"| {s['status'].upper()} | {s['days_stale']} |"
            )
    else:
        lines.append("No staleness warnings.")
    lines.append("")

    # -- Coverage Gaps --
    lines.append("## Coverage Gaps")
    lines.append("")
    if gaps:
        lines.append("| Item | Missing | Severity |")
        lines.append("|------|---------|----------|")
        for g in gaps:
            lines.append(f"| {g['item']} | {g['missing']} | {g['severity']} |")
    else:
        lines.append("No coverage gaps detected.")
    lines.append("")

    # -- Summary --
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- {len(divergences)} divergence issue(s)")
    lines.append(f"- {len(staleness)} staleness warning(s)")
    lines.append(f"- {len(gaps)} coverage gap(s)")

    total_issues = len(divergences) + len(staleness) + len(gaps)
    if total_issues == 0:
        lines.append("- No drift detected")
    lines.append("")

    return "\n".join(lines)


def _flatten_drift_findings(
    divergences: list[dict],
    staleness: list[dict],
    gaps: list[dict],
) -> list[dict]:
    """Flatten the three drift category lists into a single findings list."""
    findings: list[dict] = []
    for item in divergences:
        findings.append({"category": "divergence", **item})
    for item in staleness:
        findings.append({"category": "staleness", **item})
    for item in gaps:
        findings.append({"category": "coverage_gap", **item})
    return findings


def _format_report_json(
    divergences: list[dict],
    staleness: list[dict],
    gaps: list[dict],
) -> str:
    """Format drift findings as a DiagnosticEnvelope JSON string."""
    from specbuilder.src.diagnostic_schema import wrap_findings
    flat = _flatten_drift_findings(divergences, staleness, gaps)
    return json.dumps(wrap_findings("detect-drift", flat), indent=2, default=str)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def detect_drift(
    project_root: Path | None = None,
    staleness_days: int = DRIFT_STALENESS_DAYS,
    check_git_history: bool = True,
    output_format: str = "markdown",
) -> str:
    """Compare spec state against implementation and return a drift report.

    Args:
        project_root: Project root directory (auto-detected if None).
        staleness_days: Days after which an unchanged draft/in-review spec
            is flagged as stale.
        check_git_history: Whether to use git log for post-sign-off checks.
        output_format: ``"markdown"`` or ``"json"``.

    Returns:
        Formatted drift report string.
    """
    root = project_root or get_project_root()

    spec_modules = _get_spec_modules(root)
    impl_files = _get_implementation_files(root)
    ac_dir = root / DEFAULT_AC_DIR

    divergences: list[dict] = []
    staleness_issues: list[dict] = []
    gaps: list[dict] = []

    today = datetime.now(timezone.utc).date()

    # Track which impl files are claimed by a spec module
    claimed_impl_files: set[Path] = set()

    for mod in spec_modules:
        slug = mod["slug"]
        status = mod["status"]
        module_label = f"MOD-{mod['number']}"

        # Find implementation files matching this module
        matched_files = [f for f in impl_files if _module_matches_file(slug, f)]
        claimed_impl_files.update(matched_files)

        # --- Divergence checks ---

        # Spec says "accepted" but no implementation files
        if status == "accepted" and not matched_files:
            divergences.append(
                {
                    "module": module_label,
                    "issue": 'Spec status "accepted" but no implementation files found',
                    "severity": "MEDIUM",
                    "action": "Begin implementation or update status",
                }
            )

        # Spec says "implemented" but files don't exist
        if status == "implemented" and not matched_files:
            divergences.append(
                {
                    "module": module_label,
                    "issue": 'Spec status "implemented" but implementation files don\'t exist',
                    "severity": "HIGH",
                    "action": "Locate implementation files or revert spec status",
                }
            )

        # Post-sign-off modification check (only for accepted/implemented with files)
        if check_git_history and status in ("accepted", "implemented") and matched_files:
            # NOTE: last_updated is set by sign_off() to date.today() during frontmatter update.
            # It is NOT a reliable sign-off timestamp: if last_updated was modified during a spec
            # edit (not sign-off), post-edit implementation changes will be incorrectly flagged.
            # If last_updated is absent, this check is silently skipped
            # (see signoff_date guard below).
            signoff_date = str(mod["last_updated"]) if mod["last_updated"] else ""
            if signoff_date:
                post_changes = _check_post_signoff_changes(root, matched_files, signoff_date)
                for change in post_changes:
                    divergences.append(
                        {
                            "module": module_label,
                            "issue": (
                                "Implementation modified after"
                                f" AC sign-off ({change['file']})"
                            ),
                            "severity": "HIGH",
                            "action": "Re-verify acceptance criteria",
                        }
                    )

        # --- Staleness checks (only draft / in-review) ---
        if status in ("draft", "in-review") and mod["last_updated"]:
            try:
                last_updated = datetime.strptime(str(mod["last_updated"]), "%Y-%m-%d").date()
                days_since = (today - last_updated).days
                if days_since > staleness_days:
                    staleness_issues.append(
                        {
                            "module": module_label,
                            "last_updated": str(mod["last_updated"]),
                            "status": status,
                            "days_stale": days_since,
                        }
                    )
            except ValueError:
                # Can't parse date -- flag as a validation issue in gaps
                gaps.append(
                    {
                        "item": module_label,
                        "missing": f"Invalid last_updated date: {mod['last_updated']}",
                        "severity": "LOW",
                    }
                )
        elif status in ("draft", "in-review") and not mod["last_updated"]:
            gaps.append(
                {
                    "item": module_label,
                    "missing": "No last_updated field (cannot assess staleness)",
                    "severity": "LOW",
                }
            )

        # --- Coverage: spec module missing AC file ---
        ac_file = ac_dir / f"{mod['number']}-{slug}.md"
        if not ac_file.exists():
            gaps.append(
                {
                    "item": module_label,
                    "missing": "No AC file exists",
                    "severity": "MEDIUM",
                }
            )

    # --- Coverage: AC files with no spec module ---
    spec_stems = {f"{m['number']}-{m['slug']}" for m in spec_modules}
    if ac_dir.is_dir():
        for ac_file in sorted(ac_dir.glob("[0-9][0-9]-*.md")):
            ac_stem = ac_file.stem
            if ac_stem not in spec_stems:
                gaps.append(
                    {
                        "item": f"AC: {ac_file.name}",
                        "missing": "Orphan AC file with no matching spec module",
                        "severity": "LOW",
                    }
                )

    # --- Coverage: implementation files with no spec ---
    unclaimed = [f for f in impl_files if f not in claimed_impl_files]
    for uf in unclaimed:
        try:
            rel = uf.relative_to(root)
        except ValueError:
            rel = uf
        gaps.append(
            {
                "item": str(rel),
                "missing": "Implementation file with no corresponding spec",
                "severity": "LOW",
            }
        )

    # --- Format output ---
    if output_format == "json":
        return _format_report_json(divergences, staleness_issues, gaps)
    return _format_report_markdown(divergences, staleness_issues, gaps)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> None:
    """CLI entry point for detect-drift command."""
    import argparse

    parser = argparse.ArgumentParser(description="Detect drift between specs and implementation.")
    parser.add_argument(
        "--staleness-days",
        type=int,
        default=DRIFT_STALENESS_DAYS,
        help=(
            "Days before a draft/in-review spec is flagged stale"
            f" (default: {DRIFT_STALENESS_DAYS})"
        ),
    )
    parser.add_argument(
        "--no-git",
        action="store_true",
        help="Skip git-based post-sign-off checks",
    )
    parser.add_argument(
        "--format",
        choices=["markdown", "json"],
        default="markdown",
        dest="output_format",
        help="Output format (default: markdown)",
    )
    parser.add_argument(
        "--fail-on",
        choices=["high", "medium", "low"],
        default=None,
        dest="fail_on",
        help="Exit 1 if any finding is at or above this severity level.",
    )

    args = parser.parse_args(argv)

    report = detect_drift(
        staleness_days=args.staleness_days,
        check_git_history=not args.no_git,
        output_format=args.output_format,
    )
    print(report)

    if args.fail_on:
        _SEVERITY_RANK = {"high": 0, "medium": 1, "low": 2}
        threshold_rank = _SEVERITY_RANK[args.fail_on]
        json_report = (
            report
            if args.output_format == "json"
            else detect_drift(
                staleness_days=args.staleness_days,
                check_git_history=not args.no_git,
                output_format="json",
            )
        )
        data = json.loads(json_report)
        for finding in data.get("findings", []):
            sev = finding.get("severity", "").lower()
            if sev in _SEVERITY_RANK and _SEVERITY_RANK[sev] <= threshold_rank:
                sys.exit(1)


if __name__ == "__main__":
    main()

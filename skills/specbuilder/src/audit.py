"""Project audit and upgrade proposal generation (EXT-051).

Inspects a project's actual state, compares against SpecBuilder's
current expectations, and generates an upgrade proposal documenting
what's behind and recommending specific fixes.
"""

import argparse
import json
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from specbuilder.src.config import (
    QUALITY_PROFILES,
    SPECBUILDER_TOML_FILE,
    get_project_root,
)

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore[no-redef]


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class AuditFinding:
    """A single audit finding."""

    category: str  # "config", "hooks", "profile", "structure"
    severity: str  # "missing", "stale", "deprecated"
    description: str
    fix_description: str


# ---------------------------------------------------------------------------
# Detection checks
# ---------------------------------------------------------------------------


def _read_toml(project_root: Path) -> dict[str, Any]:
    """Read .specbuilder.toml, returning empty dict if missing/invalid."""
    toml_path = project_root / SPECBUILDER_TOML_FILE
    if not toml_path.exists():
        return {}
    try:
        result: dict[str, Any] = tomllib.loads(toml_path.read_text(encoding="utf-8"))
        return result
    except Exception:
        return {}


def check_toml_exists(project_root: Path) -> list[AuditFinding]:
    """Check if .specbuilder.toml exists."""
    toml_path = project_root / SPECBUILDER_TOML_FILE
    if not toml_path.exists():
        return [AuditFinding(
            category="config",
            severity="missing",
            description=f"{SPECBUILDER_TOML_FILE} not found",
            fix_description="Create .specbuilder.toml with project configuration",
        )]
    return []


def check_version_stamp(project_root: Path) -> list[AuditFinding]:
    """Check if specbuilder_version is stamped in config."""
    config = _read_toml(project_root)
    if not config:
        return []  # No toml — covered by check_toml_exists

    project_section = config.get("project", {})
    if "specbuilder_version" not in project_section:
        return [AuditFinding(
            category="config",
            severity="missing",
            description="Missing [project].specbuilder_version field",
            fix_description="Add specbuilder_version to track upgrade state",
        )]
    return []


def check_quality_profile_fields(project_root: Path) -> list[AuditFinding]:
    """Check if quality profile config has all expected fields."""
    config = _read_toml(project_root)
    if not config:
        return []

    quality = config.get("quality", {})
    findings: list[AuditFinding] = []

    # Check profile name is recognized
    profile_name = quality.get("profile", "")
    if profile_name and profile_name not in QUALITY_PROFILES:
        findings.append(AuditFinding(
            category="profile",
            severity="stale",
            description=(
                f"Quality profile '{profile_name}' not recognized. "
                f"Valid: {', '.join(QUALITY_PROFILES.keys())}"
            ),
            fix_description="Update profile to a recognized name",
        ))

    return findings


def check_validation_tier_awareness(project_root: Path) -> list[AuditFinding]:
    """Check if the project config is aware of validation tiers."""
    config = _read_toml(project_root)
    if not config:
        return []

    quality = config.get("quality", {})
    # If there's a quality section but no validation_tier mentioned anywhere
    if quality and "validation_tier" not in str(config):
        return [AuditFinding(
            category="config",
            severity="missing",
            description="No validation_tier configured (added in v1.12.0)",
            fix_description=(
                "Validation tier is now resolved from the quality profile. "
                "No config change needed unless you want to override the default."
            ),
        )]
    return []


def check_hook_exists(project_root: Path) -> list[AuditFinding]:
    """Check if change-control hook is installed."""
    hooks_json = project_root / ".cortex" / "hooks.json"
    if not hooks_json.exists():
        return [AuditFinding(
            category="hooks",
            severity="missing",
            description=".cortex/hooks.json not found",
            fix_description="Install change-control hook via scaffold",
        )]

    try:
        hooks = json.loads(hooks_json.read_text(encoding="utf-8"))
        # Check for PreToolUse hook (change-control gate)
        has_pretool = any(
            h.get("event") == "PreToolUse" or "PreToolUse" in str(h)
            for h in (hooks if isinstance(hooks, list) else hooks.get("hooks", []))
        )
        if not has_pretool:
            return [AuditFinding(
                category="hooks",
                severity="missing",
                description="No PreToolUse hook found in hooks.json",
                fix_description="Add change-control gate hook",
            )]
    except Exception:
        return [AuditFinding(
            category="hooks",
            severity="stale",
            description=".cortex/hooks.json is malformed",
            fix_description="Regenerate hooks.json via scaffold",
        )]

    return []


def check_spec_readme_header(project_root: Path) -> list[AuditFinding]:
    """Check if spec/README.md has stale status header."""
    readme = project_root / "spec" / "README.md"
    if not readme.exists():
        return []

    content = readme.read_text(encoding="utf-8")
    if "> **Status**:" in content or "> **Version**:" in content:
        return [AuditFinding(
            category="structure",
            severity="stale",
            description="spec/README.md has stale Status/Version header",
            fix_description=(
                "Remove status header — spec/README.md is an auto-generated "
                "index, not a deliverable with a lifecycle"
            ),
        )]
    return []


def check_root_readme_sentinels(project_root: Path) -> list[AuditFinding]:
    """Check if root README.md has auto-generation sentinel markers."""
    readme = project_root / "README.md"
    if not readme.exists():
        return []

    content = readme.read_text(encoding="utf-8")
    if "<!-- BEGIN_AUTO_COMMANDS -->" not in content:
        return [AuditFinding(
            category="structure",
            severity="missing",
            description="Root README.md missing auto-generation markers",
            fix_description=(
                "Add <!-- BEGIN_AUTO_COMMANDS --> sentinels so "
                "generate-index can keep the command table current"
            ),
        )]
    return []


def check_spec_directory(project_root: Path) -> list[AuditFinding]:
    """Check if spec/ directory exists with expected structure."""
    spec_dir = project_root / "spec"
    if not spec_dir.exists():
        return [AuditFinding(
            category="structure",
            severity="missing",
            description="No spec/ directory found",
            fix_description="Run `specbuilder scaffold` to create spec structure",
        )]

    findings: list[AuditFinding] = []
    modules_dir = spec_dir / "modules"
    if not modules_dir.exists():
        findings.append(AuditFinding(
            category="structure",
            severity="missing",
            description="spec/modules/ directory missing",
            fix_description="Create spec/modules/ for spec module files",
        ))

    return findings


def check_changelog_freshness(project_root: Path) -> list[AuditFinding]:
    """Check if source commits have accumulated since last changelog entry."""
    import subprocess

    changelog_dir = project_root / "spec" / "changelog"
    if not changelog_dir.exists():
        return []

    # Find the latest changelog date
    latest_date = None
    for f in sorted(changelog_dir.glob("*.md"), reverse=True):
        content = f.read_text(encoding="utf-8")
        date_match = re.match(r".*^date:\s*(\S+)", content, re.DOTALL | re.MULTILINE)
        if date_match:
            latest_date = date_match.group(1).strip()
            break

    if not latest_date:
        return []

    # Count source commits since that date
    try:
        result = subprocess.run(
            [
                "git", "log", f"--after={latest_date}", "--oneline",
                "--", "specbuilder/src/", "specbuilder/skills/",
            ],
            capture_output=True, text=True, cwd=str(project_root),
            timeout=10,
        )
        if result.returncode != 0:
            return []

        commit_count = len([
            line for line in result.stdout.strip().split("\n") if line
        ])

        if commit_count > 5:
            return [AuditFinding(
                category="changelog",
                severity="stale",
                description=(
                    f"{commit_count} source commits since last changelog "
                    f"entry ({latest_date}). Consider a changelog + version bump."
                ),
                fix_description=(
                    "Review recent source changes and create a changelog entry "
                    "if they include new features, bug fixes, or workflow changes"
                ),
            )]
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass  # Git unavailable — skip silently

    return []


# Registry of all checks
ALL_CHECKS: list[Callable[[Path], list[AuditFinding]]] = [
    check_toml_exists,
    check_version_stamp,
    check_quality_profile_fields,
    check_validation_tier_awareness,
    check_hook_exists,
    check_spec_readme_header,
    check_root_readme_sentinels,
    check_spec_directory,
    check_changelog_freshness,
]


# ---------------------------------------------------------------------------
# Audit runner
# ---------------------------------------------------------------------------


def run_audit(project_root: Path) -> list[AuditFinding]:
    """Run all audit checks and return findings."""
    findings: list[AuditFinding] = []
    for check in ALL_CHECKS:
        findings.extend(check(project_root))
    return findings


# ---------------------------------------------------------------------------
# Proposal generation
# ---------------------------------------------------------------------------


def generate_upgrade_proposal(
    project_root: Path,
    findings: list[AuditFinding],
) -> Path | None:
    """Generate an upgrade proposal from audit findings.

    Creates a proposal in spec/architecture/proposals/ following standard format.
    Returns the proposal path, or None if no findings.
    """
    if not findings:
        return None

    proposals_dir = project_root / "spec" / "architecture" / "proposals"
    if not proposals_dir.exists():
        # Can't generate proposal without proposal infrastructure
        return None

    # Determine next proposal number
    existing = sorted(proposals_dir.glob("[0-9][0-9][0-9]-*.md"))
    next_num = 1
    if existing:
        last_name = existing[-1].name
        match = re.match(r"(\d+)-", last_name)
        if match:
            next_num = int(match.group(1)) + 1
    proposal_num = f"{next_num:03d}"

    # Build proposal content
    from specbuilder import __version__

    findings_by_category: dict[str, list[AuditFinding]] = {}
    for f in findings:
        findings_by_category.setdefault(f.category, []).append(f)

    finding_lines: list[str] = []
    for category, category_findings in findings_by_category.items():
        finding_lines.append(f"\n### {category.title()}\n")
        for f in category_findings:
            icon = "⚠" if f.severity == "missing" else "ℹ"
            finding_lines.append(f"- {icon} **{f.severity}**: {f.description}")
            finding_lines.append(f"  - Fix: {f.fix_description}")

    content = f"""---
id: EXT-{proposal_num}
title: "Infrastructure upgrade to SpecBuilder v{__version__}"
phase: 3
status: in-progress
depends_on: []
impacts_modules: []
---

## Problem Statement

Project infrastructure is behind SpecBuilder v{__version__}. The audit detected \
{len(findings)} finding(s) that indicate missing configuration, stale templates, \
or structural gaps.

## Findings

{chr(10).join(finding_lines)}

## Scope

**Changes to apply:**

{chr(10).join(f"- [ ] {f.fix_description}" for f in findings)}

## Design

All changes are additive — no existing content will be removed or modified \
beyond appending new fields or sections.

## Success Criteria

- All audit findings resolved (re-run `specbuilder audit` shows 0 findings)
- Project configuration matches SpecBuilder v{__version__} expectations
"""

    proposal_path = proposals_dir / f"{proposal_num}-infrastructure-upgrade.md"
    proposal_path.write_text(content, encoding="utf-8")
    return proposal_path


# ---------------------------------------------------------------------------
# Apply fixes
# ---------------------------------------------------------------------------


def apply_fixes(project_root: Path, findings: list[AuditFinding]) -> list[str]:
    """Apply fixes for audit findings. Returns list of actions taken."""
    actions: list[str] = []

    for finding in findings:
        if finding.category == "config" and "specbuilder_version" in finding.description:
            _fix_version_stamp(project_root)
            actions.append("Added specbuilder_version to .specbuilder.toml")
        elif finding.category == "structure" and "stale Status" in finding.description:
            _fix_spec_readme_header(project_root)
            actions.append("Removed stale header from spec/README.md")

    return actions


def _fix_version_stamp(project_root: Path) -> None:
    """Add specbuilder_version to .specbuilder.toml."""
    from specbuilder import __version__

    toml_path = project_root / SPECBUILDER_TOML_FILE
    if not toml_path.exists():
        return

    content = toml_path.read_text(encoding="utf-8")
    if "specbuilder_version" in content:
        return

    # Append after [project] section
    if "[project]" in content:
        content = content.replace(
            "[project]",
            f"[project]\nspecbuilder_version = \"{__version__}\"",
            1,
        )
        # Clean up: avoid double newline
        content = content.replace(
            f"specbuilder_version = \"{__version__}\"\n\n",
            f"specbuilder_version = \"{__version__}\"\n",
        )
    toml_path.write_text(content, encoding="utf-8")


def _fix_spec_readme_header(project_root: Path) -> None:
    """Remove stale Status/Version/Last Updated header from spec/README.md."""
    readme = project_root / "spec" / "README.md"
    if not readme.exists():
        return

    content = readme.read_text(encoding="utf-8")
    # Remove lines matching > **Status**: ... / > **Last Updated**: ... / > **Version**: ...
    lines = content.split("\n")
    filtered = [
        line for line in lines
        if not re.match(r"^>\s*\*\*(Status|Last Updated|Version)\*\*", line)
    ]
    # Remove blank line that was between header and ## Overview
    result = "\n".join(filtered)
    result = re.sub(r"\n{3,}", "\n\n", result)
    readme.write_text(result, encoding="utf-8")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="specbuilder audit",
        description="Audit project health and generate upgrade proposals.",
    )
    parser.add_argument(
        "--format", choices=["text", "json"], default="text",
        help="Output format.",
    )
    parser.add_argument(
        "--apply", action="store_true",
        help="Generate upgrade proposal and apply safe fixes.",
    )

    args = parser.parse_args(argv)
    project_root = get_project_root()

    # Run audit
    findings = run_audit(project_root)

    if args.format == "json":
        output = [
            {
                "category": f.category,
                "severity": f.severity,
                "description": f.description,
                "fix": f.fix_description,
            }
            for f in findings
        ]
        print(json.dumps(output, indent=2))
        sys.exit(0 if not findings else 1)
    else:
        from specbuilder import __version__

        print(f"SpecBuilder Project Audit (v{__version__})")
        print("=" * 40)
        print()

        if not findings:
            print("✓ No findings — project is current.")
            sys.exit(0)

        # Group by category
        by_category: dict[str, list[AuditFinding]] = {}
        for f in findings:
            by_category.setdefault(f.category, []).append(f)

        for category, category_findings in by_category.items():
            print(f"{category.title()}:")
            for f in category_findings:
                icon = "⚠" if f.severity == "missing" else "ℹ"
                print(f"  {icon} {f.description}")
            print()

        print(f"Summary: {len(findings)} finding(s)")
        print()

    if not findings:
        sys.exit(0)

    if args.apply:
        # Generate proposal
        proposal_path = generate_upgrade_proposal(project_root, findings)
        if proposal_path:
            print(f"Generated upgrade proposal: {proposal_path}")

        # Apply safe fixes
        actions = apply_fixes(project_root, findings)
        if actions:
            print("\nApplied fixes:")
            for action in actions:
                print(f"  ✓ {action}")

        # Re-run audit to show remaining
        remaining = run_audit(project_root)
        if remaining:
            print(f"\n{len(remaining)} finding(s) remaining (manual action needed)")
        else:
            print("\n✓ All findings resolved.")
    else:
        print("To generate an upgrade proposal and apply fixes:")
        print("  python3 -m specbuilder audit --apply")

    sys.exit(0 if not findings else 1)


if __name__ == "__main__":
    main()

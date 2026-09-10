"""Project audit and upgrade proposal generation (EXT-051).

Inspects a project's actual state, compares against SpecBuilder's
current expectations, and generates an upgrade proposal documenting
what's behind and recommending specific fixes.
"""

from __future__ import annotations

import argparse
import datetime
import json
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from specbuilder.src.config import (
    QUALITY_PROFILES,
    README_TABLE_BEGIN,
    REQUIRED_PROPOSAL_FIELDS,
    SPECBUILDER_TOML_FILE,
    VALID_PROPOSAL_STATUSES,
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

    category: str  # "config", "hooks", "structure", "changelog", "skill-coverage", "readme"
    severity: str  # "missing", "stale", "deprecated", "warning", "info"
    description: str
    fix_description: str
    auto_fixable: bool = False
    fix_type: str = ""  # stable dispatch key for apply_fixes; description is display-only


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
    except Exception as e:
        print(
            f"Warning: Failed to parse .specbuilder.toml: {e}. "
            "All config-dependent audit checks will be skipped.",
            file=sys.stderr,
        )
        return {}
        # Note: check_toml_exists is unaffected — it calls toml_path.exists() directly
        # (audit.py:73–83) and never calls _read_toml(), so it reports correctly even
        # when the TOML is present but malformed.


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
            fix_type="version_stamp",
            auto_fixable=True,
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
            category="config",
            severity="stale",
            description=(
                f"Quality profile '{profile_name}' not recognized. "
                f"Valid: {', '.join(QUALITY_PROFILES.keys())}"
            ),
            fix_description="Update profile to a recognized name",
        ))

    return findings


def check_validation_tier_awareness(project_root: Path) -> list[AuditFinding]:
    """Check if the project config carries an explicit validation_tier override."""
    config = _read_toml(project_root)
    if not config:
        return []

    quality_section = config.get("quality", {})
    if not quality_section:
        return []  # No [quality] section — skip check
    if "validation_tier" not in quality_section:
        return [AuditFinding(
            category="config",
            severity="info",
            description=(
                "No explicit validation_tier in [quality] section "
                "(tier is auto-resolved from the active quality profile)"
            ),
            fix_description=(
                "No action needed. Add validation_tier only if you want to "
                "override the profile default."
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
        # Check for PreToolUse hook — handles both schema formats:
        #   Current dict-keyed: {"hooks": {"PreToolUse": [...]}}
        #   Legacy list:        {"hooks": [...]} or [{"event": "PreToolUse"}]
        inner = hooks if isinstance(hooks, list) else hooks.get("hooks", {})
        if isinstance(inner, dict):
            has_pretool = "PreToolUse" in inner
        else:
            has_pretool = any(
                h.get("event") == "PreToolUse" or "PreToolUse" in str(h)
                for h in inner
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

    lines = readme.read_text(encoding="utf-8").split("\n")
    if any(re.match(r"^>\s*\*\*(Status|Last Updated|Version)\*\*", line) for line in lines):
        return [AuditFinding(
            category="structure",
            severity="stale",
            description="spec/README.md has stale Status/Last Updated/Version header",
            fix_description=(
                "Remove status header — spec/README.md is an auto-generated "
                "index, not a deliverable with a lifecycle"
            ),
            fix_type="readme_header",
            auto_fixable=True,
        )]
    return []


def check_root_readme_sentinels(project_root: Path) -> list[AuditFinding]:
    """Check if root README.md has auto-generation sentinel markers."""
    readme = project_root / "README.md"
    if not readme.exists():
        return []

    content = readme.read_text(encoding="utf-8")
    if README_TABLE_BEGIN not in content:
        return [AuditFinding(
            category="readme",
            severity="missing",
            description="Root README.md missing auto-generation markers",
            fix_description=(
                f"Add {README_TABLE_BEGIN} sentinels so "
                "generate-index can keep the module table current"
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


def _resolve_source_paths(project_root: Path) -> tuple[str, str]:
    """Return (src_path, skills_path) relative strings for git log path filters.

    Resolution order:
    1. [project].src_root and [project].skills_root from .specbuilder.toml
    2. Probe for specbuilder/src/ and specbuilder/skills/ (dev-repo layout)
    3. Probe for src/ and skills/ (flat layout)
    4. Fall back to ("", "") — caller must skip the git log invocation entirely
       when both paths are empty to avoid false-positive findings from unfiltered
       git invocations in non-specbuilder consumer projects.
    """
    config_path = project_root / SPECBUILDER_TOML_FILE
    if config_path.exists():
        try:
            cfg = tomllib.loads(config_path.read_text(encoding="utf-8"))
            project_cfg = cfg.get("project", {})
            if "src_root" in project_cfg and "skills_root" in project_cfg:
                return project_cfg["src_root"], project_cfg["skills_root"]
        except Exception:
            pass

    # Probe common layouts
    if (project_root / "specbuilder" / "src").is_dir():
        return "specbuilder/src/", "specbuilder/skills/"
    if (project_root / "src").is_dir():
        return "src/", "skills/"

    return "", ""


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

    # Derive source path roots from config or probe common locations
    _src_root, _skills_root = _resolve_source_paths(project_root)
    if not _src_root and not _skills_root:
        # Unrecognised project layout — skip to avoid false positives
        return []

    # Count source commits since that date
    try:
        result = subprocess.run(
            [
                "git", "log", f"--after={latest_date}", "--oneline",
                "--", _src_root, _skills_root,
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


def check_skill_coverage(project_root: Path) -> list[AuditFinding]:
    """Check that all CLI flags are documented in their corresponding SKILL.md files."""
    import subprocess

    skills_dir = project_root / "specbuilder" / "skills"
    if not skills_dir.exists():
        return []  # Consumer project — not an error

    # Mapping from skill directory name to CLI subcommands.
    # NOTE: update this map when adding subcommands to any listed subskill —
    # check_skill_coverage silently misses new flags until this dict is updated.
    skill_command_map: dict[str, list[str]] = {
        "implement-spec": ["implement"],
        "verify-spec": ["detect-drift", "test-acceptance", "ac-coverage", "release"],
        "generate-spec": ["generate-module"],
        "scaffold-spec": ["scaffold"],
        "audit-spec": ["audit"],
        "checkpoint-spec": ["checkpoint"],
        "handover-consumer": ["handover-consumer"],
        # specbuilder (orchestrator) and propose-spec have no direct subcommand — skip
    }

    excluded_flags = {"--help", "--version"}
    findings: list[AuditFinding] = []

    for skill_name, subcommands in skill_command_map.items():
        skill_md = skills_dir / skill_name / "SKILL.md"
        if not skill_md.exists():
            continue
        skill_text = skill_md.read_text(encoding="utf-8")

        for subcommand in subcommands:
            try:
                result = subprocess.run(
                    ["python3", "-m", "specbuilder", subcommand, "--help"],
                    capture_output=True,
                    text=True,
                    cwd=str(project_root),
                    timeout=15,
                )
            except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
                findings.append(AuditFinding(
                    category="skill-coverage",
                    severity="warning",
                    description=(
                        f"Could not invoke '{subcommand} --help' to check flag coverage: {exc}"
                    ),
                    fix_description=(
                        "Ensure specbuilder is importable from the project root "
                        "(check PYTHONPATH)."
                    ),
                    auto_fixable=False,
                ))
                continue

            if result.returncode != 0:
                findings.append(AuditFinding(
                    category="skill-coverage",
                    severity="warning",
                    description=(
                        f"'python3 -m specbuilder {subcommand} --help' exited "
                        f"{result.returncode} — flag coverage check skipped"
                    ),
                    fix_description=(
                        f"Investigate why 'python3 -m specbuilder {subcommand} --help' "
                        "returns a non-zero exit code."
                    ),
                    auto_fixable=False,
                ))
                continue

            flags = {
                m.group(0)
                for m in re.finditer(r"--[a-z][a-z0-9-]+", result.stdout)
            } - excluded_flags

            for flag in sorted(flags):
                if flag not in skill_text:
                    findings.append(AuditFinding(
                        category="skill-coverage",
                        severity="warning",
                        description=(
                            f"Flag '{flag}' from '{subcommand} --help' not documented "
                            f"in {skill_name}/SKILL.md"
                        ),
                        fix_description=(
                            f"Add documentation for '{flag}' to {skill_name}/SKILL.md"
                        ),
                        auto_fixable=False,
                    ))

    return findings


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
    check_skill_coverage,
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


def _parse_frontmatter_str(content: str) -> dict:
    """Parse YAML frontmatter from a content string. Returns dict or {}."""
    if not content.startswith("---"):
        return {}
    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}
    raw = parts[1].strip()
    if not raw:
        return {}
    try:
        import yaml
        result = yaml.safe_load(raw)
        return result if isinstance(result, dict) else {}
    except Exception:
        pass
    # Fallback: simple key: value parser
    fm: dict = {}
    for line in raw.splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            v = v.strip()
            if v.startswith("[") and v.endswith("]"):
                fm[k.strip()] = []
            else:
                fm[k.strip()] = v.strip('"').strip("'")
    return fm


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
        print(
            f"Warning: proposals directory not found at {proposals_dir}. "
            "Skipping proposal generation.",
            file=sys.stderr,
        )
        return None

    # Idempotency guard: skip if an infrastructure-upgrade proposal already exists
    existing_upgrade = list(proposals_dir.glob("*infrastructure-upgrade*.md"))
    if existing_upgrade:
        print(
            f"Warning: upgrade proposal already exists ({existing_upgrade[0].name}). "
            "Skipping generation.",
            file=sys.stderr,
        )
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
            icon = (
                "⚠" if f.severity == "missing"
                else "⊘" if f.severity == "deprecated"
                else "▲" if f.severity == "warning"
                else "ℹ"
            )
            finding_lines.append(f"- {icon} **{f.severity}**: {f.description}")
            finding_lines.append(f"  - Fix: {f.fix_description}")

    today = datetime.date.today().isoformat()

    content = f"""---
id: EXT-{proposal_num}
title: "Infrastructure upgrade to SpecBuilder v{__version__}"
phase: 3
status: planned
created: {today}
depends_on: []
impacts_modules: []
---

## Problem Statement

Project infrastructure is behind SpecBuilder v{__version__}. The audit detected \
{len(findings)} finding(s) that indicate missing configuration, stale templates, \
or structural gaps.

## Summary

<!-- Auto-generated: summarise the upgrade work here. -->

## Prerequisites

None identified.

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

    # Pre-write schema validation
    fm = _parse_frontmatter_str(content)
    missing_fields = REQUIRED_PROPOSAL_FIELDS - set(fm.keys())
    if missing_fields:
        raise ValueError(
            f"generate_upgrade_proposal: generated frontmatter is missing required "
            f"field(s): {sorted(missing_fields)}"
        )
    if fm.get("status") not in VALID_PROPOSAL_STATUSES:
        raise ValueError(
            f"generate_upgrade_proposal: invalid status '{fm.get('status')}'; "
            f"must be one of {sorted(VALID_PROPOSAL_STATUSES)}"
        )

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
        if finding.fix_type == "version_stamp":
            if _fix_version_stamp(project_root):
                actions.append("Added specbuilder_version to .specbuilder.toml")
        elif finding.fix_type == "readme_header":
            if _fix_spec_readme_header(project_root):
                actions.append("Removed stale header from spec/README.md")

    return actions


def preview_fixes(findings: list[AuditFinding], project_root: Path) -> None:
    """Preview fixes that would be applied without writing any files."""
    from specbuilder import __version__

    fixable = [f for f in findings if f.auto_fixable]
    if not fixable:
        print("No auto-fixable findings.", file=sys.stderr)
        return

    print("Proposed fixes (dry-run — no files written):", file=sys.stderr)
    for finding in fixable:
        if finding.fix_type == "version_stamp":
            print(
                f'  • Would add specbuilder_version = "{__version__}" '
                "to .specbuilder.toml [project] section",
                file=sys.stderr,
            )
        elif finding.fix_type == "readme_header":
            print(
                "  • Would remove stale Status/Version/Last Updated header "
                "from spec/README.md",
                file=sys.stderr,
            )


def _fix_version_stamp(project_root: Path) -> bool:
    """Add specbuilder_version to .specbuilder.toml.

    Returns True if the file was written, False if the fix was skipped or failed.
    """
    from specbuilder import __version__

    toml_path = project_root / SPECBUILDER_TOML_FILE
    if not toml_path.exists():
        print(
            "Warning: .specbuilder.toml not found; version stamp fix was not written.",
            file=sys.stderr,
        )
        return False

    content = toml_path.read_text(encoding="utf-8")
    if "specbuilder_version" in content:
        return False

    try:
        parsed = tomllib.loads(content)
    except Exception as e:
        print(
            f"Warning: Failed to parse .specbuilder.toml during --apply: {e}. "
            "Version stamp fix was not written.",
            file=sys.stderr,
        )
        return False

    if "project" not in parsed:
        print(
            "Warning: .specbuilder.toml has no [project] table; "
            "version stamp fix was not written.",
            file=sys.stderr,
        )
        return False

    # Replace only the bare [project] section header line
    new_content = re.sub(
        r"(?m)^(\[project\])",
        f"[project]\nspecbuilder_version = \"{__version__}\"",
        content,
        count=1,
    )
    if new_content == content:
        print(
            "Warning: .specbuilder.toml [project] header not matched by version-stamp regex; "
            "fix was not applied.",
            file=sys.stderr,
        )
        return False
    toml_path.write_text(new_content, encoding="utf-8")
    return True


def _fix_spec_readme_header(project_root: Path) -> bool:
    """Remove stale Status/Version/Last Updated header from spec/README.md."""
    readme = project_root / "spec" / "README.md"
    if not readme.exists():
        return False

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
    return True


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
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview proposed changes without writing any file.",
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Required with --apply to confirm destructive writes.",
    )
    parser.add_argument(
        "--envelope",
        action="store_true",
        help="Wrap --format json output in a DiagnosticEnvelope."
        " Has no effect without --format json.",
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
                "auto_fixable": f.auto_fixable,
            }
            for f in findings
        ]
        if args.envelope:
            from specbuilder.src.diagnostic_schema import wrap_findings
            print(json.dumps(wrap_findings("audit", output), indent=2))
        else:
            print(json.dumps(output, indent=2))
        if not args.apply:
            sys.exit(0 if not findings else 1)
        # --apply is set: fall through to the apply block below
        if args.apply or args.dry_run:
            print(
                "Note: --format json combined with --apply/--dry-run — "
                "JSON findings on stdout, progress output on stderr.",
                file=sys.stderr,
            )
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
                icon = (
                    "⚠" if f.severity == "missing"
                    else "⊘" if f.severity == "deprecated"
                    else "▲" if f.severity == "warning"
                    else "ℹ"
                )
                print(f"  {icon} {f.description}")
            print()

        print(f"Summary: {len(findings)} finding(s)")
        print()

    if args.dry_run:
        preview_fixes(findings, project_root)
        sys.exit(1 if findings else 0)

    if args.apply:
        if not args.confirm:
            preview_fixes(findings, project_root)
            print("\n--apply requires --confirm to prevent accidental writes.", file=sys.stderr)
            print("  python3 -m specbuilder audit --apply --confirm", file=sys.stderr)
            sys.exit(1)
        # Generate proposal
        proposal_path = generate_upgrade_proposal(project_root, findings)
        if proposal_path:
            print(f"Generated upgrade proposal: {proposal_path}", file=sys.stderr)

        # Apply safe fixes
        actions = apply_fixes(project_root, findings)
        if actions:
            print("\nApplied fixes:", file=sys.stderr)
            for action in actions:
                print(f"  ✓ {action}", file=sys.stderr)

        # Re-run audit to show remaining
        remaining = run_audit(project_root)
        if remaining:
            print(
                f"\n{len(remaining)} finding(s) remaining (manual action needed)",
                file=sys.stderr,
            )
        else:
            print("\n✓ All findings resolved.", file=sys.stderr)

        sys.exit(0 if not remaining else 1)
    else:
        print("To generate an upgrade proposal and apply fixes:")
        print("  python3 -m specbuilder audit --apply")

        sys.exit(0 if not findings else 1)


if __name__ == "__main__":
    main()

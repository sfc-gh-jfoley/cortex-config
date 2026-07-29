"""Validation utilities for spec-driven project files.

Provides frontmatter parsing and schema validation for:
- Architecture decision files
- Extension proposal files
- Spec module files
- Acceptance criteria files
"""

import re
from pathlib import Path

from specbuilder.src.config import (
    ARCH_FILE_PATTERN,
    DEFAULT_DECISIONS_DIR,
    DEFAULT_PROPOSALS_DIR,
    REQUIRED_AC_FIELDS,
    REQUIRED_DECISION_FIELDS,
    REQUIRED_DECISION_SECTIONS,
    REQUIRED_PROPOSAL_FIELDS,
    REQUIRED_PROPOSAL_SECTIONS,
    REQUIRED_SPEC_FIELDS,
    REQUIRED_SPEC_SECTIONS,
    SPEC_FILE_PATTERN,
    VALID_AC_STATUSES,
    VALID_DECISION_STATUSES,
    VALID_PROPOSAL_STATUSES,
    VALID_SPEC_STATUSES,
)
from specbuilder.src.config import (
    PROMOTED_TO_PATTERN as _PROMOTED_TO_PATTERN,
)

# ---------------------------------------------------------------------------
# Changelog validation constants
# ---------------------------------------------------------------------------

REQUIRED_CHANGELOG_FIELDS = {"id", "title", "version", "date", "affected_modules", "type"}
VALID_CHANGELOG_TYPES = {"feature", "fix", "pattern", "governance"}
REQUIRED_CHANGELOG_SECTIONS = ["## Context", "## Changes", "## Reasoning"]


def parse_frontmatter(filepath: Path) -> dict:
    """Parse YAML frontmatter from a markdown file.

    Returns a dict of key-value pairs. List values (e.g., depends_on: [])
    are parsed into Python lists. Returns empty dict if no valid frontmatter.

    Uses PyYAML (yaml.safe_load) when available for robust parsing.
    Falls back to a hand-rolled parser when PyYAML is not installed.
    """
    content = filepath.read_text(encoding="utf-8")
    if not content.startswith("---"):
        return {}

    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}

    raw = parts[1].strip()
    if not raw:
        return {}

    # Try PyYAML first for robust parsing
    try:
        import yaml

        result = yaml.safe_load(raw)
        if isinstance(result, dict):
            return result
        return {}
    except ImportError:
        return _parse_frontmatter_fallback(raw)
    except Exception:
        return _parse_frontmatter_fallback(raw)


def _parse_frontmatter_fallback(raw: str) -> dict:
    """Fallback frontmatter parser when PyYAML is unavailable.

    Handles basic key-value pairs, inline lists, booleans, integers,
    and quoted strings containing colons.
    """
    frontmatter = {}
    for line in raw.split("\n"):
        line = line.strip()
        if not line or ":" not in line:
            continue

        key, value = line.split(":", 1)
        key = key.strip()
        if not key:
            continue

        value = value.strip()

        # Handle quoted strings (preserves colons and special chars inside)
        if (value.startswith('"') and value.endswith('"')) or (
            value.startswith("'") and value.endswith("'")
        ):
            value = value[1:-1]
            frontmatter[key] = value
            continue

        # Handle list values (depends_on: [EXT-001, EXT-003])
        if value.startswith("["):
            list_val: list[str] = [
                v.strip().strip('"').strip("'")
                for v in value.strip("[]").split(",")
                if v.strip()
            ]
            frontmatter[key] = list_val  # type: ignore[assignment]
            continue

        # Handle boolean values
        if value.lower() == "true":
            frontmatter[key] = True  # type: ignore[assignment]
            continue
        if value.lower() == "false":
            frontmatter[key] = False  # type: ignore[assignment]
            continue

        # Handle integer values
        try:
            frontmatter[key] = int(value)  # type: ignore[assignment]
            continue
        except ValueError:
            pass

        # Strip outer quotes from plain values (legacy behavior)
        value = value.strip('"').strip("'")
        frontmatter[key] = value

    return frontmatter


def validate_decision(filepath: Path) -> list[str]:
    """Validate an architecture decision file. Returns list of errors."""
    errors = []
    filename = filepath.name

    if not ARCH_FILE_PATTERN.match(filename):
        errors.append(f"{filename}: doesn't match NNN-slug.md pattern")

    fm = parse_frontmatter(filepath)
    if not fm:
        errors.append(f"{filename}: missing or invalid YAML frontmatter")
        return errors

    for field in REQUIRED_DECISION_FIELDS:
        if field not in fm:
            errors.append(f"{filename}: missing required field '{field}'")

    if "status" in fm and fm["status"] not in VALID_DECISION_STATUSES:
        errors.append(
            f"{filename}: invalid status '{fm['status']}'. "
            f"Must be one of: {', '.join(sorted(VALID_DECISION_STATUSES))}"
        )

    content = filepath.read_text(encoding="utf-8")
    for section in REQUIRED_DECISION_SECTIONS:
        if section not in content:
            errors.append(f"{filename}: missing required section '{section}'")

    return errors


def validate_proposal(filepath: Path, is_new_file: bool = False) -> list[str]:
    """Validate a proposal file. Returns list of errors."""
    errors = []
    filename = filepath.name

    if not ARCH_FILE_PATTERN.match(filename):
        errors.append(f"{filename}: doesn't match NNN-slug.md pattern")

    if filepath.parent.name == "planned":
        errors.append(
            f"{filename}: proposal is in a 'planned/' subdirectory, which does not "
            "exist in the lifecycle model. Move to the proposals root "
            "(spec/architecture/proposals/) or an appropriate subdirectory "
            "(implemented/, parked/)."
        )

    fm = parse_frontmatter(filepath)
    if not fm:
        errors.append(f"{filename}: missing or invalid YAML frontmatter")
        return errors

    if is_new_file and fm.get("status") != "planned":
        errors.append(
            f"New proposals must have status 'planned', got '{fm.get('status')}'"
        )

    for field in REQUIRED_PROPOSAL_FIELDS:
        if field not in fm:
            errors.append(f"{filename}: missing required field '{field}'")

    if "id" in fm and not re.fullmatch(r"EXT-\d{3,}", str(fm["id"])):
        errors.append(
            f"{filename}: 'id' value '{fm['id']}' does not match required format EXT-NNN "
            "(e.g. EXT-001, EXT-209)"
        )

    if "status" in fm and fm["status"] not in VALID_PROPOSAL_STATUSES:
        errors.append(
            f"{filename}: invalid status '{fm['status']}'. "
            f"Must be one of: {', '.join(sorted(VALID_PROPOSAL_STATUSES))}"
        )

    if "promoted_to" in fm:
        val = str(fm["promoted_to"])
        if not _PROMOTED_TO_PATTERN.match(val):
            errors.append(
                f"'promoted_to' must match 'MOD-NN' format (e.g. MOD-01, MOD-12), got: {val!r}"
            )

    if "phase" in fm:
        phase_val = fm["phase"]
        if not (isinstance(phase_val, int) and phase_val > 0):
            errors.append(
                f"Invalid phase '{phase_val}'; must be a positive integer "
                "(represents the audit/implementation cycle number, e.g. 1, 2, 9)"
            )

    content = filepath.read_text(encoding="utf-8")
    for section in REQUIRED_PROPOSAL_SECTIONS:
        if section not in content:
            errors.append(f"{filename}: missing required section '{section}'")

    return errors


def validate_spec_module(filepath: Path, ac_dir: Path | None = None) -> list[str]:
    """Validate a spec module file. Returns list of errors.

    Args:
        filepath: Path to the spec module file.
        ac_dir: Path to acceptance-criteria directory (for cross-reference check).
    """
    errors: list[str] = []
    filename = filepath.name

    # Skip auto-generated and README
    if filename.startswith("00-") or filename == "README.md":
        return errors

    if not SPEC_FILE_PATTERN.match(filename):
        errors.append(f"spec/{filename}: doesn't match NN-slug.md pattern")

    fm = parse_frontmatter(filepath)
    if not fm:
        errors.append(f"spec/{filename}: missing or invalid YAML frontmatter")
        return errors

    for field in REQUIRED_SPEC_FIELDS:
        if field not in fm:
            errors.append(f"spec/{filename}: missing required field '{field}'")

    mod_id = fm.get("id", "")
    if not re.match(r'^MOD-\d{2,}$', str(mod_id)):
        errors.append(
            f"Invalid module id '{mod_id}'; must match MOD-NN format (e.g. MOD-01, MOD-12, MOD-100)"
        )

    if "status" in fm and fm["status"] not in VALID_SPEC_STATUSES:
        errors.append(
            f"spec/{filename}: invalid status '{fm['status']}'. "
            f"Must be one of: {', '.join(sorted(VALID_SPEC_STATUSES))}"
        )

    content = filepath.read_text(encoding="utf-8")
    for section in REQUIRED_SPEC_SECTIONS:
        if section not in content:
            errors.append(f"spec/{filename}: missing required section '{section}'")

    # Check corresponding AC file exists
    if ac_dir and ac_dir.is_dir():
        ac_file = ac_dir / filename
        if not ac_file.exists():
            errors.append(
                f"spec/{filename}: no corresponding AC file at spec/acceptance-criteria/{filename}"
            )

    return errors


def validate_ac_file(filepath: Path) -> list[str]:
    """Validate an acceptance criteria file. Returns list of errors."""
    errors: list[str] = []
    filename = filepath.name

    if filename == "README.md":
        return errors

    fm = parse_frontmatter(filepath)
    if not fm:
        errors.append(f"acceptance-criteria/{filename}: missing or invalid YAML frontmatter")
        return errors

    for field in REQUIRED_AC_FIELDS:
        if field not in fm:
            errors.append(f"acceptance-criteria/{filename}: missing required field '{field}'")

    if "status" in fm and fm["status"] not in VALID_AC_STATUSES:
        errors.append(
            f"acceptance-criteria/{filename}: invalid status '{fm['status']}'. "
            f"Must be one of: {', '.join(sorted(VALID_AC_STATUSES))}"
        )

    content = filepath.read_text(encoding="utf-8")

    if "## AC-" not in content:
        errors.append(f"acceptance-criteria/{filename}: no '## AC-' sections found")

    if "## Sign-Off" not in content and "## Sign-off" not in content:
        errors.append(f"acceptance-criteria/{filename}: missing '## Sign-Off' section")

    if "| Pass |" not in content and "| Pass|" not in content:
        errors.append(f"acceptance-criteria/{filename}: no AC table with 'Pass' column found")

    return errors


def validate_changelog_entry(filepath: Path) -> list[str]:
    """Validate a changelog entry file. Returns list of errors."""
    errors: list[str] = []
    filename = filepath.name

    if not ARCH_FILE_PATTERN.match(filename):
        errors.append(f"{filename}: doesn't match NNN-slug.md pattern")

    fm = parse_frontmatter(filepath)
    if not fm:
        errors.append(f"{filename}: missing or invalid YAML frontmatter")
        return errors

    for field in REQUIRED_CHANGELOG_FIELDS:
        if field not in fm:
            errors.append(f"{filename}: missing required field '{field}'")

    if "type" in fm and fm["type"] not in VALID_CHANGELOG_TYPES:
        errors.append(
            f"{filename}: invalid type '{fm['type']}'. "
            f"Must be one of: {', '.join(sorted(VALID_CHANGELOG_TYPES))}"
        )

    content = filepath.read_text(encoding="utf-8")
    for section in REQUIRED_CHANGELOG_SECTIONS:
        if section not in content:
            errors.append(f"{filename}: missing required section '{section}'")

    return errors


def validate_skill_version(project_root: Path) -> list[str]:
    """Validate that SKILL.md frontmatter version matches body version.

    Only runs if specbuilder/SKILL.md exists (skips for consumer projects).
    Returns list of errors (empty if valid or file not present).
    """
    skill_md = project_root / "specbuilder" / "SKILL.md"
    if not skill_md.exists():
        return []

    content = skill_md.read_text(encoding="utf-8")

    # Parse frontmatter version
    fm = parse_frontmatter(skill_md)
    fm_ver = fm.get("version")
    if not fm_ver:
        return []

    # Search body for Current version: **X.Y.Z**
    match = re.search(r"Current version:\s*\*\*([^*]+)\*\*", content)
    if not match:
        return []

    body_ver = match.group(1).strip()
    if fm_ver != body_ver:
        return [f"SKILL.md: frontmatter version '{fm_ver}' != body version '{body_ver}'"]

    return []


def validate_project(project_root: Path) -> list[str]:
    """Validate all structured files in a spec-driven project.

    Args:
        project_root: Root directory of the project.

    Returns:
        List of all validation errors found. Empty list means all valid.
    """
    all_errors = []

    decisions_dir = project_root / DEFAULT_DECISIONS_DIR
    proposals_dir = project_root / DEFAULT_PROPOSALS_DIR
    ac_dir = project_root / "spec" / "acceptance-criteria"

    # Architecture files
    if decisions_dir.exists():
        for f in sorted(decisions_dir.glob("*.md")):
            all_errors.extend(validate_decision(f))

    if proposals_dir.exists():
        for f in sorted(proposals_dir.glob("**/*.md")):
            all_errors.extend(validate_proposal(f))

    # Spec modules
    modules_dir = project_root / "spec" / "modules"
    if modules_dir.exists():
        for f in sorted(modules_dir.glob("[0-9]*-*.md")):
            if not f.name.startswith("00-"):
                all_errors.extend(validate_spec_module(f, ac_dir))

    # Acceptance criteria files
    if ac_dir.exists():
        for f in sorted(ac_dir.glob("[0-9]*-*.md")):
            all_errors.extend(validate_ac_file(f))

    # Changelog entries
    changelog_dir = project_root / "spec" / "changelog"
    if changelog_dir.exists():
        for f in sorted(changelog_dir.glob("*.md")):
            all_errors.extend(validate_changelog_entry(f))

    # SKILL.md version consistency
    all_errors.extend(validate_skill_version(project_root))

    return all_errors

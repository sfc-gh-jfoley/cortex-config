"""Shared configuration constants for the SpecBuilder package.

This is the single source of truth for paths, valid statuses,
required fields, file patterns, and defaults used across all modules.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

try:
    import tomllib  # Python 3.11+
except ImportError:  # pragma: no cover
    import tomli as tomllib  # type: ignore[no-redef]  # Python 3.10 fallback

# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------

PACKAGE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = PACKAGE_DIR / "templates"


def get_project_root(start: Path | None = None) -> Path:
    """Walk up from `start` (default: cwd) to find the project root.

    Heuristic: first directory containing a `spec/` subdirectory or `.git/`.
    Falls back to `start` itself if nothing is found.
    """
    current = (start or Path.cwd()).resolve()
    for parent in [current, *current.parents]:
        if (parent / "spec").is_dir() or (parent / ".git").is_dir():
            return parent
    return current


# ---------------------------------------------------------------------------
# File naming patterns
# ---------------------------------------------------------------------------

# Architecture files: 001-slug.md, 002-slug.md, ...
ARCH_FILE_PATTERN = re.compile(r"^\d{3}-[a-z0-9-]+\.md$")

# Spec modules: 01-slug.md, 02-slug.md, ... (00 is reserved for auto-gen)
SPEC_FILE_PATTERN = re.compile(r"^\d{2,}-[a-z0-9-]+\.md$")


# ---------------------------------------------------------------------------
# Required frontmatter fields
# ---------------------------------------------------------------------------

REQUIRED_DECISION_FIELDS = {"id", "title", "date", "status"}
REQUIRED_PROPOSAL_FIELDS = {
    "id", "title", "phase", "status", "depends_on", "impacts_modules", "created"
}

# Pattern for validated promoted_to field values (e.g. MOD-01, MOD-12)
PROMOTED_TO_PATTERN = re.compile(r"^MOD-\d{2,}$")

REQUIRED_SPEC_FIELDS = {"id", "title", "status", "version", "last_updated"}
HANDOVER_SPEC_FIELDS: frozenset = frozenset({"from_handover"})
REQUIRED_AC_FIELDS = {"id", "title", "status", "version", "last_updated", "spec_reference"}


# ---------------------------------------------------------------------------
# Valid status values
# ---------------------------------------------------------------------------

VALID_DECISION_STATUSES = {"accepted", "proposed", "deprecated", "superseded"}
VALID_PROPOSAL_STATUSES = {"planned", "in-progress", "implemented", "parked", "cancelled"}
VALID_SPEC_STATUSES = {"draft", "in-review", "accepted", "implemented"}
VALID_AC_STATUSES = {"draft", "in-review", "accepted", "signed-off"}


# ---------------------------------------------------------------------------
# Required markdown sections
# ---------------------------------------------------------------------------

REQUIRED_DECISION_SECTIONS = ["## Context", "## Decision", "## Consequences"]
REQUIRED_PROPOSAL_SECTIONS = ["## Problem Statement", "## Summary", "## Prerequisites", "## Scope"]
REQUIRED_SPEC_SECTIONS = [
    "## Executive Summary",
    "## Inputs",
    "## Output",
    "## Acceptance Criteria",
    "## Edge Cases",
]


# ---------------------------------------------------------------------------
# Relative directory paths (from project root)
# ---------------------------------------------------------------------------

DEFAULT_SPEC_DIR = "spec"
DEFAULT_MODULES_DIR = "spec/modules"
DEFAULT_DECISIONS_DIR = "spec/architecture/decisions"
DEFAULT_PROPOSALS_DIR = "spec/architecture/proposals"
DEFAULT_AC_DIR = "spec/acceptance-criteria"
DEFAULT_MANIFEST_FILE = "spec/manifest.json"
DEFAULT_README_FILE = "spec/README.md"
DEFAULT_AC_README_FILE = "spec/acceptance-criteria/README.md"

# Implementation output defaults
DEFAULT_IMPL_DIR = "impl"
DEFAULT_SPECBUILDER_META_DIR = ".specbuilder"
DEFAULT_SUMMARY_FILE = "spec/POC-SUMMARY.md"

# Sentinel comments for auto-generated table boundaries
README_TABLE_BEGIN = "<!-- BEGIN_AUTO_MODULES -->"
README_TABLE_END = "<!-- END_AUTO_MODULES -->"
AC_TABLE_BEGIN = "<!-- BEGIN_AUTO_AC_STATUS -->"
AC_TABLE_END = "<!-- END_AUTO_AC_STATUS -->"
PROPOSALS_TABLE_BEGIN = "<!-- BEGIN_AUTO_PROPOSALS -->"
PROPOSALS_TABLE_END = "<!-- END_AUTO_PROPOSALS -->"


# ---------------------------------------------------------------------------
# Scaffold defaults
# ---------------------------------------------------------------------------

# spec/ is intentionally excluded from the default. Adding it retroactively
# breaks existing installs. Users who want spec/ protected should pass
# --protected-dirs spec/ at scaffold time.
DEFAULT_PROTECTED_DIRS = ["specbuilder/", "src/", "lib/", "impl/"]

# Supported artifact file extensions for Output section parsing
ARTIFACT_EXTENSIONS = (
    "sql", "py", "yaml", "yml", "json", "toml", "md", "sh",
    "ts", "js", "csv", "tf", "xml",
)
DEFAULT_TEMPLATE_STYLE = "standard"


# ---------------------------------------------------------------------------
# Skill discovery defaults
# ---------------------------------------------------------------------------

DISCOVERY_MAX_RESULTS = 5
DISCOVERY_MIN_RELEVANCE = 0.3
DOMAIN_HINTS_PATH = PACKAGE_DIR / "domain-hints.json"

# Cache configuration
CATALOG_CACHE_DIR = Path(os.environ.get("SPECBUILDER_CACHE_DIR", Path.home() / ".specbuilder"))
CATALOG_CACHE_TTL_DAYS = 7


# ---------------------------------------------------------------------------
# Drift detection defaults
# ---------------------------------------------------------------------------

DRIFT_STALENESS_DAYS = 30


# ---------------------------------------------------------------------------
# Parallel execution
# ---------------------------------------------------------------------------

MAX_CONCURRENT_AGENTS = 0  # Max agents per batch; 0 = unlimited (use CoCo's native limits)

# Team name format for implementation batches (zero-padded module number)
IMPL_TEAM_NAME_FMT = "specbuilder-impl-{:02d}"


# ---------------------------------------------------------------------------
# CI integration defaults
# ---------------------------------------------------------------------------

CI_ANNOTATION_FORMAT = "plain"  # Output format: "plain", "github", "gitlab"
CI_PROMOTE_ON_MERGE = True  # Whether --promote-merged auto-commits the status change


# ---------------------------------------------------------------------------
# Quality gate defaults
# ---------------------------------------------------------------------------

QUALITY_GATE_THRESHOLD = 75  # Minimum quality score for spec acceptance/sign-off
GATE_SENTINEL_MAX_AGE_SECONDS: int = 1800  # 30 minutes; sentinels older than this are rejected


# ---------------------------------------------------------------------------
# Environment validation defaults
# ---------------------------------------------------------------------------

SPECBUILDER_TOML_FILE = ".specbuilder.toml"
POC_SENTINEL = "spec/.poc"

QUALITY_PROFILES: dict[str, dict] = {
    "poc": {
        "threshold": 50,
        "skip_checks": ["testability", "edge_case_traceability"],
        "description": "Relaxed gate for proof-of-concept engagements",
        "validation_tier": "compile",
        "self_correct": False,
        "max_retries": 0,
    },
    "full": {
        "threshold": 75,
        "skip_checks": [],
        "description": "Standard gate for full SDD mode deliveries (default)",
        "validation_tier": "dry-run",
        "self_correct": False,
        "max_retries": 0,
    },
    "strict": {
        "threshold": 90,
        "skip_checks": [],
        "description": "High bar for critical systems",
        "validation_tier": "verify",
        "self_correct": True,
        "max_retries": 2,
    },
    "prototype": {
        "threshold": 50,
        "skip_checks": ["testability", "edge_case_traceability"],
        "description": "Relaxed profile for time-boxed prototype work."
        " Enforces minimal structure only.",
        "validation_tier": "compile",
        "self_correct": False,
        "max_retries": 0,
    },
}

# Valid validation tier names (ordered by depth)
VALIDATION_TIERS = ("compile", "dry-run", "smoke-test", "verify")

# Default sandbox schema prefix for Tier 2+ validation
DEFAULT_SANDBOX_PREFIX = "_SPECBUILDER_SANDBOX"


def get_active_profile(project_root: Path) -> dict:
    """Resolve the active quality profile from config/env/mode.

    Resolution order (highest wins):
    1. SPECBUILDER_QUALITY_PROFILE env var
    2. .specbuilder.toml [quality].profile field
    3. Auto-detection from project mode (spec/.poc exists -> poc profile)
    4. Default: "full"

    Returns a copy of the profile dict with the profile name added as 'name'.
    """
    # 1. Check env var
    env_profile = os.environ.get("SPECBUILDER_QUALITY_PROFILE")
    if env_profile and env_profile in QUALITY_PROFILES:
        return {"name": env_profile, **QUALITY_PROFILES[env_profile]}

    # 2. Check .specbuilder.toml
    config_path = project_root / SPECBUILDER_TOML_FILE
    if config_path.exists():
        try:
            config = tomllib.loads(config_path.read_text(encoding="utf-8"))
            profile_name = config.get("quality", {}).get("profile")
            if profile_name and profile_name in QUALITY_PROFILES:
                return {"name": profile_name, **QUALITY_PROFILES[profile_name]}
            elif profile_name:
                sys.stderr.write(
                    f"Warning: unknown quality profile '{profile_name}' in .specbuilder.toml; "
                    f"falling back to 'full'.\n"
                )
        except Exception as e:
            print(f"Warning: failed to read .specbuilder.toml: {e}. Using default profile.",
                  flush=True)

    # 3. Check project mode (spec/.poc sentinel)
    if (project_root / "spec" / ".poc").exists():
        return {"name": "poc", **QUALITY_PROFILES["poc"]}

    # 3a. Check .specbuilder.toml [project].mode (mirrors is_poc_mode() second check)
    if config_path.exists():
        try:
            config = tomllib.loads(config_path.read_text(encoding="utf-8"))
            if config.get("project", {}).get("mode") == "poc":
                return {"name": "poc", **QUALITY_PROFILES["poc"]}
        except Exception:
            pass  # already warned above in step 2

    # 4. Default
    return {"name": "full", **QUALITY_PROFILES["full"]}


def is_poc_mode(project_root: Path) -> bool:
    """Check if the project is in POC mode.

    Returns True if either:
    - The sentinel file spec/.poc exists, OR
    - .specbuilder.toml has mode = "poc" under [project]
    """
    if os.environ.get("SPECBUILDER_QUALITY_PROFILE") == "poc":
        return True

    # Check sentinel file
    if (project_root / POC_SENTINEL).exists():
        return True

    # Check .specbuilder.toml
    config_path = project_root / SPECBUILDER_TOML_FILE
    if config_path.exists():
        try:
            config = tomllib.loads(config_path.read_text(encoding="utf-8"))
            result: bool = config.get("project", {}).get("mode") == "poc"
            return result
        except Exception as e:
            print(f"Warning: failed to read .specbuilder.toml: {e}. Assuming non-POC mode.",
                  flush=True)

    return False


def is_prototype_mode(project_root: Path) -> bool:
    """Check if the project is in prototype mode.

    Returns True if either:
    - .specbuilder.toml has mode = "prototype" under [project], OR
    - SPECBUILDER_QUALITY_PROFILE env var equals "prototype"
    """
    if os.environ.get("SPECBUILDER_QUALITY_PROFILE") == "prototype":
        return True

    config_path = project_root / SPECBUILDER_TOML_FILE
    if config_path.exists():
        try:
            config = tomllib.loads(config_path.read_text(encoding="utf-8"))
            if config.get("quality", {}).get("profile") == "prototype":
                return True
            result: bool = config.get("project", {}).get("mode") == "prototype"
            return result
        except Exception as e:
            print(f"Warning: failed to read .specbuilder.toml: {e}. Assuming non-prototype mode.",
                  flush=True)

    return False


def get_effective_profile(project_root: Path) -> dict:
    """Resolve the effective quality profile for the project.

    Delegates to get_active_profile — single-level resolution, no sub-mode merging.
    """
    return get_active_profile(project_root)


def get_handover_flag(project_root: Path) -> bool:
    """Return True if this project should produce a customer handover artifact.

    Reads [project].handover from .specbuilder.toml.
    Also accepts legacy sub_mode = "demo" with a DeprecationWarning.
    """
    toml_path = project_root / SPECBUILDER_TOML_FILE
    if not toml_path.exists():
        return False
    try:
        with open(toml_path, "rb") as f:
            config = tomllib.load(f)
        project = config.get("project", {})
        if project.get("handover"):
            return True
        if project.get("sub_mode") == "demo":
            import warnings
            warnings.warn(
                "[project].sub_mode = 'demo' is deprecated. "
                "Use [project].handover = true instead.",
                DeprecationWarning,
                stacklevel=2,
            )
            return True
    except Exception:
        pass
    return False


# ---------------------------------------------------------------------------
# AC coverage mapping
# ---------------------------------------------------------------------------

MODULE_TEST_MAPPING: dict[str, list[str]] = {
    "MOD-01": ["test_scaffold.py"],
    "MOD-02": ["test_manifest_and_readme.py", "test_validation.py"],
    "MOD-03": ["test_ci.py", "test_validation.py"],
    "MOD-04": ["test_discover_skills.py"],
    "MOD-05": ["test_generate_module.py", "test_domain_templates.py", "test_acceptance_runner.py"],
    "MOD-06": ["test_detect_drift.py"],
    "MOD-07": ["test_implement.py", "test_implement_cli.py"],
    "MOD-08": ["test_workspace_parallel.py", "test_propose_workflow.py"],
}

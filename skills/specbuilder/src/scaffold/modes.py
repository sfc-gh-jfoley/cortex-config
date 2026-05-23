"""Scaffold mode implementations (full, lite, poc, demo)."""

from __future__ import annotations

import json
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any

from specbuilder.src.config import (
    DEFAULT_PROTECTED_DIRS,
    SPECBUILDER_TOML_FILE,
)

from .ci_templates import _install_ci_template
from .git_hooks import _install_git_precommit, _make_executable
from .templates import _render_template

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VALID_TEMPLATE_STYLES = {"standard", "minimal"}

_PACKAGE_MANAGER_FILES = [
    "pyproject.toml",
    "requirements.txt",
    "Pipfile",
    "poetry.lock",
    "uv.lock",
]


def _detect_package_manager(project_root: Path) -> str | None:
    """Detect an existing package manager in the project.

    Returns the filename that indicates a manager (e.g., "pyproject.toml"),
    or None if no package manager is detected.
    """
    for filename in _PACKAGE_MANAGER_FILES:
        if (project_root / filename).exists():
            return filename
    return None


def _slugify_project(name: str) -> str:
    """Convert a project name to a valid Python package/pyproject name."""
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug[:60] if slug else "my-project"


def _check_existing(project_root: Path, spec_dir: str) -> bool:
    """Return ``True`` if *project_root* already contains a spec directory."""
    return (project_root / spec_dir).is_dir()


def _merge_hooks_json(existing_path: Path, new_hook: dict[str, Any]) -> dict[str, Any]:
    """Merge *new_hook* into an existing ``hooks.json`` file.

    The change-control ``PreToolUse`` entry is added only when an entry
    with the same command is not already present.  All other hooks are
    preserved untouched.
    """
    with open(existing_path, encoding="utf-8") as fh:
        data: dict[str, Any] = json.load(fh)

    new_pre = new_hook.get("hooks", {}).get("PreToolUse", [])
    existing_pre = data.setdefault("hooks", {}).setdefault("PreToolUse", [])

    # Collect commands already registered so we don't duplicate.
    existing_commands: set[str] = set()
    for entry in existing_pre:
        for hook in entry.get("hooks", []):
            cmd = hook.get("command", "")
            if cmd:
                existing_commands.add(cmd)

    for entry in new_pre:
        dominated = False
        for hook in entry.get("hooks", []):
            if hook.get("command", "") in existing_commands:
                dominated = True
                break
        if not dominated:
            existing_pre.append(entry)

    return data


# ---------------------------------------------------------------------------
# Scaffold definition
# ---------------------------------------------------------------------------


def _build_file_map(
    project_root: Path,
    spec_dir: str,
    context: dict,
) -> list[tuple[Path, str, bool]]:
    """Return a list of ``(target_path, template_name, executable)`` tuples.

    This defines every file the scaffold produces and the template that
    generates its content.
    """
    s = spec_dir  # shorthand
    return [
        # spec/ tree
        (project_root / s / "README.md", "README.md.j2", False),
        (project_root / s / "INTAKE.md", "INTAKE.md.j2", False),
        (project_root / s / "architecture" / "SCHEMA.md", "SCHEMA.md.j2", False),
        (
            project_root / s / "architecture" / "decisions" / "001-spec-driven-development.md",
            "first-adr.md.j2",
            False,
        ),
        (project_root / s / "acceptance-criteria" / "README.md", "ac-readme.md.j2", False),
        # .cortex/ tree
        (project_root / ".cortex" / "hooks.json", "hooks.json.j2", False),
        (
            project_root / ".cortex" / "hooks" / "change-control-gate.sh",
            "change-control-gate.sh.j2",
            True,
        ),
        # Project-level config
        (project_root / SPECBUILDER_TOML_FILE, ".specbuilder.toml.j2", False),
    ]


def _build_lite_file_map(
    project_root: Path,
    spec_dir: str,
    context: dict,
) -> list[tuple[Path, str, bool]]:
    """Return the minimal file map for lite mode.

    Lite mode only produces: INTAKE.md, hooks.json, change-control-gate.sh.
    """
    s = spec_dir
    return [
        (project_root / s / "INTAKE.md", "INTAKE.md.j2", False),
        # .cortex/ tree
        (project_root / ".cortex" / "hooks.json", "hooks.json.j2", False),
        (
            project_root / ".cortex" / "hooks" / "change-control-gate.sh",
            "change-control-gate.sh.j2",
            True,
        ),
        # Project-level config
        (project_root / SPECBUILDER_TOML_FILE, ".specbuilder.toml.j2", False),
    ]


# Lite mode only needs spec/modules/
_LITE_EMPTY_DIRS_REL = [
    "modules",
]

# Empty directories that must exist even without files in them.
_EMPTY_DIRS_REL = [
    "architecture/proposals",
    "modules",
]


# ---------------------------------------------------------------------------
# Mode detection (EXT-003)
# ---------------------------------------------------------------------------


def detect_mode(project_root: Path, spec_dir: str = "spec") -> str:
    """Detect the current scaffold mode of a project.

    Returns: "full", "lite", or "fresh".
    """
    spec_path = project_root / spec_dir
    if (spec_path / "architecture" / "SCHEMA.md").is_file():
        return "full"
    elif (spec_path / "modules").is_dir():
        return "lite"
    return "fresh"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def scaffold_lite(
    project_root: Path,
    project_name: str,
    protected_dirs: list[str] | None = None,
    spec_dir: str = "spec",
    dry_run: bool = False,
) -> dict:
    """Create a minimal spec structure (lite mode).

    Produces only: spec/modules/, spec/INTAKE.md, .cortex/hooks/,
    and a simplified agent.md.
    """
    if protected_dirs is None:
        protected_dirs = list(DEFAULT_PROTECTED_DIRS)

    project_root = project_root.resolve()

    # Check if already scaffolded
    mode = detect_mode(project_root, spec_dir)
    if mode == "full":
        return {
            "created": [],
            "skipped": [],
            "merged": [],
            "message": (
                f"Project already has full spec structure in '{spec_dir}/'. "
                f"Use without --lite to re-scaffold, or --upgrade is not needed."
            ),
        }
    if mode == "lite":
        return {
            "created": [],
            "skipped": [],
            "merged": [],
            "message": (
                f"Lite spec structure already exists in '{spec_dir}/'. "
                f"Use --upgrade to convert to full mode."
            ),
        }

    context = {
        "project_name": project_name,
        "project_slug": _slugify_project(project_name),
        "protected_dirs": protected_dirs,
        "spec_dir": spec_dir,
        "date_today": date.today().isoformat(),
    }

    file_map = _build_lite_file_map(project_root, spec_dir, context)

    created: list[str] = []
    skipped: list[str] = []
    merged: list[str] = []

    # Create spec/modules/ directory
    for rel in _LITE_EMPTY_DIRS_REL:
        dir_path = project_root / spec_dir / rel
        if dry_run:
            print(f"[dry-run] mkdir {dir_path}")
        else:
            dir_path.mkdir(parents=True, exist_ok=True)

    # Write files
    for target, template_name, executable in file_map:
        rel = str(target.relative_to(project_root))

        if target.name == "hooks.json" and target.exists():
            new_hook = json.loads(_render_template(template_name, context))
            merged_data = _merge_hooks_json(target, new_hook)
            if dry_run:
                print(f"[dry-run] merge {rel}")
            else:
                target.write_text(
                    json.dumps(merged_data, indent=2) + "\n",
                    encoding="utf-8",
                )
            merged.append(rel)
            continue

        if target.exists():
            skipped.append(rel)
            continue

        content = _render_template(template_name, context)
        if dry_run:
            print(f"[dry-run] create {rel}")
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            if executable:
                _make_executable(target)
        created.append(rel)

    # Simplified agent.md (no architecture/changelog sections)
    agent_path = project_root / "agent.md"
    if not agent_path.exists():
        agent_content = (
            f"# {project_name}\n\n"
            f"## Spec-Driven Development (Lite Mode)\n\n"
            f"This project uses spec-driven development in lite mode.\n\n"
            f"### Workflow\n\n"
            f"1. Describe your requirement in chat or fill `{spec_dir}/INTAKE.md`\n"
            f"2. Generate a spec: `python3 -m specbuilder generate-module`\n"
            f"3. Review and accept the spec\n"
            f"4. Implement (change-control hook enforces spec-first)\n\n"
            f"### Upgrade to Full Mode\n\n"
            f"Run `python3 -m specbuilder scaffold --upgrade` to add architecture "
            f"decisions, acceptance criteria tracking, and changelog management.\n"
        )
        if dry_run:
            print("[dry-run] create agent.md")
        else:
            agent_path.write_text(agent_content, encoding="utf-8")
        created.append("agent.md")
    else:
        skipped.append("agent.md")

    # Add spec/.prototype and .specbuilder/ to .gitignore
    gitignore_path = project_root / ".gitignore"
    prototype_line = f"{spec_dir}/.prototype"
    specbuilder_meta_line = ".specbuilder/"
    if gitignore_path.exists():
        existing = gitignore_path.read_text(encoding="utf-8")
        additions = ""
        if prototype_line not in existing:
            additions += f"\n# Prototype mode sentinel\n{prototype_line}\n"
        if specbuilder_meta_line not in existing:
            additions += (
                "\n# SpecBuilder implementation metadata\n"
                f"{specbuilder_meta_line}\n"
            )
        if additions:
            if not dry_run:
                with open(gitignore_path, "a", encoding="utf-8") as f:
                    f.write(additions)
            merged.append(".gitignore")
    else:
        if not dry_run:
            gitignore_path.write_text(
                f"# Prototype mode sentinel\n{prototype_line}\n\n"
                f"# SpecBuilder implementation metadata\n"
                f"{specbuilder_meta_line}\n",
                encoding="utf-8",
            )
        created.append(".gitignore")

    return {"created": created, "skipped": skipped, "merged": merged}


def scaffold_poc(
    project_root: Path,
    project_name: str,
    protected_dirs: list[str] | None = None,
    spec_dir: str = "spec",
    reason: str = "",
    dry_run: bool = False,
) -> dict:
    """Scaffold a project in POC mode (lite structure + POC sentinel + poc profile).

    Creates the same minimal structure as scaffold_lite, plus:
    - spec/.poc sentinel file with activation metadata
    - .specbuilder.toml configured with mode = "poc" and profile = "poc"
    """
    from datetime import datetime, timezone

    from specbuilder.src.config import POC_SENTINEL, SPECBUILDER_TOML_FILE

    # First scaffold the lite structure
    result = scaffold_lite(
        project_root=project_root,
        project_name=project_name,
        protected_dirs=protected_dirs,
        spec_dir=spec_dir,
        dry_run=dry_run,
    )

    # If lite scaffold reported an existing structure, return early
    if result.get("message"):
        return result

    project_root = project_root.resolve()

    # Create spec/.poc sentinel file
    poc_path = project_root / POC_SENTINEL
    sentinel_data = json.dumps(
        {
            "activated": datetime.now(timezone.utc).isoformat(),
            "reason": reason,
        },
        indent=2,
    )
    if dry_run:
        print(f"[dry-run] create {POC_SENTINEL}")
    else:
        poc_path.parent.mkdir(parents=True, exist_ok=True)
        poc_path.write_text(sentinel_data + "\n", encoding="utf-8")
    result["created"].append(POC_SENTINEL)

    # Overwrite .specbuilder.toml with POC-specific config
    toml_path = project_root / SPECBUILDER_TOML_FILE
    toml_content = (
        "# SpecBuilder project configuration\n"
        "\n"
        "[project]\n"
        f'name = "{project_name}"\n'
        'mode = "poc"\n'
        "\n"
        "[quality]\n"
        'profile = "poc"\n'
    )
    if dry_run:
        print(f"[dry-run] overwrite {SPECBUILDER_TOML_FILE}")
    else:
        toml_path.write_text(toml_content, encoding="utf-8")
    # The toml file was already created by scaffold_lite; we overwrote it

    return result


def scaffold_demo(
    project_root: Path,
    project_name: str,
    protected_dirs: list[str] | None = None,
    spec_dir: str = "spec",
    reason: str = "",
    dry_run: bool = False,
) -> dict:
    """Scaffold a project in demo mode (POC + deploy/verify + handover).

    Creates the same structure as scaffold_poc, plus:
    - .specbuilder.toml configured with sub_mode = "demo"
    - Demo Configuration section appended to spec/INTAKE.md
    """
    from specbuilder.src.config import SPECBUILDER_TOML_FILE

    # First scaffold as POC
    result = scaffold_poc(
        project_root=project_root,
        project_name=project_name,
        protected_dirs=protected_dirs,
        spec_dir=spec_dir,
        reason=reason,
        dry_run=dry_run,
    )

    # If POC scaffold reported an existing structure, return early
    if result.get("message"):
        return result

    project_root = project_root.resolve()

    # Overwrite .specbuilder.toml with demo-specific config
    toml_path = project_root / SPECBUILDER_TOML_FILE
    toml_content = (
        "# SpecBuilder project configuration\n"
        "\n"
        "[project]\n"
        f'name = "{project_name}"\n'
        'mode = "poc"\n'
        'sub_mode = "demo"\n'
        "\n"
        "[quality]\n"
        'profile = "poc"\n'
        "\n"
        "[demo]\n"
        "# Target database for sandbox deployment (required for demo-run)\n"
        '# database = "YOUR_DATABASE"\n'
        '# sandbox_prefix = "_SPECBUILDER_DEMO"\n'
        '# test_role = "SPECBUILDER_DEMO_ROLE"\n'
    )
    if dry_run:
        print(f"[dry-run] overwrite {SPECBUILDER_TOML_FILE} with demo config")
    else:
        toml_path.write_text(toml_content, encoding="utf-8")

    # Append Demo Configuration section to INTAKE.md
    intake_path = project_root / spec_dir / "INTAKE.md"
    demo_section = (
        "\n\n## Demo Configuration\n\n"
        "| Setting | Value | Notes |\n"
        "|---------|-------|-------|\n"
        "| Target Database | | Required for deployment |\n"
        "| Sandbox Schema Prefix | `_SPECBUILDER_DEMO` | "
        "Isolated schema for demo artifacts |\n"
        "| Test Role | `SPECBUILDER_DEMO_ROLE` | "
        "Least-privilege role for deployment |\n"
        "| Source Data References | | "
        "Existing tables to read from (optional) |\n"
    )
    if dry_run:
        print(f"[dry-run] append demo configuration to {spec_dir}/INTAKE.md")
    else:
        if intake_path.exists():
            existing = intake_path.read_text(encoding="utf-8")
            intake_path.write_text(existing + demo_section, encoding="utf-8")
    result["created"].append(f"{SPECBUILDER_TOML_FILE} (demo config)")

    return result


def scaffold_project(
    project_root: Path,
    project_name: str,
    protected_dirs: list[str] | None = None,
    spec_dir: str = "spec",
    template_style: str = "standard",
    use_git_hooks: bool = False,
    ci_platform: str | None = None,
    dry_run: bool = False,
) -> dict:
    """Create the full spec-driven directory structure in *project_root*.

    Parameters
    ----------
    project_root:
        Absolute path to the target project.
    project_name:
        Human-readable name used in generated files.
    protected_dirs:
        Directories protected by the change-control hook.
    spec_dir:
        Name of the spec directory (default ``"spec"``).
    template_style:
        ``"standard"`` or ``"minimal"``.
    use_git_hooks:
        Also install a ``pre-commit`` git hook (not yet implemented).
    dry_run:
        If ``True``, report planned actions without writing anything.

    Returns
    -------
    dict
        ``{"created": [...], "skipped": [...], "merged": [...]}``.
    """
    if template_style not in _VALID_TEMPLATE_STYLES:
        raise ValueError(
            f"Invalid template_style {template_style!r}. "
            f"Choose from: {', '.join(sorted(_VALID_TEMPLATE_STYLES))}"
        )

    if protected_dirs is None:
        protected_dirs = list(DEFAULT_PROTECTED_DIRS)

    project_root = project_root.resolve()

    # Idempotency: refuse to re-scaffold an existing spec tree.
    if _check_existing(project_root, spec_dir):
        return {
            "created": [],
            "skipped": [],
            "merged": [],
            "message": (
                f"Spec directory '{spec_dir}/' already exists in "
                f"{project_root}. Aborting to avoid corruption."
            ),
        }

    context = {
        "project_name": project_name,
        "project_slug": _slugify_project(project_name),
        "protected_dirs": protected_dirs,
        "spec_dir": spec_dir,
        "date_today": date.today().isoformat(),
    }

    file_map = _build_file_map(project_root, spec_dir, context)

    created: list[str] = []
    skipped: list[str] = []
    merged: list[str] = []

    # -- Ensure empty directories exist ------------------------------------
    for rel in _EMPTY_DIRS_REL:
        dir_path = project_root / spec_dir / rel
        if dry_run:
            print(f"[dry-run] mkdir {dir_path}")
        else:
            dir_path.mkdir(parents=True, exist_ok=True)

    # -- Write files -------------------------------------------------------
    for target, template_name, executable in file_map:
        rel = str(target.relative_to(project_root))

        # Special handling: merge hooks.json when it already exists.
        if target.name == "hooks.json" and target.exists():
            new_hook = json.loads(_render_template(template_name, context))
            merged_data = _merge_hooks_json(target, new_hook)
            if dry_run:
                print(f"[dry-run] merge {rel}")
            else:
                target.write_text(
                    json.dumps(merged_data, indent=2) + "\n",
                    encoding="utf-8",
                )
            merged.append(rel)
            continue

        if target.exists():
            skipped.append(rel)
            continue

        content = _render_template(template_name, context)
        if dry_run:
            print(f"[dry-run] create {rel}")
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            if executable:
                _make_executable(target)
        created.append(rel)

    # -- Package manager detection + pyproject.toml -------------------------
    detected_pm = _detect_package_manager(project_root)
    if detected_pm is None:
        pyproject_path = project_root / "pyproject.toml"
        rel = "pyproject.toml"
        if dry_run:
            print(f"[dry-run] create {rel}")
        else:
            content = _render_template("pyproject.toml.j2", context)
            pyproject_path.write_text(content, encoding="utf-8")
        created.append(rel)

    # -- agent.md creation / injection --------------------------------------
    agent_path = project_root / "agent.md"
    agent_section = _render_template("agent-section.md.j2", context)
    if agent_path.exists():
        existing_content = agent_path.read_text(encoding="utf-8")
        if "## Spec-Driven Development Workflow" not in existing_content:
            if dry_run:
                print("[dry-run] append spec workflow section to agent.md")
            else:
                with open(agent_path, "a", encoding="utf-8") as f:
                    f.write("\n\n" + agent_section)
            merged.append("agent.md")
        else:
            skipped.append("agent.md (spec workflow section already present)")
    else:
        agent_content = f"# {project_name}\n\n" + agent_section
        if dry_run:
            print("[dry-run] create agent.md")
        else:
            agent_path.write_text(agent_content, encoding="utf-8")
        created.append("agent.md")

    # -- Post-scaffold: generate manifest and README tables ----------------
    try:
        from specbuilder.src.generate_index import generate_manifest, regenerate_readme_table

        generate_manifest(project_root)
        regenerate_readme_table(project_root)
    except Exception:
        # Non-fatal: manifest generation is optional on fresh scaffold
        pass

    # -- Install git pre-commit hook to auto-regenerate manifest ------------
    _install_git_precommit(project_root, spec_dir, dry_run, created, skipped)

    # -- CI template installation (EXT-007) ----------------------------------
    if ci_platform and ci_platform != "none":
        _install_ci_template(project_root, ci_platform, dry_run, created, skipped)

    # -- Warn if no protected dirs -----------------------------------------
    if not protected_dirs:
        print(
            "Warning: no protected directories specified. "
            "Change-control hook will not gate any paths.",
            file=sys.stderr,
        )

    return {
        "created": created,
        "skipped": skipped,
        "merged": merged,
        "package_manager": detected_pm or "uv (generated)",
    }

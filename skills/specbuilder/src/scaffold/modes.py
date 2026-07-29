"""Scaffold mode implementations (full, poc)."""

from __future__ import annotations

import json
import re
import shutil
import sys
from datetime import date
from pathlib import Path
from typing import Any

from specbuilder.src.config import (
    DEFAULT_PROTECTED_DIRS,
    POC_SENTINEL,
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


def _toml_str(v: str) -> str:
    """Return a TOML-safe double-quoted string literal for v."""
    return '"' + v.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _merge_hooks_json(existing_path: Path, new_hook: dict[str, Any]) -> dict[str, Any]:
    """Merge *new_hook* into an existing ``hooks.json`` file.

    The change-control ``PreToolUse`` entry is added only when an entry
    with the same command is not already present.  All other hooks are
    preserved untouched.
    """
    try:
        with open(existing_path, encoding="utf-8") as fh:
            data: dict[str, Any] = json.load(fh)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"hooks.json at {existing_path} is not valid JSON: {exc}"
        ) from exc

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

# WARNING: Two separate TOML rendering paths exist for poc vs full scaffold mode.
# poc:  _specbuilder_toml_content() below (Python f-strings / inline helper)
# full: .specbuilder.toml.j2 template via _build_file_map()
# When adding a new TOML field, update BOTH paths. There is no shared abstraction.


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


# Minimal structure needs spec/modules/
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


def _detect_ci_platform(project_root: Path) -> str | None:
    """Detect the CI platform in use by probing the project root.

    Returns 'github' if a .github/ directory is present, 'gitlab' if a
    .gitlab-ci.yml file is present, or None if neither is detected.
    Detection order matches SKILL.md:114 (github takes precedence).
    """
    if (project_root / ".github").is_dir():
        return "github"
    if (project_root / ".gitlab-ci.yml").is_file():
        return "gitlab"
    return None


def detect_mode(project_root: Path, spec_dir: str = "spec") -> str:
    """Detect the current scaffold mode of a project.

    Returns: "full", "poc", or "fresh".
    """
    spec_path = project_root / spec_dir

    # Full-mode structural sentinel takes highest precedence — SCHEMA.md is
    # the definitive marker of a full project, even if toml says "poc".
    if (spec_path / "architecture" / "SCHEMA.md").is_file():
        return "full"

    toml_path = project_root / ".specbuilder.toml"
    if toml_path.exists():
        try:
            try:
                import tomllib
            except ImportError:
                import tomli as tomllib
            with open(toml_path, "rb") as f:
                config = tomllib.load(f)
            if config.get("project", {}).get("mode") == "poc":
                return "poc"
        except Exception:
            pass  # malformed toml — fall through to sentinel checks
    if (project_root / POC_SENTINEL).exists():
        return "poc"
    modules_dir = spec_path / "modules"
    if modules_dir.is_dir():
        if any(modules_dir.glob("*.md")):
            return "poc"
        return "fresh"  # empty dir — treat as fresh scaffold
    return "fresh"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _scaffold_minimal(
    project_root: Path,
    project_name: str,
    protected_dirs: list[str],
    spec_dir: str,
    ci_platform: str | None,
    dry_run: bool,
) -> dict:
    """Create minimal spec structure (modules/ dir + INTAKE.md + hooks + toml).

    Internal helper shared by scaffold_poc(). Not a public scaffold mode.
    """
    s = spec_dir
    context = {
        "project_name": project_name,
        "project_slug": _slugify_project(project_name),
        "protected_dirs": protected_dirs,
        "spec_dir": spec_dir,
        "mode": "poc",   # toml will be overwritten by caller with correct mode
        "date_today": date.today().isoformat(),
    }
    file_map = [
        (project_root / s / "INTAKE.md", "INTAKE.md.j2", False),
        # .cortex/ tree
        (project_root / ".cortex" / "hooks.json", "hooks.json.j2", False),
        (
            project_root / ".cortex" / "hooks" / "change-control-gate.sh",
            "change-control-gate.sh.j2",
            True,
        ),
        # Note: .specbuilder.toml is written by scaffold_poc() after this call.
        # It is not rendered here to avoid a wasted Jinja render that is always
        # immediately overwritten by the caller.
    ]

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
            try:
                merged_data = _merge_hooks_json(target, new_hook)
            except ValueError as exc:
                print(
                    f"Warning: {exc}\n"
                    f"Skipping hook merge — {rel} will not be updated. "
                    "Fix or delete the file and re-run scaffold.",
                    file=sys.stderr,
                )
                skipped.append(rel)
                continue
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

    # -- CI template installation ---------------------------------------------
    if ci_platform and ci_platform != "none":
        _install_ci_template(project_root, ci_platform, dry_run, created, skipped)

    return {"created": created, "skipped": skipped, "merged": merged}


def _specbuilder_toml_content(
    project_name: str,
    mode: str,
    handover: bool = False,
    spec_dir: str = "spec",
    protected_dirs: list[str] | None = None,
    extra_sections: str = "",
) -> str:
    """Render the canonical .specbuilder.toml content string.

    WARNING: This is the POC path for TOML generation. The full scaffold path
    uses .specbuilder.toml.j2 via _build_file_map(). When adding a new TOML
    field, update BOTH paths. There is no shared abstraction.
    """
    lines = [
        "# SpecBuilder project configuration",
        "",
        "[project]",
        f"name = {_toml_str(project_name)}",
        f'mode = "{mode}"',
        f"spec_dir = {_toml_str(spec_dir)}",
        f'protected_dirs = {json.dumps(protected_dirs or [])}',
    ]
    if handover:
        lines.append('handover = true')
    lines += ["", "[quality]", f'profile = "{mode}"']
    if extra_sections:
        lines += ["", extra_sections]
    return "\n".join(lines) + "\n"


def scaffold_poc(
    project_root: Path,
    project_name: str,
    protected_dirs: list[str] | None = None,
    spec_dir: str = "spec",
    ci_platform: str | None = None,
    reason: str = "",
    handover: bool = False,
    dry_run: bool = False,
) -> dict:
    """Scaffold a project in POC mode (minimal structure + POC sentinel + poc profile).

    Creates: spec/modules/, spec/INTAKE.md, .cortex/hooks/, agent.md, plus:
    - spec/.poc sentinel file with activation metadata
    - .specbuilder.toml configured with mode = "poc" and profile = "poc"

    When handover=True, also writes handover = true to .specbuilder.toml and
    appends the Demo Configuration section to spec/INTAKE.md.
    """
    from datetime import datetime, timezone

    from specbuilder.src.config import POC_SENTINEL, SPECBUILDER_TOML_FILE

    if protected_dirs is None:
        protected_dirs = list(DEFAULT_PROTECTED_DIRS)

    project_root = project_root.resolve()

    # Mode detection guard
    mode = detect_mode(project_root, spec_dir)
    if mode == "full":
        return {
            "created": [],
            "skipped": [],
            "merged": [],
            "message": (
                f"Project already has full spec structure in '{spec_dir}/'. "
                f"Use without --poc to re-scaffold, or --upgrade is not needed."
            ),
        }
    if mode == "poc":
        return {
            "created": [],
            "skipped": [],
            "merged": [],
            "message": "Already scaffolded as POC. Use --upgrade-from-poc to graduate.",
        }

    # Snapshot files that _scaffold_minimal() may create, for rollback on failure.
    # These files are written before the try block and won't appear in created_paths.
    _pre_scaffold_candidates = [
        project_root / ".cortex" / "hooks.json",
        project_root / ".cortex" / "hooks" / "change-control-gate.sh",
        project_root / "agent.md",
        project_root / ".gitignore",
    ]
    pre_scaffold_snapshot: dict[Path, bytes | None] = {
        p: (p.read_bytes() if p.exists() else None)
        for p in _pre_scaffold_candidates
    }

    # Scaffold the minimal structure (CI handled separately below for pyproject.toml ordering)
    result = _scaffold_minimal(
        project_root=project_root,
        project_name=project_name,
        protected_dirs=protected_dirs,
        spec_dir=spec_dir,
        ci_platform=None,  # CI installed after pyproject.toml below (Fix 1)
        dry_run=dry_run,
    )

    created_paths: list[Path] = []

    try:
        # -- Package manager detection + pyproject.toml (CI-enabled POC only) ----
        if ci_platform and ci_platform != "none":
            detected_pm = _detect_package_manager(project_root)
            if detected_pm is None:
                pyproject_path = project_root / "pyproject.toml"
                if not pyproject_path.exists():
                    context = {
                        "project_name": project_name,
                        "project_slug": _slugify_project(project_name),
                        "protected_dirs": protected_dirs,
                        "spec_dir": spec_dir,
                        "mode": "poc",
                        "date_today": date.today().isoformat(),
                    }
                    content = _render_template("pyproject.toml.j2", context)
                    if dry_run:
                        print("[dry-run] create pyproject.toml (required for CI install step)")
                    else:
                        pyproject_path.write_text(content, encoding="utf-8")
                        created_paths.append(pyproject_path)
                    result["created"].append("pyproject.toml")

        # -- CI template installation (after pyproject.toml is guaranteed present) --
        if ci_platform and ci_platform != "none" and not handover:
            _install_ci_template(project_root, ci_platform, dry_run,
                                 result["created"], result["skipped"])

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
            created_paths.append(poc_path)
        result["created"].append(POC_SENTINEL)

        # Build toml content — include handover flag and demo section when requested
        toml_path = project_root / SPECBUILDER_TOML_FILE
        if handover:
            _DEMO_CONFIG_TOML_SECTION = (
                "[demo]\n"
                "# Target database for sandbox deployment (required for demo-run)\n"
                '# database = "YOUR_DATABASE"\n'
                '# sandbox_prefix = "_SPECBUILDER_DEMO"\n'
                '# test_role = "SPECBUILDER_DEMO_ROLE"'
            )
            toml_content = _specbuilder_toml_content(
                project_name, mode="poc", handover=True,
                spec_dir=spec_dir, protected_dirs=protected_dirs,
                extra_sections=_DEMO_CONFIG_TOML_SECTION,
            )
        else:
            toml_content = _specbuilder_toml_content(
                project_name, mode="poc", spec_dir=spec_dir, protected_dirs=protected_dirs
            )
        if dry_run:
            print(f"[dry-run] overwrite {SPECBUILDER_TOML_FILE}")
        else:
            toml_path.write_text(toml_content, encoding="utf-8")
            created_paths.append(toml_path)
        # _scaffold_minimal() no longer writes the toml; this is the sole write.

        # Append Demo Configuration section to INTAKE.md when handover=True
        if handover:
            intake_path = project_root / spec_dir / "INTAKE.md"
            demo_intake_section = (
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
                    intake_path.write_text(existing + demo_intake_section, encoding="utf-8")
            result["created"].append(f"{SPECBUILDER_TOML_FILE} (handover config)")

        result["created_paths"] = list(created_paths)
        return result
    except Exception as exc:
        if not dry_run:
            # Restore files created by _scaffold_minimal() before the try block
            for path, original in pre_scaffold_snapshot.items():
                try:
                    if original is None:
                        path.unlink(missing_ok=True)
                    else:
                        path.write_bytes(original)
                except OSError:
                    pass
            for p in reversed(created_paths):
                try:
                    if p.is_file():
                        p.unlink(missing_ok=True)
                except OSError:
                    pass
            spec_path_obj = project_root / spec_dir
            if spec_path_obj.is_dir():
                try:
                    shutil.rmtree(spec_path_obj, ignore_errors=True)
                except OSError:
                    pass
        raise RuntimeError(
            f"POC scaffold failed while writing files: {exc}. "
            "Partial output has been cleaned up. Re-run scaffold to retry."
        ) from exc


def scaffold_lite(project_root: Path, project_name: str = "") -> None:
    """Minimal scaffold: spec governance files only, no CI templates."""
    _scaffold_minimal(
        project_root,
        project_name=project_name,
        protected_dirs=list(DEFAULT_PROTECTED_DIRS),
        spec_dir="spec",
        ci_platform=None,
        dry_run=False,
    )


def scaffold_project(
    project_root: Path,
    project_name: str,
    protected_dirs: list[str] | None = None,
    spec_dir: str = "spec",
    template_style: str = "standard",
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
    dry_run:
        If ``True``, report planned actions without writing anything.

    Returns
    -------
    dict
        ``{"created": [...], "skipped": [...], "merged": [...],
        "package_manager": str}``.
        ``package_manager`` is the detected manager name (e.g. ``"uv"``,
        ``"poetry"``) or ``"uv (generated)"`` when none was found and a
        ``pyproject.toml`` was generated.
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
        "mode": "full",
        "date_today": date.today().isoformat(),
    }

    file_map = _build_file_map(project_root, spec_dir, context)

    created: list[str] = []
    skipped: list[str] = []
    merged: list[str] = []
    created_paths: list[Path] = []
    detected_pm: str | None = None

    try:
        # -- Ensure empty directories exist ------------------------------------
        for rel in _EMPTY_DIRS_REL:
            dir_path = project_root / spec_dir / rel
            if dry_run:
                print(f"[dry-run] mkdir {dir_path}")
            else:
                dir_path.mkdir(parents=True, exist_ok=True)
                created_paths.append(dir_path)

        # -- Write files -------------------------------------------------------
        for target, template_name, executable in file_map:
            rel = str(target.relative_to(project_root))

            # Special handling: merge hooks.json when it already exists.
            if target.name == "hooks.json" and target.exists():
                new_hook = json.loads(_render_template(template_name, context))
                try:
                    merged_data = _merge_hooks_json(target, new_hook)
                except ValueError as exc:
                    print(
                        f"Warning: {exc}\n"
                        f"Skipping hook merge — {rel} will not be updated. "
                        "Fix or delete the file and re-run scaffold.",
                        file=sys.stderr,
                    )
                    skipped.append(rel)
                    continue
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
                created_paths.append(target)
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
                created_paths.append(pyproject_path)
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
                created_paths.append(agent_path)
            created.append("agent.md")

        # -- Install git pre-commit hook to auto-regenerate manifest ------------
        _install_git_precommit(project_root, spec_dir, dry_run, created, skipped)

        # -- CI template installation (EXT-007) ----------------------------------
        if ci_platform and ci_platform != "none":
            _install_ci_template(project_root, ci_platform, dry_run, created, skipped)

    except Exception as exc:
        if not dry_run:
            for p in reversed(created_paths):
                try:
                    if p.is_file():
                        p.unlink(missing_ok=True)
                except OSError:
                    pass
            spec_path_obj = project_root / spec_dir
            if spec_path_obj.is_dir():
                try:
                    shutil.rmtree(spec_path_obj, ignore_errors=True)
                except OSError:
                    pass
        raise RuntimeError(
            f"Scaffold failed while writing files: {exc}. "
            "Partial output has been cleaned up. Re-run scaffold to retry."
        ) from exc

    # -- Post-scaffold: generate manifest and README tables ----------------
    try:
        from specbuilder.src.generate_index import generate_manifest, regenerate_readme_table

        generate_manifest(project_root)
        regenerate_readme_table(project_root)
    except Exception as exc:
        print(
            f"Warning: manifest generation failed: {exc}\n"
            "Run 'python3 -m specbuilder generate-manifest' to retry "
            "('generate-index' is a likely deprecated alias — verify against __main__.py).",
            file=sys.stderr,
        )

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

"""Project upgrade from lite to full mode."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from specbuilder.src.config import DEFAULT_PROTECTED_DIRS

from .git_hooks import _make_executable
from .modes import _slugify_project, detect_mode
from .templates import _render_template


def upgrade_project(
    project_root: Path,
    project_name: str | None = None,
    spec_dir: str = "spec",
    dry_run: bool = False,
) -> dict:
    """Convert a lite project to full mode without overwriting existing specs.

    Adds: acceptance-criteria/, architecture/ (SCHEMA.md, decisions/, proposals/),
    changelog/, and upgrades agent.md.
    """
    project_root = project_root.resolve()
    mode = detect_mode(project_root, spec_dir)

    if mode == "fresh":
        return {
            "created": [],
            "skipped": [],
            "merged": [],
            "message": "No spec structure found. Run scaffold first (with or without --lite).",
        }
    if mode == "full":
        return {
            "created": [],
            "skipped": [],
            "merged": [],
            "message": "Project already has full spec structure. No upgrade needed.",
        }

    # Detect project name from agent.md if not provided
    if not project_name:
        agent_path = project_root / "agent.md"
        if agent_path.exists():
            first_line = agent_path.read_text(encoding="utf-8").split("\n")[0]
            if first_line.startswith("# "):
                project_name = first_line[2:].strip()
        if not project_name:
            project_name = project_root.name

    context = {
        "project_name": project_name,
        "project_slug": _slugify_project(project_name),
        "protected_dirs": list(DEFAULT_PROTECTED_DIRS),
        "spec_dir": spec_dir,
        "date_today": date.today().isoformat(),
    }

    created: list[str] = []
    skipped: list[str] = []
    merged: list[str] = []

    s = spec_dir

    # Create directories that full mode has but lite doesn't
    upgrade_dirs = [
        "architecture/decisions",
        "architecture/proposals",
        "acceptance-criteria",
        "changelog",
    ]
    for rel in upgrade_dirs:
        dir_path = project_root / s / rel
        if not dir_path.exists():
            if dry_run:
                print(f"[dry-run] mkdir {dir_path}")
            else:
                dir_path.mkdir(parents=True, exist_ok=True)

    # Create missing full-mode files
    upgrade_files = [
        (project_root / s / "README.md", "README.md.j2", False),
        (project_root / s / "architecture" / "SCHEMA.md", "SCHEMA.md.j2", False),
        (
            project_root / s / "architecture" / "decisions" / "001-spec-driven-development.md",
            "first-adr.md.j2",
            False,
        ),
        (project_root / s / "acceptance-criteria" / "README.md", "ac-readme.md.j2", False),
    ]

    for target, template_name, executable in upgrade_files:
        rel = str(target.relative_to(project_root))
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

    # Upgrade agent.md to include full workflow
    agent_path = project_root / "agent.md"
    agent_section = _render_template("agent-section.md.j2", context)
    if agent_path.exists():
        existing_content = agent_path.read_text(encoding="utf-8")
        if "## Spec-Driven Development Workflow" not in existing_content:
            if dry_run:
                print("[dry-run] upgrade agent.md to full mode")
            else:
                # Replace lite mode section with full
                if "## Spec-Driven Development (Lite Mode)" in existing_content:
                    parts = existing_content.split("## Spec-Driven Development (Lite Mode)")
                    new_content = parts[0] + agent_section
                else:
                    new_content = existing_content + "\n\n" + agent_section
                agent_path.write_text(new_content, encoding="utf-8")
            merged.append("agent.md")
        else:
            skipped.append("agent.md (already has full workflow)")

    # Post-upgrade: generate manifest and README tables
    try:
        from specbuilder.src.generate_index import generate_manifest, regenerate_readme_table

        if not dry_run:
            generate_manifest(project_root)
            regenerate_readme_table(project_root)
    except Exception:
        pass

    return {"created": created, "skipped": skipped, "merged": merged}

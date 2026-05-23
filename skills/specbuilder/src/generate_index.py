"""Index generation for spec-driven projects (MOD-02).

Validates all structured files against SCHEMA.md rules and generates
spec/manifest.json plus README tables.

Usage:
    python3 -m specbuilder.generate_index [--validate-only]

Exit codes:
    0 = success
    1 = validation error
"""

import json
import re
import sys
from datetime import date
from pathlib import Path

from specbuilder.src.config import (
    AC_TABLE_BEGIN,
    AC_TABLE_END,
    DEFAULT_AC_README_FILE,
    DEFAULT_DECISIONS_DIR,
    DEFAULT_MANIFEST_FILE,
    DEFAULT_MODULES_DIR,
    DEFAULT_PROPOSALS_DIR,
    DEFAULT_README_FILE,
    DEFAULT_SPEC_DIR,
    PROPOSALS_TABLE_BEGIN,
    PROPOSALS_TABLE_END,
    README_TABLE_BEGIN,
    README_TABLE_END,
    get_project_root,
)
from specbuilder.src.validation import (
    parse_frontmatter,
    validate_project,
)


def load_decisions(project_root: Path) -> list[dict]:
    """Load and sort all architecture decision files."""
    decisions_dir = project_root / DEFAULT_DECISIONS_DIR
    decisions: list[dict[str, str]] = []
    if not decisions_dir.exists():
        return decisions
    for f in sorted(decisions_dir.glob("*.md")):
        fm = parse_frontmatter(f)
        if fm:
            fm["_file"] = f.name
            decisions.append(fm)
    return decisions


def load_proposals(project_root: Path) -> list[dict]:
    """Load and sort all proposal files (recursive — includes subdirectories)."""
    proposals_dir = project_root / DEFAULT_PROPOSALS_DIR
    proposals: list[dict[str, str]] = []
    if not proposals_dir.exists():
        return proposals
    for f in sorted(proposals_dir.glob("**/*.md")):
        fm = parse_frontmatter(f)
        if fm:
            # Store relative path from proposals_dir (e.g., "implemented/003-foo.md")
            fm["_file"] = str(f.relative_to(proposals_dir))
            proposals.append(fm)
    return proposals


def load_changelog(project_root: Path) -> list[dict]:
    """Load and sort all changelog entry files."""
    changelog_dir = project_root / "spec" / "changelog"
    entries: list[dict[str, str]] = []
    if not changelog_dir.exists():
        return entries
    for f in sorted(changelog_dir.glob("*.md")):
        fm = parse_frontmatter(f)
        if fm:
            fm["_file"] = f.name
            entries.append(fm)
    return entries


def load_spec_modules(project_root: Path) -> list[dict]:
    """Load and sort all spec module files (excluding 00-* auto-generated)."""
    spec_dir = project_root / DEFAULT_MODULES_DIR
    ac_dir = project_root / DEFAULT_SPEC_DIR / "acceptance-criteria"
    modules: list[dict[str, str | list[str] | None]] = []
    if not spec_dir.exists():
        return modules
    for f in sorted(spec_dir.glob("[0-9][0-9]-*.md")):
        # Skip reserved 00-* prefix
        if f.name.startswith("00-"):
            continue
        fm = parse_frontmatter(f)
        if not fm:
            continue
        # Extract slug: "01-scaffold.md" -> "scaffold"
        match = re.match(r"^\d{2}-(.+)\.md$", f.name)
        slug = match.group(1) if match else f.stem
        # Check for corresponding AC file
        ac_file = ac_dir / f.name
        ac_path = f"{DEFAULT_SPEC_DIR}/acceptance-criteria/{f.name}" if ac_file.exists() else None
        modules.append(
            {
                "id": fm.get("id", ""),
                "slug": slug,
                "title": fm.get("title", ""),
                "status": fm.get("status", ""),
                "version": fm.get("version", ""),
                "depends_on": fm.get("depends_on", []),
                "origin": fm.get("origin", ""),
                "spec": f"{DEFAULT_MODULES_DIR}/{f.name}",
                "ac": ac_path,
            }
        )
    return modules


def generate_manifest(project_root: Path) -> dict:
    """Generate a thin JSON manifest of all spec artifacts.

    Writes spec/manifest.json and returns the manifest dict.
    """
    modules = load_spec_modules(project_root)
    decisions = load_decisions(project_root)
    proposals = load_proposals(project_root)
    changelog = load_changelog(project_root)

    manifest = {
        "_generated": date.today().isoformat(),
        "_generator": "specbuilder.generate_index",
        "modules": modules,
        "decisions": [
            {
                "id": d.get("id", ""),
                "title": d.get("title", ""),
                "status": d.get("status", ""),
                "date": d.get("date", ""),
                "file": f"{DEFAULT_SPEC_DIR}/architecture/decisions/{d['_file']}",
            }
            for d in decisions
        ],
        "proposals": [
            {
                "id": e.get("id", ""),
                "title": e.get("title", ""),
                "phase": e.get("phase", ""),
                "status": e.get("status", ""),
                "depends_on": e.get("depends_on", []),
                "impacts_modules": e.get("impacts_modules", []),
                "promoted_to": e.get("promoted_to", ""),
                "file": f"{DEFAULT_SPEC_DIR}/architecture/proposals/{e['_file']}",
            }
            for e in proposals
        ],
        "changelog": [
            {
                "id": c.get("id", ""),
                "title": c.get("title", ""),
                "version": c.get("version", ""),
                "date": str(c.get("date", "")),
                "type": c.get("type", ""),
                "file": f"{DEFAULT_SPEC_DIR}/changelog/{c['_file']}",
            }
            for c in changelog
        ],
    }

    manifest_path = project_root / DEFAULT_MANIFEST_FILE
    manifest_path.write_text(json.dumps(manifest, indent=2, default=str) + "\n", encoding="utf-8")
    return manifest


def regenerate_readme_table(project_root: Path) -> None:
    """Regenerate the Modules table in spec/README.md and AC status table.

    Uses sentinel comments as boundaries when present; falls back to
    finding the table header row for legacy files.
    """
    modules = load_spec_modules(project_root)

    # --- spec/README.md ---
    readme_path = project_root / DEFAULT_README_FILE
    if readme_path.exists():
        content = readme_path.read_text(encoding="utf-8")
        # Build module table rows
        table_rows = []
        for m in modules:
            # Extract number from spec path: "spec/01-scaffold.md" -> "01"
            num_match = re.match(r"^\d{2}", Path(m["spec"]).name)
            num = num_match.group(0) if num_match else "?"
            # Get first line of Executive Summary from spec file
            spec_file = project_root / m["spec"]
            desc = ""
            if spec_file.exists():
                spec_content = spec_file.read_text(encoding="utf-8")
                # Find content after "## Executive Summary"
                es_match = re.search(r"## Executive Summary\s*\n(.+)", spec_content)
                if es_match:
                    desc = es_match.group(1).strip()
            # Use slug as display name (title-cased, hyphens to spaces)
            display_name = m["slug"].replace("-", " ").title()
            filename = Path(m["spec"]).name
            status = m["status"]
            table_rows.append(
                f"| {num} | [{display_name}](./modules/{filename}) | {status} | {desc} |"
            )
        table_block = "\n".join(table_rows)

        if README_TABLE_BEGIN in content and README_TABLE_END in content:
            # Sentinel-based replacement
            begin_idx = content.index(README_TABLE_BEGIN) + len(README_TABLE_BEGIN)
            end_idx = content.index(README_TABLE_END)
            content = content[:begin_idx] + "\n" + table_block + "\n" + content[end_idx:]
        else:
            # Legacy fallback: find "| # | Module |" header and replace table up to next "## "
            header_pattern = re.compile(
                r"(\| *# *\| *Module *\|[^\n]*\n\|[-| ]*\n)(.*?)(?=\n## |\Z)",
                re.DOTALL,
            )
            match = header_pattern.search(content)
            if match:
                replacement = match.group(1) + table_block + "\n"
                content = content[: match.start()] + replacement + content[match.end() :]

        readme_path.write_text(content, encoding="utf-8")

    # --- spec/README.md proposals section ---
    if readme_path.exists():
        content = readme_path.read_text(encoding="utf-8")
        proposals = load_proposals(project_root)

        # Only render root-level proposals (not in subdirectories)
        active_proposals = [
            p
            for p in proposals
            if "/" not in p["_file"]  # no subdirectory separator = root level
        ]
        # Count archived proposals
        implemented_count = sum(1 for p in proposals if "implemented/" in p["_file"])
        parked_count = sum(1 for p in proposals if "parked/" in p["_file"])

        # Build proposals table
        proposal_rows = []
        for p in active_proposals:
            pid = p.get("id", "")
            title = p.get("title", "")
            phase = p.get("phase", "")
            status = p.get("status", "")
            proposal_rows.append(f"| {pid} | {title} | {phase} | {status} |")

        proposals_block = "\n".join(proposal_rows)

        # Add summary note about archived proposals
        if implemented_count or parked_count:
            parts = []
            if implemented_count:
                parts.append(f"{implemented_count} implemented")
            if parked_count:
                parts.append(f"{parked_count} parked")
            proposals_block += f"\n\n> {', '.join(parts)} — see `manifest.json` for full index."

        if PROPOSALS_TABLE_BEGIN in content and PROPOSALS_TABLE_END in content:
            begin_idx = content.index(PROPOSALS_TABLE_BEGIN) + len(PROPOSALS_TABLE_BEGIN)
            end_idx = content.index(PROPOSALS_TABLE_END)
            content = content[:begin_idx] + "\n" + proposals_block + "\n" + content[end_idx:]
            readme_path.write_text(content, encoding="utf-8")

    # --- spec/acceptance-criteria/README.md ---
    ac_readme_path = project_root / DEFAULT_AC_README_FILE
    if ac_readme_path.exists():
        content = ac_readme_path.read_text(encoding="utf-8")
        # Build AC status table rows
        ac_rows = []
        for m in modules:
            filename = Path(m["spec"]).name
            ac_status = ""
            last_reviewed = ""
            if m["ac"]:
                ac_file = project_root / m["ac"]
                if ac_file.exists():
                    ac_fm = parse_frontmatter(ac_file)
                    ac_status = ac_fm.get("status", "")
                    last_reviewed = ac_fm.get("last_updated", "")
            ac_rows.append(f"| [{filename}](../{filename}) | {ac_status} | {last_reviewed} |")
        ac_block = "\n".join(ac_rows)

        if AC_TABLE_BEGIN in content and AC_TABLE_END in content:
            begin_idx = content.index(AC_TABLE_BEGIN) + len(AC_TABLE_BEGIN)
            end_idx = content.index(AC_TABLE_END)
            content = content[:begin_idx] + "\n" + ac_block + "\n" + content[end_idx:]
        else:
            # Legacy fallback: find Status Tracker table header
            header_pattern = re.compile(
                r"(\| *Module *\| *AC Status *\|[^\n]*\n\|[-| ]*\n)(.*?)(?=\n## |\Z)",
                re.DOTALL,
            )
            match = header_pattern.search(content)
            if match:
                replacement = match.group(1) + ac_block + "\n"
                content = content[: match.start()] + replacement + content[match.end() :]

        ac_readme_path.write_text(content, encoding="utf-8")


def _sync_skill_version(project_root: Path) -> None:
    """Sync SKILL.md frontmatter version and body version from the latest changelog.

    Reads the latest changelog entry's version field and updates SKILL.md
    to match, keeping the single source of truth in the changelog.
    """
    # Get version from latest changelog
    changelog = load_changelog(project_root)
    if not changelog:
        return

    # Latest changelog entry (sorted by filename, last = highest number)
    latest_version = changelog[-1].get("version", "")
    if not latest_version:
        return

    skill_path = project_root / "specbuilder" / "SKILL.md"
    if not skill_path.exists():
        return

    content = skill_path.read_text(encoding="utf-8")

    # Update frontmatter version
    content = re.sub(
        r'^(version:\s*)"[^"]+"',
        f'\\1"{latest_version}"',
        content,
        count=1,
        flags=re.MULTILINE,
    )

    # Update body "Current version: **X.Y.Z**"
    content = re.sub(
        r"Current version:\s*\*\*[^*]+\*\*",
        f"Current version: **{latest_version}**",
        content,
    )

    skill_path.write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# Root README auto-generation (EXT-050)
# ---------------------------------------------------------------------------

_ROOT_README_COMMANDS_BEGIN = "<!-- BEGIN_AUTO_COMMANDS -->"
_ROOT_README_COMMANDS_END = "<!-- END_AUTO_COMMANDS -->"
_ROOT_README_STRUCTURE_BEGIN = "<!-- BEGIN_AUTO_STRUCTURE -->"
_ROOT_README_STRUCTURE_END = "<!-- END_AUTO_STRUCTURE -->"
_ROOT_README_DEPS_BEGIN = "<!-- BEGIN_AUTO_DEPS -->"
_ROOT_README_DEPS_END = "<!-- END_AUTO_DEPS -->"


def _generate_structure_section(project_root: Path) -> str:
    """Generate an annotated ASCII tree of the project structure.

    Covers specbuilder/ (top 2 levels with docstring descriptions),
    spec/, tests/, scripts/, and .github/.
    """
    lines: list[str] = []

    # specbuilder/ top-level
    sb_dir = project_root / "specbuilder"
    if sb_dir.is_dir():
        lines.append("specbuilder/              \u2190 THE SKILL (copy this into your project)")

        # Top-level files in specbuilder/
        top_files = sorted(f for f in sb_dir.iterdir() if f.is_file() and f.name != "__pycache__")
        for f in top_files:
            if f.suffix == ".md" and f.name == "SKILL.md":
                lines.append(
                    "\u251c\u2500\u2500 SKILL.md              \u2190 CoCo skill definition"
                )
            elif f.name == "__main__.py":
                lines.append(
                    "\u251c\u2500\u2500 __main__.py           \u2190 Unified CLI dispatch"
                )
            elif f.name == "README.md":
                lines.append(
                    "\u2514\u2500\u2500 README.md             \u2190 User-facing documentation"
                )

        # src/ directory
        src_dir = sb_dir / "src"
        if src_dir.is_dir():
            lines.append("\u251c\u2500\u2500 src/")
            src_files = sorted(
                f for f in src_dir.iterdir()
                if f.is_file() and f.suffix == ".py" and f.name != "__init__.py"
            )
            for sf in src_files:
                # Get first line of module docstring
                desc = ""
                try:
                    text = sf.read_text(encoding="utf-8")
                    if text.startswith('"""') or text.startswith("'''"):
                        quote = text[:3]
                        end = text.index(quote, 3)
                        docstring = text[3:end].strip()
                        first_line = docstring.split("\n")[0]
                        if len(first_line) > 45:
                            first_line = first_line[:42] + "..."
                        desc = f" \u2190 {first_line}"
                except Exception:
                    pass
                # Pad filename for alignment
                name = sf.name
                padding = max(1, 22 - len(name))
                lines.append(f"\u2502   \u251c\u2500\u2500 {name}{' ' * padding}{desc}")

            # Subdirectories in src/
            src_subdirs = sorted(
                d for d in src_dir.iterdir()
                if d.is_dir() and d.name != "__pycache__"
            )
            for sd in src_subdirs:
                lines.append(f"\u2502   \u2514\u2500\u2500 {sd.name}/")

        # skills/ directory
        skills_dir = sb_dir / "skills"
        if skills_dir.is_dir():
            lines.append(
                "\u251c\u2500\u2500 skills/               \u2190 Sub-skills (loaded on demand)"
            )
            subdirs = sorted(d for d in skills_dir.iterdir() if d.is_dir())
            for sd in subdirs:
                lines.append(f"\u2502   \u251c\u2500\u2500 {sd.name}/")

    # spec/ directory
    spec_dir = project_root / "spec"
    if spec_dir.is_dir():
        lines.append("")
        lines.append("spec/                     \u2190 This project's own specs")

    # tests/ directory with count
    tests_dir = project_root / "tests"
    if tests_dir.is_dir():
        test_count = 0
        for test_file in tests_dir.glob("test_*.py"):
            try:
                text = test_file.read_text(encoding="utf-8")
                # Count all lines that define a test function
                for line in text.splitlines():
                    stripped = line.lstrip()
                    if stripped.startswith("def test_"):
                        test_count += 1
            except Exception:
                pass
        # Round down to nearest 10
        rounded = (test_count // 10) * 10
        lines.append(f"tests/                    \u2190 Test suite ({rounded}+ tests)")

    # scripts/ directory
    scripts_dir = project_root / "scripts"
    if scripts_dir.is_dir():
        lines.append("scripts/                  \u2190 CI scripts")

    # .github/ directory
    github_dir = project_root / ".github" / "workflows"
    if github_dir.is_dir():
        lines.append(".github/workflows/        \u2190 GitHub Actions CI")

    return "```\n" + "\n".join(lines) + "\n```\n"


def _generate_deps_section(project_root: Path) -> str:
    """Generate the dependencies section from pyproject.toml.

    Reads [project].dependencies and formats as a markdown list.
    """
    import sys

    if sys.version_info >= (3, 11):
        import tomllib
    else:
        try:
            import tomli as tomllib  # type: ignore[no-redef]
        except ImportError:
            return ""

    pyproject_path = project_root / "pyproject.toml"
    if not pyproject_path.exists():
        return ""

    with open(pyproject_path, "rb") as f:
        data = tomllib.load(f)

    project_data = data.get("project", {})
    requires_python = project_data.get("requires-python", "")
    deps = project_data.get("dependencies", [])

    lines: list[str] = []

    # Python version requirement
    if requires_python:
        lines.append(f"- Python {requires_python}")

    # Format each dependency
    for dep in deps:
        # Parse PEP 508 dependency string
        # Handle markers like "; python_version < '3.11'"
        marker_note = ""
        dep_core = dep
        if ";" in dep:
            dep_core, marker = dep.split(";", 1)
            dep_core = dep_core.strip()
            marker = marker.strip()
            # Convert marker to human-readable note
            if "python_version" in marker:
                marker_note = f" (Python {marker.split('python_version')[1].strip()} only)"
                # Clean up quotes
                marker_note = marker_note.replace("'", "").replace('"', "")

        # Split name and version spec
        for op in [">=", "<=", "==", "!=", "~="]:
            if op in dep_core:
                name, version = dep_core.split(op, 1)
                lines.append(f"- {name.strip()} {op} {version.strip()}{marker_note}")
                break
        else:
            lines.append(f"- {dep_core}{marker_note}")

    return "\n".join(lines) + "\n"


def _splice_section(content: str, begin_marker: str, end_marker: str, new_body: str) -> str:
    """Replace content between begin/end sentinel markers.

    Returns the content unchanged if markers are not present.
    """
    if begin_marker not in content or end_marker not in content:
        return content
    begin_idx = content.index(begin_marker) + len(begin_marker)
    end_idx = content.index(end_marker)
    return content[:begin_idx] + "\n" + new_body + content[end_idx:]


def _regenerate_root_readme(project_root: Path) -> None:
    """Regenerate auto-generated sections in the root README.md.

    Regenerates:
    - Command table from __main__.py COMMANDS dict (EXT-050)
    - Project structure tree (EXT-061)
    - Dependencies list from pyproject.toml (EXT-061)

    Only runs if the root README contains at least one sentinel marker.
    """
    readme_path = project_root / "README.md"
    if not readme_path.exists():
        return

    content = readme_path.read_text(encoding="utf-8")

    # Check if any sentinel markers are present
    has_commands = _ROOT_README_COMMANDS_BEGIN in content
    has_structure = _ROOT_README_STRUCTURE_BEGIN in content
    has_deps = _ROOT_README_DEPS_BEGIN in content

    if not (has_commands or has_structure or has_deps):
        return

    # Regenerate COMMANDS section
    if has_commands:
        try:
            from specbuilder.__main__ import COMMANDS

            rows = ["| Command | Description |", "|---------|-------------|"]
            for cmd, module_path in COMMANDS.items():
                desc = cmd  # fallback
                try:
                    mod = __import__(module_path, fromlist=["__doc__"])
                    if mod.__doc__:
                        first_line = mod.__doc__.strip().split("\n")[0]
                        if len(first_line) > 80:
                            first_line = first_line[:77] + "..."
                        desc = first_line
                except Exception:
                    pass
                rows.append(f"| `{cmd}` | {desc} |")

            new_table = "\n".join(rows) + "\n"
            content = _splice_section(
                content, _ROOT_README_COMMANDS_BEGIN, _ROOT_README_COMMANDS_END, new_table
            )
        except Exception:
            pass  # Non-fatal

    # Regenerate STRUCTURE section (EXT-061)
    if has_structure:
        try:
            new_structure = _generate_structure_section(project_root)
            content = _splice_section(
                content, _ROOT_README_STRUCTURE_BEGIN, _ROOT_README_STRUCTURE_END, new_structure
            )
        except Exception:
            pass  # Non-fatal

    # Regenerate DEPS section (EXT-061)
    if has_deps:
        try:
            new_deps = _generate_deps_section(project_root)
            if new_deps:
                content = _splice_section(
                    content, _ROOT_README_DEPS_BEGIN, _ROOT_README_DEPS_END, new_deps
                )
        except Exception:
            pass  # Non-fatal

    readme_path.write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# AC file generation (EXT-059)
# ---------------------------------------------------------------------------

AC_HEADING_PATTERN = re.compile(r"^### (AC-\d+):\s*(.+)$", re.MULTILINE)
AC_FILE_HEADING_PATTERN = re.compile(r"^## (AC-\d+):", re.MULTILINE)


def generate_ac_files(project_root: Path) -> list[str]:
    """Sync AC files with module spec AC sections.

    For each module spec:
    - If AC file is missing: generate a complete one
    - If AC file has fewer sections: append stub sections
    - If AC file is already in sync: skip

    Returns list of files created or updated.
    """
    modules_dir = project_root / DEFAULT_MODULES_DIR
    ac_dir = project_root / DEFAULT_SPEC_DIR / "acceptance-criteria"

    if not modules_dir.exists():
        return []
    if not ac_dir.exists():
        ac_dir.mkdir(parents=True)

    updated: list[str] = []

    for module_file in sorted(modules_dir.glob("[0-9][0-9]-*.md")):
        if module_file.name.startswith("00-"):
            continue

        module_content = module_file.read_text(encoding="utf-8")
        fm = parse_frontmatter(module_file)
        if not fm:
            continue

        # Find all AC headings in the spec module
        spec_acs = AC_HEADING_PATTERN.findall(module_content)
        if not spec_acs:
            continue

        ac_file = ac_dir / module_file.name

        if not ac_file.exists():
            # Generate a complete AC file
            _generate_new_ac_file(ac_file, module_file, fm, spec_acs)
            updated.append(str(ac_file.relative_to(project_root)))
        else:
            # Check for missing sections and append if needed
            ac_content = ac_file.read_text(encoding="utf-8")
            existing_acs = AC_FILE_HEADING_PATTERN.findall(ac_content)

            if len(existing_acs) < len(spec_acs):
                _append_missing_ac_sections(
                    ac_file, ac_content, fm, spec_acs, existing_acs
                )
                updated.append(str(ac_file.relative_to(project_root)))

    return updated


def _generate_new_ac_file(
    ac_file: Path,
    module_file: Path,
    fm: dict,
    spec_acs: list[tuple[str, str]],
) -> None:
    """Generate a complete new AC file from spec module AC headings."""
    # Extract module number from filename: "01-scaffold.md" -> "01"
    num_match = re.match(r"^(\d{2})", module_file.name)
    module_num = num_match.group(1) if num_match else "00"

    title = fm.get("title", "Untitled")
    version = fm.get("version", "0.1.0")
    today = date.today().isoformat()

    lines = [
        "---",
        f"id: AC-{module_num}",
        f'title: "AC — {title}"',
        "status: draft",
        f'version: "{version}"',
        f"last_updated: {today}",
        f'spec_reference: "../modules/{module_file.name}"',
        "---",
    ]

    for ac_id, ac_title in spec_acs:
        # Extract the number from AC-N
        ac_num = ac_id.split("-")[1]
        lines.append("")
        lines.append(f"## {ac_id}: {ac_title}")
        lines.append("")
        lines.append("Criteria pending — synced from spec module.")
        lines.append("")
        lines.append("| # | Criterion | Pass | Notes |")
        lines.append("|---|-----------|------|-------|")
        lines.append(f"| {ac_num}.1 | (pending) | ☐ | |")
        lines.append("")
        lines.append("---")

    # Add Sign-Off section
    lines.append("")
    lines.append("## Sign-Off")
    lines.append("")
    lines.append("| Reviewer | Date | Result | Comments |")
    lines.append("|----------|------|--------|----------|")
    lines.append("| | | ☐ Pass / ☐ Fail | |")
    lines.append("")

    ac_file.write_text("\n".join(lines), encoding="utf-8")


def _append_missing_ac_sections(
    ac_file: Path,
    ac_content: str,
    fm: dict,
    spec_acs: list[tuple[str, str]],
    existing_acs: list[str],
) -> None:
    """Append stub sections for ACs present in spec but missing from AC file."""
    existing_set = set(existing_acs)
    version = fm.get("version", "")

    # Update frontmatter version if different
    if version:
        ac_content = re.sub(
            r'^(version:\s*)"[^"]+"',
            f'\\1"{version}"',
            ac_content,
            count=1,
            flags=re.MULTILINE,
        )

    # Find insertion point: before Sign-Off section if it exists, else append at end
    sign_off_match = re.search(r"\n## Sign-Off\b", ac_content)
    if sign_off_match:
        insert_pos = sign_off_match.start()
        before = ac_content[:insert_pos]
        after = ac_content[insert_pos:]
    else:
        before = ac_content.rstrip()
        after = ""

    new_sections = []
    for ac_id, ac_title in spec_acs:
        if ac_id not in existing_set:
            ac_num = ac_id.split("-")[1]
            new_sections.append("")
            new_sections.append("---")
            new_sections.append("")
            new_sections.append(f"## {ac_id}: {ac_title}")
            new_sections.append("")
            new_sections.append("Criteria pending — synced from spec module.")
            new_sections.append("")
            new_sections.append("| # | Criterion | Pass | Notes |")
            new_sections.append("|---|-----------|------|-------|")
            new_sections.append(f"| {ac_num}.1 | (pending) | ☐ | |")

    if new_sections:
        result = before + "\n".join(new_sections) + "\n" + after
        ac_file.write_text(result, encoding="utf-8")


def generate(project_root: Path | None = None, validate_only: bool = False) -> int:
    """Run index generation.

    Args:
        project_root: Root directory. Auto-detected if None.
        validate_only: If True, only validate without generating output.

    Returns:
        Exit code (0 = success, 1 = validation error).
    """
    if project_root is None:
        project_root = get_project_root()

    # Validate all files
    errors = validate_project(project_root)

    if errors:
        print("Validation errors:", file=sys.stderr)
        for err in errors:
            print(f"  ✗ {err}", file=sys.stderr)
        return 1

    if validate_only:
        print("All project files valid")
        return 0

    # Generate
    generate_manifest(project_root)
    print(f"Generated {DEFAULT_MANIFEST_FILE}")

    regenerate_readme_table(project_root)
    print(f"Regenerated {DEFAULT_README_FILE}")

    # Sync AC files with spec module AC sections (EXT-059)
    ac_updated = generate_ac_files(project_root)
    if ac_updated:
        print(f"Updated {len(ac_updated)} AC file(s)")

    # Sync SKILL.md version from changelog
    _sync_skill_version(project_root)

    # Regenerate root README auto-sections (EXT-050)
    _regenerate_root_readme(project_root)

    return 0


def main() -> None:
    """CLI entry point."""
    validate_only = "--validate-only" in sys.argv
    sys.exit(generate(validate_only=validate_only))


if __name__ == "__main__":
    main()

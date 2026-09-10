"""Intake parsing and spec module generation (MOD-05).

Handles the full pipeline from requirement intake to generated spec module:
  1. Parse a filled INTAKE.md or free-form text into structured fields.
  2. Determine next module number from existing spec files.
  3. Generate a spec module with valid frontmatter and all required sections.
  4. Generate a matching acceptance-criteria file.
  5. Update spec/README.md with the new module entry.
"""

from __future__ import annotations

import datetime
import json
import re
import sys
from datetime import date
from pathlib import Path

from specbuilder.src.config import (
    DEFAULT_AC_DIR,
    DEFAULT_MODULES_DIR,
    GATE_SENTINEL_MAX_AGE_SECONDS,
    TEMPLATES_DIR,
    get_active_profile,
    get_project_root,
    is_poc_mode,
    is_prototype_mode,
)
from specbuilder.src.spec_quality import check_spec_quality

# ---------------------------------------------------------------------------
# Section headers in INTAKE.md (order matters for sequential parsing)
# ---------------------------------------------------------------------------

_INTAKE_HEADERS: list[tuple[str, str]] = [
    ("## Module Title", "title"),
    ("## Description", "description"),
    ("## Input Data", "inputs"),
    ("## Existing Environment", "existing_environment"),
    ("## Desired Output", "outputs"),
    ("## Business Rules & Constraints", "business_rules"),
    ("## Reference Examples", "references"),
    ("## Priority Items", "priorities"),
    ("## Known Unknowns", "unknowns"),
    ("## Dependencies", "dependencies"),
    ("## Relevant Skills / Tools", "skills"),
]

_INTAKE_KEYS = [key for _, key in _INTAKE_HEADERS]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _strip_comments(text: str) -> str:
    """Remove HTML comments from markdown text."""
    return re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL).strip()


def _is_blank(value: str | None) -> bool:
    """Return True if value is empty or placeholder-only."""
    if not value:
        return True
    cleaned = value.strip().strip("-").strip()
    return cleaned == "" or cleaned == "- "


def _extract_section(content: str, start_header: str, next_headers: list[str]) -> str | None:
    """Extract text between *start_header* and the first of *next_headers*."""
    idx = content.find(start_header)
    if idx == -1:
        return None
    body_start = idx + len(start_header)
    end = len(content)
    for nh in next_headers:
        pos = content.find(nh, body_start)
        if pos != -1 and pos < end:
            end = pos
    raw = content[body_start:end]
    cleaned = _strip_comments(raw).strip(" \n-")
    return cleaned if cleaned else None


# ---------------------------------------------------------------------------
# Public API — intake parsing
# ---------------------------------------------------------------------------


def parse_intake(source: str) -> dict:
    """Parse a filled INTAKE.md or free-form text into structured fields.

    Returns dict with keys:
        title, description, inputs, outputs, business_rules,
        references, priorities, unknowns, skills
    Keys with no content are ``None``.
    """
    result: dict = {k: None for k in _INTAKE_KEYS}

    # Detect structured INTAKE.md by looking for its section headers.
    header_strings = [h for h, _ in _INTAKE_HEADERS]
    found_headers = [h for h in header_strings if h in source]

    if len(found_headers) >= 2:
        # Structured intake — extract each section.
        for i, (header, key) in enumerate(_INTAKE_HEADERS):
            remaining = [h for h, _ in _INTAKE_HEADERS[i + 1 :]]
            # Also stop at the trailing instructions block.
            remaining.append("---")
            value = _extract_section(source, header, remaining)
            result[key] = value if not _is_blank(value) else None
    else:
        # Free-form text — best-effort extraction.
        result = _parse_freeform(source)

    return result


def _parse_freeform(text: str) -> dict:
    """Extract structured fields from unstructured / conversational text."""
    result: dict = {k: None for k in _INTAKE_KEYS}

    lines = text.strip().splitlines()
    if not lines:
        return result

    # Title: first non-blank line (strip leading #).
    for line in lines:
        stripped = line.strip().lstrip("#").strip()
        if stripped:
            result["title"] = stripped[:120]
            break

    # Description: everything after the title line up to a keyword boundary.
    title_found = False
    desc_lines: list[str] = []
    for line in lines:
        if not title_found:
            if line.strip().lstrip("#").strip() == result.get("title"):
                title_found = True
            continue
        lower = line.lower().strip()
        if any(lower.startswith(kw) for kw in ("input", "output", "rule", "constraint", "accept")):
            break
        desc_lines.append(line)
    desc = "\n".join(desc_lines).strip()
    result["description"] = desc if desc else None

    # Simple keyword scanning for remaining fields.
    full = text.lower()

    input_match = re.search(
        r"(?:input(?:s)?|data source|requires?)[:\s]*(.+?)(?:\n\n|\Z)",
        full,
        re.DOTALL,
    )
    if input_match:
        result["inputs"] = input_match.group(1).strip()[:500]

    output_match = re.search(
        r"(?:output|produce|generate|result)[:\s]*(.+?)(?:\n\n|\Z)",
        full,
        re.DOTALL,
    )
    if output_match:
        result["outputs"] = output_match.group(1).strip()[:500]

    rules_match = re.search(
        r"(?:rule|constraint|must|requirement)[:\s]*(.+?)(?:\n\n|\Z)",
        full,
        re.DOTALL,
    )
    if rules_match:
        result["business_rules"] = rules_match.group(1).strip()[:500]

    ref_match = re.search(
        r"(?:reference|example|related)[:\s]*(.+?)(?:\n\n|\Z)", full, re.DOTALL
    )
    if ref_match:
        result["references"] = ref_match.group(1).strip()[:500]

    priority_match = re.search(
        r"(?:priorit(?:y|ies)|important|critical)[:\s]*(.+?)(?:\n\n|\Z)", full, re.DOTALL
    )
    if priority_match:
        result["priorities"] = priority_match.group(1).strip()[:500]

    unknown_match = re.search(
        r"(?:unknown|question|unclear|open item)[:\s]*(.+?)(?:\n\n|\Z)", full, re.DOTALL
    )
    if unknown_match:
        result["unknowns"] = unknown_match.group(1).strip()[:500]

    dep_match = re.search(
        r"(?:dependenc(?:y|ies)|depend(?:s)? on|requires?)[:\s]*(.+?)(?:\n\n|\Z)", full, re.DOTALL
    )
    if dep_match:
        result["dependencies"] = dep_match.group(1).strip()[:500]

    skills_match = re.search(
        r"(?:skill|tool|framework|librar(?:y|ies))[:\s]*(.+?)(?:\n\n|\Z)", full, re.DOTALL
    )
    if skills_match:
        result["skills"] = skills_match.group(1).strip()[:500]

    return result


# ---------------------------------------------------------------------------
# Module numbering
# ---------------------------------------------------------------------------


def get_next_module_number(spec_dir: Path) -> int:
    """Return the next sequential module number (max existing + 1).

    Scans ``spec_dir`` for files matching ``NN-*.md``.  Module 00 is
    always reserved and excluded.  Handles gaps by using max+1.
    """
    pattern = re.compile(r"^(\d{2,})-.*\.md$")
    numbers: list[int] = []
    if spec_dir.is_dir():
        for f in spec_dir.iterdir():
            m = pattern.match(f.name)
            if m:
                num = int(m.group(1))
                if num != 0:
                    numbers.append(num)
    return (max(numbers) + 1) if numbers else 1


# ---------------------------------------------------------------------------
# Slug generation
# ---------------------------------------------------------------------------


def slugify(title: str) -> str:
    """Convert *title* to a kebab-case slug (max 40 chars).

    Lowercases, replaces non-alphanumeric runs with hyphens, and trims.
    """
    slug = title.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    # Collapse multiple hyphens.
    slug = re.sub(r"-{2,}", "-", slug)
    return slug[:40].rstrip("-")


# ---------------------------------------------------------------------------
# Spec module generation
# ---------------------------------------------------------------------------


def generate_spec_module(
    intake: dict,
    recommendations: list[dict] | None = None,
    module_number: int | None = None,
    project_root: Path | None = None,
) -> str:
    """Generate a complete spec module as a markdown string.

    The output includes valid YAML frontmatter and all required sections
    per SCHEMA.md.  If *recommendations* (from skill discovery) are
    provided, an Extension Points section is appended.
    """
    root = project_root or get_project_root()
    if module_number is None:
        module_number = get_next_module_number(root / DEFAULT_MODULES_DIR)

    mod_id = f"MOD-{module_number:02d}"
    title = intake.get("title") or "Untitled Module"
    today = date.today().isoformat()

    # --- frontmatter --------------------------------------------------------
    lines: list[str] = [
        "---",
        f"id: {mod_id}",
        f'title: "{title}"',
        "status: draft",
        'version: "0.1.0"',
        f"last_updated: {today}",
        "---",
        "",
        f"# Module {module_number:02d}: {title}",
        "",
        "---",
        "",
    ]

    # --- Executive Summary --------------------------------------------------
    description = intake.get("description") or "No description provided."
    lines += [
        "## Executive Summary",
        "",
        description,
        "",
        "---",
        "",
    ]

    # --- Inputs -------------------------------------------------------------
    inputs_text = intake.get("inputs") or "No specific inputs identified."
    lines += [
        "## Inputs",
        "",
        inputs_text,
        "",
        "---",
        "",
    ]

    # --- Output -------------------------------------------------------------
    outputs_text = intake.get("outputs") or "No specific outputs identified."
    lines += [
        "## Output",
        "",
        outputs_text,
        "",
    ]

    # Add Delivery subsection if intake suggests SQL/infrastructure artifacts
    _sql_indicators = {
        "sql",
        "ddl",
        "create table",
        "create view",
        "migration",
        "schema",
        "stored procedure",
        "task",
        "stream",
        "pipe",
    }
    intake_lower = (
        (intake.get("description") or "").lower() + " " + (intake.get("outputs") or "").lower()
    )
    if any(term in intake_lower for term in _sql_indicators):
        lines += [
            "### Delivery",
            "",
            "| Artifact | Location | Execution |",
            "|----------|----------|-----------|",
            "| SQL scripts | `sql/` | Manual review, then execute via `snowsql` or CoCo |",
            "",
        ]

    lines += ["---", ""]

    # --- Dependencies (optional) --------------------------------------------
    deps_text = intake.get("dependencies")
    if deps_text and not _is_blank(deps_text):
        lines += [
            "## Dependencies",
            "",
            "| Package | Purpose | Required |",
            "|---------|---------|----------|",
        ]
        # Parse deps_text — each line could be "package - reason" or just "package"
        for dep_line in deps_text.strip().split("\n"):
            dep_line = dep_line.strip().lstrip("- ")
            if not dep_line:
                continue
            if " - " in dep_line:
                pkg, reason = dep_line.split(" - ", 1)
                lines.append(f"| {pkg.strip()} | {reason.strip()} | Yes |")
            else:
                lines.append(f"| {dep_line} | — | Yes |")
        lines += ["", "---", ""]

    # --- Acceptance Criteria ------------------------------------------------
    lines += [
        "## Acceptance Criteria",
        "",
    ]
    ac_items = _build_acceptance_criteria(intake)
    for category, criteria in ac_items:
        lines.append(f"### {category}")
        lines.append("")
        for criterion in criteria:
            lines.append(f"- [ ] {criterion}")
        lines.append("")

    lines += ["---", ""]

    # --- Edge Cases ---------------------------------------------------------
    lines += [
        "## Edge Cases",
        "",
        "| Scenario | Expected Behavior |",
        "|----------|-------------------|",
    ]
    edge_cases = _build_edge_cases(intake)
    for scenario, behavior in edge_cases:
        lines.append(f"| {scenario} | {behavior} |")
    lines += ["", "---", ""]

    # --- Extension Points (optional) ----------------------------------------
    if recommendations:
        lines += [
            "## Extension Points",
            "",
        ]
        for rec in recommendations:
            name = rec.get("skill_name", "Unknown skill")  # matches discover_skills.py:513
            desc = rec.get("useful_for", "")               # matches discover_skills.py:517
            lines.append(f"- **{name}**: {desc}")
        lines.append("")

    return "\n".join(lines)


def _build_acceptance_criteria(intake: dict) -> list[tuple[str, list[str]]]:
    """Derive acceptance-criteria groups from intake fields."""
    groups: list[tuple[str, list[str]]] = []

    # AC-1: Core functionality.
    core: list[str] = []
    if intake.get("description"):
        core.append("Module produces correct output for standard inputs")
    core.append("All required input fields are validated before processing")
    core.append("Output matches the specified format and structure")
    groups.append(("AC-1: Core Functionality", core))

    # AC-2: Input handling.
    input_criteria: list[str] = [
        "Missing required inputs produce a clear error message",
        "Invalid input formats are rejected with guidance",
    ]
    if intake.get("inputs"):
        input_criteria.append("All listed input sources are accessible and read correctly")
    groups.append(("AC-2: Input Handling", input_criteria))

    # AC-3: Business rules.
    rules_criteria: list[str] = []
    if intake.get("business_rules"):
        for rule in intake["business_rules"].strip().splitlines():
            rule = rule.strip().lstrip("- ").strip()
            if rule:
                rules_criteria.append(f"Business rule enforced: {rule}")
    if not rules_criteria:
        rules_criteria.append("No customer-identifiable data in output")
        rules_criteria.append("All generated content follows project conventions")
    groups.append(("AC-3: Business Rules & Constraints", rules_criteria))

    # AC-4: Output validation.
    output_criteria: list[str] = [
        "Output passes schema validation",
        "Output is reproducible given identical inputs",
    ]
    groups.append(("AC-4: Output Validation", output_criteria))

    return groups


def _build_edge_cases(intake: dict) -> list[tuple[str, str]]:
    """Generate at least 5 edge-case rows from intake context."""
    cases: list[tuple[str, str]] = [
        ("All optional inputs are omitted", "Module uses sensible defaults; output is still valid"),
        (
            "Input data is empty or zero-length",
            "Clear error message returned; no partial output written",
        ),
        (
            "Input contains unexpected special characters",
            "Characters are escaped or sanitized; no crashes",
        ),
        (
            "Module is run twice with identical inputs",
            "Idempotent result; no duplicate side-effects",
        ),
        (
            "Very large input (10x typical size)",
            "Processes within reasonable time; memory does not spike",
        ),
    ]

    # Add context-specific cases from business rules or priorities.
    if intake.get("business_rules"):
        cases.append(
            (
                "Business rule boundary condition",
                "Boundary values are handled correctly per stated rules",
            )
        )
    if intake.get("priorities"):
        cases.append(
            (
                "Nice-to-have feature is requested but not implemented yet",
                "Graceful degradation; user informed that feature is planned",
            )
        )

    return cases


# ---------------------------------------------------------------------------
# Acceptance-criteria file generation
# ---------------------------------------------------------------------------


def generate_ac_file(spec_content: str, module_number: int, title: str) -> str:
    """Generate a matching acceptance-criteria markdown file.

    Parses ``## AC-`` and ``### AC-`` sections from *spec_content* and
    builds tables with #, Criterion, Pass, Notes columns.  Includes a
    Sign-Off section at the end.
    """
    today = date.today().isoformat()
    slug = slugify(title)
    lines: list[str] = [
        "---",
        f"id: AC-{module_number:02d}",
        f'title: "AC — {title}"',
        "status: draft",
        'version: "0.1.0"',
        f"last_updated: {today}",
        f'spec_reference: "../modules/{module_number:02d}-{slug}.md"',
        "---",
        "",
    ]

    # Extract AC sections from spec_content.
    ac_sections = _extract_ac_sections(spec_content)

    if ac_sections:
        for ac_id, ac_title, criteria in ac_sections:
            lines.append(f"## {ac_id}: {ac_title}")
            lines.append("")
            lines.append(f"Criteria for {ac_title.lower()}.")
            lines.append("")
            lines.append("| # | Criterion | Pass | Notes |")
            lines.append("|---|-----------|------|-------|")
            for i, criterion in enumerate(criteria, 1):
                crit_num = f"{ac_id.split('-')[1]}.{i}" if "-" in ac_id else f"{i}"
                lines.append(f"| {crit_num} | {criterion} | ☐ | |")
            lines.append("")
            lines.append("---")
            lines.append("")
    else:
        # Fallback: single AC section.
        lines += [
            "## AC-1: General",
            "",
            "General acceptance criteria.",
            "",
            "| # | Criterion | Pass | Notes |",
            "|---|-----------|------|-------|",
            "| 1.1 | Module produces expected output | ☐ | |",
            "| 1.2 | Output passes validation | ☐ | |",
            "",
            "---",
            "",
        ]

    # Sign-Off section.
    lines += [
        "## Sign-Off",
        "",
        "| Reviewer | Date | Result | Comments |",
        "|----------|------|--------|----------|",
        "| | | ☐ Pass / ☐ Fail | |",
    ]

    return "\n".join(lines)


def _extract_ac_sections(spec_content: str) -> list[tuple[str, str, list[str]]]:
    """Parse AC sections from generated spec content.

    Returns list of (ac_id, title, [criterion_texts]).
    Handles both ``### AC-N: Title`` and ``## AC-N: Title`` formats.
    """
    results: list[tuple[str, str, list[str]]] = []

    # Find all AC section headers.
    ac_pattern = re.compile(r"^#{2,3}\s+(AC-\d+):\s*(.+)$", re.MULTILINE)
    matches = list(ac_pattern.finditer(spec_content))

    for i, m in enumerate(matches):
        ac_id = m.group(1)
        ac_title = m.group(2).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(spec_content)
        section_body = spec_content[start:end]

        # Extract criteria: lines starting with "- [ ]".
        criteria: list[str] = []
        for line in section_body.splitlines():
            stripped = line.strip()
            if stripped.startswith("- [ ]"):
                criteria.append(stripped[5:].strip())

        if criteria:
            results.append((ac_id, ac_title, criteria))

    return results


# ---------------------------------------------------------------------------
# README update
# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
# Domain templates (EXT-009)
# ---------------------------------------------------------------------------

_DOMAINS_DIR = TEMPLATES_DIR / "domains"

# Keywords that trigger template suggestions
_TEMPLATE_KEYWORDS: dict[str, list[str]] = {
    "data-pipeline": [
        "pipeline",
        "etl",
        "elt",
        "transform",
        "ingest",
        "source table",
        "target table",
        "dynamic table",
        "staging",
        "warehouse",
        "merge",
        "incremental",
        "batch",
        "stream",
        "data load",
        "refresh",
    ],
    "streamlit-app": [
        "streamlit",
        "dashboard",
        "app",
        "ui",
        "visualization",
        "chart",
        "page",
        "interactive",
        "frontend",
        "user interface",
        "display",
    ],
    "security-policy": [
        "masking",
        "row access",
        "rbac",
        "role",
        "policy",
        "grant",
        "governance",
        "compliance",
        "pii",
        "sensitive",
        "audit",
        "permission",
        "access control",
    ],
    "ml": [
        "ml",
        "machine-learning",
        "machine learning",
        "model",
        "feature store",
        "cortex function",
        "ml pipeline",
        "training",
        "inference",
        "embedding",
        "classification",
        "regression",
        "prediction",
    ],
}


def list_templates() -> list[str]:
    """Return available domain template names.

    Checks both bundled templates and project-local templates (spec/templates/).
    """
    templates = []
    if _DOMAINS_DIR.is_dir():
        for f in sorted(_DOMAINS_DIR.glob("*.md.j2")):
            templates.append(f.stem.replace(".md", ""))
    return templates


def suggest_template(intake: dict) -> str | None:
    """Suggest a domain template based on intake content keywords.

    Returns template name (e.g., "data-pipeline") or None if no strong match.
    """
    # Build a text blob from intake fields
    text_parts = [
        intake.get("title", ""),
        intake.get("description", ""),
        intake.get("inputs", ""),
        intake.get("outputs", ""),
    ]
    text = " ".join(text_parts).lower()

    scores: dict[str, int] = {}
    for template_name, keywords in _TEMPLATE_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in text)
        if score > 0:
            scores[template_name] = score

    if not scores:
        return None

    # Require at least 2 keyword matches for a suggestion
    best = max(scores, key=scores.get)  # type: ignore[arg-type]
    if scores[best] >= 2:
        return best
    return None


def generate_from_template(
    template_name: str,
    intake: dict,
    module_number: int,
    project_root: Path | None = None,
) -> str:
    """Generate a spec module from a domain template.

    Args:
        template_name: Name of the template (e.g., "data-pipeline").
        intake: Parsed intake dict (used as Jinja2 context).
        module_number: Assigned module number.
        project_root: Project root for custom template discovery.

    Returns:
        Rendered spec module as a string.

    Raises:
        FileNotFoundError: If the template doesn't exist.
    """
    # Check project-local templates first
    if project_root:
        local_template = project_root / "spec" / "templates" / f"{template_name}.md.j2"
        if local_template.exists():
            template_path = local_template
        else:
            template_path = _DOMAINS_DIR / f"{template_name}.md.j2"
    else:
        template_path = _DOMAINS_DIR / f"{template_name}.md.j2"

    if not template_path.exists():
        available = list_templates()
        raise FileNotFoundError(
            f"Template '{template_name}' not found. Available: {', '.join(available) or 'none'}"
        )

    # Build context from intake + computed values
    context = dict(intake)  # All intake fields available in template
    context["module_num"] = module_number
    context["module_num_padded"] = f"{module_number:02d}"
    context["mod_id"] = f"MOD-{module_number:02d}"
    context["date"] = date.today().isoformat()
    context["title"] = intake.get("title", "Untitled Module")
    context["description"] = intake.get("description", "")

    # Inject environment metadata if cached (EXT-041)
    if project_root:
        from specbuilder.src.environment import load_cached_results

        env_cache = load_cached_results(project_root)
        if env_cache and "objects" in env_cache:
            # If any declared objects match source tables, inject column metadata
            source_fields: list[dict] = []
            for obj_name, obj_data in env_cache["objects"].items():
                if (
                    obj_data.get("exists")
                    and "columns" in obj_data
                    and obj_data.get("type") in ("table", "view", "table/view")
                ):
                    source_fields.extend(obj_data["columns"])
            if source_fields:
                context["source_fields"] = source_fields

    # Render with Jinja2
    try:
        from jinja2 import Environment, FileSystemLoader

        env = Environment(
            loader=FileSystemLoader(str(template_path.parent)),
            keep_trailing_newline=True,
        )
        tmpl = env.get_template(template_path.name)
        rendered: str = tmpl.render(**context)
        return rendered
    except ImportError:
        # Fallback: simple variable substitution (no filters/blocks)
        raw = template_path.read_text(encoding="utf-8")
        # Strip Jinja2 comments
        raw = re.sub(r"\{#-?.*?-?#\}", "", raw)
        # Strip block tags (for/if/endif/endfor/else)
        raw = re.sub(r"\{%-?.*?-?%\}", "", raw)

        # Handle default filter: {{ var | default("value") }} → value if var not in context
        def _replace_with_default(m: re.Match[str]) -> str:
            var = m.group(1).strip()
            parts = var.split("|")
            var_name = parts[0].strip()
            if var_name in context:
                return str(context[var_name])
            # Look for default("...") in filter chain
            for part in parts[1:]:
                default_match = re.search(r'default\(\s*"([^"]*)"\s*\)', part)
                if default_match:
                    return default_match.group(1)
            return ""

        raw = re.sub(r"\{\{\s*(.+?)\s*\}\}", _replace_with_default, raw)
        return raw


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def _apply_prototype_constraints(spec_content: str) -> str:
    """Inject prototype-mode constraints into spec frontmatter.

    Sets validation_tier: compile in the YAML frontmatter block.
    """
    # Insert validation_tier after the last frontmatter field before closing ---
    if spec_content.startswith("---"):
        end = spec_content.find("\n---", 3)
        if end != -1:
            frontmatter = spec_content[3:end]
            if "validation_tier:" not in frontmatter:
                spec_content = (
                    spec_content[:end]
                    + "\nvalidation_tier: compile"
                    + spec_content[end:]
                )
    return spec_content


def write_module(
    project_root: Path,
    intake: dict,
    recommendations: list[dict] | None = None,
    template: str | None = None,
) -> dict:
    """Orchestrate full module generation: spec + AC + README update.

    Returns dict with keys:
        - ``spec_path``: Path to the generated spec module
        - ``ac_path``: Path to the generated AC file (None in lite mode)
        - ``module_number``: The assigned module number
        - ``title``: The module title
        - ``template``: Template used (None if generic)
    """
    root = project_root.resolve()

    gate_file = root / ".specbuilder" / "gate-open"
    if not gate_file.exists():
        raise RuntimeError(
            "Acceptance gate not open. Have the user explicitly confirm the spec before calling "
            "write_module(). To open the gate, run:\n"
            '  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > .specbuilder/gate-open'
        )
    _sentinel_content = gate_file.read_text(encoding="utf-8").strip()
    if not _sentinel_content:
        raise RuntimeError(
            "stale gate sentinel: zero-byte sentinel from pre-EXT-175 'touch' invocation; "
            "recreate with 'echo \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\" > .specbuilder/gate-open'"
        )
    try:
        _ts_str = _sentinel_content.replace("Z", "+00:00")
        _sentinel_ts = datetime.datetime.fromisoformat(_ts_str)
        if _sentinel_ts.tzinfo is None:
            _sentinel_ts = _sentinel_ts.replace(tzinfo=datetime.timezone.utc)
        _age = (datetime.datetime.now(datetime.timezone.utc) - _sentinel_ts).total_seconds()
        if _age > GATE_SENTINEL_MAX_AGE_SECONDS:
            raise RuntimeError(
                f"stale gate sentinel: created at {_sentinel_content}; recreate sentinel"
            )
    except ValueError:
        raise RuntimeError(
            f"stale gate sentinel: unreadable timestamp '{_sentinel_content}'; "
            "recreate with 'echo \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\" > .specbuilder/gate-open'"
        )

    modules_dir = root / DEFAULT_MODULES_DIR
    ac_dir = root / DEFAULT_AC_DIR

    # Ensure modules directory exists.
    modules_dir.mkdir(parents=True, exist_ok=True)

    # Detect if project lacks acceptance-criteria dir: skip AC file generation
    is_lite = not (root / "spec" / "acceptance-criteria").is_dir()

    if not is_lite:
        ac_dir.mkdir(parents=True, exist_ok=True)

    module_number = get_next_module_number(modules_dir)
    title = intake.get("title") or "Untitled Module"
    slug = slugify(title)
    description = intake.get("description") or title

    # Truncate description for the README table cell.
    desc_oneline = description.replace("\n", " ").strip()
    if len(desc_oneline) > 120:
        desc_oneline = desc_oneline[:117] + "..."

    # Generate spec module (from template or programmatic).
    try:
        if template:
            spec_content = generate_from_template(
                template, intake, module_number, project_root=root
            )
        else:
            spec_content = generate_spec_module(
                intake,
                recommendations=recommendations,
                module_number=module_number,
                project_root=root,
            )
        if is_poc_mode(root):
            spec_content = spec_content.replace("status: draft", "status: accepted", 1)
        if is_prototype_mode(root):
            # Prototype: compile-tier validation only; no self-correction directives
            spec_content = _apply_prototype_constraints(spec_content)
        # Quality gate: block below-threshold specs before writing
        _qr = check_spec_quality(spec_content, get_active_profile(root))
        if _qr["score"] < _qr["threshold"]:
            return {
                "error": "quality_below_threshold",
                "score": _qr["score"],
                "threshold": _qr["threshold"],
                "findings": _qr["findings"],
            }
        spec_path = modules_dir / f"{module_number:02d}-{slug}.md"
        if spec_path.exists():
            raise FileExistsError(
                f"Spec file already exists: {spec_path}. "
                f"Use a different module number or remove the existing file explicitly."
            )
        spec_path.write_text(spec_content, encoding="utf-8")
    except Exception:
        gate_file.unlink(missing_ok=True)
        raise

    # Generate AC file (skip in lite mode).
    ac_path = None
    if not is_lite:
        try:
            ac_content = generate_ac_file(spec_content, module_number, title)
            ac_path = ac_dir / f"{module_number:02d}-{slug}.md"
            if ac_path.exists():
                raise FileExistsError(
                    f"Spec file already exists: {ac_path}. "
                    f"Use a different module number or remove the existing file explicitly."
                )
            ac_path.write_text(ac_content, encoding="utf-8")
        except Exception:
            # Roll back: remove the spec that was already written so the project
            # is not left with a partially-initialised module.
            try:
                spec_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise

    # Regenerate manifest to keep it in sync (works without git pre-commit hook)
    try:
        from specbuilder.src.generate_index import (
            generate_ac_files,
            generate_manifest,
            regenerate_readme_table,
        )

        generate_manifest(root)
        regenerate_readme_table(root)
        if not is_lite:
            generate_ac_files(root)
    except Exception as exc:
        print(
            f"Warning: post-write manifest regeneration failed: {exc}\n"
            "The spec and AC files were written successfully.\n"
            "To sync the manifest and README, run:\n"
            "  python3 -m specbuilder generate-manifest && "
            "python3 -m specbuilder sync-ac-files",
            file=sys.stderr,
        )

    gate_file.unlink()  # sentinel consumed (one-time token); callers must recreate
    return {
        "spec_path": str(spec_path),
        "ac_path": str(ac_path) if ac_path else None,
        "module_number": module_number,
        "title": title,
        "template": template,
    }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Generate a spec module from an intake form or free-form text.",
    )
    parser.add_argument(
        "file",
        nargs="?",
        default=None,
        help="Path to intake file. Reads stdin if omitted.",
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=None,
        help="Project root directory (auto-detected if omitted).",
    )
    parser.add_argument(
        "--recommendations",
        type=str,
        default=None,
        help="Path to JSON file with skill recommendations.",
    )
    parser.add_argument(
        "--template",
        type=str,
        default=None,
        help="Domain template to use (e.g., data-pipeline, streamlit-app, security-policy).",
    )
    parser.add_argument(
        "--list-templates",
        action="store_true",
        help="List available domain templates and exit.",
    )
    parser.add_argument(
        "--suggest-template",
        action="store_true",
        help="Suggest a template based on intake content and exit.",
    )
    args = parser.parse_args()

    # List templates
    if args.list_templates:
        templates = list_templates()
        if templates:
            print("Available domain templates:")
            for t in templates:
                print(f"  - {t}")
        else:
            print("No domain templates found.")
        sys.exit(0)

    # Read intake source.
    if args.file:
        source = Path(args.file).read_text(encoding="utf-8")
    else:
        source = sys.stdin.read()
        if not source.strip():
            print("Error: stdin is empty — no intake content to parse.", file=sys.stderr)
            sys.exit(1)

    intake = parse_intake(source)

    # Suggest template
    if args.suggest_template:
        suggestion = suggest_template(intake)
        if suggestion:
            print(f"Suggested template: {suggestion}")
        else:
            print("No template match — use generic generation.")
        sys.exit(0)

    # Load recommendations if provided.
    recs = None
    if args.recommendations:
        recs = json.loads(Path(args.recommendations).read_text(encoding="utf-8"))

    root = args.project_root or get_project_root()
    result = write_module(root, intake, recommendations=recs, template=args.template)

    if result.get("error") == "quality_below_threshold":
        print(
            f"Error: spec quality score {result['score']:.0f}/100 is below the "
            f"{result['threshold']}/100 threshold for the active quality profile.\n"
            "Improve the spec content, or use a lower-threshold profile "
            "(e.g., export SPECBUILDER_QUALITY_PROFILE=poc).",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"Generated module {result['module_number']:02d}: {result['title']}")
    print(f"  Spec:   {result['spec_path']}")
    if result["ac_path"]:
        print(f"  AC:     {result['ac_path']}")
    else:
        print("  AC:     (skipped — no acceptance-criteria dir)")
    if result.get("template"):
        print(f"  Template: {result['template']}")

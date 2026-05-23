"""Intake environment capture and metadata enrichment (EXT-041).

Parses the "Existing Environment" section from INTAKE.md, generates
validation queries for declared Snowflake objects, and caches results
for template enrichment and sign-off drift detection.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from specbuilder.src.config import DEFAULT_SPECBUILDER_META_DIR

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ENVIRONMENT_CACHE_FILE = "environment.json"

EXISTENCE_QUERIES: dict[str, str] = {
    "database": "SHOW DATABASES LIKE '{name}'",
    "schema": "SHOW SCHEMAS LIKE '{schema}' IN DATABASE {database}",
    "table": "SHOW TABLES LIKE '{table}' IN SCHEMA {schema}",
    "view": "SHOW VIEWS LIKE '{view}' IN SCHEMA {schema}",
    "role": "SHOW ROLES LIKE '{name}'",
    "warehouse": "SHOW WAREHOUSES LIKE '{name}'",
    "stage": "SHOW STAGES LIKE '{name}' IN SCHEMA {schema}",
    "table/view": "SHOW TABLES LIKE '{table}' IN SCHEMA {schema}",
}

_PLACEHOLDER_PATTERNS = re.compile(
    r"(TODO|PLACEHOLDER|EXAMPLE|YOUR_|TBD|FIXME)", re.IGNORECASE
)


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def parse_environment_section(intake_path: Path) -> list[dict]:
    """Parse the 'Existing Environment' markdown table from INTAKE.md.

    Returns a list of dicts with keys: object, type, purpose.
    Only includes rows where the Object column is non-empty.
    """
    if not intake_path.exists():
        return []

    content = intake_path.read_text(encoding="utf-8")

    # Find the "## Existing Environment" section
    section_match = re.search(
        r"##\s+Existing Environment\b(.*?)(?=\n##\s|\Z)",
        content,
        re.DOTALL,
    )
    if not section_match:
        return []

    section_text = section_match.group(1)

    # Find the markdown table (look for | Object | Type | Purpose |)
    table_match = re.search(
        r"\|\s*Object\s*\|\s*Type\s*\|\s*Purpose\s*\|.*?\n"
        r"\|[-\s|]+\|\s*\n"  # separator row
        r"((?:\|.*\n)*)",  # data rows
        section_text,
        re.IGNORECASE,
    )
    if not table_match:
        return []

    rows_text = table_match.group(1)
    results: list[dict] = []

    for line in rows_text.strip().splitlines():
        # Split on | and strip whitespace
        cells = [c.strip() for c in line.split("|")]
        # Remove leading/trailing empty strings from split
        cells = [c for c in cells if c != "" or cells.index(c) not in (0, len(cells) - 1)]
        # After splitting "| A | B | C |", we get ['', ' A ', ' B ', ' C ', '']
        # Re-parse more carefully
        parts = line.split("|")
        if len(parts) < 4:
            continue
        # parts[0] is before first |, parts[1] is Object, parts[2] is Type, parts[3] is Purpose
        obj_name = parts[1].strip()
        obj_type = parts[2].strip().lower()
        obj_purpose = parts[3].strip()

        # Only include rows where object is non-empty
        if obj_name and not _is_separator_row(line):
            results.append({
                "object": obj_name,
                "type": obj_type,
                "purpose": obj_purpose,
            })

    return results


def _is_separator_row(line: str) -> bool:
    """Check if a markdown table row is a separator (e.g., |---|---|---|)."""
    stripped = line.replace("|", "").replace("-", "").replace(" ", "").replace(":", "")
    return stripped == ""


# ---------------------------------------------------------------------------
# Validation query generation
# ---------------------------------------------------------------------------


def get_validation_queries(declared: list[dict]) -> list[dict]:
    """Generate SHOW queries for each declared object.

    Returns a list of {object, type, query} dicts ready for execution.
    """
    queries: list[dict] = []

    for obj in declared:
        obj_name = obj["object"]
        obj_type = obj["type"]
        query = _build_query(obj_name, obj_type)

        if query:
            queries.append({
                "object": obj_name,
                "type": obj_type,
                "query": query,
            })

    return queries


def _build_query(obj_name: str, obj_type: str) -> str | None:
    """Build the appropriate SHOW query for an object reference."""
    template = EXISTENCE_QUERIES.get(obj_type)
    if not template:
        return None

    parts = obj_name.split(".")

    if obj_type == "database":
        return template.format(name=parts[-1])
    elif obj_type == "schema":
        if len(parts) >= 2:
            return template.format(schema=parts[-1], database=parts[-2])
        return template.format(schema=parts[0], database=parts[0])
    elif obj_type in ("table", "view", "table/view"):
        if len(parts) >= 3:
            return template.format(
                table=parts[-1], view=parts[-1],
                schema=f"{parts[-3]}.{parts[-2]}",
            )
        elif len(parts) >= 2:
            return template.format(
                table=parts[-1], view=parts[-1],
                schema=parts[-2],
            )
        return template.format(table=parts[0], view=parts[0], schema="PUBLIC")
    elif obj_type == "stage":
        if len(parts) >= 3:
            return template.format(name=parts[-1], schema=f"{parts[-3]}.{parts[-2]}")
        elif len(parts) >= 2:
            return template.format(name=parts[-1], schema=parts[-2])
        return template.format(name=parts[0], schema="PUBLIC")
    elif obj_type in ("role", "warehouse"):
        return template.format(name=parts[-1])

    return None


# ---------------------------------------------------------------------------
# Placeholder detection
# ---------------------------------------------------------------------------


def is_placeholder(reference: str) -> bool:
    """Return True if reference contains TODO, PLACEHOLDER, EXAMPLE, YOUR_, TBD, FIXME."""
    return bool(_PLACEHOLDER_PATTERNS.search(reference))


# ---------------------------------------------------------------------------
# Caching
# ---------------------------------------------------------------------------


def cache_results(project_root: Path, results: dict) -> Path:
    """Write validation results to .specbuilder/environment.json.

    Returns the path to the cache file.
    """
    cache_dir = project_root / DEFAULT_SPECBUILDER_META_DIR
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / ENVIRONMENT_CACHE_FILE

    payload = {
        "validated_at": datetime.now(timezone.utc).isoformat(),
        "objects": results,
    }

    cache_path.write_text(
        json.dumps(payload, indent=2, default=str),
        encoding="utf-8",
    )
    return cache_path


def load_cached_results(project_root: Path) -> dict | None:
    """Load cached environment results if they exist.

    Returns the parsed JSON dict or None if cache doesn't exist.
    """
    cache_path = project_root / DEFAULT_SPECBUILDER_META_DIR / ENVIRONMENT_CACHE_FILE
    if not cache_path.exists():
        return None

    try:
        data: dict[Any, Any] = json.loads(cache_path.read_text(encoding="utf-8"))
        return data
    except (json.JSONDecodeError, OSError):
        return None

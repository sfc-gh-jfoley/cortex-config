"""Artifact parsing — extracts artifact definitions from spec Output sections.

Parses backtick-quoted file paths, infers artifact types from extensions and
context, and maps artifacts to domain agents.
"""

import re
from pathlib import Path
from typing import Any

from specbuilder.src.agents.registry import match_domain
from specbuilder.src.config import ARTIFACT_EXTENSIONS

# Pre-compile the artifact path pattern from config extensions
_EXT_PATTERN = "|".join(ARTIFACT_EXTENSIONS)
_PATH_PATTERN = re.compile(rf"`([a-zA-Z0-9_./-]+\.(?:{_EXT_PATTERN}))`")

# ---------------------------------------------------------------------------
# Artifact parsing
# ---------------------------------------------------------------------------


def parse_output_section(spec_path: Path) -> list[dict]:
    """Parse the spec's Output section into structured artifact definitions.

    Looks for lines matching patterns like:
    - `path/to/file.sql` — description
    - **`path/to/file.py`** — description
    - Bullet items with backtick-quoted paths

    Returns a list of dicts: {"path": str, "type": str, "description": str, "depends_on": []}
    """
    content = spec_path.read_text(encoding="utf-8")

    # Find the Output section
    output_match = re.search(r"^## Output\s*\n(.*?)(?=^## |\Z)", content, re.MULTILINE | re.DOTALL)
    if not output_match:
        return []

    output_text = output_match.group(1)
    artifacts: list[dict[str, Any]] = []

    # Pattern: backtick-quoted file paths (with common extensions)
    path_pattern = _PATH_PATTERN

    # Pattern for depends_on annotations: (depends_on: path1, path2)
    depends_pattern = re.compile(r"\(?\s*depends_on:\s*([^)\n]+)\s*\)?")

    for match in path_pattern.finditer(output_text):
        path = match.group(1)
        # Extract the artifact's own line first for accurate type inference
        line_start = output_text.rfind("\n", 0, match.start()) + 1
        line_end = output_text.find("\n", match.end())
        line = output_text[line_start : line_end if line_end != -1 else len(output_text)]
        # Determine type from extension and per-line context (not full output_text)
        artifact_type = _infer_type(path, line)

        # Extract depends_on from the line
        depends_on = []
        dep_match = depends_pattern.search(line)
        if dep_match:
            deps_str = dep_match.group(1)
            depends_on = [d.strip() for d in deps_str.split(",") if d.strip()]

        # Clean description (remove the depends_on annotation)
        desc_line = depends_pattern.sub("", line)
        description = desc_line.replace(f"`{path}`", "").strip(" -\u2014\u2022*")

        artifacts.append(
            {
                "path": path,
                "type": artifact_type,
                "description": description,
                "depends_on": depends_on,
                "domain": match_domain(artifact_type),
            }
        )

    seen: set[str] = set()
    deduped = []
    for a in artifacts:
        apath: str = a["path"]
        if apath not in seen:
            seen.add(apath)
            deduped.append(a)
    return deduped


def _infer_type(path: str, context: str) -> str:
    """Infer artifact type from file extension and surrounding context."""
    ext = Path(path).suffix.lower()

    type_map = {
        ".sql": "DDL",  # Default; refined below
        ".py": ".py",
        ".yaml": "config",
        ".yml": "config",
        ".json": "config",
        ".toml": "config",
        ".md": "documentation",
        ".sh": "script",
    }

    base_type = type_map.get(ext, "unknown")

    # Refine SQL types from context
    if ext == ".sql":
        context_lower = context.lower()
        if "procedure" in context_lower or "sproc" in context_lower:
            return "stored-procedure"
        if "masking" in context_lower or "mask" in context_lower:
            return "masking-policy"
        if "grant" in context_lower or "role" in context_lower:
            return "grant"
        if "stream" in context_lower:
            return "stream"
        if "task" in context_lower:
            return "task"
        if "dynamic" in context_lower:
            return "dynamic-table"
        return "DDL"

    # Refine Python types
    if ext == ".py":
        if "streamlit" in context.lower():
            return "streamlit"
        if "udf" in context.lower():
            return "UDF"
        return ".py"

    return base_type

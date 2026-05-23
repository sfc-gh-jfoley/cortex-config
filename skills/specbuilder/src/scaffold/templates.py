"""Template rendering utilities for scaffold."""

from __future__ import annotations

import re
from typing import Any

from specbuilder.src.config import TEMPLATES_DIR

# ---------------------------------------------------------------------------
# Template rendering
# ---------------------------------------------------------------------------

# Try Jinja2 first; fall back to naive {{ var }} replacement.
_JINJA_ENV: Any
try:
    from jinja2 import Environment, FileSystemLoader

    _JINJA_ENV = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        keep_trailing_newline=True,
    )
    _HAS_JINJA = True
except ImportError:  # pragma: no cover
    _JINJA_ENV = None
    _HAS_JINJA = False


def _render_template(template_name: str, context: dict) -> str:
    """Load a template from ``specbuilder/templates/`` and render it.

    When Jinja2 is available the full engine is used (including comments,
    loops, etc.).  Without Jinja2 a simple ``{{ key }}`` replacement is
    performed — sufficient for templates that only use scalar variables.
    """
    if _HAS_JINJA:
        tmpl = _JINJA_ENV.get_template(template_name)
        rendered: str = tmpl.render(**context)
        return rendered

    # Fallback: read raw file and do literal replacements.
    raw = (TEMPLATES_DIR / template_name).read_text(encoding="utf-8")
    # Strip Jinja2 comments  {#- ... -#}
    raw = re.sub(r"\{#-?.*?-?#\}", "", raw)
    # Remove leading blank lines left by stripped comments
    raw = raw.lstrip("\n")
    for key, value in context.items():
        if isinstance(value, list):
            # Best-effort: join list items for simple templates.
            value = ", ".join(str(v) for v in value)
        raw = raw.replace("{{ " + key + " }}", str(value))
    return raw

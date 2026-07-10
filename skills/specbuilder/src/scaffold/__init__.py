"""Project scaffolding for spec-driven development (MOD-01).

Creates the full spec directory structure, hooks, and templates in a
customer's project.  Designed to be idempotent — running twice on the
same project will not corrupt existing files.

See: spec/01-scaffold.md
"""

from .cli import main
from .modes import detect_mode, scaffold_poc, scaffold_project
from .prototype import end_prototype, start_prototype
from .upgrade import upgrade_project

__all__ = [
    "detect_mode",
    "end_prototype",
    "main",
    "scaffold_poc",
    "scaffold_project",
    "start_prototype",
    "upgrade_project",
]

"""Dispatch planning — topological sort and dispatch manifest generation.

Groups artifacts into dependency-ordered batches and produces a machine-readable
dispatch plan for CoCo to execute.
"""

from datetime import date
from pathlib import Path

from specbuilder.src.agents.registry import get_agent_config

# ---------------------------------------------------------------------------
# Topological sort
# ---------------------------------------------------------------------------


def topological_sort(artifacts: list[dict]) -> list[list[dict]]:
    """Group artifacts into dependency levels using Kahn's algorithm.

    Returns a list of lists — each inner list can be executed in parallel.
    Uses declared depends_on edges to determine ordering. Domain priority
    is used as a tiebreaker for deterministic ordering within each level.

    Raises:
        ValueError: If a circular dependency is detected.
    """
    domain_priority = {
        "data-engineering": 0,
        "security": 1,
        "app-dev": 2,
        "ml": 2,
        "fallback": 3,
    }

    # Build graph structures
    by_path = {a["path"]: a for a in artifacts}
    in_degree = {a["path"]: 0 for a in artifacts}
    dependents: dict[str, list[str]] = {a["path"]: [] for a in artifacts}

    for a in artifacts:
        for dep in a.get("depends_on", []):
            if dep in by_path:
                in_degree[a["path"]] += 1
                dependents[dep].append(a["path"])

    levels = []
    remaining = set(in_degree.keys())

    while remaining:
        # Find all zero-in-degree nodes
        ready = [p for p in remaining if in_degree[p] == 0]
        if not ready:
            cycle_members = sorted(remaining)
            raise ValueError(f"Circular dependency detected: {' → '.join(cycle_members)}")

        # Sort by domain priority for deterministic output
        ready.sort(key=lambda p: domain_priority.get(by_path[p].get("domain", "fallback"), 3))

        levels.append([by_path[p] for p in ready])

        for p in ready:
            remaining.remove(p)
            for dep_path in dependents[p]:
                in_degree[dep_path] -= 1

    return levels


# ---------------------------------------------------------------------------
# Agent dispatch (preparation — actual spawning is done by CoCo at runtime)
# ---------------------------------------------------------------------------


def prepare_dispatch_plan(
    artifacts: list[dict],
    module_id: str,
    spec_path: Path,
) -> dict:
    """Prepare a structured dispatch manifest for CoCo to execute.

    Produces a machine-readable `workspace/dispatch.json` with batched
    execution order, domain→skills mapping, and validation config.

    Returns:
        The dispatch manifest dict (also written to workspace/dispatch.json).
    """
    levels = topological_sort(artifacts)

    execution_order = []
    for batch_idx, level_artifacts in enumerate(levels, start=1):
        batch_artifacts = []
        for art in level_artifacts:
            config = get_agent_config(art.get("domain", "fallback"))
            batch_artifacts.append(
                {
                    "name": Path(art["path"]).stem,
                    "path": art["path"],
                    "type": art["type"],
                    "domain": art["domain"],
                    "description": art.get("description", ""),
                    "template": config["prompt_template"],
                    "skills": config["skills"],
                    "depends_on": art.get("depends_on", []),
                }
            )
        execution_order.append(
            {
                "batch": batch_idx,
                "parallel": True,
                "artifacts": batch_artifacts,
            }
        )

    dispatch = {
        "module": module_id,
        "spec_path": str(spec_path),
        "generated": date.today().isoformat(),
        "execution_order": execution_order,
        "validation": {
            "checks": ["sql_compile", "cross_reference", "import_check"],
        },
    }

    return dispatch

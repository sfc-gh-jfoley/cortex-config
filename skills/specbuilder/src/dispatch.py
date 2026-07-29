"""Dispatch planning — topological sort and dispatch manifest generation.

Groups artifacts into dependency-ordered batches and produces a machine-readable
dispatch plan for CoCo to execute.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from specbuilder.src.agents.registry import AGENT_REGISTRY, get_agent_config
from specbuilder.src.config import MAX_CONCURRENT_AGENTS

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
    # Derived from AGENT_REGISTRY insertion order.
    # app-dev (index 2) takes priority over ml (index 3) — intentional by design.
    domain_priority = {domain: i for i, domain in enumerate(AGENT_REGISTRY)}

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

        # Sort by domain priority for deterministic output; unknown domains sort last.
        n_domains = len(AGENT_REGISTRY)
        ready.sort(
            key=lambda p: domain_priority.get(by_path[p].get("domain", "fallback"), n_domains)
        )

        levels.append([by_path[p] for p in ready])

        for p in ready:
            remaining.remove(p)
            for dep_path in dependents[p]:
                in_degree[dep_path] -= 1

    return levels


# ---------------------------------------------------------------------------
# Agent dispatch (preparation — actual spawning is done by CoCo at runtime)
# ---------------------------------------------------------------------------


def _read_impl_status(metadata_dir: Path) -> dict:
    """Read impl-status.json and return a dict keyed by artifact path."""
    status_file = metadata_dir / "impl-status.json"
    if not status_file.exists():
        return {}
    try:
        import json
        data = json.loads(status_file.read_text(encoding="utf-8"))
        return {entry["path"]: entry for entry in data.get("artifacts", [])}
    except Exception:
        return {}


def prepare_dispatch_plan(
    artifacts: list[dict],
    module_id: str,
    spec_path: Path,
    metadata_dir: Path,
    quality_profile: dict | None = None,
) -> dict:
    """Prepare a structured dispatch manifest for CoCo to execute.

    Builds a machine-readable manifest with batched execution order,
    domain→skills mapping, and validation config.

    Returns:
        The dispatch manifest dict. The caller is responsible for writing
        it to ``workspace/dispatch.json``.
    """
    status_map = _read_impl_status(metadata_dir)
    pending = [
        a for a in artifacts
        if status_map.get(a["path"], {}).get("status") != "implemented"
    ]
    levels = topological_sort(pending)

    execution_order = []
    batch_idx = 0
    for level_artifacts in levels:
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

        # Subdivide into sub-batches when a concurrency cap is active.
        # MAX_CONCURRENT_AGENTS == 0 means unlimited (single chunk per level).
        if MAX_CONCURRENT_AGENTS > 0:
            chunks = [
                batch_artifacts[i : i + MAX_CONCURRENT_AGENTS]
                for i in range(0, len(batch_artifacts), MAX_CONCURRENT_AGENTS)
            ]
        else:
            chunks = [batch_artifacts]

        for chunk in chunks:
            batch_idx += 1
            batch_entry = {
                "batch": batch_idx,
                "parallel": True,
                "artifacts": chunk,
            }
            if len(chunk) == 1:
                batch_entry["single_artifact"] = True
            execution_order.append(batch_entry)

    dispatch: dict[str, Any] = {
        "module": module_id,
        "spec_path": str(spec_path),
        "generated": date.today().isoformat(),
        "execution_order": execution_order,
    }

    if quality_profile is not None:
        dispatch["quality_profile"] = {
            "name": quality_profile.get("name", "full"),
            "validation_tier": quality_profile.get("validation_tier", "compile"),
            "self_correct": quality_profile.get("self_correct", False),
            "max_retries": quality_profile.get("max_retries", 0),
            "skip_checks": quality_profile.get("skip_checks", []),
            "threshold": quality_profile.get("threshold", 75),
        }

    return dispatch

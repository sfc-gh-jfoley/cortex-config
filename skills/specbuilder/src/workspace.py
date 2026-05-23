"""Implementation output and status tracking.

Manages the impl/ directory for file stubs and .specbuilder/ for metadata:
artifact implementation status tracking and validation prep.
"""

import json
from datetime import date
from pathlib import Path
from typing import Any

from specbuilder.src.config import DEFAULT_IMPL_DIR

# ---------------------------------------------------------------------------
# Stub generation
# ---------------------------------------------------------------------------


_STUB_HEADERS = {
    ".sql": (
        "-- {description}\n-- Module: {module}\n-- Generated: {date}\n"
        "-- Status: STUB \u2014 implementation pending\n\n"
        "-- TODO: Implement according to spec acceptance criteria\n"
    ),
    ".py": (
        '"""{description}\n\nModule: {module}\nGenerated: {date}\n'
        'Status: STUB \u2014 implementation pending\n"""\n\n'
        "# TODO: Implement according to spec acceptance criteria\n"
    ),
    ".yaml": (
        "# {description}\n# Module: {module}\n# Generated: {date}\n"
        "# Status: STUB \u2014 implementation pending\n\n"
        "# TODO: Implement according to spec acceptance criteria\n"
    ),
    ".json": (
        '{{\n  "_comment": "{description}",'
        '\n  "_module": "{module}",'
        '\n  "_generated": "{date}",'
        '\n  "_status": "stub"\n}}\n'
    ),
    ".md": (
        "# {description}\n\n> Module: {module}  \n"
        "> Generated: {date}  \n> Status: STUB\n\n"
        "TODO: Implement according to spec acceptance criteria\n"
    ),
}


def generate_stubs(
    artifacts: list[dict],
    impl_dir: Path,
    metadata_dir: Path,
    module_id: str,
) -> dict:
    """Create file skeletons for all artifacts.

    Args:
        artifacts: Parsed artifact definitions.
        impl_dir: Root directory for generated stub files.
        metadata_dir: Directory for metadata (impl-status.json).
        module_id: Module identifier (e.g., "MOD-07").

    Returns:
        Implementation status manifest dict.
    """
    manifest: dict = {
        "spec_module": module_id,
        "generated": date.today().isoformat(),
        "artifacts": [],
    }

    _impl_prefix = DEFAULT_IMPL_DIR.rstrip("/") + "/"

    for artifact in artifacts:
        # Strip a leading "impl/" prefix if present — artifact paths in specs
        # are project-root-relative (e.g. "impl/sql/foo.sql"), but impl_dir
        # is already rooted at <project_root>/impl.  Without this, paths like
        # "impl/sql/foo.sql" would resolve to impl/impl/sql/foo.sql (EXT-070).
        rel_path = artifact["path"]
        if rel_path.startswith(_impl_prefix):
            rel_path = rel_path[len(_impl_prefix):]
        file_path = impl_dir / rel_path
        file_path.parent.mkdir(parents=True, exist_ok=True)

        ext = Path(artifact["path"]).suffix.lower()
        template = _STUB_HEADERS.get(ext, "# {description}\n# TODO: implement\n")
        content = template.format(
            description=artifact.get("description", artifact["path"]),
            module=module_id,
            date=date.today().isoformat(),
        )

        file_path.write_text(content, encoding="utf-8")

        manifest["artifacts"].append(
            {
                "path": artifact["path"],
                "type": artifact["type"],
                "domain": artifact["domain"],
                "status": "stub",
                "produced_by": "specbuilder.implement",
            }
        )

    # Write implementation status manifest
    manifest_path = metadata_dir / "impl-status.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )

    return manifest


# ---------------------------------------------------------------------------
# Implementation status tracking (EXT-002)
# ---------------------------------------------------------------------------


def update_artifact_status(
    metadata_dir: Path,
    artifact_path: str,
    status: str,
    error: str | None = None,
) -> dict:
    """Update the status of an artifact in impl-status.json.

    Valid statuses: stub, in_progress, implemented, failed, skipped

    Args:
        metadata_dir: Path to metadata directory (.specbuilder/).
        artifact_path: The artifact's path (key in manifest).
        status: New status value.
        error: Optional error context (for failed status).

    Returns:
        Updated manifest dict.
    """
    manifest_path = metadata_dir / "impl-status.json"
    if not manifest_path.exists():
        return {"error": "No implementation status manifest found"}

    manifest: dict[Any, Any] = json.loads(manifest_path.read_text(encoding="utf-8"))

    for artifact in manifest.get("artifacts", []):
        if artifact["path"] == artifact_path:
            artifact["status"] = status
            if error:
                artifact["error"] = error
            elif "error" in artifact:
                del artifact["error"]
            break

    manifest_path.write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def _artifact_slug(path: str) -> str:
    """Convert artifact path to a filesystem-safe slug for status files.

    Example: 'sql/tables.sql' \u2192 'sql--tables'
    """
    from pathlib import Path as _Path

    stem = _Path(path).stem
    parent = str(_Path(path).parent)
    if parent == ".":
        return stem
    return f"{parent.replace('/', '--')}--{stem}"


def write_artifact_status(
    metadata_dir: Path,
    artifact_path: str,
    status: str,
    error: str | None = None,
) -> None:
    """Write artifact status to an isolated per-artifact file.

    Creates .specbuilder/.status/<slug>.json for race-free parallel writes.
    Use reconcile_status_files() after a batch barrier to merge status
    into impl-status.json.

    Args:
        metadata_dir: Path to metadata directory (.specbuilder/).
        artifact_path: The artifact's path (key in manifest).
        status: New status value (stub, in_progress, implemented, failed, skipped).
        error: Optional error context (for failed status).
    """
    from datetime import datetime

    status_dir = metadata_dir / ".status"
    status_dir.mkdir(parents=True, exist_ok=True)

    slug = _artifact_slug(artifact_path)
    entry = {
        "path": artifact_path,
        "status": status,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "error": error,
    }

    status_file = status_dir / f"{slug}.json"
    status_file.write_text(
        json.dumps(entry, indent=2) + "\n", encoding="utf-8"
    )


def reconcile_status_files(metadata_dir: Path) -> dict:
    """Merge all .status/*.json files into impl-status.json.

    Reads each per-artifact status file and updates the corresponding
    entry in impl-status.json. This is the authoritative reconciliation
    point after parallel agent execution.

    Returns:
        Updated manifest dict. Returns error dict if no manifest found.
    """
    manifest_path = metadata_dir / "impl-status.json"
    if not manifest_path.exists():
        return {"error": "No implementation status manifest found"}

    status_dir = metadata_dir / ".status"
    if not status_dir.exists():
        result: dict[Any, Any] = json.loads(manifest_path.read_text(encoding="utf-8"))
        return result

    manifest: dict[Any, Any] = json.loads(manifest_path.read_text(encoding="utf-8"))

    for status_file in status_dir.glob("*.json"):
        try:
            entry = json.loads(status_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue

        for artifact in manifest.get("artifacts", []):
            if artifact["path"] == entry.get("path"):
                artifact["status"] = entry["status"]
                if entry.get("error"):
                    artifact["error"] = entry["error"]
                elif "error" in artifact:
                    del artifact["error"]
                break

    manifest_path.write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def check_dispatch_status(metadata_dir: Path) -> dict:
    """Check the current status of all dispatched artifacts.

    Returns a summary with counts and blocked batches.
    """
    manifest_path = metadata_dir / "impl-status.json"
    dispatch_path = metadata_dir / "dispatch.json"

    if not manifest_path.exists():
        return {"error": "No implementation status manifest found"}

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    artifacts = manifest.get("artifacts", [])

    summary: dict = {
        "total": len(artifacts),
        "stub": sum(1 for a in artifacts if a.get("status") == "stub"),
        "in_progress": sum(
            1 for a in artifacts if a.get("status") == "in_progress"
        ),
        "implemented": sum(
            1 for a in artifacts if a.get("status") == "implemented"
        ),
        "failed": sum(
            1 for a in artifacts if a.get("status") == "failed"
        ),
        "skipped": sum(
            1 for a in artifacts if a.get("status") == "skipped"
        ),
    }

    # Identify blocked batches from dispatch.json
    blocked_batches = []
    if dispatch_path.exists():
        dispatch = json.loads(dispatch_path.read_text(encoding="utf-8"))
        failed_names = {
            a["path"] for a in artifacts if a.get("status") == "failed"
        }
        for batch in dispatch.get("execution_order", []):
            for art in batch.get("artifacts", []):
                deps = art.get("depends_on", [])
                if any(dep in failed_names for dep in deps):
                    blocked_batches.append(batch["batch"])
                    break

    summary["blocked_batches"] = sorted(set(blocked_batches))

    # Failed artifact details
    summary["failures"] = [
        {"path": a["path"], "error": a.get("error", "unknown")}
        for a in artifacts
        if a.get("status") == "failed"
    ]

    return summary


def skip_dependents(
    metadata_dir: Path, failed_artifact_path: str
) -> list[str]:
    """Mark artifacts that depend on a failed artifact as 'skipped'.

    Returns list of skipped artifact paths.
    """
    dispatch_path = metadata_dir / "dispatch.json"
    if not dispatch_path.exists():
        return []

    dispatch = json.loads(dispatch_path.read_text(encoding="utf-8"))
    skipped = []

    for batch in dispatch.get("execution_order", []):
        for art in batch.get("artifacts", []):
            if failed_artifact_path in art.get("depends_on", []):
                update_artifact_status(
                    metadata_dir,
                    art["path"],
                    "skipped",
                    error=f"Dependency failed: {failed_artifact_path}",
                )
                skipped.append(art["path"])

    return skipped


# ---------------------------------------------------------------------------
# Validation preparation
# ---------------------------------------------------------------------------


def prepare_validation(impl_dir: Path, metadata_dir: Path) -> dict:
    """Prepare validation context for the validation agent.

    Reads the implementation status manifest and collects artifact paths
    for validation.

    Args:
        impl_dir: Directory containing implemented artifact files.
        metadata_dir: Directory containing impl-status.json.

    Returns:
        Dict with manifest data and file listing for the validator.
    """
    manifest_path = metadata_dir / "impl-status.json"
    if not manifest_path.exists():
        return {"error": "No implementation status manifest found"}

    manifest: dict[Any, Any] = json.loads(manifest_path.read_text(encoding="utf-8"))

    # Collect actual file contents status
    for artifact in manifest.get("artifacts", []):
        file_path = impl_dir / artifact["path"]
        artifact["exists"] = file_path.exists()
        if file_path.exists():
            content = file_path.read_text(encoding="utf-8")
            artifact["is_stub"] = (
                "STUB" in content
                or "TODO: implement" in content.lower()
            )

    return manifest

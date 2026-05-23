"""Execution checkpoint protocol for multi-proposal batch implementations.

Provides local resumption state for multi-proposal batches. The execution log
is stored in .specbuilder/execution-log.md (gitignored) and serves as a
single-session recovery artifact. Cross-session handoff relies on committed
proposal frontmatter statuses (source of truth) and cortex memory.

Usage:
    python3 -m specbuilder checkpoint --init EXT-055,EXT-056,EXT-057
    python3 -m specbuilder checkpoint --status
    python3 -m specbuilder checkpoint --wave 1 [--results "908 passed, ruff clean"]
    python3 -m specbuilder checkpoint --complete
"""

import argparse
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

from specbuilder.src.config import (
    DEFAULT_PROPOSALS_DIR,
    DEFAULT_SPECBUILDER_META_DIR,
    get_project_root,
)
from specbuilder.src.validation import parse_frontmatter

# ---------------------------------------------------------------------------
# Execution log file
# ---------------------------------------------------------------------------

EXECUTION_LOG_FILE = "execution-log.md"


def _log_path(project_root: Path) -> Path:
    return project_root / DEFAULT_SPECBUILDER_META_DIR / EXECUTION_LOG_FILE


# ---------------------------------------------------------------------------
# Dependency graph
# ---------------------------------------------------------------------------


def build_dependency_graph(
    proposal_ids: list[str], project_root: Path
) -> list[list[str]]:
    """Topologically sort proposals into dependency-ordered waves.

    Proposals with no intra-batch dependencies land in wave 1.
    Proposals depending on wave-1 proposals land in wave 2, etc.

    Returns a list of waves, where each wave is a list of proposal IDs.
    Raises ValueError on circular dependencies.
    """
    # Load depends_on for each proposal
    proposals_dir = project_root / DEFAULT_PROPOSALS_DIR
    deps: dict[str, list[str]] = {}

    for pid in proposal_ids:
        # Find the proposal file
        fm = _find_proposal_frontmatter(pid, proposals_dir)
        raw_deps = fm.get("depends_on", []) if fm else []
        # Only keep intra-batch dependencies
        deps[pid] = [d for d in raw_deps if d in proposal_ids]

    # Kahn's algorithm for topological sort into waves
    in_degree = {pid: len(deps[pid]) for pid in proposal_ids}
    resolved: set[str] = set()
    waves: list[list[str]] = []

    remaining = set(proposal_ids)
    iteration_limit = len(proposal_ids)
    iterations = 0

    while remaining:
        # Find all proposals with no unresolved dependencies
        wave = [pid for pid in sorted(remaining) if in_degree[pid] == 0]
        if not wave:
            circular = sorted(remaining)
            raise ValueError(
                f"Circular dependency detected among: {', '.join(circular)}"
            )

        waves.append(wave)
        resolved.update(wave)
        remaining -= set(wave)

        # Decrement in-degree for dependents
        for pid in remaining:
            in_degree[pid] = len([d for d in deps[pid] if d not in resolved])

        iterations += 1
        if iterations > iteration_limit:
            raise ValueError("Dependency resolution exceeded iteration limit")

    return waves


def _find_proposal_frontmatter(
    proposal_id: str, proposals_dir: Path
) -> dict:
    """Find and parse frontmatter for a proposal by ID."""
    # Extract numeric part: EXT-055 -> 055
    match = re.match(r"EXT-(\d+)", proposal_id)
    if not match:
        return {}

    num = match.group(1)

    # Search in proposals dir (root and subdirectories)
    for md_file in proposals_dir.glob(f"**/{num}-*.md"):
        fm = parse_frontmatter(md_file)
        if fm and fm.get("id") == proposal_id:
            return fm

    return {}


def _find_proposal_file(proposal_id: str, proposals_dir: Path) -> Path | None:
    """Find the file path for a proposal by ID."""
    match = re.match(r"EXT-(\d+)", proposal_id)
    if not match:
        return None

    num = match.group(1)

    for md_file in proposals_dir.glob(f"**/{num}-*.md"):
        fm = parse_frontmatter(md_file)
        if fm and fm.get("id") == proposal_id:
            return md_file

    return None


# ---------------------------------------------------------------------------
# Init
# ---------------------------------------------------------------------------


def init_execution_log(proposal_ids: list[str], project_root: Path) -> Path:
    """Create a new execution log for a batch of proposals.

    Returns the path to the created log file.
    """
    waves = build_dependency_graph(proposal_ids, project_root)

    # Build graph notation: "EXT-055,EXT-056 → EXT-058 → EXT-060"
    graph_str = " → ".join(",".join(w) for w in waves)

    # Build wave plan
    wave_plan_lines = []
    for i, wave in enumerate(waves, 1):
        ids_str = ", ".join(wave)
        wave_plan_lines.append(f"- Wave {i}: {ids_str}")

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M")

    content = f"""# Execution Log

## Batch: {proposal_ids[0]} through {proposal_ids[-1]}
Started: {now}
Dependency graph: {graph_str}
Total waves: {len(waves)}

### Wave Plan
{chr(10).join(wave_plan_lines)}
"""

    log_file = _log_path(project_root)
    log_file.parent.mkdir(parents=True, exist_ok=True)
    log_file.write_text(content, encoding="utf-8")

    return log_file


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------


def get_status(project_root: Path) -> dict:
    """Derive current batch state from execution log and proposal statuses.

    Returns a dict with:
        - batch: list of proposal IDs in the batch
        - waves: list of waves (each a list of IDs)
        - completed_waves: number of waves marked complete in the log
        - proposal_statuses: dict mapping ID -> current frontmatter status
        - next_wave: list of IDs in the next incomplete wave (or None)
    """
    log_file = _log_path(project_root)
    proposals_dir = project_root / DEFAULT_PROPOSALS_DIR

    result: dict = {
        "batch": [],
        "waves": [],
        "completed_waves": 0,
        "proposal_statuses": {},
        "next_wave": None,
    }

    if not log_file.exists():
        return result

    content = log_file.read_text(encoding="utf-8")

    # Parse batch proposals from dependency graph line
    graph_match = re.search(r"^Dependency graph:\s*(.+)$", content, re.MULTILINE)
    if graph_match:
        graph_str = graph_match.group(1)
        waves = []
        for wave_part in graph_str.split("→"):
            ids = [s.strip() for s in wave_part.strip().split(",") if s.strip()]
            waves.append(ids)
        result["waves"] = waves
        result["batch"] = [pid for wave in waves for pid in wave]

    # Count completed waves from section headers
    completed = re.findall(r"### Wave \d+ \(completed", content)
    result["completed_waves"] = len(completed)

    # Get current proposal statuses from frontmatter (source of truth)
    for pid in result["batch"]:
        fm = _find_proposal_frontmatter(pid, proposals_dir)
        result["proposal_statuses"][pid] = fm.get("status", "unknown")

    # Determine next wave
    completed_count = result["completed_waves"]
    if completed_count < len(result["waves"]):
        result["next_wave"] = result["waves"][completed_count]

    return result


def print_status(project_root: Path) -> None:
    """Print human-readable status summary."""
    status = get_status(project_root)

    if not status["batch"]:
        print("No active execution log found.")
        print("Start a batch with: specbuilder checkpoint --init EXT-001,EXT-002,...")
        return

    batch_range = f"{status['batch'][0]}–{status['batch'][-1]}"
    total_waves = len(status["waves"])
    completed = status["completed_waves"]

    print(f"Batch: {batch_range} ({len(status['batch'])} proposals)")
    print(f"Progress: {completed}/{total_waves} waves complete")
    print()

    for i, wave in enumerate(status["waves"], 1):
        if i <= completed:
            marker = "✓"
        elif i == completed + 1:
            marker = "→"
        else:
            marker = "○"

        statuses = [
            f"{pid} [{status['proposal_statuses'].get(pid, '?')}]"
            for pid in wave
        ]
        print(f"  {marker} Wave {i}: {', '.join(statuses)}")

    if status["next_wave"]:
        print(f"\nNext: Wave {completed + 1} ready — {', '.join(status['next_wave'])}")
    else:
        print("\nAll waves complete. Run --complete to finalize.")


# ---------------------------------------------------------------------------
# Record wave
# ---------------------------------------------------------------------------


def record_wave(
    wave_num: int, project_root: Path, results: str | None = None
) -> bool:
    """Record completion of a wave in the execution log.

    Returns True on success, False if preconditions fail.
    """
    log_file = _log_path(project_root)
    proposals_dir = project_root / DEFAULT_PROPOSALS_DIR

    if not log_file.exists():
        print("Error: No execution log found. Run --init first.", file=sys.stderr)
        return False

    status = get_status(project_root)

    if wave_num < 1 or wave_num > len(status["waves"]):
        print(
            f"Error: Wave {wave_num} out of range (1–{len(status['waves'])})",
            file=sys.stderr,
        )
        return False

    # Check wave N-1 proposals are implemented (skip for wave 1)
    if wave_num > 1:
        prev_wave = status["waves"][wave_num - 2]
        for pid in prev_wave:
            fm = _find_proposal_frontmatter(pid, proposals_dir)
            if fm.get("status") != "implemented":
                print(
                    f"Error: Wave {wave_num - 1} not complete — "
                    f"{pid} status is '{fm.get('status', 'unknown')}', "
                    f"expected 'implemented'.",
                    file=sys.stderr,
                )
                return False

    # Check not already recorded
    if wave_num <= status["completed_waves"]:
        print(f"Wave {wave_num} already recorded.", file=sys.stderr)
        return False

    # Append wave completion to log
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M")
    wave_proposals = status["waves"][wave_num - 1]

    lines = [f"\n### Wave {wave_num} (completed {now})"]
    for pid in wave_proposals:
        fm = _find_proposal_frontmatter(pid, proposals_dir)
        title = fm.get("title", pid)
        lines.append(f"- [x] {pid}: {title}")

    if results:
        lines.append(f"Integration check: {results}")

    content = log_file.read_text(encoding="utf-8")
    content += "\n".join(lines) + "\n"
    log_file.write_text(content, encoding="utf-8")

    print(f"Wave {wave_num} recorded ({len(wave_proposals)} proposals).")
    if wave_num < len(status["waves"]):
        next_wave = status["waves"][wave_num]
        print(f"Next: Wave {wave_num + 1} — {', '.join(next_wave)}")
    else:
        print("All waves complete. Run --complete to finalize.")

    return True


# ---------------------------------------------------------------------------
# Complete
# ---------------------------------------------------------------------------


def complete_batch(project_root: Path) -> bool:
    """Finalize batch: update proposal statuses and move to implemented/.

    Returns True on success.
    """
    status = get_status(project_root)

    if not status["batch"]:
        print("Error: No execution log found.", file=sys.stderr)
        return False

    proposals_dir = project_root / DEFAULT_PROPOSALS_DIR
    implemented_dir = proposals_dir / "implemented"
    implemented_dir.mkdir(parents=True, exist_ok=True)

    updated = 0
    moved = 0

    for pid in status["batch"]:
        filepath = _find_proposal_file(pid, proposals_dir)
        if not filepath:
            print(f"  Warning: Could not find file for {pid}", file=sys.stderr)
            continue

        # Update frontmatter status to implemented
        content = filepath.read_text(encoding="utf-8")
        current_status = parse_frontmatter(filepath).get("status", "")

        if current_status != "implemented":
            updated_content = re.sub(
                r"^(status:\s*).*$",
                r"\1implemented",
                content,
                count=1,
                flags=re.MULTILINE,
            )
            filepath.write_text(updated_content, encoding="utf-8")
            updated += 1

        # Move to implemented/ (if not already there)
        if "implemented" not in str(filepath.parent):
            dest = implemented_dir / filepath.name
            shutil.move(str(filepath), str(dest))
            moved += 1

    # Regenerate manifest
    from specbuilder.src.generate_index import generate

    generate(project_root=project_root)

    # Clean up execution log
    log_file = _log_path(project_root)
    if log_file.exists():
        # Append completion marker
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M")
        content = log_file.read_text(encoding="utf-8")
        content += f"\n## Batch Complete ({now})\n"
        log_file.write_text(content, encoding="utf-8")

    print(f"Batch complete: {updated} status updates, {moved} files moved.")
    print("Manifest regenerated.")
    return True


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Execution checkpoint protocol for multi-proposal batches.",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--init",
        metavar="IDS",
        help="Initialize batch with comma-separated proposal IDs (e.g., EXT-055,EXT-056)",
    )
    group.add_argument(
        "--status",
        action="store_true",
        help="Print current batch state (re-derives from proposal statuses)",
    )
    group.add_argument(
        "--wave",
        type=int,
        metavar="N",
        help="Record completion of wave N",
    )
    group.add_argument(
        "--complete",
        action="store_true",
        help="Finalize batch: update statuses, move to implemented/, regenerate manifest",
    )
    parser.add_argument(
        "--results",
        metavar="TEXT",
        help="Verification results string (used with --wave)",
    )
    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    project_root = get_project_root()

    if args.init:
        ids = [s.strip() for s in args.init.split(",") if s.strip()]
        if len(ids) < 2:
            print("Error: Batch requires at least 2 proposals.", file=sys.stderr)
            sys.exit(2)
        try:
            log_path = init_execution_log(ids, project_root)
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(2)
        print(f"Execution log created: {log_path.relative_to(project_root)}")
        print(f"Batch: {len(ids)} proposals")
        waves = build_dependency_graph(ids, project_root)
        print(f"Waves: {len(waves)}")
        for i, wave in enumerate(waves, 1):
            print(f"  Wave {i}: {', '.join(wave)}")

    elif args.status:
        print_status(project_root)

    elif args.wave is not None:
        success = record_wave(args.wave, project_root, results=args.results)
        if not success:
            sys.exit(1)

    elif args.complete:
        success = complete_batch(project_root)
        if not success:
            sys.exit(1)


if __name__ == "__main__":
    main()

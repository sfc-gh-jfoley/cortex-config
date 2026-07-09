#!/usr/bin/env python3
"""GEPA Population State Machine.

Manages the evolutionary state for Genetic Evaluation and Parameter Adaptation (GEPA)
optimization of semantic views. Tracks candidates, generations, operator weights,
and convergence.

Usage:
  python population_state.py init <workspace_dir> --pop-size N --agent-name NAME --baseline-fitness SCORE
  python population_state.py add-candidate <state_path> --id ID --generation G --mutations "desc"
  python population_state.py remove-candidates <state_path> --ids id1,id2
  python population_state.py update-fitness <state_path> --id ID --fitness SCORE
  python population_state.py update-weights <state_path> --winners id1,id2 --losers id3,id4
  python population_state.py get-status <state_path>
  python population_state.py increment-generation <state_path>

Run with: python3 scripts/population_state.py
"""

import argparse
import json
import os
import sys
from pathlib import Path


DEFAULT_OPERATOR_WEIGHTS = {
    "add_synonym": 0.12,
    "improve_description": 0.12,
    "add_filter": 0.10,
    "add_vqr": 0.12,
    "add_metric": 0.12,
    "refine_metric_expr": 0.10,
    "add_metric_description": 0.08,
    "change_relationship": 0.10,
    "add_time_dimension": 0.08,
    "remove_column": 0.06,
}

WEIGHT_FLOOR = 0.02


def load_state(state_path: str) -> dict:
    """Load GEPA state from JSON file."""
    path = Path(state_path)
    if not path.exists():
        print(f"Error: State file not found: {state_path}", file=sys.stderr)
        sys.exit(1)
    with open(path) as f:
        return json.load(f)


def save_state(state_path: str, state: dict) -> None:
    """Save GEPA state to JSON file."""
    with open(state_path, "w") as f:
        json.dump(state, f, indent=2)


def cmd_init(args):
    """Initialize a new GEPA state file."""
    workspace = Path(args.workspace_dir)
    workspace.mkdir(parents=True, exist_ok=True)
    state_path = workspace / "gepa_state.json"

    state = {
        "agent_name": args.agent_name,
        "population_size": args.pop_size,
        "max_generations": 10,
        "mini_batch_pct": 0.30,
        "convergence_threshold": 3,
        "current_generation": 1,
        "convergence_counter": 0,
        "baseline_fitness": args.baseline_fitness,
        "best_fitness": args.baseline_fitness,
        "candidates": [],
        "operator_weights": dict(DEFAULT_OPERATOR_WEIGHTS),
        "batch_history": [],
    }

    save_state(str(state_path), state)
    print(json.dumps({"state_path": str(state_path), "status": "initialized"}))


def cmd_add_candidate(args):
    """Add a candidate to the population."""
    state = load_state(args.state_path)

    candidate = {
        "id": args.id,
        "generation": args.generation,
        "mutations": args.mutations,
        "fitness": None,
        "status": "pending",
    }

    state["candidates"].append(candidate)
    save_state(args.state_path, state)
    print(json.dumps({"added": args.id, "total_candidates": len(state["candidates"])}))


def cmd_remove_candidates(args):
    """Remove candidates by ID."""
    state = load_state(args.state_path)
    ids_to_remove = set(args.ids.split(","))

    before_count = len(state["candidates"])
    state["candidates"] = [
        c for c in state["candidates"] if c["id"] not in ids_to_remove
    ]
    removed_count = before_count - len(state["candidates"])

    save_state(args.state_path, state)
    print(json.dumps({"removed": removed_count, "remaining": len(state["candidates"])}))


def cmd_update_fitness(args):
    """Update fitness score for a candidate."""
    state = load_state(args.state_path)

    found = False
    for candidate in state["candidates"]:
        if candidate["id"] == args.id:
            candidate["fitness"] = args.fitness
            candidate["status"] = "evaluated"
            found = True
            break

    if not found:
        print(f"Error: Candidate {args.id} not found", file=sys.stderr)
        sys.exit(1)

    save_state(args.state_path, state)
    print(json.dumps({"updated": args.id, "fitness": args.fitness}))


def cmd_update_weights(args):
    """Update operator weights based on tournament results."""
    state = load_state(args.state_path)
    winners = set(args.winners.split(","))
    losers = set(args.losers.split(","))

    # Map candidate IDs to their mutation operators
    candidate_map = {c["id"]: c for c in state["candidates"]}

    # Extract operator from mutation description (first word before space)
    def extract_operator(mutations_str: str) -> str | None:
        """Extract the operator name from mutation description."""
        for op in state["operator_weights"]:
            if op in mutations_str:
                return op
        return None

    # Boost winner operators
    for w_id in winners:
        if w_id in candidate_map:
            op = extract_operator(candidate_map[w_id].get("mutations", ""))
            if op and op in state["operator_weights"]:
                state["operator_weights"][op] += 0.02

    # Penalize loser operators
    for l_id in losers:
        if l_id in candidate_map:
            op = extract_operator(candidate_map[l_id].get("mutations", ""))
            if op and op in state["operator_weights"]:
                state["operator_weights"][op] = max(
                    WEIGHT_FLOOR, state["operator_weights"][op] - 0.01
                )

    # Normalize weights to sum to 1.0
    total = sum(state["operator_weights"].values())
    if total > 0:
        state["operator_weights"] = {
            k: round(v / total, 4) for k, v in state["operator_weights"].items()
        }

    save_state(args.state_path, state)
    print(json.dumps({"weights_updated": True, "operator_weights": state["operator_weights"]}))


def cmd_get_status(args):
    """Get current GEPA status."""
    state = load_state(args.state_path)

    evaluated = [c for c in state["candidates"] if c["fitness"] is not None]
    pending = [c for c in state["candidates"] if c["fitness"] is None]

    # Check convergence conditions
    converged = False
    reason = None

    if state["convergence_counter"] >= state["convergence_threshold"]:
        converged = True
        reason = f"convergence_counter ({state['convergence_counter']}) >= threshold ({state['convergence_threshold']})"
    elif state["current_generation"] >= state["max_generations"]:
        converged = True
        reason = f"max_generations reached ({state['max_generations']})"
    elif len(evaluated) >= 2:
        scores = [c["fitness"] for c in evaluated]
        if max(scores) - min(scores) < 0.02:
            converged = True
            reason = "population collapse (all within 2%)"

    status = {
        "agent_name": state["agent_name"],
        "generation": state["current_generation"],
        "max_generations": state["max_generations"],
        "baseline_fitness": state["baseline_fitness"],
        "best_fitness": state["best_fitness"],
        "convergence_counter": state["convergence_counter"],
        "convergence_threshold": state["convergence_threshold"],
        "total_candidates": len(state["candidates"]),
        "evaluated": len(evaluated),
        "pending": len(pending),
        "converged": converged,
        "convergence_reason": reason,
    }

    print(json.dumps(status, indent=2))


def cmd_increment_generation(args):
    """Increment the generation counter."""
    state = load_state(args.state_path)
    state["current_generation"] += 1
    save_state(args.state_path, state)
    print(json.dumps({"generation": state["current_generation"]}))


def main():
    parser = argparse.ArgumentParser(description="GEPA Population State Machine")
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # init
    p_init = subparsers.add_parser("init", help="Initialize new GEPA state")
    p_init.add_argument("workspace_dir", help="Directory to create state file in")
    p_init.add_argument("--pop-size", type=int, required=True, help="Population size")
    p_init.add_argument("--agent-name", required=True, help="Semantic view name")
    p_init.add_argument("--baseline-fitness", type=float, required=True, help="Baseline fitness score")

    # add-candidate
    p_add = subparsers.add_parser("add-candidate", help="Add a candidate")
    p_add.add_argument("state_path", help="Path to gepa_state.yaml")
    p_add.add_argument("--id", required=True, help="Candidate ID")
    p_add.add_argument("--generation", type=int, required=True, help="Generation number")
    p_add.add_argument("--mutations", required=True, help="Mutation description")

    # remove-candidates
    p_rm = subparsers.add_parser("remove-candidates", help="Remove candidates")
    p_rm.add_argument("state_path", help="Path to gepa_state.yaml")
    p_rm.add_argument("--ids", required=True, help="Comma-separated candidate IDs")

    # update-fitness
    p_fit = subparsers.add_parser("update-fitness", help="Update candidate fitness")
    p_fit.add_argument("state_path", help="Path to gepa_state.yaml")
    p_fit.add_argument("--id", required=True, help="Candidate ID")
    p_fit.add_argument("--fitness", type=float, required=True, help="Fitness score")

    # update-weights
    p_wt = subparsers.add_parser("update-weights", help="Update operator weights")
    p_wt.add_argument("state_path", help="Path to gepa_state.yaml")
    p_wt.add_argument("--winners", required=True, help="Comma-separated winner IDs")
    p_wt.add_argument("--losers", required=True, help="Comma-separated loser IDs")

    # get-status
    p_st = subparsers.add_parser("get-status", help="Get GEPA status")
    p_st.add_argument("state_path", help="Path to gepa_state.yaml")

    # increment-generation
    p_gen = subparsers.add_parser("increment-generation", help="Increment generation")
    p_gen.add_argument("state_path", help="Path to gepa_state.yaml")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    commands = {
        "init": cmd_init,
        "add-candidate": cmd_add_candidate,
        "remove-candidates": cmd_remove_candidates,
        "update-fitness": cmd_update_fitness,
        "update-weights": cmd_update_weights,
        "get-status": cmd_get_status,
        "increment-generation": cmd_increment_generation,
    }

    commands[args.command](args)


if __name__ == "__main__":
    main()

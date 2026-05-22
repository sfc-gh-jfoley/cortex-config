#!/usr/bin/env python3
"""Tournament selection for GEPA evolutionary optimization.

Ranks candidates by fitness, selects winners/losers, updates operator weights
and convergence tracking in the state file.

Usage:
  python tournament.py <scores_json> <state_path>

Input scores_json format:
  {"cand_1": 0.75, "cand_2": 0.60, "cand_3": 0.82, "cand_4": 0.55}

Output (stdout JSON):
  {"winners": [...], "losers": [...], "best_fitness": 0.82, "converged": false}

Run with: uvx --with pyyaml python scripts/tournament.py
"""

import json
import sys
from pathlib import Path

import yaml


WEIGHT_BOOST = 0.02
WEIGHT_PENALTY = 0.01
WEIGHT_FLOOR = 0.02
DEFAULT_OPERATORS = [
    "add_synonym", "improve_description", "add_filter", "add_vqr",
    "add_metric", "refine_metric_expr", "add_metric_description",
    "change_relationship", "add_time_dimension", "remove_column",
]


def load_state(state_path: str) -> dict:
    """Load GEPA state from YAML file."""
    path = Path(state_path)
    if not path.exists():
        print(f"Error: State file not found: {state_path}", file=sys.stderr)
        sys.exit(1)
    with open(path) as f:
        return yaml.safe_load(f)


def save_state(state_path: str, state: dict) -> None:
    """Save GEPA state to YAML file."""
    with open(state_path, "w") as f:
        yaml.dump(state, f, default_flow_style=False, sort_keys=False)


def extract_operator(mutations_str: str) -> str | None:
    """Extract operator name from mutations description."""
    if not mutations_str:
        return None
    for op in DEFAULT_OPERATORS:
        if op in mutations_str:
            return op
    return None


def run_tournament(scores: dict[str, float], state: dict) -> dict:
    """Execute tournament selection.

    Args:
        scores: Map of candidate_id -> fitness score
        state: Current GEPA state dict

    Returns:
        Tournament result with winners, losers, best_fitness, converged flag
    """
    # Rank by score descending
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)

    # Split into winners (top half) and losers (bottom half)
    midpoint = len(ranked) // 2
    # Elitism: ensure at least 1 winner (the best)
    if midpoint == 0:
        midpoint = 1

    winners = [cid for cid, _ in ranked[:midpoint]]
    losers = [cid for cid, _ in ranked[midpoint:]]

    # Best fitness from this generation
    gen_best = ranked[0][1] if ranked else 0.0

    return {
        "winners": winners,
        "losers": losers,
        "gen_best_fitness": gen_best,
        "ranked": ranked,
    }


def update_operator_weights(state: dict, winners: list[str], losers: list[str]) -> None:
    """Adjust operator weights: boost winners' ops, penalize losers' ops."""
    candidates_by_id = {c["id"]: c for c in state["candidates"]}

    for wid in winners:
        if wid in candidates_by_id:
            op = extract_operator(candidates_by_id[wid].get("mutations", ""))
            if op and op in state["operator_weights"]:
                state["operator_weights"][op] += WEIGHT_BOOST

    for lid in losers:
        if lid in candidates_by_id:
            op = extract_operator(candidates_by_id[lid].get("mutations", ""))
            if op and op in state["operator_weights"]:
                state["operator_weights"][op] = max(
                    WEIGHT_FLOOR, state["operator_weights"][op] - WEIGHT_PENALTY
                )

    # Normalize to sum to 1.0
    total = sum(state["operator_weights"].values())
    if total > 0:
        state["operator_weights"] = {
            k: round(v / total, 4) for k, v in state["operator_weights"].items()
        }


def check_convergence(state: dict, gen_best: float) -> bool:
    """Check if population has converged.

    Convergence conditions:
    - convergence_counter >= threshold (no improvement for N gens)
    - current_generation >= max_generations
    - Population collapse (not checked here — requires score variance)
    """
    threshold = state.get("convergence_threshold", 3)
    max_gen = state.get("max_generations", 10)

    # Check generation limit
    if state["current_generation"] >= max_gen:
        return True

    # Check convergence counter
    if state["convergence_counter"] >= threshold:
        return True

    # Early termination: gen 1 winner >10% above baseline
    if state["current_generation"] == 1:
        baseline = state.get("baseline_fitness", 0.0)
        if baseline > 0 and gen_best > baseline * 1.10:
            return True

    return False


def main() -> None:
    if len(sys.argv) != 3:
        print("Usage: python tournament.py <scores_json> <state_path>", file=sys.stderr)
        sys.exit(1)

    scores_input = sys.argv[1]
    state_path = sys.argv[2]

    # Parse scores — accept either a JSON string or a file path
    if Path(scores_input).exists():
        with open(scores_input) as f:
            scores = json.load(f)
    else:
        try:
            scores = json.loads(scores_input)
        except json.JSONDecodeError:
            print(f"Error: Cannot parse scores. Provide JSON string or file path.", file=sys.stderr)
            sys.exit(1)

    # Validate scores
    if not scores:
        print("Error: Empty scores dict.", file=sys.stderr)
        sys.exit(1)

    state = load_state(state_path)

    # Run tournament
    result = run_tournament(scores, state)
    winners = result["winners"]
    losers = result["losers"]
    gen_best = result["gen_best_fitness"]

    # Update fitness in state for each scored candidate
    for cid, score in scores.items():
        for candidate in state["candidates"]:
            if candidate["id"] == cid:
                candidate["fitness"] = score
                candidate["status"] = "evaluated"
                break

    # Update operator weights
    update_operator_weights(state, winners, losers)

    # Update convergence tracking
    prev_best = state.get("best_fitness", 0.0)
    if gen_best > prev_best:
        state["best_fitness"] = gen_best
        state["convergence_counter"] = 0
    else:
        state["convergence_counter"] += 1

    # Check convergence
    converged = check_convergence(state, gen_best)

    # Save state
    save_state(state_path, state)

    # Output result
    output = {
        "winners": winners,
        "losers": losers,
        "best_fitness": state["best_fitness"],
        "gen_best_fitness": gen_best,
        "convergence_counter": state["convergence_counter"],
        "converged": converged,
    }
    print(json.dumps(output))


if __name__ == "__main__":
    main()

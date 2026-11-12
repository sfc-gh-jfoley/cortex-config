#!/usr/bin/env python3
"""Tournament selection for GEPA evolutionary optimization.

Ranks candidates by fitness, selects winners/losers, updates operator weights
and convergence tracking in the state file.

Usage:
  python tournament.py <scores_json> <state_path> --metric-version v3

Input scores_json format:
  {"cand_1": 0.75, "cand_2": 0.60, "cand_3": 0.82, "cand_4": 0.55}

Output (stdout JSON):
  {"winners": [...], "losers": [...], "best_fitness": 0.82, "converged": false}

Run with: python3 scripts/tournament.py
"""

import json
import sys
from pathlib import Path


EARLY_STOP_DELTA = 0.10

sys.path.insert(0, str(Path(__file__).resolve().parent))
from population_state import apply_weight_update, check_metric_version  # noqa: E402


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


def check_convergence(state: dict, gen_best: float) -> bool:
    """Check if population has converged.

    Convergence conditions:
    - convergence_counter >= threshold (no improvement for N gens)
    - current_generation >= max_generations
    - generation 1 best more than 0.10 above baseline
    """
    threshold = state.get("convergence_threshold", 3)
    max_gen = state.get("max_generations", 10)

    # Check generation limit
    if state["current_generation"] >= max_gen:
        return True

    # Check convergence counter
    if state["convergence_counter"] >= threshold:
        return True

    # Early stop: generation 1 best is more than 0.10 (absolute) above baseline
    if state["current_generation"] == 1:
        baseline = state.get("baseline_fitness", 0.0)
        if gen_best > baseline + EARLY_STOP_DELTA:
            return True

    return False


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("scores_json")
    parser.add_argument("state_path")
    parser.add_argument("--metric-version", required=True, help="sql_correctness version of these scores")
    ns = parser.parse_args()
    scores_input = ns.scores_json
    state_path = ns.state_path

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
    try:
        check_metric_version(state, ns.metric_version)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

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
                candidate["metric_version"] = ns.metric_version
                break

    # Update operator weights
    apply_weight_update(state, winners, losers)

    # Update convergence tracking
    prev_best = state.get("best_fitness", 0.0)
    if gen_best > prev_best:
        state["best_fitness"] = gen_best
        best = next((c for c in state["candidates"] if c["id"] == result["ranked"][0][0]), None)
        if best:
            state["best_candidate_fqn"] = best.get("candidate_fqn")
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
        "best_candidate_fqn": state.get("best_candidate_fqn"),
    }
    print(json.dumps(output))


if __name__ == "__main__":
    main()

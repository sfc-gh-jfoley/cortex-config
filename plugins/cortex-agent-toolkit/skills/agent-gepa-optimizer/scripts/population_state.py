"""Manage gepa_state.yaml — the persistent state between GEPA generations."""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml


STATE_VERSION = 1

DEFAULT_OPERATOR_WEIGHTS = {
    "add_retry_logic": 0.15,
    "add_wrong_example": 0.15,
    "add_routing_rule": 0.15,
    "add_format_template": 0.10,
    "fix_example": 0.20,
    "add_domain_rule": 0.10,
    "rewrite_ambiguous_rule": 0.10,
    "remove_verbose_rule": 0.05,
}


def init_state(pop_size: int, agent_name: str, baseline_fitness: float,
               max_generations: int = 10) -> dict:
    """Create a fresh GEPA state dict."""
    return {
        "version": STATE_VERSION,
        "agent_name": agent_name,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "population_size": pop_size,
        "max_generations": max_generations,
        "current_generation": 0,
        "convergence_counter": 0,
        "best_candidate": {
            "id": "baseline",
            "fitness": baseline_fitness,
            "mutations": [],
            "generation_born": 0,
        },
        "baseline_fitness": baseline_fitness,
        "mean_fitness_history": [],
        "operator_weights": dict(DEFAULT_OPERATOR_WEIGHTS),
        "population": [],
        "history": [],
    }


def load_state(path: str) -> dict | None:
    """Load state from YAML file. Returns None if file doesn't exist."""
    p = Path(path)
    if not p.exists():
        return None
    with p.open("r") as f:
        return yaml.safe_load(f)


def save_state(state: dict, path: str) -> None:
    """Write state to YAML file."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w") as f:
        yaml.dump(state, f, default_flow_style=False, sort_keys=False)


def set_population(state: dict, candidates: list[dict]) -> dict:
    """Replace the current population with a new list of candidates.

    Each candidate dict should have at minimum:
        {"id": str, "mutations_applied": list[str], "generation_born": int}
    Optional fields: parent_id, last_fitness, file_dir
    """
    state["population"] = candidates
    return state


def add_candidate(state: dict, candidate_id: str, mutations: list[str],
                  generation: int, parent_id: str | None = None,
                  file_dir: str | None = None) -> dict:
    """Add a single candidate to the population."""
    state["population"].append({
        "id": candidate_id,
        "parent_id": parent_id,
        "mutations_applied": mutations,
        "generation_born": generation,
        "last_fitness": None,
        "file_dir": file_dir,
    })
    return state


def remove_candidates(state: dict, candidate_ids: list[str]) -> dict:
    """Remove eliminated candidates from the population."""
    state["population"] = [
        c for c in state["population"] if c["id"] not in candidate_ids
    ]
    return state


def add_generation(state: dict, gen_number: int, batch_questions: list[str],
                   results: dict, winner: str | None, eliminated: list[str]) -> dict:
    """Record a completed generation in state history."""
    state["current_generation"] = gen_number
    state["history"].append({
        "generation": gen_number,
        "batch_questions": batch_questions,
        "results": results,
        "winner": winner,
        "eliminated": eliminated,
    })

    # Track mean population fitness for convergence condition #4
    fitness_values = [
        v.get("EVAL_AGG_SCORE", 0.0) for v in results.values()
        if isinstance(v, dict)
    ]
    if fitness_values:
        mean_fitness = sum(fitness_values) / len(fitness_values)
        state.setdefault("mean_fitness_history", []).append(mean_fitness)

    # Update convergence counter
    if winner and winner != state["best_candidate"]["id"]:
        winner_fitness = results.get(winner, {}).get("EVAL_AGG_SCORE", 0.0)
        if winner_fitness > state["best_candidate"]["fitness"]:
            state["best_candidate"] = {
                "id": winner,
                "fitness": winner_fitness,
                "mutations": _get_candidate_mutations(state, winner),
                "generation_born": gen_number,
            }
            state["convergence_counter"] = 0
        else:
            state["convergence_counter"] += 1
    else:
        state["convergence_counter"] += 1

    return state


def get_cleanup_targets(state: dict) -> list[str]:
    """Return agent FQN suffixes for variants that should be DROPped."""
    targets = []
    for entry in state["history"]:
        for elim in entry.get("eliminated", []):
            suffix = f"GEPA_CAND_{elim}"
            if suffix not in targets:
                targets.append(suffix)
    return targets


def update_operator_weights(state: dict, operator: str, success: bool) -> dict:
    """Adjust operator weight based on tournament outcome.

    Rates per mutation-operators.md:
      - Winner's operator: +0.02
      - Loser's operator: -0.01
      - Floor: 0.02 (operator never fully disabled)
      - No cap (normalization at selection time handles scale)
    """
    weights = state.get("operator_weights", dict(DEFAULT_OPERATOR_WEIGHTS))
    current = weights.get(operator, 0.10)
    if success:
        weights[operator] = current + 0.02
    else:
        weights[operator] = max(0.02, current - 0.01)
    state["operator_weights"] = weights
    return state


def _get_candidate_mutations(state: dict, candidate_id: str) -> list[str]:
    """Look up mutations applied to a candidate from population."""
    for cand in state["population"]:
        if cand["id"] == candidate_id:
            return cand.get("mutations_applied", [])
    return []


def main():
    parser = argparse.ArgumentParser(description="GEPA population state manager")
    sub = parser.add_subparsers(dest="command", required=True)

    # init
    p_init = sub.add_parser("init", help="Initialize new state file")
    p_init.add_argument("path", help="Output state file path")
    p_init.add_argument("--pop-size", type=int, required=True)
    p_init.add_argument("--agent-name", required=True)
    p_init.add_argument("--baseline-fitness", type=float, required=True)
    p_init.add_argument("--max-generations", type=int, default=10)

    # load
    p_load = sub.add_parser("load", help="Load and print state as JSON")
    p_load.add_argument("path", help="State file path")

    # cleanup-targets
    p_clean = sub.add_parser("cleanup-targets", help="Print agent suffixes to drop")
    p_clean.add_argument("path", help="State file path")

    # add-candidate
    p_add = sub.add_parser("add-candidate", help="Register a candidate in state")
    p_add.add_argument("state_path", help="State file path")
    p_add.add_argument("--id", required=True, help="Candidate ID")
    p_add.add_argument("--mutations", default="", help="Comma-separated mutation operators applied")
    p_add.add_argument("--generation", type=int, required=True)
    p_add.add_argument("--parent-id", default=None)
    p_add.add_argument("--file-dir", default=None)

    # remove-candidates
    p_rm = sub.add_parser("remove-candidates", help="Remove eliminated candidates")
    p_rm.add_argument("state_path", help="State file path")
    p_rm.add_argument("--ids", required=True, help="Comma-separated candidate IDs to remove")

    args = parser.parse_args()

    if args.command == "init":
        path = Path(args.path)
        if path.is_dir():
            path = path / "gepa_state.yaml"
        state = init_state(
            pop_size=args.pop_size,
            agent_name=args.agent_name,
            baseline_fitness=args.baseline_fitness,
            max_generations=args.max_generations,
        )
        save_state(state, str(path))
        print(json.dumps({"status": "ok", "path": str(path)}))

    elif args.command == "load":
        state = load_state(args.path)
        if state is None:
            print(json.dumps({"error": "state file not found", "path": args.path}))
            sys.exit(1)
        print(json.dumps(state, default=str))

    elif args.command == "cleanup-targets":
        state = load_state(args.path)
        if state is None:
            print(json.dumps({"error": "state file not found", "path": args.path}))
            sys.exit(1)
        targets = get_cleanup_targets(state)
        print(json.dumps(targets))

    elif args.command == "add-candidate":
        state = load_state(args.state_path)
        if state is None:
            print(json.dumps({"error": "state file not found", "path": args.state_path}))
            sys.exit(1)
        mutations = [m.strip() for m in args.mutations.split(",") if m.strip()]
        add_candidate(state, args.id, mutations, args.generation,
                      parent_id=args.parent_id, file_dir=args.file_dir)
        save_state(state, args.state_path)
        print(json.dumps({"status": "ok", "population_size": len(state["population"])}))

    elif args.command == "remove-candidates":
        state = load_state(args.state_path)
        if state is None:
            print(json.dumps({"error": "state file not found", "path": args.state_path}))
            sys.exit(1)
        ids = [i.strip() for i in args.ids.split(",") if i.strip()]
        remove_candidates(state, ids)
        save_state(state, args.state_path)
        print(json.dumps({"status": "ok", "population_size": len(state["population"])}))


if __name__ == "__main__":
    main()

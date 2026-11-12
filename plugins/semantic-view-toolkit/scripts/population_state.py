"""GEPA population state machine.

Tracks candidates (as candidate view names, never the production view), generations, operator
weights, the metric version, and the best candidate. The operator list comes from mutate.py.

Usage:
  population_state.py init <workspace_dir> --pop-size N --agent-name NAME --source-fqn DB.SCH.SV \
      --baseline-fitness SCORE [--metric-version v3]
  population_state.py add-candidate <state> --id ID --generation G --operator OP --mutations "desc" \
      --candidate-fqn FQN [--parent-fqn FQN] [--mutation-summary "short diff summary"]
  population_state.py remove-candidates <state> --ids id1,id2
  population_state.py update-fitness <state> --id ID --fitness SCORE --metric-version v3
  population_state.py update-weights <state> --winners id1,id2 --losers id3,id4
  population_state.py record-final <state> --id ID --fitness SCORE --metric-version v3 --questions-file F
  population_state.py finalize <state> [--min-repeats 2]
  population_state.py get-status <state>
  population_state.py increment-generation <state>
"""

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import candidate as candidate_contract  # noqa: E402
from mutate import OPERATORS  # noqa: E402

_even = round(1.0 / len(OPERATORS), 4)
DEFAULT_OPERATOR_WEIGHTS = {op: _even for op in OPERATORS}

WEIGHT_FLOOR = 0.02
BOOST_GAIN, BOOST_CAP = 0.5, 0.10
PENALTY_GAIN, PENALTY_CAP = 0.25, 0.05
DEFAULT_METRIC_VERSION = "v3"


def extract_operator(candidate: dict):
    """Exact operator match: the stored field, else a whole-token match in the description."""
    op = candidate.get("operator")
    if op in OPERATORS:
        return op
    text = candidate.get("mutations") or ""
    for name in OPERATORS:
        if re.search(rf"(?<![A-Za-z0-9_]){re.escape(name)}(?![A-Za-z0-9_])", text):
            return name
    return None


def reference_fitness(state: dict, candidate: dict) -> float:
    """Parent's fitness when known, else the baseline."""
    parent = candidate.get("parent_fqn")
    for c in state["candidates"]:
        if parent and c.get("candidate_fqn") == parent and c.get("fitness") is not None:
            return c["fitness"]
    return state["baseline_fitness"]


def apply_weight_update(state: dict, winners, losers) -> None:
    """Scale each operator's change by the score delta against its reference; floor, then normalize."""
    weights = state["operator_weights"]
    by_id = {c["id"]: c for c in state["candidates"]}
    for wid in winners:
        c = by_id.get(wid)
        op = extract_operator(c) if c else None
        if op in weights and c.get("fitness") is not None:
            delta = c["fitness"] - reference_fitness(state, c)
            weights[op] += min(BOOST_CAP, BOOST_GAIN * max(delta, 0.0))
    for lid in losers:
        c = by_id.get(lid)
        op = extract_operator(c) if c else None
        if op in weights and c.get("fitness") is not None:
            delta = c["fitness"] - reference_fitness(state, c)
            weights[op] = max(WEIGHT_FLOOR, weights[op] - min(PENALTY_CAP, PENALTY_GAIN * max(-delta, 0.0)))
    total = sum(weights.values())
    if total > 0:
        state["operator_weights"] = {k: round(max(v / total, 0.0), 4) for k, v in weights.items()}


def check_metric_version(state: dict, version: str) -> None:
    pinned = state.get("metric_version")
    if version != pinned:
        raise ValueError(
            f"metric version {version!r} differs from the pinned {pinned!r}; "
            "scores from different metric versions are not comparable"
        )


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
        "source_fqn": args.source_fqn,
        "metric_version": args.metric_version,
        "best_candidate_fqn": None,
        "final_runs": [],
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

    try:
        candidate_contract.check_guard(state["source_fqn"], args.candidate_fqn)
        if args.parent_fqn:
            candidate_contract.check_guard(state["source_fqn"], args.parent_fqn)
    except candidate_contract.ContractError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    candidate = {
        "id": args.id,
        "generation": args.generation,
        "operator": args.operator,
        "mutations": args.mutations,
        "mutation_summary": args.mutation_summary,
        "candidate_fqn": args.candidate_fqn,
        "parent_fqn": args.parent_fqn,
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

    try:
        check_metric_version(state, args.metric_version)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    found = False
    for candidate in state["candidates"]:
        if candidate["id"] == args.id:
            candidate["fitness"] = args.fitness
            candidate["metric_version"] = args.metric_version
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
    apply_weight_update(state, args.winners.split(","), args.losers.split(","))

    save_state(args.state_path, state)
    print(json.dumps({"weights_updated": True, "operator_weights": state["operator_weights"]}))


def cmd_record_final(args):
    """Record one repeat evaluation of a finalist on the shared question list."""
    state = load_state(args.state_path)
    try:
        check_metric_version(state, args.metric_version)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    if args.id != "production" and not any(c["id"] == args.id for c in state["candidates"]):
        print(f"Error: Candidate {args.id} not found (use --id production for the baseline)", file=sys.stderr)
        sys.exit(1)
    questions = json.loads(Path(args.questions_file).read_text())
    digest = hashlib.sha256("\n".join(sorted(questions)).encode()).hexdigest()[:16]
    state.setdefault("final_runs", []).append(
        {"id": args.id, "fitness": args.fitness, "questions_sha": digest, "metric_version": args.metric_version}
    )
    save_state(args.state_path, state)
    print(json.dumps({"recorded": args.id, "questions_sha": digest}))


def finalize_winner(state: dict, min_repeats: int = 2) -> dict:
    """Pick the winner by mean over repeated runs on one question list; set best_candidate_fqn."""
    if min_repeats < 2:
        raise ValueError("--min-repeats must be at least 2: one run is within generation noise")
    runs = state.get("final_runs", [])
    if not runs:
        raise ValueError("no final runs recorded")
    if len({r["questions_sha"] for r in runs}) != 1:
        raise ValueError("final runs used different question lists; re-run on one list")
    if len({r["metric_version"] for r in runs}) != 1:
        raise ValueError("final runs mix metric versions")
    by_id = {}
    for r in runs:
        by_id.setdefault(r["id"], []).append(r["fitness"])
    short = [i for i, v in by_id.items() if len(v) < min_repeats]
    if short:
        raise ValueError(f"candidates with fewer than {min_repeats} repeats: {short}")
    means = {i: sum(v) / len(v) for i, v in by_id.items()}
    production_mean = means.pop("production", None)
    if not means:
        raise ValueError("no candidate finalists recorded (only production)")
    best_id = max(means, key=means.get)
    cand = next((c for c in state["candidates"] if c["id"] == best_id), None)
    if cand is None:
        raise ValueError(f"finalist {best_id} is no longer in the state file (removed after record-final); re-run it")
    state["best_candidate_fqn"] = cand["candidate_fqn"]
    state["best_fitness"] = means[best_id]
    delta = None if production_mean is None else round(means[best_id] - production_mean, 6)
    return {"winner": best_id, "best_candidate_fqn": cand["candidate_fqn"], "means": means,
            "production_mean": production_mean, "delta_vs_production": delta}


def cmd_finalize(args):
    state = load_state(args.state_path)
    try:
        result = finalize_winner(state, args.min_repeats)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    save_state(args.state_path, state)
    print(json.dumps(result))


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
        "metric_version": state.get("metric_version"),
        "best_candidate_fqn": state.get("best_candidate_fqn"),
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
    p_init.add_argument("--source-fqn", required=True, help="Production DB.SCH.SV (never modified)")
    p_init.add_argument("--metric-version", default=DEFAULT_METRIC_VERSION, help="Pinned sql_correctness version")
    p_init.add_argument("--baseline-fitness", type=float, required=True, help="Baseline fitness score")

    # add-candidate
    p_add = subparsers.add_parser("add-candidate", help="Add a candidate")
    p_add.add_argument("state_path", help="Path to gepa_state.json")
    p_add.add_argument("--id", required=True, help="Candidate ID")
    p_add.add_argument("--generation", type=int, required=True, help="Generation number")
    p_add.add_argument("--operator", required=True, choices=OPERATORS, help="Mutation operator")
    p_add.add_argument("--mutations", required=True, help="Mutation description")
    p_add.add_argument("--candidate-fqn", required=True, help="Candidate view name from candidate.py name")
    p_add.add_argument("--parent-fqn", help="Candidate this one was mutated from (omit for generation 1)")
    p_add.add_argument("--mutation-summary", default="", help="Short summary of the change")

    # remove-candidates
    p_rm = subparsers.add_parser("remove-candidates", help="Remove candidates")
    p_rm.add_argument("state_path", help="Path to gepa_state.json")
    p_rm.add_argument("--ids", required=True, help="Comma-separated candidate IDs")

    # update-fitness
    p_fit = subparsers.add_parser("update-fitness", help="Update candidate fitness")
    p_fit.add_argument("state_path", help="Path to gepa_state.json")
    p_fit.add_argument("--id", required=True, help="Candidate ID")
    p_fit.add_argument("--fitness", type=float, required=True, help="Fitness score")
    p_fit.add_argument("--metric-version", required=True, help="sql_correctness version that produced the score")

    p_rf = subparsers.add_parser("record-final", help="Record a finalist repeat run")
    p_rf.add_argument("state_path")
    p_rf.add_argument("--id", required=True)
    p_rf.add_argument("--fitness", type=float, required=True)
    p_rf.add_argument("--metric-version", required=True)
    p_rf.add_argument("--questions-file", required=True, help="JSON list of the questions evaluated")

    p_fin = subparsers.add_parser("finalize", help="Choose winner from repeated finalist runs")
    p_fin.add_argument("state_path")
    p_fin.add_argument("--min-repeats", type=int, default=2)

    # update-weights
    p_wt = subparsers.add_parser("update-weights", help="Update operator weights")
    p_wt.add_argument("state_path", help="Path to gepa_state.json")
    p_wt.add_argument("--winners", required=True, help="Comma-separated winner IDs")
    p_wt.add_argument("--losers", required=True, help="Comma-separated loser IDs")

    # get-status
    p_st = subparsers.add_parser("get-status", help="Get GEPA status")
    p_st.add_argument("state_path", help="Path to gepa_state.json")

    # increment-generation
    p_gen = subparsers.add_parser("increment-generation", help="Increment generation")
    p_gen.add_argument("state_path", help="Path to gepa_state.json")

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
        "record-final": cmd_record_final,
        "finalize": cmd_finalize,
        "get-status": cmd_get_status,
        "increment-generation": cmd_increment_generation,
    }

    commands[args.command](args)


if __name__ == "__main__":
    main()

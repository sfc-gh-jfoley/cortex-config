"""Manage tpe_optimizer_state.json — persistent state for the TPE instruction optimizer run."""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


STATE_VERSION = 1


def _load(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        print(json.dumps({"error": "state file not found", "path": path}))
        sys.exit(1)
    with p.open("r") as f:
        return json.load(f)


def _save(state: dict, path: str) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w") as f:
        json.dump(state, f, indent=2)


def main():
    parser = argparse.ArgumentParser(description="TPE optimizer state manager")
    sub = parser.add_subparsers(dest="command", required=True)

    # init
    p_init = sub.add_parser("init", help="Create fresh state file")
    p_init.add_argument("path", help="Output state file path")
    p_init.add_argument("--agent-name", required=True)
    p_init.add_argument("--n-trials", type=int, default=20)
    p_init.add_argument("--n-startup-trials", type=int, default=5)
    p_init.add_argument("--few-shot-k", type=int, default=2)
    p_init.add_argument("--instruction-pool-size", type=int, default=12)
    p_init.add_argument("--baseline-score", type=float, default=0.0)
    p_init.add_argument("--study-db", default="tpe_study.db")

    # load
    p_load = sub.add_parser("load", help="Print state as JSON")
    p_load.add_argument("path")

    # record-trial
    p_rec = sub.add_parser("record-trial", help="Add a completed trial to state")
    p_rec.add_argument("path")
    p_rec.add_argument("--trial-number", type=int, required=True)
    p_rec.add_argument("--score", type=float, required=True)
    p_rec.add_argument("--params", default="{}", help="JSON dict of trial params")

    # add-deployed
    p_dep = sub.add_parser("add-deployed", help="Track a deployed candidate agent")
    p_dep.add_argument("path")
    p_dep.add_argument("--agent-name", required=True, dest="deployed_agent")

    # remove-deployed
    p_rm = sub.add_parser("remove-deployed", help="Remove a deployed candidate agent from tracking")
    p_rm.add_argument("path")
    p_rm.add_argument("--agent-name", required=True, dest="deployed_agent")

    # show-best
    p_best = sub.add_parser("show-best", help="Print best trial info as JSON")
    p_best.add_argument("path")

    args = parser.parse_args()

    if args.command == "init":
        path = Path(args.path)
        if path.is_dir():
            path = path / "tpe_optimizer_state.json"
        state = {
            "version": STATE_VERSION,
            "run_id": str(uuid4()),
            "agent_name": args.agent_name,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "n_trials": args.n_trials,
            "n_startup_trials": args.n_startup_trials,
            "few_shot_k": args.few_shot_k,
            "instruction_pool_size": args.instruction_pool_size,
            "baseline_score": args.baseline_score,
            "best_trial_number": None,
            "best_score": None,
            "best_params": None,
            "completed_trials": [],
            "deployed_agents": [],
            "study_db_path": args.study_db,
        }
        _save(state, str(path))
        print(json.dumps({"status": "ok", "path": str(path), "run_id": state["run_id"]}))

    elif args.command == "load":
        state = _load(args.path)
        print(json.dumps(state, default=str))

    elif args.command == "record-trial":
        state = _load(args.path)
        try:
            params = json.loads(args.params)
        except json.JSONDecodeError:
            print(json.dumps({"error": "invalid JSON for --params"}), file=sys.stderr)
            sys.exit(1)
        trial_entry = {
            "trial_number": args.trial_number,
            "score": args.score,
            "params": params,
        }
        state["completed_trials"].append(trial_entry)
        best = state.get("best_score")
        if best is None or args.score > best:
            state["best_trial_number"] = args.trial_number
            state["best_score"] = args.score
            state["best_params"] = params
            print(
                f"Trial {args.trial_number}: score={args.score:.4f} — NEW BEST",
                file=sys.stderr,
            )
        else:
            print(
                f"Trial {args.trial_number}: score={args.score:.4f} (best={best:.4f})",
                file=sys.stderr,
            )
        _save(state, args.path)
        print(json.dumps({"status": "ok", "completed": len(state["completed_trials"])}))

    elif args.command == "add-deployed":
        state = _load(args.path)
        if args.deployed_agent not in state["deployed_agents"]:
            state["deployed_agents"].append(args.deployed_agent)
        _save(state, args.path)
        print(json.dumps({"status": "ok", "deployed_agents": state["deployed_agents"]}))

    elif args.command == "remove-deployed":
        state = _load(args.path)
        state["deployed_agents"] = [
            a for a in state["deployed_agents"] if a != args.deployed_agent
        ]
        _save(state, args.path)
        print(json.dumps({"status": "ok", "deployed_agents": state["deployed_agents"]}))

    elif args.command == "show-best":
        state = _load(args.path)
        print(json.dumps({
            "best_trial_number": state.get("best_trial_number"),
            "best_score": state.get("best_score"),
            "best_params": state.get("best_params"),
        }))


if __name__ == "__main__":
    main()

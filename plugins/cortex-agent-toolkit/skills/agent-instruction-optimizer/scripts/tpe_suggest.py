"""Load or create the optuna TPE study and suggest the next trial parameters.

Outputs a JSON object with trial_number and sampled parameter indices.
Prints {"done": true} when the trial budget is exhausted.
"""

import argparse
import json
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(
        description="Suggest next TPE trial parameters for instruction optimization"
    )
    parser.add_argument("--study-db", required=True,
                        help="Path to SQLite study file (created if absent)")
    parser.add_argument("--agent-name", required=True,
                        help="Optuna study name (use agent name for uniqueness)")
    parser.add_argument("--instruction-pool", required=True,
                        help="Path to instruction_pool.json")
    parser.add_argument("--trace-pool", required=True,
                        help="Path to trace_pool.json")
    parser.add_argument("--few-shot-k", type=int, default=2,
                        help="Number of few-shot demos per candidate")
    parser.add_argument("--n-startup-trials", type=int, default=5,
                        help="Random exploration trials before TPE kicks in")
    parser.add_argument("--n-trials", type=int, default=20,
                        help="Total trial budget")
    parser.add_argument("--best-only", action="store_true",
                        help="Print best trial params and exit (no new trial)")
    args = parser.parse_args()

    try:
        import optuna
    except ImportError:
        print(
            "ERROR: optuna not installed. Run: pip install 'optuna>=3.6.0'",
            file=sys.stderr,
        )
        sys.exit(1)

    # Suppress optuna's default INFO logging to keep stderr clean
    optuna.logging.set_verbosity(optuna.logging.WARNING)

    # Load pools to know parameter ranges
    with open(args.instruction_pool) as f:
        instruction_pool = json.load(f)
    with open(args.trace_pool) as f:
        trace_pool = json.load(f)

    instr_pool_size = len(instruction_pool)
    trace_pool_size = len(trace_pool)

    if instr_pool_size == 0:
        print("ERROR: instruction_pool.json is empty", file=sys.stderr)
        sys.exit(1)
    if trace_pool_size == 0 and args.few_shot_k > 0:
        print("ERROR: trace_pool.json is empty but few_shot_k > 0", file=sys.stderr)
        sys.exit(1)

    storage_url = f"sqlite:///{Path(args.study_db).resolve()}"
    study = optuna.create_study(
        direction="maximize",
        sampler=optuna.samplers.TPESampler(n_startup_trials=args.n_startup_trials),
        storage=storage_url,
        study_name=args.agent_name,
        load_if_exists=True,
    )

    if args.best_only:
        try:
            best = study.best_trial
            print(json.dumps({
                "trial_number": best.number,
                "value": best.value,
                "params": best.params,
            }))
        except ValueError:
            # No completed trials yet
            print(json.dumps({"trial_number": None, "value": None, "params": {}}))
        return

    # Count only COMPLETE trials toward the budget
    import optuna.trial as ot
    completed = [
        t for t in study.trials
        if t.state == ot.TrialState.COMPLETE
    ]
    if len(completed) >= args.n_trials:
        print(f"Budget exhausted: {len(completed)}/{args.n_trials} trials complete",
              file=sys.stderr)
        print(json.dumps({"done": True, "completed": len(completed)}))
        return

    # Ask for the next trial (non-blocking suggest)
    trial = study.ask()

    params: dict[str, int] = {}
    params["instruction_idx"] = trial.suggest_int(
        "instruction_idx", 0, instr_pool_size - 1
    )
    for i in range(args.few_shot_k):
        params[f"fewshot_{i}"] = trial.suggest_int(
            f"fewshot_{i}", 0, trace_pool_size - 1
        )

    print(
        f"Trial {trial.number}: instruction_idx={params['instruction_idx']}, "
        f"fewshot={[params[f'fewshot_{i}'] for i in range(args.few_shot_k)]}"
        f" ({len(completed)+1}/{args.n_trials})",
        file=sys.stderr,
    )

    output = {
        "trial_number": trial.number,
        "done": False,
        **params,
    }
    print(json.dumps(output))


if __name__ == "__main__":
    main()

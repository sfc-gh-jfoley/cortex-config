"""Record a trial score back into the optuna TPE study.

Calls study.tell() to close the trial opened by tpe_suggest.py.
Must be called once per trial, after the eval score is known.
"""

import argparse
import json
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(
        description="Record a completed trial score into the optuna study"
    )
    parser.add_argument("--study-db", required=True,
                        help="Path to SQLite study file")
    parser.add_argument("--agent-name", required=True,
                        help="Optuna study name")
    parser.add_argument("--trial-number", type=int, required=True,
                        help="Trial number returned by tpe_suggest")
    parser.add_argument("--score", type=float, required=True,
                        help="Eval score for this trial (0.0–1.0)")
    args = parser.parse_args()

    try:
        import optuna
        import optuna.trial as ot
    except ImportError:
        print(
            "ERROR: optuna not installed. Run: pip install 'optuna>=3.6.0'",
            file=sys.stderr,
        )
        sys.exit(1)

    optuna.logging.set_verbosity(optuna.logging.WARNING)

    storage_url = f"sqlite:///{Path(args.study_db).resolve()}"
    study = optuna.load_study(
        study_name=args.agent_name,
        storage=storage_url,
    )

    # Find the frozen trial matching the requested number
    matching = [
        t for t in study.trials
        if t.number == args.trial_number
    ]
    if not matching:
        print(
            f"ERROR: trial {args.trial_number} not found in study '{args.agent_name}'",
            file=sys.stderr,
        )
        sys.exit(1)

    frozen_trial = matching[0]
    if frozen_trial.state != ot.TrialState.WAITING and \
            frozen_trial.state != ot.TrialState.RUNNING:
        print(
            f"WARNING: trial {args.trial_number} is in state {frozen_trial.state.name}, "
            "not WAITING/RUNNING. tell() may be a no-op.",
            file=sys.stderr,
        )

    # study.tell() accepts an int (trial number) or the original Trial object from ask().
    # FrozenTrial from study.trials[] is NOT accepted — use the int directly.
    study.tell(args.trial_number, args.score)

    # Determine best score across all completed trials
    try:
        best_value = study.best_value
        best_number = study.best_trial.number
    except ValueError:
        best_value = args.score
        best_number = args.trial_number

    print(
        f"Trial {args.trial_number} recorded: score={args.score:.4f}, "
        f"best so far=trial {best_number} ({best_value:.4f})",
        file=sys.stderr,
    )
    print(json.dumps({
        "status": "ok",
        "trial_number": args.trial_number,
        "score": args.score,
        "best_trial_number": best_number,
        "best_score": best_value,
    }))


if __name__ == "__main__":
    main()

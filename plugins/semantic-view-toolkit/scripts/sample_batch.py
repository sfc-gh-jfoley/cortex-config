#!/usr/bin/env python3
"""GEPA Stratified Mini-Batch Sampling.

Selects a stratified subset of VQRs for evaluation each generation.
Ensures diversity through rotation and difficulty stratification.

Usage:
  python sample_batch.py <database> <schema> <sv_name> --batch-pct 0.30 --generation G --history-file <state_path>

Since this script can't execute SQL directly, it requires VQR data piped in or
provided via a file. In practice the calling agent runs DESCRIBE SEMANTIC VIEW
and passes the VQR list via stdin.

Alternative usage (stdin mode):
  echo '<vqr_json>' | python sample_batch.py --from-stdin --batch-pct 0.30 --generation G --history-file <state_path>

Input VQR JSON format (stdin or file):
  [
    {"question": "What is total revenue?", "previously_passed": true},
    {"question": "Show top customers", "previously_passed": false}
  ]

Output: JSON list of selected VQR question strings to stdout, or with --emit-eval-yaml CANDIDATE_FQN
the evaluation config YAML that restricts the run to those questions.

Run with: python3 scripts/sample_batch.py
"""

import argparse
import hashlib
import json
import math
import random
import sys
from pathlib import Path


MIN_VQRS_FOR_SAMPLING = 5


def render_eval_config(analyst_name: str, questions: list, metric_version: str = "v3") -> str:
    """Analyst evaluation YAML restricted to the sampled questions (documented spec)."""
    lines = [
        "evaluation:",
        "  analyst_params:",
        f"    analyst_name: {json.dumps(analyst_name)}",
        '    analyst_type: "SEMANTIC VIEW"',
        "  source_metadata:",
        '    type: "verified_queries"',
        "    verified_queries:",
    ]
    lines += [f"      - {json.dumps(q)}" for q in questions]
    lines += ["", "metrics:", '  - name: "sql_correctness"', f'    version: "{metric_version}"']
    return "\n".join(lines) + "\n"


MIN_VQRS_FOR_HOLDOUT = 8


def split_holdout(vqrs: list, holdout_pct: float) -> dict:
    """Deterministic train/hold-out split by question hash (same input, same split, any run).

    Hold-out questions are scored only at finalist time and are never shown to the mutator.
    Fewer than MIN_VQRS_FOR_HOLDOUT questions: no hold-out (too small to be meaningful), reported as such.
    """
    questions = sorted({v["question"] for v in vqrs})
    if len(questions) < MIN_VQRS_FOR_HOLDOUT:
        return {"train": questions, "holdout": [], "note": f"fewer than {MIN_VQRS_FOR_HOLDOUT} questions: no hold-out; "
                "finalist scores are measured on questions the mutator saw, so treat gains as optimistic"}
    ranked = sorted(questions, key=lambda q: hashlib.sha256(q.encode()).hexdigest())
    n_hold = max(1, round(len(ranked) * holdout_pct))
    holdout = set(ranked[:n_hold])
    return {"train": [q for q in questions if q not in holdout], "holdout": [q for q in questions if q in holdout], "note": None}


def load_state(state_path: str) -> dict:
    """Load GEPA state from JSON file."""
    path = Path(state_path)
    if not path.exists():
        return {"batch_history": []}
    with open(path) as f:
        return json.load(f) or {"batch_history": []}


def save_state(state_path: str, state: dict) -> None:
    """Save GEPA state to JSON file."""
    with open(state_path, "w") as f:
        json.dump(state, f, indent=2)


def get_previous_batch(state: dict, generation: int) -> set[str]:
    """Get VQR questions used in the immediately previous generation."""
    for entry in state.get("batch_history", []):
        if entry.get("generation") == generation - 1:
            return set(entry.get("questions", []))
    return set()


def stratified_sample(
    vqrs: list[dict],
    batch_pct: float,
    generation: int,
    state: dict,
) -> list[str]:
    """Select a stratified mini-batch of VQRs.

    Strategy:
    1. Split into previously-passing and previously-failing pools
    2. Sample proportionally from each pool
    3. Avoid reusing the same VQRs from the previous generation
    4. Ensure minimum representation from each pool

    Args:
        vqrs: List of VQR dicts with "question" and optionally "previously_passed"
        batch_pct: Fraction to sample (0.20 - 0.50)
        generation: Current generation number
        state: GEPA state dict for batch history

    Returns:
        List of selected VQR question strings
    """
    if not vqrs:
        return []

    if len(vqrs) < MIN_VQRS_FOR_SAMPLING:
        batch_pct = 1.0
    batch_size = max(1, math.ceil(len(vqrs) * batch_pct))
    batch_size = min(batch_size, len(vqrs))  # Can't sample more than we have

    # Split by difficulty
    passing = [v for v in vqrs if v.get("previously_passed", True)]
    failing = [v for v in vqrs if not v.get("previously_passed", True)]

    # Get previous batch for rotation
    prev_batch = get_previous_batch(state, generation)

    # Prefer VQRs NOT in previous batch (rotation)
    def prioritize_rotation(pool: list[dict]) -> list[dict]:
        fresh = [v for v in pool if v["question"] not in prev_batch]
        stale = [v for v in pool if v["question"] in prev_batch]
        return fresh + stale  # Fresh items first

    passing = prioritize_rotation(passing)
    failing = prioritize_rotation(failing)

    # Allocate proportionally, ensuring representation from both pools
    if passing and failing:
        # Ensure at least 1 from each pool, then allocate rest proportionally
        fail_ratio = len(failing) / len(vqrs)
        fail_count = max(1, round(batch_size * fail_ratio))
        pass_count = batch_size - fail_count
        # Ensure pass_count is at least 1 if passing pool exists
        if pass_count < 1:
            pass_count = 1
            fail_count = batch_size - 1
    elif failing:
        fail_count = batch_size
        pass_count = 0
    else:
        pass_count = batch_size
        fail_count = 0

    # Sample from each pool
    selected_passing = passing[:pass_count]
    selected_failing = failing[:fail_count]

    # If we didn't get enough, backfill from the other pool
    selected = selected_passing + selected_failing
    if len(selected) < batch_size:
        remaining = [v for v in vqrs if v["question"] not in {s["question"] for s in selected}]
        needed = batch_size - len(selected)
        selected.extend(remaining[:needed])

    # Shuffle to avoid order bias
    random.shuffle(selected)

    return [v["question"] for v in selected]


def main():
    parser = argparse.ArgumentParser(description="GEPA Stratified Mini-Batch Sampling")
    parser.add_argument("database", nargs="?", help="Database name (for reference)")
    parser.add_argument("schema", nargs="?", help="Schema name (for reference)")
    parser.add_argument("sv_name", nargs="?", help="Semantic view name (for reference)")
    parser.add_argument("--from-stdin", action="store_true", help="Read VQR JSON from stdin")
    parser.add_argument("--from-file", help="Read VQR JSON from file")
    parser.add_argument("--batch-pct", type=float, default=0.30, help="Batch percentage (0.20-0.50)")
    parser.add_argument("--generation", type=int, help="Current generation number (required unless --holdout-pct)")
    parser.add_argument("--history-file", help="Path to gepa_state.json (required unless --holdout-pct)")
    parser.add_argument("--holdout-pct", type=float, help="Print a deterministic {train, holdout} split of the input questions and exit")
    parser.add_argument("--emit-eval-yaml", metavar="CANDIDATE_FQN", help="Print evaluation YAML for this candidate instead of the question list")
    parser.add_argument("--reuse-questions", metavar="FILE", help="With --emit-eval-yaml: use this saved question list instead of sampling")
    parser.add_argument("--metric-version", default="v3", help="Pinned sql_correctness version")
    parser.add_argument("--seed", type=int, help="Random seed for reproducibility")
    args = parser.parse_args()

    if args.holdout_pct is None and (args.generation is None or not args.history_file):
        print("Error: --generation and --history-file are required", file=sys.stderr)
        sys.exit(1)
    if args.holdout_pct is not None and not 0.1 <= args.holdout_pct <= 0.5:
        print("Error: --holdout-pct must be between 0.1 and 0.5", file=sys.stderr)
        sys.exit(1)

    # Validate batch-pct
    if args.batch_pct < 0.10 or args.batch_pct > 1.0:
        print("Error: --batch-pct must be between 0.10 and 1.0", file=sys.stderr)
        sys.exit(1)

    if args.seed is not None:
        random.seed(args.seed)

    if args.reuse_questions:
        if not args.emit_eval_yaml:
            print("Error: --reuse-questions requires --emit-eval-yaml", file=sys.stderr)
            sys.exit(1)
        saved = json.loads(Path(args.reuse_questions).read_text())
        print(render_eval_config(args.emit_eval_yaml, saved, args.metric_version), end="")
        return

    # Read VQR input
    if args.from_stdin or (not args.from_file and not sys.stdin.isatty()):
        vqr_data = sys.stdin.read()
    elif args.from_file:
        with open(args.from_file) as f:
            vqr_data = f.read()
    else:
        print(
            "Error: Provide VQR data via --from-stdin, --from-file, or pipe to stdin.\n"
            "Expected format: [{\"question\": \"...\", \"previously_passed\": true/false}, ...]",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        vqrs = json.loads(vqr_data)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON input: {e}", file=sys.stderr)
        sys.exit(1)

    if not isinstance(vqrs, list):
        print("Error: Input must be a JSON array of VQR objects", file=sys.stderr)
        sys.exit(1)

    if args.holdout_pct is not None:
        print(json.dumps(split_holdout(vqrs, args.holdout_pct), indent=2))
        return

    # Normalize: if input is just strings, wrap them
    normalized_vqrs = []
    for item in vqrs:
        if isinstance(item, str):
            normalized_vqrs.append({"question": item, "previously_passed": True})
        elif isinstance(item, dict) and "question" in item:
            normalized_vqrs.append(item)
        else:
            print(f"Warning: Skipping malformed VQR entry: {item}", file=sys.stderr)

    # Load state for history
    state = load_state(args.history_file)

    # Perform sampling
    selected = stratified_sample(normalized_vqrs, args.batch_pct, args.generation, state)

    # Record in batch history
    if "batch_history" not in state:
        state["batch_history"] = []
    state["batch_history"].append({
        "generation": args.generation,
        "questions": selected,
        "batch_size": len(selected),
        "total_vqrs": len(normalized_vqrs),
    })
    save_state(args.history_file, state)

    if args.emit_eval_yaml:
        print(render_eval_config(args.emit_eval_yaml, selected, args.metric_version), end="")
    else:
        print(json.dumps(selected, indent=2))


if __name__ == "__main__":
    main()

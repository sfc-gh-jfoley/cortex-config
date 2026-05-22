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

Output: JSON list of selected VQR question strings to stdout.

Run with: uvx --with pyyaml python scripts/sample_batch.py
"""

import argparse
import json
import math
import random
import sys
from pathlib import Path

import yaml


def load_state(state_path: str) -> dict:
    """Load GEPA state from YAML file."""
    path = Path(state_path)
    if not path.exists():
        return {"batch_history": []}
    with open(path) as f:
        return yaml.safe_load(f) or {"batch_history": []}


def save_state(state_path: str, state: dict) -> None:
    """Save GEPA state to YAML file."""
    with open(state_path, "w") as f:
        yaml.dump(state, f, default_flow_style=False, sort_keys=False)


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
    parser.add_argument("--generation", type=int, required=True, help="Current generation number")
    parser.add_argument("--history-file", required=True, help="Path to gepa_state.yaml")
    parser.add_argument("--seed", type=int, help="Random seed for reproducibility")
    args = parser.parse_args()

    # Validate batch-pct
    if args.batch_pct < 0.10 or args.batch_pct > 1.0:
        print("Error: --batch-pct must be between 0.10 and 1.0", file=sys.stderr)
        sys.exit(1)

    if args.seed is not None:
        random.seed(args.seed)

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

    # Output selected VQR questions
    print(json.dumps(selected, indent=2))


if __name__ == "__main__":
    main()

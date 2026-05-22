"""Tournament selection for GEPA — binary tournament with elitism."""

import argparse
import json
import random
import sys
from collections import Counter
from pathlib import Path

import yaml


def run_tournament(population: list[dict], scores: dict) -> tuple[list[dict], list[dict]]:
    """Binary tournament selection.

    Pairs candidates randomly, the higher-fitness candidate in each pair wins.
    Odd populations: the unpaired candidate gets a bye (survives automatically).

    Args:
        population: list of candidate dicts with at least 'id' field
        scores: {candidate_id: {"EVAL_AGG_SCORE": float, ...}}

    Returns:
        (winners, losers) — each a list of candidate dicts
    """
    def fitness(cand_id: str) -> float:
        s = scores.get(cand_id, {})
        return s.get("EVAL_AGG_SCORE", 0.0)

    shuffled = list(population)
    random.shuffle(shuffled)

    winners = []
    losers = []

    # Binary tournament: pair off candidates
    for i in range(0, len(shuffled) - 1, 2):
        a, b = shuffled[i], shuffled[i + 1]
        if fitness(a["id"]) >= fitness(b["id"]):
            winners.append(a)
            losers.append(b)
        else:
            winners.append(b)
            losers.append(a)

    # Odd candidate gets a bye
    if len(shuffled) % 2 == 1:
        winners.append(shuffled[-1])

    return winners, losers


def apply_elitism(winners: list[dict], losers: list[dict],
                  best_candidate: dict, scores: dict) -> tuple[list[dict], list[dict]]:
    """Ensure the all-time best candidate survives regardless of tournament.

    If best_candidate was eliminated, swap it back in (replacing worst winner).
    """
    best_id = best_candidate["id"]

    # Check if best is already in winners
    winner_ids = {w["id"] for w in winners}
    if best_id in winner_ids:
        return winners, losers

    # Check if best is in current population at all
    loser_ids = {l["id"] for l in losers}
    if best_id not in loser_ids:
        return winners, losers  # Best wasn't in tournament (e.g., baseline)

    # Find best in losers
    best_entry = None
    for l in losers:
        if l["id"] == best_id:
            best_entry = l
            break

    if best_entry is None:
        return winners, losers

    # Swap: remove best from losers, replace worst winner
    def fitness(cand_id: str) -> float:
        return scores.get(cand_id, {}).get("EVAL_AGG_SCORE", 0.0)

    worst_winner = min(winners, key=lambda w: fitness(w["id"]))
    losers.remove(best_entry)
    losers.append(worst_winner)
    winners.remove(worst_winner)
    winners.append(best_entry)

    return winners, losers


def check_diversity(population: list[dict]) -> bool:
    """Check population diversity — no single lineage dominates >50%.

    Lineage is tracked via parent_id. If >50% share the same root ancestor,
    diversity is too low.
    """
    if len(population) <= 2:
        return True

    # Count root parents (use parent_id, or id if no parent)
    roots = []
    for cand in population:
        root = cand.get("parent_id") or cand["id"]
        roots.append(root)

    counter = Counter(roots)
    most_common_count = counter.most_common(1)[0][1]
    return most_common_count / len(population) <= 0.5


def fill_population(winners: list[dict], pop_size: int,
                    generation: int) -> list[dict]:
    """Create new candidate metadata to fill population back to pop_size.

    These are placeholders — actual file mutations are done by mutate.py.
    Assigns each new candidate a parent from winners (round-robin).
    """
    if not winners:
        return []

    new_candidates = []
    slots_to_fill = pop_size - len(winners)

    for i in range(slots_to_fill):
        parent = winners[i % len(winners)]
        new_id = f"gen{generation}_cand{i}"
        new_candidates.append({
            "id": new_id,
            "parent_id": parent["id"],
            "mutations_applied": [],  # Filled by mutate.py later
            "generation_born": generation,
            "last_fitness": None,
            "file_dir": None,  # Set by mutate.py prepare step
        })

    return new_candidates


def main():
    parser = argparse.ArgumentParser(description="GEPA tournament selection")
    parser.add_argument("scores_json", help="Path to scores JSON file (or - for stdin)")
    parser.add_argument("state_path", help="Path to gepa_state.yaml")
    parser.add_argument("--generation", type=int, default=None,
                        help="Generation number (for fill_population)")
    parser.add_argument("--seed", type=int, default=None,
                        help="Random seed for reproducibility")

    args = parser.parse_args()

    # Set seed
    if args.seed is not None:
        random.seed(args.seed)

    # Load scores
    if args.scores_json == "-":
        scores = json.load(sys.stdin)
    else:
        with open(args.scores_json, "r") as f:
            scores = json.load(f)

    # Load state
    state_path = Path(args.state_path)
    if not state_path.exists():
        print(json.dumps({"error": "state file not found"}))
        sys.exit(1)

    with state_path.open("r") as f:
        state = yaml.safe_load(f)

    population = state.get("population", [])
    best_candidate = state.get("best_candidate", {"id": "baseline", "fitness": 0.0})
    pop_size = state.get("population_size", 6)
    generation = args.generation or state.get("current_generation", 0) + 1

    # Run tournament
    winners, losers = run_tournament(population, scores)

    # Apply elitism
    winners, losers = apply_elitism(winners, losers, best_candidate, scores)

    # Check diversity
    diverse = check_diversity(winners)

    # Fill population
    new_candidates = fill_population(winners, pop_size, generation)

    # Output results
    result = {
        "winners": winners,
        "losers": losers,
        "new_candidates": new_candidates,
        "diversity_ok": diverse,
        "generation": generation,
    }

    print(json.dumps(result, default=str))
    print(f"[tournament] {len(winners)} winners, {len(losers)} eliminated, "
          f"{len(new_candidates)} new slots, diverse={diverse}", file=sys.stderr)


if __name__ == "__main__":
    main()

# Tournament Rules

Tournament selection mechanics for GEPA evolutionary optimization.

## Core Algorithm

After each generation's evaluation, tournament selection determines which candidates survive and which are eliminated.

### Selection Process

1. **Score all candidates** — Each candidate gets a `sql_correctness` mean score from evaluation
2. **Rank by score** — Sort candidates descending by fitness
3. **Split at midpoint** — Top half = winners, bottom half = losers
4. **Apply elitism** — Best candidate always survives (even on ties)
5. **Apply diversity** — Deduplicate identical mutations
6. **Update weights** — Adjust operator probabilities based on outcomes

## Detailed Rules

### Ranking

```
Input: {cand_1: 0.75, cand_2: 0.60, cand_3: 0.82, cand_4: 0.55, cand_5: 0.70, cand_6: 0.68}
Ranked: [cand_3(0.82), cand_1(0.75), cand_5(0.70), cand_6(0.68), cand_2(0.60), cand_4(0.55)]
Midpoint: 3 (population_size / 2)
Winners: [cand_3, cand_1, cand_5]
Losers:  [cand_6, cand_2, cand_4]
```

### Elitism

The best candidate (highest fitness) **always** survives to the next generation:

- If the best is already in winners: no action needed
- If tied scores at midpoint: the tied candidate in the upper half wins
- Purpose: prevent regression — best-so-far is never lost

### Diversity Enforcement

If two candidates in the winners pool have **identical mutation descriptions**, keep only the higher-scoring one:

```
Example:
  cand_1: "add_synonym on REVENUE" → score 0.75
  cand_5: "add_synonym on REVENUE" → score 0.70

Result: Keep cand_1, demote cand_5 to losers
```

This prevents the population from converging on a single mutation strategy too quickly.

### Operator Weight Adaptation

After each tournament, operator weights are updated based on which operators produced winners vs losers:

| Outcome | Weight Change | Minimum |
|---------|---------------|---------|
| Winner's operator | +0.02 | — |
| Loser's operator | -0.01 | 0.02 (floor) |

**Normalization:** After adjustments, all weights are normalized to sum to 1.0.

**Example:**

Before tournament:
```yaml
operator_weights:
  add_synonym: 0.12
  improve_description: 0.12
  add_filter: 0.10
```

Tournament result: `add_synonym` candidate won, `add_filter` candidate lost.

After adjustment:
```
add_synonym: 0.12 + 0.02 = 0.14
add_filter: 0.10 - 0.01 = 0.09
(normalize to sum = 1.0)
```

**Rationale:** This creates an explore-exploit balance. Successful operators are tried more often, but the floor (0.02) ensures no operator is completely abandoned.

## Convergence Tracking

After tournament:

1. Compare current generation's best score to `best_fitness`
2. If improved: update `best_fitness`, reset `convergence_counter = 0`
3. If not improved: increment `convergence_counter += 1`

## Edge Cases

### Odd Population Size

If population size is odd (e.g., 5):
- `midpoint = 5 // 2 = 2`
- Winners: top 2
- Losers: bottom 3

### All Candidates Score Identically

If all scores are equal:
- Random selection for winners/losers (order from sorted is arbitrary)
- No weight adjustment (all operators equally unsuccessful)
- Convergence counter increments (no improvement)
- May trigger population collapse stop condition

### Single Candidate

If only 1 candidate was evaluated (others failed):
- That candidate is automatically the winner
- No losers, no weight adjustment
- Check against baseline for convergence

### Candidate Evaluation Failure

If a candidate fails to evaluate (DDL error, timeout):
- Assign fitness = 0.0 (worst possible)
- It will be ranked last and eliminated
- Its operator gets the -0.01 penalty

## Output Format

The `tournament.py` script outputs:

```json
{
  "winners": ["cand_3", "cand_1", "cand_5"],
  "losers": ["cand_6", "cand_2", "cand_4"],
  "best_fitness": 0.82,
  "converged": false
}
```

Fields:
- `winners`: IDs of candidates surviving to inform next generation
- `losers`: IDs of eliminated candidates
- `best_fitness`: Updated best score (may be unchanged)
- `converged`: Whether any stop condition was triggered

## Next Generation

After tournament:

1. Remove losers from population (`population_state.py remove-candidates`)
2. For each winner, generate a new candidate via mutation (`mutate.py`)
3. New candidates inherit the winner's DDL as their starting point
4. Evaluate new candidates against mini-batch VQRs
5. Run next tournament

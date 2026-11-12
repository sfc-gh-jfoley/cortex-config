# Tournament Rules

Implemented by `scripts/tournament.py`; weight math lives in `scripts/population_state.py` (`apply_weight_update`).

## Selection

1. Scores are `sql_correctness` means for one generation, all from the same question batch and the same pinned metric version. `tournament.py` requires `--metric-version` and exits non-zero if it differs from the version pinned at init.
2. Rank descending. Winners are the top `len // 2` (at least 1); the rest are losers.
3. Ties are broken by input order (sort is stable). There is no separate elitism or deduplication step.
4. Candidate evaluation failure: score 0.0.

## Operator weights

Each candidate's change is scaled by its score delta against its reference (its parent's fitness if known, else the baseline):

| Outcome | Change | Cap |
|---|---|---|
| Winner | `+0.5 * max(delta, 0)` | +0.10 |
| Loser | `-0.25 * max(-delta, 0)` | -0.05 |

Weights are floored at 0.02 and normalized to sum to 1. A winner that did not beat its reference gets no boost. The operator comes from the candidate's stored `operator` field, matched exactly (never by substring).

## Convergence and best candidate

If the generation best beats `best_fitness`, update it, reset `convergence_counter` and record `best_candidate_fqn`; otherwise increment the counter. This is a ranking heuristic on noisy single runs over different batches. The winner for promotion is chosen only by `population_state.py finalize` after at least two runs per finalist on one question list.

## Output

`winners`, `losers`, `best_fitness`, `gen_best_fitness`, `convergence_counter`, `converged`, `best_candidate_fqn`.

## Next generation

Remove losers from state (`remove-candidates`; their views are dropped only through `SV-CANDIDATE-CLEANUP`), mutate winners into new candidates with fresh candidate names, evaluate on the next batch, repeat.

# Convergence Criteria

Where each rule is implemented: `scripts/tournament.py` (`check_convergence`) and `scripts/population_state.py` (`get-status`).

| Rule | Condition | Where |
|---|---|---|
| Counter | `convergence_counter >= convergence_threshold` (default 3 generations without a new best) | tournament, get-status |
| Max generations | `current_generation >= max_generations` (default 10) | tournament, get-status |
| Early stop | Generation 1 best is more than 0.10 (absolute) above `baseline_fitness` | tournament |
| Collapse | `get-status` only: at least 2 evaluated candidates within 0.02 of each other | get-status |

There is no automatic "no improvement over baseline" failure stop. After the loop, `finalize` and the accept rule in the skill (mean beats production by at least 0.02 on one question list, no new regressions) decide the outcome; if nothing beats production, report that and review the question set before another run.

The counter compares generation bests measured on different mini-batches, so treat it as a heuristic. Scores are only comparable within one metric version; the state pins `metric_version` and rejects others.

| Parameter | Default |
|---|---|
| `max_generations` | 10 |
| `convergence_threshold` | 3 |
| `population_size` | 6 |
| `mini_batch_pct` | 0.30 |

State fields: `current_generation`, `convergence_counter`, `convergence_threshold`, `max_generations`, `baseline_fitness`, `best_fitness`, `best_candidate_fqn`, `metric_version`.

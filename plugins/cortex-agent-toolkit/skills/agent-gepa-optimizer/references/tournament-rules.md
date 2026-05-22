# GEPA Tournament Rules

Selection mechanism for choosing winners and losers from the candidate population each generation. Uses binary tournament selection with elitism to balance exploration (trying new mutations) with exploitation (keeping what works).

## Tournament Structure

### Binary Tournament (Size = 2)

Each tournament round:
1. **Random pairing** — shuffle population, pair candidates sequentially (1v2, 3v4, 5v6 for pop_size=6)
2. **Compare fitness** — each candidate's fitness = mean `answer_correctness` across all mini-batch questions
3. **Winner advances** — higher fitness candidate survives to next generation
4. **Loser eliminated** — removed from population, slot filled by mutated offspring of a winner

### Fitness Metric

| Priority | Metric | Source | Usage |
|----------|--------|--------|-------|
| Primary | `answer_correctness` | Mean across mini-batch eval | Tournament comparison |
| Secondary | `logical_consistency` | Mean across mini-batch eval | Tiebreaker only |

**Fitness calculation:**
```
fitness(candidate) = mean(answer_correctness scores across all mini-batch questions)
```

For runs_per_split=1 (mini-batch default), this is a single eval run's mean score. For full validation (Phase 4), use the configured runs_per_split from metadata.yaml and average across runs.

## Elitism

**Top-1 elitism:** The single highest-fitness candidate in the population ALWAYS survives to the next generation, regardless of tournament outcome.

- If the elite candidate wins its tournament: normal advancement (no special handling)
- If the elite candidate loses its tournament: override — elite survives anyway, loser is still eliminated
- Effect: the best-known solution is never lost to random pairing luck

**Elite mutation:** The elite candidate is NOT mutated when carried forward. It enters the next generation unchanged. This preserves the current best while the rest of the population explores.

## Tie-Breaking Rules

When two candidates have identical primary fitness (answer_correctness):

1. **Secondary metric:** Compare mean `logical_consistency` — higher wins
2. **Mutation count (Occam's razor):** If still tied, prefer the candidate with fewer total mutations applied since baseline. Simpler instructions are preferred when performance is equal.
3. **Age (older wins):** If still tied after mutation count, prefer the candidate that has survived more generations (more proven across different mini-batches).
4. **Random:** If all tiebreakers are equal, random coin flip.

## Population Replacement

After all tournaments in a generation are resolved:

1. **Identify survivors** — winners + elite candidate (deduplicated)
2. **Count empty slots** — `pop_size - len(survivors)`
3. **Fill slots via mutation:**
   - Select a survivor (weighted random by fitness rank — fitter candidates more likely to be parents)
   - Clone the survivor's instruction files
   - Apply 1-2 mutations (selected via operator weights from gepa-mutation-operators.md)
   - New candidate = mutated clone
4. **Assign IDs** — new candidates get fresh IDs: `CAND_{generation}_{slot}`

**Example (pop_size=6):**
- 3 tournaments produce 3 winners
- Elite is one of the winners (no duplicate)
- 3 empty slots filled by mutating clones of winners
- Next generation: 3 original winners + 3 new mutated offspring = 6

## Diversity Maintenance

**Problem:** Without diversity pressure, the population converges to clones of the elite — all candidates become minor variations of the same instruction set, reducing exploration.

**Detection:** After replacement, check parent lineage:
```
if count(candidates sharing same original_parent) > ceil(pop_size * 0.5):
    diversity_alert = True
```

**Intervention (when diversity_alert = True):**
1. Identify the 1-2 lowest-fitness candidates in the new population
2. Replace them with **random-restart candidates**: fresh mutations applied directly to the BASELINE instructions (not to any evolved candidate)
3. Random-restart candidates use 2 mutations (instead of the usual 1-2) to differentiate them further from the baseline

**Lineage tracking:** Each candidate records `original_parent` (the generation-0 candidate it descends from) in gepa_state.yaml. Random-restart candidates get a new unique `original_parent` ID.

## Generation Lifecycle

```
Generation N:
  1. Deploy all pop_size candidates as temporary agents
  2. Fire mini-batch eval for each candidate (runs_per_split=1)
  3. Poll until all evals complete
  4. Collect fitness scores
  5. Run tournaments (binary, with elitism)
  6. Replace losers with mutated offspring of winners
  7. Check diversity, inject random-restarts if needed
  8. Update operator weights based on winner/loser mutations
  9. Check convergence criteria (see gepa-convergence-criteria.md)
  10. If not converged: increment generation, goto 1
      If converged: proceed to Phase 4 (full validation)
```

## Baseline Comparison

Every candidate's fitness is also compared against the **baseline fitness** (the original agent's score, computed once at GEPA initialization):

- Candidates scoring BELOW baseline are flagged but NOT automatically eliminated (they may recover via mutation in the next generation)
- If ALL candidates score below baseline for 2 consecutive generations → trigger failure mode (see gepa-convergence-criteria.md)
- The baseline score is stored in gepa_state.yaml as `baseline_fitness` and never updated during GEPA execution

## Summary

| Parameter | Value | Notes |
|-----------|-------|-------|
| Tournament size | 2 (binary) | Fixed, not configurable |
| Elitism | Top-1 | Best candidate always survives unmutated |
| Primary fitness | answer_correctness (mean) | From mini-batch eval |
| Tiebreaker order | logical_consistency → mutation count → age → random | In priority order |
| Diversity threshold | >50% same lineage | Triggers random-restart injection |
| Random-restart count | 1-2 per intervention | Replace lowest-fitness candidates |
| Mutations per offspring | 1-2 | Selected via operator weights |

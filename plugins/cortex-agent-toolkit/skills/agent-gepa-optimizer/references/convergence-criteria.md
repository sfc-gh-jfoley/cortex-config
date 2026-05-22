# GEPA Convergence Criteria

Rules for determining when the evolutionary search should stop. Multiple stopping conditions exist to handle different scenarios — from successful convergence to outright failure.

## Stopping Conditions

### 1. Fitness Plateau (Primary Stop)

```
IF convergence_counter >= 3:
    STOP → promote winner to Phase 4 validation
```

**Definition:** `convergence_counter` increments when the best fitness in the population does not improve between consecutive generations. It resets to 0 whenever a new best fitness is observed.

```
best_fitness_gen_N > best_fitness_gen_N-1  →  convergence_counter = 0
best_fitness_gen_N <= best_fitness_gen_N-1  →  convergence_counter += 1
```

**Rationale:** 3 consecutive generations without improvement indicates the mutation operators cannot find better solutions in the current search neighborhood. Further generations waste eval budget.

---

### 2. Maximum Generations (Hard Stop)

```
IF current_generation >= max_generations:
    STOP → promote best candidate to Phase 4 validation
```

**Default:** `max_generations = 10` (configurable in gepa_state.yaml)

**Rationale:** Upper bound prevents runaway GEPA sessions. Even without convergence, 10 generations of evolution with pop_size=6 explores 60+ candidate variants — sufficient for instruction-level optimization.

---

### 3. Population Collapse

```
IF max(population_fitness) - min(population_fitness) < 0.02:
    STOP → promote best candidate to Phase 4 validation
```

**Definition:** All candidates score within 2 percentage points of each other. The population has lost diversity — all candidates are effectively equivalent.

**Rationale:** When all candidates perform similarly, tournament selection becomes random and mutations cannot create meaningful differentiation. Further evolution is unproductive.

---

### 4. Mean Improvement Stall

```
IF mean_improvement_last_2_gens < 0.01:
    STOP → promote best candidate to Phase 4 validation
```

**Calculation:**
```
mean_pop_fitness_gen_N = mean(fitness across all pop_size candidates)
mean_pop_fitness_gen_N-2 = mean(fitness from 2 generations ago)
mean_improvement_last_2_gens = (mean_pop_fitness_gen_N - mean_pop_fitness_gen_N-2) / 2
```

**Rationale:** Even if the best candidate occasionally improves, if the overall population mean isn't rising, the evolutionary process isn't making systematic progress. Different from fitness plateau (#1) which only tracks the single best candidate.

**Minimum generations:** Only applies after generation 3 (need 2 generations of history to compute).

---

### 5. Early Termination (Success Shortcut)

```
IF generation == 1 AND best_fitness > baseline_fitness * 1.10:
    STOP → skip remaining generations, go directly to Phase 4 validation
```

**Definition:** If the very first generation produces a candidate that exceeds the baseline by more than 10%, the optimization problem was likely "easy" (e.g., missing retry logic, obvious buggy example). No need to explore further.

**Rationale:** Avoids wasting 9 more generations when a simple mutation already achieved significant improvement. The 10% threshold ensures this isn't triggered by noise (mini-batch variance is typically 2-5%).

---

### 6. Failure Mode (No Improvement Possible)

```
IF generation >= 3 AND no_candidate_ever_beat_baseline:
    STOP → report failure, do NOT proceed to Phase 4
```

**Definition:** After 3 full generations of evolution, no single candidate in any generation has achieved fitness higher than the baseline. This means:
- 3 generations × pop_size=6 = 18 evaluated candidates
- None outperformed the original agent
- The mutation operators cannot improve this agent via instruction changes alone

**Output on failure:**
```
GEPA STOPPED: No candidate exceeded baseline fitness after {N} generations.
Baseline fitness: {baseline_fitness}
Best candidate fitness: {best_ever_fitness}
Recommendation: Instruction-level optimization unlikely to help. Consider:
  - Architectural changes (different tools, guardrails)
  - Data quality improvements (eval questions may be ambiguous)
  - Model upgrade (current model may be at capability limit)
```

**Rationale:** Aligns with optimization-patterns.md #12 — know when to stop. If 18+ instruction variants all fail, the problem is not instruction-solvable.

---

## Convergence State Tracking

All convergence state lives in `gepa_state.yaml` at the top level:

```yaml
# Top-level fields (flat, not nested)
current_generation: 3
convergence_counter: 2              # generations without best improvement
baseline_fitness: 0.780             # original agent's fitness (immutable)
max_generations: 10                 # configurable hard stop
mean_fitness_history:               # per-generation population means (appended by add_generation)
  - 0.795  # gen 1
  - 0.812  # gen 2
  - 0.818  # gen 3
best_candidate:
  id: "cand_4"
  fitness: 0.847                    # highest fitness seen across all gens
  mutations: ["add_routing_rule", "fix_example"]
  generation_born: 2
```

## Decision Flow

```
After each generation's tournament completes:

1. Update best_fitness_current_gen
2. Check Early Termination (#5) — if gen==1 and >10% above baseline → STOP (success)
3. Check Failure Mode (#6) — if gen>=3 and never beat baseline → STOP (failure)
4. Check Population Collapse (#3) — if spread < 2% → STOP (converged)
5. Check Fitness Plateau (#1) — if convergence_counter >= 3 → STOP (converged)
6. Check Mean Improvement Stall (#4) — if gen>=3 and <1% mean gain → STOP (converged)
7. Check Max Generations (#2) — if gen >= max_generations → STOP (hard limit)
8. None triggered → continue to next generation
```

**Priority:** Checks are evaluated in the order above. First matching condition determines the stop reason logged in gepa_state.yaml.

## Post-Convergence Actions

On successful convergence (conditions 1-5):
1. Log stop reason and final generation number to `gepa_state.yaml`
2. Identify winner: candidate with `best_fitness_ever` (may not be from the final generation — elitism preserves it)
3. Proceed to Phase 4: full DEV validation with `runs_per_split` from metadata.yaml
4. If Phase 4 confirms improvement → accept (hand off to review/SKILL.md accept flow)
5. If Phase 4 shows regression on full set → reject (the mini-batch signal was misleading)

On failure (condition 6):
1. Log failure to `optimization_log.md` with `[GEPA FAILED]` tag
2. Clean up: DROP all candidate agents, remove gepa_population/ directory
3. Do NOT modify the original agent instructions
4. Report failure to user with recommendations

## Summary

| Condition | Threshold | Action | Min Generation |
|-----------|-----------|--------|---------------|
| Fitness plateau | 3 gens no improvement | Promote winner → Phase 4 | Any |
| Max generations | 10 (configurable) | Promote best → Phase 4 | 10 |
| Population collapse | <2% spread | Promote best → Phase 4 | Any |
| Mean stall | <1% gain over 2 gens | Promote best → Phase 4 | 3 |
| Early termination | >10% above baseline in gen 1 | Skip to Phase 4 | 1 |
| Failure mode | Never beat baseline after 3 gens | STOP, report failure | 3 |

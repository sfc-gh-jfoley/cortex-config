# Convergence Criteria

Stop conditions for GEPA evolutionary optimization. These determine when the optimization loop should terminate.

## Stop Conditions

### 1. Convergence Counter Threshold

```
convergence_counter >= convergence_threshold (default: 3)
```

**What it means:** The best fitness score has not improved for N consecutive generations.

**Behavior:**
- `convergence_counter` increments each generation where `best_fitness` doesn't improve
- Resets to 0 whenever a new best fitness is achieved
- Default threshold: 3 generations without improvement

**Result status:** `CONVERGED` — optimization has plateaued, current best is likely near-optimal.

---

### 2. Maximum Generations

```
current_generation >= max_generations (default: 10)
```

**What it means:** The optimization has run for the maximum allowed number of generations.

**Behavior:**
- Hard cap to prevent runaway optimization
- Default: 10 generations
- Configurable per run (higher for complex SVs, lower for simple ones)

**Result status:** `MAX_GENERATIONS_REACHED` — may or may not have converged. Report final best.

---

### 3. Population Collapse

```
max(scores) - min(scores) < 0.02 (all candidates within 2%)
```

**What it means:** All candidates in the current generation have nearly identical fitness scores.

**Behavior:**
- Checked after tournament scoring
- Requires at least 2 evaluated candidates
- Threshold: 2% absolute difference between best and worst

**Result status:** `COLLAPSED` — diversity lost, further evolution unlikely to help.

---

### 4. No Improvement Over Baseline (Failure)

```
current_generation >= 3 AND best_fitness <= baseline_fitness
```

**What it means:** After 3 generations, no candidate has beaten the original (unmutated) SV.

**Behavior:**
- Only triggers after generation 3 (gives mutations time to work)
- Compares against `baseline_fitness` (the original SV's eval score)
- Strictly less-than-or-equal (even matching baseline counts as failure)

**Result status:** `FAILED` — mutations are not helping. Consider:
- Re-evaluating the eval dataset (VQRs may be incorrect)
- Checking if the SV structure has fundamental issues
- Trying a different mutation strategy

---

### 5. Early Termination (Strong Improvement)

```
current_generation == 1 AND best_fitness > baseline_fitness + 0.10
```

**What it means:** A generation-1 candidate exceeds baseline by more than 10 percentage points.

**Behavior:**
- Only checked after generation 1
- Requires >10% improvement (absolute, not relative)
- Immediate termination — the winning mutation is clearly beneficial

**Result status:** `EARLY_CONVERGED` — strong improvement found quickly, apply and move on.

---

## Decision Flow

```
After each generation's tournament:

1. Did any candidate beat baseline + 10% AND gen == 1?
   → YES: EARLY_CONVERGED (stop)
   → NO: continue

2. Is max(scores) - min(scores) < 0.02?
   → YES: COLLAPSED (stop)
   → NO: continue

3. Is current_generation >= max_generations?
   → YES: MAX_GENERATIONS_REACHED (stop)
   → NO: continue

4. Is convergence_counter >= threshold?
   → YES: CONVERGED (stop)
   → NO: continue

5. Is gen >= 3 AND best_fitness <= baseline?
   → YES: FAILED (stop)
   → NO: continue to next generation
```

## Configuration Defaults

| Parameter | Default | Range | Description |
|-----------|---------|-------|-------------|
| `max_generations` | 10 | 3–50 | Hard generation cap |
| `convergence_threshold` | 3 | 2–10 | Generations without improvement before stopping |
| `population_size` | 6 | 4–20 | Candidates per generation |
| `mini_batch_pct` | 0.30 | 0.20–0.50 | Fraction of VQRs evaluated per generation |
| `early_termination_delta` | 0.10 | 0.05–0.20 | Improvement threshold for early stop |
| `collapse_threshold` | 0.02 | 0.01–0.05 | Min spread before declaring collapse |

## State Tracking

The convergence state is tracked in `gepa_state.json`:

```json
{
  "current_generation": 3,
  "convergence_counter": 1,
  "convergence_threshold": 3,
  "max_generations": 10,
  "baseline_fitness": 0.65,
  "best_fitness": 0.78
}
```

Updated after each tournament via `population_state.py` and `tournament.py`.

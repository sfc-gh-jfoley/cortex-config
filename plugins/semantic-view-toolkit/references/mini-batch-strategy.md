# Mini-Batch Strategy

VQR stratification for mini-batch evaluation in GEPA optimization. Evaluates candidates on a subset of verified queries each generation to reduce cost while maintaining signal quality.

## Overview

Full evaluation of all VQRs for every candidate in every generation is expensive. Mini-batch evaluation samples a representative subset, reducing API calls while preserving the ability to detect meaningful fitness differences.

## Configuration

| Parameter | Default | Range | Description |
|-----------|---------|-------|-------------|
| `mini_batch_pct` | 0.30 | 0.20–0.50 | Fraction of VQRs to sample per generation |
| Min batch size | 3 | — | Never sample fewer than 3 VQRs |
| Max batch size | 50 | — | Cap to prevent expensive evaluations |

## Stratification Logic

### Difficulty Categories

VQRs are classified into difficulty tiers based on historical pass/fail data:

| Category | Definition | Sampling Priority |
|----------|-----------|------------------|
| **Previously Failing** | VQR failed in baseline or recent evaluation | HIGH (40% of batch) |
| **Previously Passing** | VQR passed in baseline or recent evaluation | MEDIUM (40% of batch) |
| **Unknown** | No evaluation history (new VQRs) | FILL (remaining 20%) |

### Why Include Passing VQRs?

- **Regression detection:** A mutation that fixes one failure might break a previously-passing query
- **Balanced signal:** If we only test failing VQRs, we can't detect regressions
- **Convergence accuracy:** Final fitness should reflect overall quality, not just failure rate

### Stratification Targets

For a batch of size N:
- ~40% from failing pool (at least `ceil(N * 0.4)` items)
- ~40% from passing pool
- ~20% from unknown pool (if available)

If any pool is exhausted, fill from remaining pools.

## Rotation Rules

### No Consecutive Reuse

The same VQR batch should NOT be used in consecutive generations. This prevents:
- Overfitting to a specific subset of queries
- False convergence (candidate optimized for batch, not general quality)

### Implementation

Track `batch_history` in state file:
```yaml
batch_history:
  - generation: 1
    vqrs: ["What is total revenue?", "How many customers?", ...]
    batch_size: 6
    total_vqrs: 20
  - generation: 2
    vqrs: ["Top 5 products by sales", "Monthly trend", ...]
    batch_size: 6
    total_vqrs: 20
```

When sampling for generation G:
1. Get VQRs used in generation G-1
2. Prefer VQRs NOT in that set
3. If fresh pool is too small, allow up to 30% overlap with previous batch

### Rotation Algorithm

```python
fresh = [v for v in all_vqrs if v not in previous_batch]
stale = [v for v in all_vqrs if v in previous_batch]

# Take from fresh first
selected = sample(fresh, min(batch_size, len(fresh)))

# Fill remaining from stale if needed
if len(selected) < batch_size:
    selected += sample(stale, batch_size - len(selected))
```

## History Tracking

### Per-Generation Record

Each generation's batch selection is recorded with:
- Generation number
- Selected VQR questions
- Batch size
- Total VQR pool size

### Pass/Fail Updates

After evaluation completes, update VQR pass/fail history:
- VQR passed: `passed = True` for future stratification
- VQR failed: `passed = False` for future stratification

This feedback loop ensures failing VQRs get more attention in future batches.

## Noise Acceptance

### 1 Run Per Candidate Per Generation

Unlike some evolutionary approaches that average multiple runs, GEPA uses **1 evaluation run per candidate per generation**.

**Rationale:**
- EXECUTE_AI_EVALUATION is deterministic-ish (same prompt → similar output)
- The primary noise source is batch selection, not evaluation randomness
- Multiple runs would multiply API costs without proportional signal gain
- Batch rotation across generations provides natural variance reduction

### Implication for Fitness Comparison

- Fitness scores are point estimates, not means
- Small differences (< 0.03) between candidates may be noise
- Tournament selection's top-half/bottom-half split naturally accounts for noise (you need to be clearly better, not marginally better)

## Batch Size Guidelines

| Total VQRs | Recommended batch_pct | Resulting Batch Size |
|------------|----------------------|---------------------|
| 5–10 | 0.50 | 3–5 (minimum viable) |
| 10–20 | 0.30 | 3–6 |
| 20–50 | 0.30 | 6–15 |
| 50–100 | 0.25 | 13–25 |
| 100+ | 0.20 | 20–50 (cap at 50) |

## Edge Cases

### Too Few VQRs (< 5)

If the semantic view has fewer than 5 VQRs:
- Use ALL VQRs every generation (no mini-batching)
- Set `mini_batch_pct = 1.0`
- Note: this makes add_vqr operator especially valuable

### All VQRs Passing

If all VQRs pass in baseline:
- Stratification collapses to uniform random sampling
- Focus shifts to regression detection
- Consider adding harder VQRs via add_vqr operator

### No Evaluation History

First generation has no pass/fail history:
- Treat all VQRs as "unknown" category
- Sample uniformly at random
- After Gen 1 evaluation, assign pass/fail for future batches

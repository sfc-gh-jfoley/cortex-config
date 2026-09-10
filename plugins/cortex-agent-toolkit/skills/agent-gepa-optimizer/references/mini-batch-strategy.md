# GEPA Mini-Batch Strategy

Evaluation strategy for GEPA generations. Each generation evaluates candidates on a rotating subset (mini-batch) of the DEV split to reduce cost while maintaining signal quality. Full evaluation is reserved for the final validation phase only.

## Batch Size Calculation

```
batch_size = max(5, ceil(total_dev_questions * 0.30))
```

| DEV Set Size | Batch Size | Coverage per Generation |
|--------------|-----------|----------------------|
| 10 | 5 (floor) | 50% |
| 15 | 5 | 33% |
| 20 | 6 | 30% |
| 30 | 9 | 30% |
| 50 | 15 | 30% |
| 100 | 30 | 30% |

**Rationale:** 30% provides enough signal to distinguish clearly better/worse candidates while keeping eval cost at ~1/3 of full evaluation. The floor of 5 ensures minimum statistical relevance even for tiny DEV sets.

## Stratified Sampling

Mini-batches are stratified by `TEST_CATEGORY` (from the eval table) to ensure each batch is representative of the full question distribution.

**SQL pattern for stratified batch selection:**
```sql
CREATE OR REPLACE VIEW {DB}.{SCHEMA}.GEPA_MINI_BATCH_GEN_{N} AS
SELECT *
FROM {DB}.{SCHEMA}.{EVAL_TABLE}
WHERE SPLIT = 'DEV'
QUALIFY ROW_NUMBER() OVER (
    PARTITION BY TEST_CATEGORY
    ORDER BY UNIFORM(0::FLOAT, 1::FLOAT, RANDOM({seed}))
) <= CEIL(
    {batch_size} * (
        COUNT(*) OVER (PARTITION BY TEST_CATEGORY)
        / COUNT(*) OVER ()
    )
)
```

**Key points:**
- `PARTITION BY TEST_CATEGORY` ensures proportional sampling from each category
- `ORDER BY UNIFORM(...)` with a generation-specific seed provides deterministic randomness
- `RANDOM({seed})` where seed = `generation_number * 1000 + gepa_run_id` — reproducible per generation
- View (NOT temporary) — eval runs execute in a different session and cannot see temporary objects

**Category proportionality:** If DEV has 60% "routing" questions and 40% "formatting" questions, a batch of 10 will contain ~6 routing and ~4 formatting questions.

## Batch Rotation

**Goal:** Cover the full DEV set within 3-4 generations to avoid overfitting to a subset.

**Tracking:** `gepa_state.json` maintains a `used_questions` list:
```yaml
batch_history:
  gen_1: [Q_ID_1, Q_ID_4, Q_ID_7, Q_ID_12, Q_ID_15]
  gen_2: [Q_ID_2, Q_ID_5, Q_ID_8, Q_ID_11, Q_ID_14]
  gen_3: [Q_ID_3, Q_ID_6, Q_ID_9, Q_ID_10, Q_ID_13]
```

**Rotation mechanism:**
1. After batch selection, compare with previous generation's batch
2. If overlap > 80% with the immediately preceding generation → re-sample with a different seed
3. Track cumulative coverage: `covered_questions / total_dev_questions`
4. If coverage < 100% after 4 generations → bias next batch toward uncovered questions by adding a `WHERE QUESTION_ID NOT IN (...)` filter for questions used in the last 2 generations

**Anti-gaming rule:** No exact batch reuse in consecutive generations. At least 20% of questions must differ between generation N and generation N-1. This prevents a candidate from overfitting to a single batch via lucky mutations.

## Implementation Details

### View Naming Convention

```
{DB}.{SCHEMA}.GEPA_MINI_BATCH_GEN_{generation_number}
```

Each generation creates a new view. Previous generation views are dropped during cleanup.

### Eval Configuration

For mini-batch generations:
- **runs_per_split = 1** (single eval run per candidate on the mini-batch)
- **dataset_name pattern:** `{AGENT}_gepa_gen{G}_cand{C}_dev_ds_r1`
- **table_name in YAML config:** points to the mini-batch view

**Rationale for runs_per_split=1:** Mini-batches are inherently noisy due to small sample size. Running multiple times on a small batch adds cost without meaningfully reducing variance — the noise comes from question sampling, not model non-determinism at this scale. Accept the noise during selection; validate rigorously in Phase 4.

### Phase 4 Full Validation (Different Strategy)

When GEPA converges and selects a winner:
- Eval on FULL DEV set (no mini-batch view, use the actual DEV split)
- Use `runs_per_split` from project's `metadata.yaml` (typically 3)
- Compare winner's mean score against baseline's mean score
- Statistical significance: winner must exceed baseline by more than 1 standard deviation of the baseline's run variance

### Dataset Slot Management

Each candidate × run needs a unique dataset slot to avoid version lock collisions:

```
Candidate 1, Run 1: {AGENT}_gepa_gen3_cand1_dev_ds_r1
Candidate 2, Run 1: {AGENT}_gepa_gen3_cand2_dev_ds_r1
...
Candidate 6, Run 1: {AGENT}_gepa_gen3_cand6_dev_ds_r1
```

For pop_size=6 with runs_per_split=1: **6 dataset slots per generation** (not 18). This is the key cost saving from using runs_per_split=1 during selection.

### Cleanup Between Generations

After tournament selection completes for generation N:
1. DROP VIEW `GEPA_MINI_BATCH_GEN_{N}` (no longer needed)
2. DROP AGENT for all eliminated candidates
3. Dataset slots are reusable — version locks clear automatically when eval completes

## Cost Analysis

| Scenario | Eval Calls/Gen | Questions/Gen | Total (10 gens) |
|----------|---------------|---------------|-----------------|
| pop_size=6, runs=1, batch=30% of 50 | 6 | 90 | 900 questions |
| pop_size=6, runs=3, batch=30% of 50 | 18 | 270 | 2,700 questions |
| Full DEV (no mini-batch), runs=3 | 18 | 900 | 9,000 questions |

**Selected approach (row 1)** balances exploration cost against signal quality. Phase 4 validation adds one additional full eval (runs_per_split × full DEV set) to confirm the winner.

## Summary

| Parameter | Value | Notes |
|-----------|-------|-------|
| Batch size | `max(5, ceil(DEV * 0.30))` | 30% of DEV set, minimum 5 |
| Stratification | Proportional by TEST_CATEGORY | Via QUALIFY + ROW_NUMBER |
| Rotation | Full DEV coverage within 3-4 gens | Track in gepa_state.json |
| Anti-gaming | ≥20% different from prior gen | Re-sample if violated |
| runs_per_split (mini-batch) | 1 | Cost control during selection |
| runs_per_split (Phase 4) | From metadata.yaml | Rigorous final validation |
| View type | Permanent (CREATE OR REPLACE VIEW) | Required for cross-session eval |
| Dataset naming | `{AGENT}_gepa_gen{G}_cand{C}_dev_ds_r{N}` | Unique per candidate × run |

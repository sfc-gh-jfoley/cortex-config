# SV Optimization — Setup

> Procedural reference for the `sv-iterative-optimizer` skill. Loaded by the router in `SKILL.md` (SETUP intent). Not independently invokable.

## Purpose

Initialize the optimization workspace for a semantic view before running iterations.
Run this once per SV before using `references/optimize.md`.

---

## Step 1: Collect Target

Ask the user:
```
1. Semantic view to optimize (fully-qualified: DB.SCHEMA.SV_NAME)?
2. Accuracy target (default: 85%)?
3. Repeats per evaluation (default 2, minimum 2). The accept threshold is derived from observed run-to-run variation (below), not fixed.
```

Store as: `SV_FQN`, `ACCURACY_TARGET`, `REPEATS`.

Verify the SV exists:
```sql
SELECT GET_DDL('SEMANTIC_VIEW', '<SV_FQN>');
```

If this fails → report error and stop.

---

## Step 2: Check for Baseline Eval Score

Check if a baseline score exists in EVAL_HISTORY:
```sql
SELECT run_name, mean_score, run_timestamp
FROM <DB>._SV_TOOLKIT_META.EVAL_HISTORY
WHERE source_sv_fqn = '<SV_FQN>' OR sv_fqn = '<SV_FQN>'
  AND metric_version = '<METRIC_VERSION>'  -- never compare scores across metric versions
ORDER BY run_timestamp DESC
LIMIT 1;
```

**If no baseline exists:**
- Report: "No baseline evaluation found for `<SV_FQN>`."
- Offer: "Run sv-evaluation first to establish a baseline score, then return here."
- STOP — optimization requires a baseline.

**If baseline exists:** Record `baseline_score = mean_score` from the most recent row, plus its metric version and question list. If the baseline used a different metric version or question list than this loop will (`sql_correctness` pinned to `v3`, hold-out list below), do not compare against it: re-run the baseline under the loop's settings.

### Step 2b: Fix the eval question list and measure noise

1. Select the hold-out VQR questions (see `SKILL.md`, VQR Split Strategy) and save them as `EVAL_QUESTIONS`.
2. Evaluate the unchanged production SV on `EVAL_QUESTIONS` `REPEATS` times (>=2) with `sql_correctness` v3. Record the per-run means as `BASELINE_RUNS`; `BASELINE_SCORE` = their mean.
3. `NOISE = max(BASELINE_RUNS) - min(BASELINE_RUNS)`. `ACCEPT_THRESHOLD = max(2 * NOISE, 1 / len(EVAL_QUESTIONS))`: a change must beat run-to-run variation and be at least one question's worth.
4. Create the working candidate (kind `cand`) per `references/candidate-promotion.md` section 2 (`candidate.py new-run`, `name`, GET_DDL, `rewrite-ddl`, `register`). Store `RUN`, `CAND_FQN`. All later mutation and evaluation happen on `CAND_FQN`.

---

## Step 3: Create OPTIMIZATION_LOG

> **Note (INTERACTIVE mode only):** When creating `_SV_TOOLKIT_META` objects for the first
> time in INTERACTIVE mode (gate `META-ROLLBACK-CLONE`), offer: "Want me to create a rollback clone first?
> (`CREATE DATABASE <db>_RESTORE CLONE <db>`)"
> In AUTONOMOUS mode, `CREATE SCHEMA/TABLE IF NOT EXISTS` is additive and idempotent
> — no prompt needed.

```sql
-- gate META-SCHEMA-CREATE: additive and idempotent
CREATE SCHEMA IF NOT EXISTS <DB>._SV_TOOLKIT_META;

CREATE TABLE IF NOT EXISTS <DB>._SV_TOOLKIT_META.OPTIMIZATION_LOG (
    ITERATION_ID VARCHAR,
    TIMESTAMP TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP(),
    SV_FQN VARCHAR,
    MUTATION_OPERATOR VARCHAR,
    MUTATION_DESCRIPTION VARCHAR,
    EVAL_SCORE_BEFORE FLOAT,
    EVAL_SCORE_AFTER FLOAT,
    REGRESSIONS INT,
    DECISION VARCHAR,  -- ACCEPTED / REJECTED
    DDL_SNAPSHOT VARCHAR,
    NOTES VARCHAR
);
```

---

## Step 4: Present Setup Summary

```
Optimization Setup Complete
─────────────────────────────────────────
SV:               <SV_FQN>
Baseline Score:   <baseline_score> (<N> VQRs)
Accuracy Target:  <ACCURACY_TARGET>%
Accept Threshold: +<ACCEPT_THRESHOLD> (from noise <NOISE> over <REPEATS> runs)
Candidate:        <CAND_FQN>
Metric:           sql_correctness v3 (pinned)
OPTIMIZATION_LOG: <DB>._SV_TOOLKIT_META.OPTIMIZATION_LOG ✓
─────────────────────────────────────────
Ready to optimize. Run: sv-iterative-optimizer → optimize (references/optimize.md)
```

**STOP GATE (INTERACTIVE mode):** Wait for user confirmation before proceeding. **AUTONOMOUS mode:** proceed straight into the optimize loop (see `SKILL.md` Execution Mode).

---

## Output Variables

| Variable | Value |
|---|---|
| `SV_FQN` | Fully-qualified SV name |
| `BASELINE_SCORE` | Most recent mean_score from EVAL_HISTORY |
| `ACCURACY_TARGET` | User-defined target (default 0.85) |
| `EVAL_QUESTIONS` | Fixed hold-out question list |
| `REPEATS` | Evaluation repeats per state (>=2) |
| `ACCEPT_THRESHOLD` | Derived from observed noise (Step 2b) |
| `RUN`, `CAND_FQN` | Candidate run id and name |
| `OPTIMIZATION_LOG_TABLE` | `<DB>._SV_TOOLKIT_META.OPTIMIZATION_LOG` |

---

## Failure summary format

Defined in `references/eval-data.md` (shared with sv-gepa-optimizer's `--failures-file`).

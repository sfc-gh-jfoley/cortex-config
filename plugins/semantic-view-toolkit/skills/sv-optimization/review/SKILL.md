---
name: sv-optimization-review
description: >
  Review optimization iteration history for a semantic view. Queries OPTIMIZATION_LOG
  to show score trajectory, accepted/rejected mutations, and recommends next action
  (continue iterating, escalate to GEPA, or declare done).
triggers:
  - review optimization results
  - show optimization history
  - accept or reject changes
  - compare scores
  - optimization progress
  - sv iteration history
---

# SV Optimization — Review

## Purpose

Inspect the iteration history in OPTIMIZATION_LOG to understand what mutations were tried,
which were accepted, and whether to continue, escalate to sv-gepa-optimizer, or stop.

---

## Step 1: Load Iteration History

```sql
SELECT
    ITERATION_ID,
    TIMESTAMP,
    MUTATION_OPERATOR,
    MUTATION_DESCRIPTION,
    EVAL_SCORE_BEFORE,
    EVAL_SCORE_AFTER,
    ROUND((EVAL_SCORE_AFTER - EVAL_SCORE_BEFORE) * 100, 2) AS delta_pct,
    REGRESSIONS,
    DECISION,
    NOTES
FROM <DB>._SV_TOOLKIT_META.OPTIMIZATION_LOG
WHERE SV_FQN = '<SV_FQN>'
ORDER BY TIMESTAMP ASC;
```

If 0 rows → "No optimization history found for `<SV_FQN>`. Run setup + optimize first."

---

## Step 2: Compute Score Trajectory

From the query results, derive:
- `iterations_total` — count of rows
- `iterations_accepted` — count where DECISION = 'ACCEPTED'
- `iterations_rejected` — count where DECISION = 'REJECTED'
- `consecutive_rejections` — count of REJECTED rows from the tail of the history
- `score_start` — EVAL_SCORE_BEFORE of the first row
- `score_current` — EVAL_SCORE_AFTER of the most recent ACCEPTED row (or score_start if none)
- `total_improvement` — score_current - score_start

---

## Step 3: Present History Report

```
Optimization History: <SV_FQN>
══════════════════════════════════════════════════════════════
 Iter  │ Operator             │ Before → After  │ Δ%    │ Decision
───────┼──────────────────────┼─────────────────┼───────┼──────────
 1     │ improve_description  │ 0.62 → 0.71     │ +9%   │ ACCEPTED
 2     │ add_synonym          │ 0.71 → 0.70     │ -1%   │ REJECTED
 3     │ add_metric           │ 0.71 → 0.75     │ +4%   │ ACCEPTED
 4     │ add_filter           │ 0.75 → 0.74     │ -1%   │ REJECTED
══════════════════════════════════════════════════════════════
Starting score:   0.62
Current score:    0.75  (+13%)
Target:           0.85  (10% remaining)
Consecutive rejections: 1
```

---

## Step 4: Recommend Next Action

| Condition | Recommendation |
|---|---|
| `score_current >= ACCURACY_TARGET` | **Done** — target reached |
| `consecutive_rejections >= 3` | **Escalate** → sv-gepa-optimizer (local optimum) |
| `consecutive_rejections < 3` | **Continue** → run another optimize iteration |
| `iterations_total >= 10 AND total_improvement < 5%` | **Escalate** → sv-gepa-optimizer (slow convergence) |

Present recommendation:
```
Recommendation: <Continue iterating | Escalate to sv-gepa-optimizer | Done>

Reason: <e.g., "2 consecutive rejections — try a different operator" or "target reached">

Options:
  A) Run another optimize iteration
  B) Escalate to sv-gepa-optimizer (broader population search)
  C) Stop here — accept current accuracy of <score_current>
  D) Manually review and edit SV DDL
```

**STOP GATE (GUIDED mode):** Wait for user selection.

---

## Step 5: Accepted Change Log (Optional Detail)

On request, show DDL snapshots for ACCEPTED iterations:
```sql
SELECT ITERATION_ID, TIMESTAMP, MUTATION_OPERATOR, EVAL_SCORE_AFTER, DDL_SNAPSHOT
FROM <DB>._SV_TOOLKIT_META.OPTIMIZATION_LOG
WHERE SV_FQN = '<SV_FQN>'
  AND DECISION = 'ACCEPTED'
ORDER BY TIMESTAMP ASC;
```

---
name: sv-optimization-setup
description: >
  One-time setup for semantic view iterative optimization. Collects target SV, creates
  _SV_TOOLKIT_META.OPTIMIZATION_LOG if absent, records baseline eval score, and
  configures accept/reject thresholds for the optimization loop.
triggers:
  - set up optimization
  - initialize sv optimization
  - scaffold optimization
  - start optimization
---

# SV Optimization — Setup

## Purpose

Initialize the optimization workspace for a semantic view before running iterations.
Run this once per SV before using `optimize/SKILL.md`.

---

## Step 1: Collect Target

Ask the user:
```
1. Semantic view to optimize (fully-qualified: DB.SCHEMA.SV_NAME)?
2. Accuracy target (default: 85%)?
3. Accept threshold — minimum improvement to accept a mutation (default: 2% absolute)?
```

Store as: `SV_FQN`, `ACCURACY_TARGET`, `ACCEPT_THRESHOLD`.

Verify the SV exists:
```sql
DESCRIBE SEMANTIC VIEW <SV_FQN>;
```

If this fails → report error and stop.

---

## Step 2: Check for Baseline Eval Score

Check if a baseline score exists in EVAL_HISTORY:
```sql
SELECT run_name, mean_score, run_timestamp
FROM <DB>._SV_TOOLKIT_META.EVAL_HISTORY
WHERE sv_fqn = '<SV_FQN>'
ORDER BY run_timestamp DESC
LIMIT 1;
```

**If no baseline exists:**
- Report: "No baseline evaluation found for `<SV_FQN>`."
- Offer: "Run sv-evaluation first to establish a baseline score, then return here."
- STOP — optimization requires a baseline.

**If baseline exists:** Record `baseline_score = mean_score` from the most recent row.

---

## Step 3: Create OPTIMIZATION_LOG

> **DDL/DML safety gate**: Before creating `_SV_TOOLKIT_META` objects ask the user:
> "Want me to create a rollback clone first? (`CREATE DATABASE <db>_RESTORE CLONE <db>`)"
> If yes, create the clone before proceeding.

```sql
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
Accept Threshold: +<ACCEPT_THRESHOLD>% minimum improvement
OPTIMIZATION_LOG: <DB>._SV_TOOLKIT_META.OPTIMIZATION_LOG ✓
─────────────────────────────────────────
Ready to optimize. Run: sv-optimization → optimize
```

**STOP GATE (GUIDED mode):** Wait for user confirmation before proceeding.

---

## Output Variables

| Variable | Value |
|---|---|
| `SV_FQN` | Fully-qualified SV name |
| `BASELINE_SCORE` | Most recent mean_score from EVAL_HISTORY |
| `ACCURACY_TARGET` | User-defined target (default 0.85) |
| `ACCEPT_THRESHOLD` | Minimum improvement to accept (default 0.02) |
| `OPTIMIZATION_LOG_TABLE` | `<DB>._SV_TOOLKIT_META.OPTIMIZATION_LOG` |

---
name: sv-optimization-optimize
description: >
  Run one iteration of semantic view optimization: select a mutation operator based on
  eval failures, apply it to SV DDL, re-evaluate via sv-evaluation, compare against
  baseline, accept or reject, and write the result to OPTIMIZATION_LOG.
triggers:
  - run optimization iteration
  - optimize sv
  - improve sv
  - next iteration
  - fix sv failures
  - apply mutation
---

# SV Optimization — Optimize (One Iteration)

## Prerequisites

Setup phase must be complete (`setup/SKILL.md` has run):
- `SV_FQN`, `BASELINE_SCORE`, `ACCEPT_THRESHOLD`, `OPTIMIZATION_LOG_TABLE` are set
- `_SV_TOOLKIT_META.OPTIMIZATION_LOG` exists

---

## Step 1: Load Current SV State

```sql
-- Get current DDL
DESCRIBE SEMANTIC VIEW <SV_FQN>;
```

Save DDL as `CURRENT_DDL`. Get most recent score as `SCORE_BEFORE`:
```sql
SELECT run_name, mean_score
FROM <DB>._SV_TOOLKIT_META.EVAL_HISTORY
WHERE sv_fqn = '<SV_FQN>'
ORDER BY run_timestamp DESC
LIMIT 1;
```

---

## Step 2: Analyze Recent Failures

Get the most recent eval run name, then query failures:
```sql
SELECT question, generated_sql, reference_sql, sql_correctness, error_message
FROM TABLE(SNOWFLAKE.CORTEX.GET_ANALYST_AI_EVALUATION_DATA('<latest_run_name>'))
WHERE sql_correctness < 1.0
ORDER BY sql_correctness ASC;
```

Map failures to mutation operators using the table in `../SKILL.md` (Mutation Strategy section).
Select the operator that addresses the most common failure pattern.

---

## Step 3: Apply Mutation

Select ONE mutation operator from `references/mutation-operators.md`. Apply it to the SV DDL.

For LLM-assisted mutations (descriptions, synonyms), use CORTEX.COMPLETE:
```sql
-- Read ~/.snowflake/cortex/vault/LLMs.md for current default_agent value — do not hardcode
SELECT SNOWFLAKE.CORTEX.COMPLETE(
    '<default_agent>',
    '<mutation_prompt_from_mutation-operators.md>'
) AS mutated_ddl;
```

For structural mutations (add metric, change relationship), generate DDL changes directly.

Save proposed DDL as `CANDIDATE_DDL`.

**STOP GATE (GUIDED mode):** Show the proposed change and wait for approval:
```
Proposed mutation: <OPERATOR>
Target: <column/relationship being changed>
Change: <before → after>

Apply this change and run evaluation? (yes / skip / different mutation)
```

---

## Step 4: Deploy Candidate

```sql
-- Deploy the mutated SV
CREATE OR REPLACE SEMANTIC VIEW <SV_FQN>
<CANDIDATE_DDL>;
```

If deploy fails → report error, restore original DDL, STOP.

---

## Step 5: Evaluate

Route to `sv-evaluation` to run a fresh evaluation:
- Use all VQRs for a complete signal
- Record run as `EVAL_RUN_NAME`

After eval completes, get score:
```sql
SELECT AVG(sql_correctness) AS score_after,
       SUM(CASE WHEN sql_correctness = 1.0 THEN 1 ELSE 0 END) AS perfect,
       SUM(CASE WHEN sql_correctness = 0.0 THEN 1 ELSE 0 END) AS failed
FROM TABLE(SNOWFLAKE.CORTEX.GET_ANALYST_AI_EVALUATION_DATA('<EVAL_RUN_NAME>'));
```

Store as `SCORE_AFTER`.

---

## Step 6: Accept or Reject

**ACCEPT if:**
- `SCORE_AFTER - SCORE_BEFORE >= ACCEPT_THRESHOLD` (default 0.02)
- No new regressions (previously-passing VQRs did not drop to failing)

**REJECT if:**
- Score improved by less than `ACCEPT_THRESHOLD`
- New regressions detected

**On REJECT:** Restore original DDL:
```sql
CREATE OR REPLACE SEMANTIC VIEW <SV_FQN>
<CURRENT_DDL>;
```

---

## Step 7: Write to OPTIMIZATION_LOG

```sql
INSERT INTO <DB>._SV_TOOLKIT_META.OPTIMIZATION_LOG
    (ITERATION_ID, SV_FQN, MUTATION_OPERATOR, MUTATION_DESCRIPTION,
     EVAL_SCORE_BEFORE, EVAL_SCORE_AFTER, REGRESSIONS, DECISION, DDL_SNAPSHOT, NOTES)
VALUES (
    CONCAT('<SV_NAME>', '_iter_', TO_CHAR(CURRENT_TIMESTAMP(), 'YYYYMMDD_HH24MISS')),
    '<SV_FQN>',
    '<OPERATOR>',
    '<description of what was changed>',
    <SCORE_BEFORE>,
    <SCORE_AFTER>,
    <REGRESSION_COUNT>,
    '<ACCEPTED|REJECTED>',
    '<CANDIDATE_DDL_if_accepted_else_CURRENT_DDL>',
    '<optional notes>'
);
```

---

## Step 8: Report and Next Action

```
Iteration Result
────────────────────────────────
Operator:    <OPERATOR>
Score:       <SCORE_BEFORE> → <SCORE_AFTER> (<delta>%)
Regressions: <N>
Decision:    ACCEPTED / REJECTED
────────────────────────────────
```

Check termination conditions (from `../SKILL.md`):
- Target reached → celebrate and stop
- 3 consecutive rejections → suggest sv-gepa-optimizer
- Otherwise → offer to run another iteration

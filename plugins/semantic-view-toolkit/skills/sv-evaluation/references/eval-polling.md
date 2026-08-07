---
name: sv-eval-polling
description: Polling patterns, config format, and result extraction for EXECUTE_AI_EVALUATION with semantic views.
---

# SV Eval Polling & Results Reference

> **Status as of 2026-08-07:** `EXECUTE_AI_EVALUATION` with `analyst_type: "SEMANTIC VIEW"` works correctly.
> The 392700 error documented in SKILL.md Step 9b was a platform bug fixed between 2026-07-23 and 2026-08-07.
> No workaround required. Use the standard path below.

---

## Eval Config YAML

```yaml
evaluation:
  analyst_params:
    analyst_name: "<DB>.<SCHEMA>.<SV_NAME>"   # MUST be 3-part FQN
    analyst_type: "SEMANTIC VIEW"
  source_metadata:
    type: "verified_queries"
    # Omit verified_queries list to evaluate ALL embedded VQRs.
    # To evaluate a subset, add:
    # verified_queries:
    #   - "Question text 1"
    #   - "Question text 2"

metrics:
  - "sql_correctness"
```

**Critical:** `analyst_name` must be the fully-qualified 3-part name (`DB.SCHEMA.SV`), not just the SV name. A bare name causes "Model does not exist" even when the correct database is active.

---

## Stage Setup

```sql
CREATE OR REPLACE STAGE <DB>.<SCHEMA>.SV_EVAL_CONFIGS
  ENCRYPTION = (TYPE = 'SNOWFLAKE_SSE');
-- Note: do NOT specify FILE_FORMAT = (TYPE = 'YAML') — that parameter is invalid.
```

Upload config (requires SnowSQL or `snow sql` CLI — PUT is not supported in sql_execute):

```bash
snow sql --connection <connection> -q "
  USE ROLE <ROLE>;
  USE DATABASE <DB>;
  USE SCHEMA <SCHEMA>;
  PUT file:///tmp/<config_file>.yaml @<DB>.<SCHEMA>.SV_EVAL_CONFIGS
    AUTO_COMPRESS=FALSE OVERWRITE=TRUE;
"
```

---

## Launch & Poll

```sql
-- Launch (role must have EXECUTE TASK on account, CREATE TASK and CREATE DATASET on schema)
CALL EXECUTE_AI_EVALUATION(
    'START',
    OBJECT_CONSTRUCT('run_name', '<run_name>'),
    '@<DB>.<SCHEMA>.SV_EVAL_CONFIGS/<config_file>.yaml'
);

-- Poll (call every 30s)
CALL EXECUTE_AI_EVALUATION(
    'STATUS',
    OBJECT_CONSTRUCT('run_name', '<run_name>'),
    '@<DB>.<SCHEMA>.SV_EVAL_CONFIGS/<config_file>.yaml'
);
```

Status progression: `CREATED → INVOCATION_IN_PROGRESS → INVOCATION_COMPLETED → COMPUTATION_IN_PROGRESS → COMPLETED`

Shell polling loop (30s interval, max 10 min):
```bash
for i in $(seq 1 20); do
  STATUS=$(snow sql --connection <conn> -q "
    USE ROLE <ROLE>; USE DATABASE <DB>; USE SCHEMA <SCHEMA>;
    CALL EXECUTE_AI_EVALUATION('STATUS',
      OBJECT_CONSTRUCT('run_name', '<run_name>'),
      '@<DB>.<SCHEMA>.SV_EVAL_CONFIGS/<config_file>.yaml');" 2>&1 \
    | grep -oE 'CREATED|INVOCATION_IN_PROGRESS|INVOCATION_COMPLETED|COMPUTATION_IN_PROGRESS|COMPLETED|FAILED' | tail -1)
  echo "$(date +%H:%M:%S) — $STATUS"
  [ "$STATUS" = "COMPLETED" ] || [ "$STATUS" = "FAILED" ] && break
  sleep 30
done
```

---

## Read Results

```sql
-- Per-VQR scores
SELECT
    INPUT           AS question,
    OUTPUT          AS generated_sql,
    GROUND_TRUTH    AS reference_sql,
    EVAL_AGG_SCORE  AS sql_correctness,
    ERROR           AS error_message,
    METRIC_STATUS,
    METRIC_CALLS
FROM TABLE(SNOWFLAKE.LOCAL.GET_ANALYST_AI_EVALUATION_DATA(
    '<DB>', '<SCHEMA>', '<SV_NAME>', 'SEMANTIC VIEW', '<run_name>'
))
WHERE METRIC_NAME = 'sql_correctness'
ORDER BY EVAL_AGG_SCORE ASC;

-- Summary
SELECT
    AVG(EVAL_AGG_SCORE)                                               AS mean_score,
    ROUND(AVG(EVAL_AGG_SCORE) * 100, 1)                              AS accuracy_pct,
    COUNT(*)                                                          AS total_vqrs,
    SUM(CASE WHEN EVAL_AGG_SCORE = 1.0 THEN 1 ELSE 0 END)           AS perfect,
    SUM(CASE WHEN EVAL_AGG_SCORE > 0 AND EVAL_AGG_SCORE < 1 THEN 1 ELSE 0 END) AS partial,
    SUM(CASE WHEN EVAL_AGG_SCORE = 0.0 THEN 1 ELSE 0 END)           AS failed
FROM TABLE(SNOWFLAKE.LOCAL.GET_ANALYST_AI_EVALUATION_DATA(
    '<DB>', '<SCHEMA>', '<SV_NAME>', 'SEMANTIC VIEW', '<run_name>'
))
WHERE METRIC_NAME = 'sql_correctness';
```

---

## Required Privileges

| Privilege | Object | Notes |
|-----------|--------|-------|
| `EXECUTE TASK` | Account | |
| `USE AI FUNCTIONS` | Account | |
| `SNOWFLAKE.CORTEX_USER` database role | — | Grant to executing role |
| `CREATE TASK` | Target schema | |
| `CREATE DATASET` | Target schema | |
| `SELECT`, `MONITOR` | Semantic view | |

---

## Known Issues

| Error | Root cause | Fix |
|-------|-----------|-----|
| "Evaluation must contain 'source_metadata'" | Missing `source_metadata` block in YAML | Add `source_metadata: {type: "verified_queries"}` inside `evaluation:` |
| "Model X does not exist or not authorized" | Bare SV name used instead of 3-part FQN | Use `DB.SCHEMA.SV_NAME` in `analyst_name` |
| Stuck in `CREATED` indefinitely + INGESTION task FAILED with "Cannot parse null string" | `EXECUTE_AI_EVALUATION('START', ...)` generates the root task with `''` (empty string) as the last arg to `SYSTEM$EXECUTE_AI_OBSERVABILITY_TASK`; Snowflake's internal `PARSE_JSON('')` raises this error. Platform bug — not caused by SV content. | **Workaround:** Use `cortex analyst query "<question>" --view=<SV_FQN>` to manually score each VQR. Compare generated SQL against VQR ground-truth SQL. This matches the pre-eval-framework approach used in T05a. |
| "Dataset version already exists" | Prior run lock not released | `ALTER DATASET <DB>.<SCHEMA>.<SV_NAME>_r<N> DROP VERSION 'SYSTEM_AI_OBS_CORTEX_AGENT_DATASET_VERSION_DO_NOT_DELETE'` |
| 392700 | Historical SV-type bug (pre-Aug 2026) | No longer applies — use standard path |

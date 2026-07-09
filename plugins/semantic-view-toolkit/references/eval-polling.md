# Eval Polling

Pattern for polling EXECUTE_AI_EVALUATION completion and retrieving results.

## Evaluation Lifecycle

```
CREATED → INVOCATION_IN_PROGRESS → INVOCATION_COMPLETED → COMPUTATION_IN_PROGRESS → COMPLETED
```

### Status Descriptions

| Status | Meaning |
|--------|---------|
| `CREATED` | Evaluation job submitted, not yet started |
| `INVOCATION_IN_PROGRESS` | Cortex Analyst is generating SQL for each VQR |
| `INVOCATION_COMPLETED` | All SQL generated, awaiting metric computation |
| `COMPUTATION_IN_PROGRESS` | Computing sql_correctness and other metrics |
| `COMPLETED` | All metrics computed, results available |

## Starting an Evaluation

**Canonical approach: upload config to a stage, then pass the stage path.**
This is more robust than inline strings for large configs and keeps GEPA generation history auditable.

```sql
-- Step 1: Create stage (idempotent, with FILE_FORMAT)
CREATE OR REPLACE STAGE <DB>.<SCHEMA>.SV_EVAL_CONFIGS
  ENCRYPTION = (TYPE = 'SNOWFLAKE_SSE')
  FILE_FORMAT = (TYPE = 'YAML');
```

Write config YAML to a local temp file, upload it, then call:

```sql
-- Step 2: Upload config
PUT file:///tmp/<eval_config>.yaml
  @<DB>.<SCHEMA>.SV_EVAL_CONFIGS/
  AUTO_COMPRESS = FALSE OVERWRITE = TRUE;

-- Step 3: Start evaluation (new START pattern)
CALL EXECUTE_AI_EVALUATION(
    'START',
    OBJECT_CONSTRUCT('run_name', '<run_name>'),
    '@<DB>.<SCHEMA>.SV_EVAL_CONFIGS/<config>.yaml'
);
```

## Polling Pattern

### Method 1: STATUS Call (Recommended)

```sql
-- Check evaluation status (new STATUS pattern)
CALL EXECUTE_AI_EVALUATION(
    'STATUS',
    OBJECT_CONSTRUCT('run_name', '<run_name>'),
    '@<DB>.<SCHEMA>.SV_EVAL_CONFIGS/<config>.yaml'
);
```

**Polling interval:** Every 30 seconds

**Implementation:**

```python
import time

MAX_WAIT_SECONDS = 900  # 15 minutes
POLL_INTERVAL = 30      # 30 seconds

def poll_evaluation(run_name, config_path, connection):
    elapsed = 0
    while elapsed < MAX_WAIT_SECONDS:
        result = connection.execute(
            f"CALL EXECUTE_AI_EVALUATION('STATUS', OBJECT_CONSTRUCT('run_name', '{run_name}'), '{config_path}')"
        )
        # CALL result returns a row with STATUS column
        row = result.fetchone()
        status = row[1] if isinstance(row, tuple) else row['STATUS']
        
        if status == 'COMPLETED':
            return 'COMPLETED'
        elif status in ('FAILED', 'CANCELLED'):
            return status
        
        time.sleep(POLL_INTERVAL)
        elapsed += POLL_INTERVAL
    
    return 'TIMEOUT'
```

### Method 2: Check Scored Results

Alternatively, check `GET_ANALYST_AI_EVALUATION_DATA` for scored results (use new 5-arg form):

```sql
-- Check if results are available by querying new 5-arg function
SELECT *
FROM TABLE(SNOWFLAKE.LOCAL.GET_ANALYST_AI_EVALUATION_DATA(
  '<DB>', '<SCHEMA>', '<SV_NAME>', 'SEMANTIC VIEW', '<run_name>'
))
WHERE METRIC_NAME = 'sql_correctness'
LIMIT 5;
```

If this returns rows with non-NULL metric values, evaluation is complete.

## Retrieving Results (Normalized Pattern)

**Canonical normalized projection** — use this CTE pattern in all result queries:

```sql
-- Raw results from 5-arg SNOWFLAKE.LOCAL function
WITH raw AS (
  SELECT INPUT, OUTPUT, GROUND_TRUTH, ERROR,
         EVAL_AGG_SCORE, METRIC_STATUS, METRIC_CALLS
  FROM TABLE(SNOWFLAKE.LOCAL.GET_ANALYST_AI_EVALUATION_DATA(
    '<DB>', '<SCHEMA>', '<SV_NAME>', 'SEMANTIC VIEW', '<run_name>'
  ))
  WHERE METRIC_NAME = 'sql_correctness'
)
-- Normalized projection for downstream consumers
SELECT
  INPUT           AS question,
  OUTPUT          AS generated_output,
  GROUND_TRUTH    AS reference_output,
  EVAL_AGG_SCORE  AS sql_correctness,
  ERROR           AS error_message,
  METRIC_STATUS,
  METRIC_CALLS
FROM raw;
```

**Key changes:**
- Function: `SNOWFLAKE.CORTEX.GET_ANALYST_AI_EVALUATION_DATA` (1-arg, old) → `SNOWFLAKE.LOCAL.GET_ANALYST_AI_EVALUATION_DATA` (5-arg, new)
- Arguments: `<evaluation_name>` → `'<DB>', '<SCHEMA>', '<SV_NAME>', 'SEMANTIC VIEW', '<run_name>'`
- Schema: old columns `question, generated_sql, reference_sql, sql_correctness, error_message` → new columns `INPUT, OUTPUT, GROUND_TRUTH, ERROR, EVAL_AGG_SCORE, METRIC_STATUS, METRIC_CALLS`
- All queries **must** use this CTE normalization to map new schema to old names

### Aggregating Scores

```sql
-- Mean sql_correctness (the fitness score for GEPA)
-- Use the normalized CTE pattern from "Retrieving Results" section
WITH raw AS (
  SELECT EVAL_AGG_SCORE
  FROM TABLE(SNOWFLAKE.LOCAL.GET_ANALYST_AI_EVALUATION_DATA(
    '<DB>', '<SCHEMA>', '<SV_NAME>', 'SEMANTIC VIEW', '<run_name>'
  ))
  WHERE METRIC_NAME = 'sql_correctness'
)
SELECT
    AVG(EVAL_AGG_SCORE) AS mean_score,
    COUNT(*) AS total_vqrs,
    SUM(CASE WHEN EVAL_AGG_SCORE = 1.0 THEN 1 ELSE 0 END) AS perfect_count,
    SUM(CASE WHEN EVAL_AGG_SCORE = 0.0 THEN 1 ELSE 0 END) AS failed_count
FROM raw;
```

## Timeout Handling

**Maximum wait:** 15 minutes (900 seconds)

If evaluation hasn't completed within 15 minutes:

1. **Report partial results** if any metrics are available
2. **Log the timeout** with current status
3. **Don't retry automatically** — let the calling skill decide

**Common timeout causes:**
- Very large VQR set (>50 questions)
- Complex SQL generation (many joins, subqueries)
- System load (shared Cortex Analyst capacity)

## Parallel Evaluation (Multiple Candidates)

When evaluating N candidates in the same generation:

### Sequential Polling (Recommended)

Poll one evaluation at a time to avoid flooding:

```python
def poll_all_candidates(eval_names, connection):
    results = {}
    for eval_name in eval_names:
        status = poll_evaluation(eval_name, connection)
        if status == 'COMPLETED':
            results[eval_name] = get_scores(eval_name, connection)
        else:
            results[eval_name] = {'status': status, 'score': 0.0}
    return results
```

### Why Not Parallel Polling?

- Avoids excessive SQL calls during peak evaluation
- Evaluations are independent — they don't block each other
- Sequential polling still catches completions within 30 seconds
- Reduces risk of rate limiting or connection pool exhaustion

### Launch in Parallel, Poll Sequentially

```python
# Launch all evaluations (parallel is fine for launch)
for candidate in candidates:
    launch_evaluation(candidate.eval_name, candidate.sv_fqn, eval_config)

# Then poll sequentially
for candidate in candidates:
    result = poll_evaluation(candidate.eval_name, connection)
    candidate.fitness = get_mean_score(candidate.eval_name, connection)
```

## Error Handling

### Evaluation Failures

| Error | Cause | Recovery |
|-------|-------|----------|
| `FAILED` status | DDL compile error or invalid SV | Score = 0.0, mark candidate as failed |
| `CANCELLED` status | Manual cancellation or system issue | Retry once, then score = 0.0 |
| Timeout | Long-running evaluation | Report partial, skip candidate |
| Permission error | Role can't access SV or eval function | Abort entire generation, report |

### Partial Results

If evaluation completed for some VQRs but not all:

```sql
-- Check completion count (use normalized CTE pattern)
WITH raw AS (
  SELECT EVAL_AGG_SCORE
  FROM TABLE(SNOWFLAKE.LOCAL.GET_ANALYST_AI_EVALUATION_DATA(
    '<DB>', '<SCHEMA>', '<SV_NAME>', 'SEMANTIC VIEW', '<run_name>'
  ))
  WHERE METRIC_NAME = 'sql_correctness'
)
SELECT
    COUNT(*) AS total,
    COUNT(EVAL_AGG_SCORE) AS scored,
    COUNT(*) - COUNT(EVAL_AGG_SCORE) AS pending
FROM raw;
```

If `scored / total >= 0.80`, use partial results (scale appropriately). Otherwise, treat as timeout.

## Naming Convention

Evaluation names should be unique and traceable:

```
Format: {sv_name}__gen{generation}__cand{candidate_id}
Example: MY_DB__MY_SCHEMA__REVENUE_SV__gen3__cand_7
```

This allows querying historical evaluations and correlating with GEPA state.

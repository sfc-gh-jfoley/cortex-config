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

```sql
-- Start evaluation
CALL SNOWFLAKE.CORTEX.EXECUTE_AI_EVALUATION(
    '<evaluation_name>',
    '<semantic_view_fqn>',
    '<eval_config_yaml>'
);
```

The eval config YAML specifies:
- Which VQRs to evaluate (question strings)
- Which metrics to compute (typically `sql_correctness`)
- Optional parameters (model, temperature)

## Polling Pattern

### Method 1: STATUS Function (Recommended)

```sql
-- Check evaluation status
SELECT SNOWFLAKE.CORTEX.GET_AI_EVALUATION_STATUS('<evaluation_name>') AS status;
```

**Polling interval:** Every 30 seconds

**Implementation:**

```python
import time

MAX_WAIT_SECONDS = 900  # 15 minutes
POLL_INTERVAL = 30      # 30 seconds

def poll_evaluation(eval_name, connection):
    elapsed = 0
    while elapsed < MAX_WAIT_SECONDS:
        result = connection.execute(
            f"SELECT SNOWFLAKE.CORTEX.GET_AI_EVALUATION_STATUS('{eval_name}') AS status"
        )
        status = result.fetchone()['STATUS']
        
        if status == 'COMPLETED':
            return 'COMPLETED'
        elif status in ('FAILED', 'CANCELLED'):
            return status
        
        time.sleep(POLL_INTERVAL)
        elapsed += POLL_INTERVAL
    
    return 'TIMEOUT'
```

### Method 2: Check Scored Results

Alternatively, check `GET_ANALYST_AI_EVALUATION_DATA` for scored results:

```sql
-- Check if results are available (COMPLETED_METRICS > 0)
SELECT *
FROM TABLE(SNOWFLAKE.CORTEX.GET_ANALYST_AI_EVALUATION_DATA('<evaluation_name>'))
LIMIT 5;
```

If this returns rows with non-NULL metric values, evaluation is complete.

## Retrieving Results

```sql
-- Get full evaluation results
SELECT
    question,
    generated_sql,
    reference_sql,
    sql_correctness,
    error_message
FROM TABLE(SNOWFLAKE.CORTEX.GET_ANALYST_AI_EVALUATION_DATA('<evaluation_name>'));
```

### Aggregating Scores

```sql
-- Mean sql_correctness (the fitness score for GEPA)
SELECT
    AVG(sql_correctness) AS mean_score,
    COUNT(*) AS total_vqrs,
    SUM(CASE WHEN sql_correctness = 1.0 THEN 1 ELSE 0 END) AS perfect_count,
    SUM(CASE WHEN sql_correctness = 0.0 THEN 1 ELSE 0 END) AS failed_count
FROM TABLE(SNOWFLAKE.CORTEX.GET_ANALYST_AI_EVALUATION_DATA('<evaluation_name>'));
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
-- Check completion count
SELECT
    COUNT(*) AS total,
    COUNT(sql_correctness) AS scored,
    COUNT(*) - COUNT(sql_correctness) AS pending
FROM TABLE(SNOWFLAKE.CORTEX.GET_ANALYST_AI_EVALUATION_DATA('<evaluation_name>'));
```

If `scored / total >= 0.80`, use partial results (scale appropriately). Otherwise, treat as timeout.

## Naming Convention

Evaluation names should be unique and traceable:

```
Format: {sv_name}__gen{generation}__cand{candidate_id}
Example: MY_DB__MY_SCHEMA__REVENUE_SV__gen3__cand_7
```

This allows querying historical evaluations and correlating with GEPA state.

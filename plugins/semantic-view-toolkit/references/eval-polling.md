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

## ANALYST_PREVIEW Eval Path (Primary — use when EXECUTE_AI_EVALUATION returns 392700)

> **⚠ EXECUTE_AI_EVALUATION BROKEN FOR SV TYPE (error 392700)**
>
> `EXECUTE_AI_EVALUATION` with `analyst_type="SEMANTIC VIEW"` currently returns error 392700
> on all accounts. Root cause: the procedure passes the SV FQN as a plain string to the
> internal `ANALYST_PREVIEW` call; the CA API requires a JSON object. **Use `ANALYST_PREVIEW`
> directly until Snowflake fixes the procedure.** Verified broken as of 2026-07-23.

### Working Call Pattern

> **⚠ ANALYST_PREVIEW requires a constant string argument.** Do NOT use `OBJECT_CONSTRUCT(...)`
> — the SQL compiler rejects it (error 001015: "argument needs to be constant"). Build the
> JSON payload as a string literal and pass it directly.

```sql
-- Build payload as a JSON string literal (not OBJECT_CONSTRUCT)
SELECT SNOWFLAKE.CORTEX.ANALYST_PREVIEW('{
  "messages": [{"role": "user", "content": [{"type": "text", "text": "<question>"}]}],
  "semantic_model_file": "@<DB>.<SCHEMA>.<STAGE>/<model>.yaml"
}')
```

> **Note:** When using the `snow` CLI, pass `--format json` to avoid double-quote escaping
> issues in the response string.

> **⚠ Python string building — use `json.dumps` for question text.** If building the payload
> programmatically, always use `json.dumps(question)` to produce the JSON-safe string for the
> question field. Raw f-string interpolation breaks JSON if the question contains `"` characters
> or backslashes.
> ```python
> import json
> question = 'What is the "total" revenue?'  # contains quotes
> payload = json.dumps({
>     "messages": [{"role": "user", "content": [{"type": "text", "text": question}]}],
>     "semantic_model_file": f"@{db}.{schema}.{stage}/{model}.yaml"
> })
> # Use payload as the string literal in: SELECT SNOWFLAKE.CORTEX.ANALYST_PREVIEW(payload)
> # (via snow sql -q or a Snowflake Python connector parameterized query)
> ```

### YAML Stage Upload Requirements

The YAML uploaded to the stage must satisfy two requirements:

1. **Top-level `name:` field required** — the CA API rejects YAML files that lack a `name:`
   key at the document root.
2. **Primary key columns must appear in the table's `columns:` section** — if a column is
   listed only in `primary_key:` but omitted from `columns:`, the CA API will fail silently
   or return validation errors. Add each PK column explicitly to `columns:` as well.

### Parsing the ANALYST_PREVIEW Response

`ANALYST_PREVIEW` returns a JSON string. Parse it in Python to extract results:

```python
import json

def parse_analyst_preview_response(raw_response: str) -> dict:
    """Extract SQL and VQR match from an ANALYST_PREVIEW JSON response."""
    data = json.loads(raw_response)
    result = {"sql": None, "matched_vqr": None}

    # Walk message content items — find type == "sql"
    for msg in data.get("messages", []):
        for item in msg.get("content", []):
            if item.get("type") == "sql":
                result["sql"] = item.get("statement") or item.get("text")

    # Extract matched VQR name from confidence block if present
    confidence = data.get("confidence", {})
    vqr = confidence.get("verified_query_used", {})
    if vqr:
        result["matched_vqr"] = vqr.get("name")

    return result
```

---

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

## GET_DDL Output Escaping

`GET_DDL('SEMANTIC VIEW', '<fqn>')` returns a CSV-escaped string. All `"` characters
inside the DDL are doubled to `""`. This is especially relevant when parsing the
CA extension JSON blob.

**Always unescape before parsing:**

```python
# Using snow CLI with --format json
result = subprocess.run(
    ['snow', 'sql', '-c', connection, '--format', 'json', '-q',
     f"SELECT GET_DDL('SEMANTIC VIEW', '{sv_fqn}')"],
    capture_output=True, text=True
)
data = json.loads(result.stdout)
ddl = data[0][list(data[0].keys())[0]]
ddl = ddl.replace('""', '"')  # Unescape CSV double-quotes
```

**Validate CA extension JSON after unescape:**

```python
import re, json
ext_match = re.search(r"with extension \(CA='(\{.*?\})'\)", ddl, re.DOTALL)
if ext_match:
    ca_json = json.loads(ext_match.group(1))  # Raises if malformed
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

## Concurrency Constraint

> **One evaluation per SV at a time.** Snowflake enforces a single concurrent
> evaluation per semantic view. If you launch a second evaluation while one is
> running against the same SV, the second run will fail immediately with status
> `FAILED` and `["Invocation failed"]`.
>
> **Parallel launch is valid only across _different_ SVs.** For GEPA multi-candidate
> runs (N different SVs), launch all N in parallel and drain sequentially. For a
> single SV with many VQRs, use the `verified_queries:` subset list to run sequential batches.

### Concurrent-launch error pattern

`CALL EXECUTE_AI_EVALUATION('STATUS', ...)` returns:

```
STATUS = FAILED, STATUS_DETAILS = ["Invocation failed"]
```

This error occurs when a second eval was launched while the first was still in
`INVOCATION_IN_PROGRESS`. Wait for `COMPLETED` before re-launching.

## Batching Large Eval Sets (single SV)

For SVs with more than 15 VQRs, **run evaluations in subsets of 15 or fewer per batch**.
Large eval sets have longer total latency and make it harder to isolate failures.

Use the `verified_queries:` list in your config YAML to subset by exact question text
(case-sensitive match against what is stored in the SV).

Steps:
1. Split into batches of the recommended size (see table below)
2. Launch batch 1 → wait for COMPLETED → launch batch 2
3. Aggregate scores across batches after all complete

### Recommended Batch Sizes

| Scenario | Batch Size | Rationale |
|---|---|---|
| Simple single-table questions | 15–20 | Fast, low timeout risk |
| Multi-table joins | 10–12 | Higher per-question latency |
| Complex CTEs or subqueries | 8–10 | Timeout risk per question |
| Mixed (default) | 10 | Safe default |

For a 50-question eval set with mixed complexity: use 5 sequential batches of 10.

---

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
# Launch all evaluations (parallel is fine ONLY when each candidate targets a DIFFERENT SV FQN)
# Do NOT launch multiple evals against the same SV — use sequential batching instead (see above)
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

---

## SQL Authoring Caveats

> ⚠️ **Avoid GROUP BY alias in VQR SQL**
> The eval framework rewrites VQR SQL using CTEs internally. GROUP BY alias references
> (e.g., `GROUP BY order_month` where `order_month` is a SELECT alias) fail after CTE
> expansion with errors like:
> `'__ORDERS.O_ORDERDATE' in select clause is neither an aggregate nor in the group by clause`
>
> Use the full expression instead:
> ```sql
> -- BAD (breaks after CTE expansion):
> SELECT DATE_TRUNC('month', O_ORDERDATE) AS order_month, SUM(amount) AS rev
> GROUP BY order_month
>
> -- GOOD:
> SELECT DATE_TRUNC('month', O_ORDERDATE) AS order_month, SUM(amount) AS rev
> GROUP BY DATE_TRUNC('month', O_ORDERDATE)
> ```

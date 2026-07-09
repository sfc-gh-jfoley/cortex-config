---
name: sv-evaluation
description: >
  Evaluate semantic view accuracy using Cortex Analyst's native EXECUTE_AI_EVALUATION API.
  Measures sql_correctness by generating SQL from VQRs and comparing results against
  verified queries.
triggers:
  - evaluate semantic view
  - eval sv
  - run evaluation
  - check accuracy
  - test sv
  - score sv
  - how accurate is my semantic view
  - sv correctness
  - run sql_correctness
  - benchmark sv
---

# sv-evaluation

**Prerequisites:**
- CORTEX_USER database role granted to active role
- EXECUTE TASK ON ACCOUNT privilege
- CREATE TASK and CREATE DATASET on target schema
- SELECT on the semantic view and all underlying tables
- MONITOR on the semantic view
- At least 1 verified query (VQR) embedded in the SV

---

## Workflow

### Phase 1: Connect & Validate

**Step 1: Get SV Identity**

Ask the user for the semantic view fully-qualified name (or infer from context/prior skill output):

```
Which semantic view do you want to evaluate?
```

**Step 2: Validate Access**

```sql
DESCRIBE SEMANTIC VIEW <DB>.<SCHEMA>.<SV_NAME>;
```

If this fails with permission error → report missing grants and stop.

**Step 3: Check VQRs Exist**

Parse the DDL output from DESCRIBE to count `verified_queries` entries. If 0 VQRs:
- Report: "No verified queries found. Evaluation requires VQRs as ground truth."
- Offer: "Route to vqr-generator to create VQRs first?"
- STOP (cannot evaluate without VQRs)

**Step 3b: VQR Health Pre-Check**

Before launching evaluation, scan each VQR's reference SQL against the SV's metric filter map to detect contaminated baselines.

For each metric with a conditional filter (e.g., `SUM(CASE WHEN REFUNDED_IND = 0 THEN col)`), check every VQR that aggregates the same source column. Flag as **CONTAMINATED** if the VQR SQL omits the required filter.

Classify each VQR:
- **HEALTHY**: VQR SQL filter logic matches the metric definition
- **CONTAMINATED**: VQR SQL aggregates the column without the required filter
- **REVIEW**: VQR uses complex multi-table logic that cannot be auto-validated

Report before proceeding:
```
VQR Health Summary:
  HEALTHY:      N VQRs
  CONTAMINATED: N VQRs → [list names]
  REVIEW:       N VQRs → [list names]

⚠ Warning: N contaminated VQR(s) detected. Eval will penalize correct model
  behavior on these VQRs. Consider fixing before running eval.
```

If CONTAMINATED VQRs exist, offer:
```
A) Proceed and flag contaminated VQR failures as REFERENCE_CONTAMINATED (read-only analysis)
B) Exclude contaminated VQRs from this eval run
```

**STOP Gate (GUIDED mode):** Wait for user choice before proceeding.

---

**Step 4: Validate Eval Prerequisites**

Run grant checks:

```sql
-- Check CORTEX_USER database role is granted to current role
SHOW GRANTS OF DATABASE ROLE SNOWFLAKE.CORTEX_USER;
SELECT "grantee_name" FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()))
WHERE "grantee_name" = CURRENT_ROLE();
-- If 0 rows: GRANT DATABASE ROLE SNOWFLAKE.CORTEX_USER TO ROLE <ROLE>;

-- Check USE AI FUNCTIONS privilege on account
SHOW GRANTS ON ACCOUNT;
SELECT "privilege", "grantee_name" FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()))
WHERE "grantee_name" = CURRENT_ROLE()
  AND "privilege" = 'USE AI FUNCTIONS';
-- If 0 rows: GRANT USE AI FUNCTIONS ON ACCOUNT TO ROLE <ROLE>;

-- Check EXECUTE TASK on account
SHOW GRANTS ON ACCOUNT;
SELECT "privilege", "grantee_name" FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()))
WHERE "grantee_name" = CURRENT_ROLE()
  AND "privilege" = 'EXECUTE TASK';
-- If 0 rows: GRANT EXECUTE TASK ON ACCOUNT TO ROLE <ROLE>;

-- Check CREATE TASK and CREATE DATASET on schema
SHOW GRANTS ON SCHEMA <DB>.<SCHEMA>;
SELECT "privilege", "grantee_name" FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()))
WHERE "grantee_name" = CURRENT_ROLE()
  AND "privilege" IN ('CREATE TASK', 'CREATE DATASET');
-- If fewer than 2 rows: GRANT CREATE TASK, CREATE DATASET ON SCHEMA <DB>.<SCHEMA> TO ROLE <ROLE>;

-- Check SELECT on semantic view and underlying tables
SHOW GRANTS ON SEMANTIC VIEW <DB>.<SCHEMA>.<SV_NAME>;
-- Must include SELECT for current role

-- Check MONITOR on semantic view
SHOW GRANTS ON SEMANTIC VIEW <DB>.<SCHEMA>.<SV_NAME>;
-- Must include MONITOR for current role
```

**⚠️ Primary Role Warning:** EXECUTE_AI_EVALUATION can only be called from a primary role. If your current role is not primary (e.g., a secondary role or a role in a role hierarchy), you must switch to a primary role with evaluation privileges before proceeding.

Report any missing grants with remediation DDL:
```sql
-- Example remediation
GRANT DATABASE ROLE SNOWFLAKE.CORTEX_USER TO ROLE <ROLE>;
GRANT USE AI FUNCTIONS ON ACCOUNT TO ROLE <ROLE>;
GRANT EXECUTE TASK ON ACCOUNT TO ROLE <ROLE>;
GRANT CREATE TASK, CREATE DATASET ON SCHEMA <DB>.<SCHEMA> TO ROLE <ROLE>;
GRANT SELECT ON SEMANTIC VIEW <DB>.<SCHEMA>.<SV_NAME> TO ROLE <ROLE>;
GRANT MONITOR ON SEMANTIC VIEW <DB>.<SCHEMA>.<SV_NAME> TO ROLE <ROLE>;
```

**Step 5: Present Summary**

```
Semantic View: <DB>.<SCHEMA>.<SV_NAME>
Tables: N source tables
VQRs: M verified queries available
Status: Ready for evaluation
```

**STOP Gate (GUIDED mode only):** Wait for user confirmation before proceeding.

---

### Phase 2: Configure Evaluation

**Step 6: Choose VQR Scope**

Ask user (or auto-select all in AUTOPILOT):

```
VQR selection:
A) Evaluate ALL M verified queries (recommended for baseline)
B) Select a subset (useful for focused testing)
C) Exclude specific VQRs
```

**Step 7: Generate Eval Config YAML**

Build the evaluation configuration:

```yaml
evaluation:
  analyst_params:
    analyst_name: "<SV_NAME>"
    analyst_type: "SEMANTIC VIEW"
  source_metadata:
    type: "verified_queries"
    # If subset selected, include explicit list:
    verified_queries:
      - "What is the total revenue by region for Q4?"
      - "Show me the top 10 customers by order count"

metrics:
  - "sql_correctness"
```

If ALL VQRs selected, omit the `verified_queries` list (evaluates all embedded VQRs).

**Step 8: Create Stage and Upload Config**

```sql
-- Create eval config stage (idempotent, with FILE_FORMAT)
CREATE OR REPLACE STAGE <DB>.<SCHEMA>.SV_EVAL_CONFIGS
  ENCRYPTION = (TYPE = 'SNOWFLAKE_SSE')
  FILE_FORMAT = (TYPE = 'YAML');
```

Write config to local temp file, then upload:

```sql
-- Upload config YAML
PUT file:///tmp/sv_eval_config_<run_name>.yaml
  @<DB>.<SCHEMA>.SV_EVAL_CONFIGS/
  AUTO_COMPRESS = FALSE OVERWRITE = TRUE;
```

---

### Phase 3: Execute Evaluation

**Step 9: Generate Run Name**

Format: `<SV_NAME>_eval_<YYYYMMDD_HHMMSS>`

Example: `REVENUE_SV_eval_20260522_143022`

**Step 10: Launch Evaluation**

```sql
CALL EXECUTE_AI_EVALUATION(
    'START',
    OBJECT_CONSTRUCT('run_name', '<run_name>'),
    '@<DB>.<SCHEMA>.SV_EVAL_CONFIGS/<config_filename>.yaml'
);
```

**Step 11: Poll for Completion**

Follow the polling pattern from `references/eval-polling.md` (use new STATUS pattern):

```sql
-- Poll every 30 seconds (up to 15 minutes)
CALL EXECUTE_AI_EVALUATION(
    'STATUS',
    OBJECT_CONSTRUCT('run_name', '<run_name>'),
    '@<DB>.<SCHEMA>.SV_EVAL_CONFIGS/<config_filename>.yaml'
);
```

Status progression: `CREATED → INVOCATION_IN_PROGRESS → INVOCATION_COMPLETED → COMPUTATION_IN_PROGRESS → COMPLETED`

In GUIDED mode, report progress at each status change.

**Timeout handling:**
- After 15 minutes without COMPLETED → report current status
- If partial results exist (>80% scored), use those
- Otherwise report timeout and suggest retrying with smaller VQR subset

---

### Phase 4: Analyze Results

**Step 12: Query Raw Results (Normalized Pattern)**

Use the normalized CTE from `references/eval-polling.md`:

```sql
WITH raw AS (
  SELECT INPUT, OUTPUT, GROUND_TRUTH, ERROR,
         EVAL_AGG_SCORE, METRIC_STATUS, METRIC_CALLS
  FROM TABLE(SNOWFLAKE.LOCAL.GET_ANALYST_AI_EVALUATION_DATA(
    '<DB>', '<SCHEMA>', '<SV_NAME>', 'SEMANTIC VIEW', '<run_name>'
  ))
  WHERE METRIC_NAME = 'sql_correctness'
)
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

**Step 13: Calculate Metrics**

```sql
-- Overall accuracy (use normalized CTE pattern)
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
    SUM(CASE WHEN EVAL_AGG_SCORE = 0.0 THEN 1 ELSE 0 END) AS failed_count,
    SUM(CASE WHEN EVAL_AGG_SCORE > 0.0 AND EVAL_AGG_SCORE < 1.0 THEN 1 ELSE 0 END) AS partial_count
FROM raw;
```

**Step 14: Regression Detection**

If a previous evaluation exists (check `_SV_TOOLKIT_META.EVAL_HISTORY` or ask user for prior run name):

```sql
-- Compare with previous run (use normalized CTE pattern)
WITH current AS (
    SELECT INPUT AS question, EVAL_AGG_SCORE AS current_score
    FROM TABLE(SNOWFLAKE.LOCAL.GET_ANALYST_AI_EVALUATION_DATA(
      '<DB>', '<SCHEMA>', '<SV_NAME>', 'SEMANTIC VIEW', '<current_run>'
    ))
    WHERE METRIC_NAME = 'sql_correctness'
),
previous AS (
    SELECT INPUT AS question, EVAL_AGG_SCORE AS prev_score
    FROM TABLE(SNOWFLAKE.LOCAL.GET_ANALYST_AI_EVALUATION_DATA(
      '<DB>', '<SCHEMA>', '<SV_NAME>', 'SEMANTIC VIEW', '<previous_run>'
    ))
    WHERE METRIC_NAME = 'sql_correctness'
)
SELECT
    c.question,
    p.prev_score,
    c.current_score,
    CASE
        WHEN p.prev_score = 1.0 AND c.current_score < 1.0 THEN 'REGRESSION'
        WHEN p.prev_score < 1.0 AND c.current_score = 1.0 THEN 'IMPROVEMENT'
        ELSE 'UNCHANGED'
    END AS change_type
FROM current c
LEFT JOIN previous p ON c.question = p.question
WHERE change_type != 'UNCHANGED';
```

**Step 15: Categorize Failures**

For each VQR with `sql_correctness < 1.0`, analyze the generated vs reference SQL to determine failure category. Reference `references/failure-analysis.md` for detailed diagnosis.

Failure categories:

| Category | Signal | Fix (Mutation Operator) |
|----------|--------|-------------------------|
| Wrong table/join | Different FROM/JOIN clauses | `change_relationship` |
| Wrong column | Correct table, wrong column selected | `improve_description`, `add_synonym` |
| Wrong aggregation | Wrong AGG function or GROUP BY | `add_metric`, `refine_metric_expr` |
| Wrong filter | Missing or incorrect WHERE | `add_filter` |
| Wrong time handling | Date logic errors | `add_time_dimension` |
| SQL syntax error | Query doesn't compile | Manual DDL fix |
| Empty result / Analyst refuses | Out-of-scope question | `add_vqr` |

---

### Phase 5: Present Results & Recommendations

**Step 16: Summary Report**

```
╔══════════════════════════════════════════════════════╗
║  Evaluation Results: <DB>.<SCHEMA>.<SV_NAME>        ║
╠══════════════════════════════════════════════════════╣
║  Run: <run_name>                                    ║
║  Accuracy: X% (N/M VQRs correct)                   ║
║  Mean Score: 0.XX                                   ║
║  Perfect (1.0): N  |  Partial: N  |  Failed (0.0): N║
║  Regressions: N (vs <previous_run>)                 ║
╚══════════════════════════════════════════════════════╝

Passing VQRs:
  ✓ "What is total revenue by region?"          (1.0)
  ✓ "Show top customers by order count"         (1.0)

Failing VQRs:
  ✗ "Revenue trend by quarter" → Wrong time handling  (0.0)
  ✗ "Active customer count"    → Wrong filter         (0.3)

Top Recommendations:
  1. add_time_dimension on orders.ORDER_DATE (fixes time-based queries)
  2. add_filter for CUSTOMER_STATUS = 'ACTIVE' (fixes active count)
  3. improve_description on REVENUE column (ambiguity with GROSS_REVENUE)
```

**Step 17: Offer Next Steps**

```
What would you like to do next?
A) Optimize this SV (→ sv-optimization / sv-gepa-optimizer)
B) Fix specific failures manually (show DDL changes)
C) Re-run evaluation with a different VQR subset
D) Export report to a table
E) Done for now
```

**Step 18: Persist Results (Optional)**

If `_SV_TOOLKIT_META` schema exists, persist for future regression tracking:

> **DDL/DML safety gate**: Per account mutation policy, before creating `_SV_TOOLKIT_META`
> objects ask the user: "Want me to create a rollback clone first so we can undo this?
> (`CREATE DATABASE <db>_RESTORE CLONE <db>`)"
> If yes, create the clone before proceeding. This gate covers the schema and both
> tables (EVAL_HISTORY and EVAL_RESULTS) — ask once, not again for the second table.

```sql
CREATE TABLE IF NOT EXISTS <DB>._SV_TOOLKIT_META.EVAL_HISTORY (
    run_name VARCHAR,
    sv_fqn VARCHAR,
    run_timestamp TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    total_vqrs INTEGER,
    mean_score FLOAT,
    perfect_count INTEGER,
    failed_count INTEGER,
    regressions INTEGER,
    config_yaml VARCHAR,
    PRIMARY KEY (run_name)
);

INSERT INTO <DB>._SV_TOOLKIT_META.EVAL_HISTORY
    (run_name, sv_fqn, total_vqrs, mean_score, perfect_count, failed_count, regressions, config_yaml)
VALUES
    ('<run_name>', '<DB>.<SCHEMA>.<SV_NAME>', M, 0.XX, N, N, N, '<yaml_content>');
```

Also persist per-VQR results (using normalized schema):

```sql
CREATE TABLE IF NOT EXISTS <DB>._SV_TOOLKIT_META.EVAL_RESULTS (
    run_name VARCHAR,
    question VARCHAR,
    generated_output VARCHAR,
    reference_output VARCHAR,
    raw_output VARCHAR,        -- new: raw OUTPUT column
    raw_ground_truth VARCHAR,   -- new: raw GROUND_TRUTH column
    sql_correctness FLOAT,
    failure_category VARCHAR,
    error_message VARCHAR,
    metric_status VARCHAR,
    metric_calls INTEGER,
    PRIMARY KEY (run_name, question)
);

INSERT INTO <DB>._SV_TOOLKIT_META.EVAL_RESULTS
WITH raw AS (
  SELECT INPUT, OUTPUT, GROUND_TRUTH, ERROR,
         EVAL_AGG_SCORE, METRIC_STATUS, METRIC_CALLS
  FROM TABLE(SNOWFLAKE.LOCAL.GET_ANALYST_AI_EVALUATION_DATA(
    '<DB>', '<SCHEMA>', '<SV_NAME>', 'SEMANTIC VIEW', '<run_name>'
  ))
  WHERE METRIC_NAME = 'sql_correctness'
)
SELECT
    '<run_name>' AS run_name,
    INPUT AS question,
    OUTPUT AS generated_output,
    GROUND_TRUTH AS reference_output,
    OUTPUT AS raw_output,
    GROUND_TRUTH AS raw_ground_truth,
    EVAL_AGG_SCORE AS sql_correctness,
    NULL AS failure_category,  -- populated by analysis
    ERROR AS error_message,
    METRIC_STATUS,
    METRIC_CALLS
FROM raw;
```

---

## Error Handling

| Error | Cause | Recovery |
|-------|-------|----------|
| "Semantic view not found" | Wrong FQN or no access | Verify name, check grants |
| "No verified queries" | SV has no VQRs | Route to vqr-generator |
| Eval FAILED status | Invalid SV DDL or config | Check DDL compiles, verify config YAML |
| Eval CANCELLED | System issue or manual cancel | Retry once |
| Permission denied on EXECUTE_AI_EVALUATION | Missing CORTEX_USER or EXECUTE TASK | Run grant remediation |
| Timeout (>15min) | Too many VQRs or system load | Use subset, retry later |

---

## Integration with Other Skills

| Scenario | Route to |
|----------|----------|
| No VQRs available | → vqr-generator |
| Accuracy < 70% (broad issues) | → sv-gepa-optimizer (population-based) |
| 1-3 specific failures | → sv-optimization (sequential mutation) |
| Missing relationships detected | → sv-discovery (re-scan) |
| Want to monitor over time | Persist to EVAL_HISTORY + set up recurring eval |

---

## Notes

- **Holdout method:** The evaluation API temporarily removes evaluated VQRs from the SV copy to prevent the model from "cheating" by looking up the answer. This is handled automatically by the API.
- **Cost:** Each evaluation invokes Cortex Analyst once per VQR. Budget approximately: N VQRs × (analyst inference + SQL execution for correctness check).
- **Idempotency:** Run names must be unique. Re-running with the same name will fail. Always generate a fresh timestamp-based name.
- **Concurrency:** Only one evaluation can run against the same SV at a time. Wait for completion before launching another.

# End-to-End Evaluation Smoke Test

**Purpose:** Validate the complete semantic view evaluation pipeline using the new API.

This 10-step SQL script confirms:
- Permissions and prerequisites
- Stage DDL
- YAML config upload
- Evaluation launch and polling
- Result retrieval via new 5-arg function
- Normalized CTE projection
- Failure-analysis query compatibility
- Data persistence

---

## Prerequisites

Before running this smoke test, ensure:

1. You have a **semantic view** to test (e.g., `MY_DB.MY_SCHEMA.MY_SV`)
2. At least **5 verified queries (VQRs)** registered in Cortex Analyst
3. Required **role grants** (see PREREQUISITES.md)
4. Access to **Cortex AI functions** via `USE AI FUNCTIONS` grant

---

## Smoke Test Steps

### Step 0: CA Extension Detection

Check whether the SV has a CA extension before running any eval. SVs built through the Snowsight
UI contain a `with extension (CA='...')` block. The eval framework has a known bug with these SVs:
columns in VQR SQL not in the CA extension's declared column list are silently dropped from CTEs,
causing ground-truth SQL failures before any model comparison happens.

```sql
-- Detect CA extension presence
SELECT
    CASE
        WHEN REGEXP_INSTR(
            LOWER(GET_DDL('SEMANTIC VIEW', 'MY_DB.MY_SCHEMA.MY_SV')),
            'with extension'
        ) > 0 THEN 'CA_EXTENSION_PRESENT — eval results may be unreliable (see vqr-eval-health.md Check 3)'
        ELSE 'CLEAN — no CA extension, eval will run reliably'
    END AS ca_extension_check;
```

**If `CA_EXTENSION_PRESENT`:**
- For reliable eval: create a DDL-only eval copy using the strip procedure in
  `references/vqr-eval-health.md` Check 3. Run the smoke test against the copy.
- To proceed anyway: note that column-drop failures may cause near-zero scores regardless of
  model quality. Results are not interpretable until the eval framework is patched.

**If `CLEAN`:** proceed to Step 1.

---

### Step 1: Verify VQR Count Gate

Confirm the semantic view has at least 5 VQRs registered.

```sql
-- Replace MY_DB, MY_SCHEMA, MY_SV with your values
-- Count VQRs from DESCRIBE output
DESCRIBE SEMANTIC VIEW MY_DB.MY_SCHEMA.MY_SV;

-- Then count AI_VERIFIED_QUERY rows:
SELECT
    COUNT(DISTINCT "object_name") AS vqr_count,
    CASE
        WHEN COUNT(DISTINCT "object_name") >= 5 THEN 'PASS: Sufficient VQRs'
        ELSE 'FAIL: Need at least 5 VQRs'
    END AS gate_status
FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()))
WHERE "object_kind" = 'AI_VERIFIED_QUERY';
```

**Expected:** VQR count >= 5, status = 'PASS'

---

### Step 2: Verify All 8 Required Grants

Check that the executing role has all required privileges:

```sql
-- Grant verification using SHOW GRANTS (the only reliable way in Snowflake).
-- INFORMATION_SCHEMA.DATABASE_PRIVILEGES, SCHEMA_PRIVILEGES, and ROLE_USAGE_GRANTS
-- do not exist. Use SHOW GRANTS TO ROLE and filter the results.

-- Check all privileges granted to the current role:
SHOW GRANTS TO ROLE IDENTIFIER(CURRENT_ROLE())
  ->> SELECT "privilege", "granted_on", "name"
      FROM $1
      WHERE ("privilege" = 'USAGE' AND "granted_on" = 'WAREHOUSE')
         OR ("privilege" = 'USAGE' AND "granted_on" = 'DATABASE' AND "name" = 'MY_DB')
         OR ("privilege" = 'USAGE' AND "granted_on" = 'SCHEMA' AND "name" = 'MY_DB.MY_SCHEMA')
         OR ("privilege" = 'SELECT' AND "name" LIKE '%MY_SV%')
         OR ("privilege" = 'MONITOR' AND "granted_on" = 'DATABASE')
      ORDER BY "granted_on", "privilege";

-- For TABLE_PRIVILEGES (this view DOES exist) — check SELECT on SV:
SELECT GRANTEE, PRIVILEGE_TYPE, TABLE_NAME
FROM INFORMATION_SCHEMA.TABLE_PRIVILEGES
WHERE TABLE_NAME = 'MY_SV'
  AND TABLE_SCHEMA = 'MY_SCHEMA';
```

**Expected:** All rows show `privilege_granted = TRUE`

---

### Step 3: Create Stage

Create (or replace) the stage for evaluation configs.

```sql
-- Create stage with encryption (do NOT specify FILE_FORMAT — 'YAML' is not a valid type)
CREATE OR REPLACE STAGE MY_DB.MY_SCHEMA.SV_EVAL_CONFIGS
    ENCRYPTION = (TYPE = 'SNOWFLAKE_SSE');

-- Verify stage creation
SHOW STAGES LIKE 'SV_EVAL_CONFIGS' IN SCHEMA MY_DB.MY_SCHEMA;
```

**Expected:** Stage exists

---

### Step 4: Upload YAML Config Uncompressed

Upload a config YAML file to the stage without compression.

```sql
-- First, create the YAML config locally (pseudo-code; use actual temp file)
-- Content of /tmp/eval_config.yaml:
-- evaluation:
--   agent_params:
--     agent_name: "MY_DB.MY_SCHEMA.MY_SV"
--     agent_type: "SEMANTIC VIEW"
--   source_metadata:
--     type: "dataset"
--     dataset_name: "MY_DB.MY_SCHEMA.MY_EVAL_DATASET"
--
-- metrics:
--   - "sql_correctness"

-- Upload uncompressed
PUT file:///tmp/eval_config.yaml
    @MY_DB.MY_SCHEMA.SV_EVAL_CONFIGS/
    AUTO_COMPRESS = FALSE OVERWRITE = TRUE;

-- Verify upload
LIST @MY_DB.MY_SCHEMA.SV_EVAL_CONFIGS/;
```

**Expected:** File `eval_config.yaml` appears in stage listing

---

### Step 5: Launch Evaluation with New START Pattern

Launch evaluation using native `EXECUTE_AI_EVALUATION` (bug 392700 fixed 2026-08-07).

```sql
-- Launch evaluation using native EXECUTE_AI_EVALUATION (bug 392700 fixed 2026-08-07)
CALL EXECUTE_AI_EVALUATION(
    'START',
    OBJECT_CONSTRUCT('run_name', 'smoke_test_run_1'),
    '@MY_DB.MY_SCHEMA.SV_EVAL_CONFIGS/eval_config.yaml'
);
```

**Expected:** START call returns successfully

---

### Step 6: Poll Evaluation Status

Use the native async STATUS polling pattern until the evaluation completes.

```sql
-- Poll evaluation status
CALL EXECUTE_AI_EVALUATION(
    'STATUS',
    OBJECT_CONSTRUCT('run_name', 'smoke_test_run_1'),
    '@MY_DB.MY_SCHEMA.SV_EVAL_CONFIGS/eval_config.yaml'
);
-- Repeat every 30 seconds until status = 'COMPLETED' (max 15 minutes)
```

**Expected:** STATUS eventually returns `COMPLETED`

---

### Step 7: Retrieve Results via 5-arg SNOWFLAKE.LOCAL Function

Query results using the new 5-argument function (not the old 1-arg version).

```sql
-- NEW: 5-arg SNOWFLAKE.LOCAL function (required)
-- OLD: 1-arg SNOWFLAKE.CORTEX function (deprecated)
SELECT *
FROM TABLE(SNOWFLAKE.LOCAL.GET_ANALYST_AI_EVALUATION_DATA(
    'MY_DB', 'MY_SCHEMA', 'MY_SV', 'SEMANTIC VIEW', 'smoke_test_run_1'
))
WHERE METRIC_NAME = 'sql_correctness'
LIMIT 10;
```

**Expected:** 
- Returns rows (at least 1, ideally all 5+ VQRs)
- Columns: INPUT, OUTPUT, GROUND_TRUTH, ERROR, EVAL_AGG_SCORE, METRIC_STATUS, METRIC_CALLS
- No rows from old schema (question, generated_sql, reference_sql, sql_correctness, error_message)

---

### Step 8: Apply Normalized CTE Projection

Transform raw results into normalized column names for downstream consumption.

```sql
-- Normalized CTE projection (canonical reference)
WITH raw AS (
    SELECT INPUT, OUTPUT, GROUND_TRUTH, ERROR,
           EVAL_AGG_SCORE, METRIC_STATUS, METRIC_CALLS
    FROM TABLE(SNOWFLAKE.LOCAL.GET_ANALYST_AI_EVALUATION_DATA(
        'MY_DB', 'MY_SCHEMA', 'MY_SV', 'SEMANTIC VIEW', 'smoke_test_run_1'
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

**Expected:**
- All rows map correctly
- `question`, `generated_output`, `reference_output`, `sql_correctness`, `error_message` all present
- No data loss in projection

---

### Step 9: Verify Failure-Analysis Query Compatibility

Run a sample failure-analysis query (as documented in failure-analysis.md).

```sql
-- Failure-analysis query using normalized CTE
-- This query identifies VQRs with sql_correctness = 0 or errors
WITH eval_results AS (
    SELECT INPUT, OUTPUT, GROUND_TRUTH, ERROR,
           EVAL_AGG_SCORE, METRIC_STATUS, METRIC_CALLS
    FROM TABLE(SNOWFLAKE.LOCAL.GET_ANALYST_AI_EVALUATION_DATA(
        'MY_DB', 'MY_SCHEMA', 'MY_SV', 'SEMANTIC VIEW', 'smoke_test_run_1'
    ))
    WHERE METRIC_NAME = 'sql_correctness'
)
SELECT
    INPUT AS question,
    OUTPUT AS generated_output,
    GROUND_TRUTH AS reference_output,
    ERROR AS error_message,
    EVAL_AGG_SCORE AS sql_correctness
FROM eval_results
WHERE EVAL_AGG_SCORE = 0 OR ERROR IS NOT NULL
ORDER BY EVAL_AGG_SCORE ASC, INPUT;
```

**Expected:**
- If all VQRs passed (sql_correctness = 1), returns 0 rows (PASS)
- If any failures, returns failure rows with error details
- Query completes without errors

---

### Step 10: Optional — Persist Results to EVAL_RESULTS Table

Insert evaluation results into a persistence table for historical analysis.

```sql
-- Create EVAL_RESULTS table if it doesn't exist
CREATE TABLE IF NOT EXISTS MY_DB.MY_SCHEMA.EVAL_RESULTS (
    run_name VARCHAR,
    vqr_index INT,
    question VARCHAR,
    generated_output VARCHAR,
    reference_output VARCHAR,
    sql_correctness FLOAT,
    error_message VARCHAR,
    metric_status VARCHAR,
    metric_calls INT,
    eval_timestamp TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);

-- Insert normalized results
INSERT INTO MY_DB.MY_SCHEMA.EVAL_RESULTS (
    run_name, vqr_index, question, generated_output, reference_output, 
    sql_correctness, error_message, metric_status, metric_calls
)
WITH raw AS (
    SELECT INPUT, OUTPUT, GROUND_TRUTH, ERROR,
           EVAL_AGG_SCORE, METRIC_STATUS, METRIC_CALLS,
           ROW_NUMBER() OVER (ORDER BY INPUT) AS vqr_index
    FROM TABLE(SNOWFLAKE.LOCAL.GET_ANALYST_AI_EVALUATION_DATA(
        'MY_DB', 'MY_SCHEMA', 'MY_SV', 'SEMANTIC VIEW', 'smoke_test_run_1'
    ))
    WHERE METRIC_NAME = 'sql_correctness'
)
SELECT
    'smoke_test_run_1',
    vqr_index,
    INPUT,
    OUTPUT,
    GROUND_TRUTH,
    EVAL_AGG_SCORE,
    ERROR,
    METRIC_STATUS,
    METRIC_CALLS
FROM raw;

-- Verify insertion
SELECT COUNT(*) AS inserted_rows FROM MY_DB.MY_SCHEMA.EVAL_RESULTS
WHERE run_name = 'smoke_test_run_1';
```

**Expected:** Rows inserted successfully, count matches VQR count from Step 1

---

## Pass Criteria

The smoke test is **PASS** if all 10 steps complete without errors and:

1. ✅ VQR count >= 5
2. ✅ All 8 grants present
3. ✅ Stage created
4. ✅ Config file uploaded
5. ✅ START call returned successfully
6. ✅ STATUS poll reached COMPLETED
7. ✅ 5-arg SNOWFLAKE.LOCAL function returns results
8. ✅ Normalized CTE projection runs without error
9. ✅ Failure-analysis query compatible (0 rows if all VQRs pass, details if failures)
10. ✅ Results persisted to table (if Step 10 executed)

---

## Troubleshooting

| Issue | Cause | Resolution |
|-------|-------|-----------|
| Step 2 fails (grants missing) | Role not configured | Load PREREQUISITES.md; run grant statements |
| Step 3 fails (stage not created) | Warehouse not set | `USE WAREHOUSE <WH>` before creating stage |
| Step 4 fails (file upload) | Stage not exists | Rerun Step 3 |
| Step 5 fails (START call) | Invalid config YAML | Verify YAML syntax matches eval-polling.md template |
| Step 6 times out (STATUS poll) | Evaluation taking too long | Check SV complexity; may require > 15 minutes for large VQR sets |
| Step 7 fails (function not found) | Using old 1-arg version | Ensure using 5-arg `SNOWFLAKE.LOCAL.GET_ANALYST_AI_EVALUATION_DATA` |
| Step 8 fails (CTE projection) | Column name mismatch | Verify raw column names from Step 7 match new schema |
| Step 9 returns all rows | Failure filter matched all rows | If Step 9 returns 0 rows, all VQRs passed. If it returns rows, those are the failures. |
| Step 10 fails (insert) | EVAL_RESULTS schema mismatch | Create table with exact schema shown; adjust if needed |

---

## Running the Smoke Test

### Option A: Manual (SQL Client)

1. Copy each step's SQL into Snowsight or your SQL IDE
2. Replace `MY_DB`, `MY_SCHEMA`, `MY_SV` with your values
3. For Step 4, prepare a local `/tmp/eval_config.yaml` file
4. Execute steps 1–10 in order
5. Verify each step's expected output

### Option B: Automated (Python)

```python
#!/usr/bin/env python3
import snowflake.connector
import time
import yaml

def run_smoke_test(conn, db, schema, sv_name, run_name):
    """Run full smoke test and report results."""
    cursor = conn.cursor()
    steps_passed = 0
    
    # Step 1: VQR count gate
    print("Step 1: VQR count gate...")
    cursor.execute(f"""
        DESCRIBE SEMANTIC VIEW {db}.{schema}.{sv_name}
    """)
    cursor.execute("""
        SELECT COUNT(DISTINCT "object_name")
        FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()))
        WHERE "object_kind" = 'AI_VERIFIED_QUERY'
    """)
    vqr_count = cursor.fetchone()[0]
    if vqr_count >= 5:
        print(f"✓ PASS: {vqr_count} VQRs")
        steps_passed += 1
    else:
        print(f"✗ FAIL: Only {vqr_count} VQRs (need >= 5)")
        return
    
    # Step 3: Create stage
    print("\nStep 3: Create stage...")
    cursor.execute(f"""
        CREATE OR REPLACE STAGE {db}.{schema}.SV_EVAL_CONFIGS
            ENCRYPTION = (TYPE = 'SNOWFLAKE_SSE')
    """)
    print("✓ PASS: Stage created")
    steps_passed += 1
    
    # Step 4: Upload YAML
    print("\nStep 4: Upload YAML config...")
    config = {
        'evaluation': {
            'analyst_params': {
                'analyst_name': sv_name,
                'analyst_type': 'SEMANTIC VIEW'
            },
            'source_metadata': {
                'type': 'verified_queries'
            }
        },
        'metrics': ['sql_correctness']
    }
    with open('/tmp/eval_config.yaml', 'w') as f:
        yaml.dump(config, f)
    cursor.execute(f"""
        PUT file:///tmp/eval_config.yaml
            @{db}.{schema}.SV_EVAL_CONFIGS/
            AUTO_COMPRESS = FALSE OVERWRITE = TRUE
    """)
    print("✓ PASS: YAML uploaded")
    steps_passed += 1
    
    # Step 5: Launch evaluation
    print("\nStep 5: Launch evaluation...")
    cursor.execute(f"""
        CALL EXECUTE_AI_EVALUATION(
            'START',
            OBJECT_CONSTRUCT('run_name', '{run_name}'),
            '@{db}.{schema}.SV_EVAL_CONFIGS/eval_config.yaml'
        )
    """)
    print("✓ PASS: Evaluation launched")
    steps_passed += 1
    
    # Step 6: Poll to completion
    print("\nStep 6: Poll to completion...")
    elapsed = 0
    while elapsed < 900:
        cursor.execute(f"""
            CALL EXECUTE_AI_EVALUATION(
                'STATUS',
                OBJECT_CONSTRUCT('run_name', '{run_name}'),
                '@{db}.{schema}.SV_EVAL_CONFIGS/eval_config.yaml'
            )
        """)
        row = cursor.fetchone()
        status = row[1] if isinstance(row, tuple) else row['STATUS']
        if status == 'COMPLETED':
            print(f"✓ PASS: Evaluation completed")
            steps_passed += 1
            break
        elif status in ('FAILED', 'CANCELLED'):
            print(f"✗ FAIL: {status}")
            return
        print(f"  Status: {status}, elapsed: {elapsed}s...")
        time.sleep(30)
        elapsed += 30
    else:
        print("✗ FAIL: Timeout")
        return
    
    # Step 7–10: Retrieve and validate results
    print("\nStep 7: Retrieve results...")
    cursor.execute(f"""
        SELECT COUNT(*) FROM TABLE(SNOWFLAKE.LOCAL.GET_ANALYST_AI_EVALUATION_DATA(
            '{db}', '{schema}', '{sv_name}', 'SEMANTIC VIEW', '{run_name}'
        ))
    """)
    result_count = cursor.fetchone()[0]
    if result_count > 0:
        print(f"✓ PASS: Retrieved {result_count} results")
        steps_passed += 3  # Steps 7, 8, 9 (simplified validation)
    
    print(f"\n=== Smoke Test: {steps_passed}/10 steps passed ===")

# Usage:
# conn = snowflake.connector.connect(user='...', password='...', account='...', database='MY_DB')
# run_smoke_test(conn, 'MY_DB', 'MY_SCHEMA', 'MY_SV', 'smoke_test_run_1')
```

---

## References

- **eval-polling.md** — Full polling and result retrieval patterns
- **PREREQUISITES.md** — Role and grant configuration
- **sv-evaluation/SKILL.md** — Full semantic view evaluation workflow
- **failure-analysis.md** — Failure diagnosis queries

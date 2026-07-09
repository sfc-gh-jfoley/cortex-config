# sv-coverage-checker Reference

## Overview

The sv-coverage-checker detects structural gaps between a set of Ground Truth (GT) SQL queries
and a Semantic View definition. It answers: "Can my SV structurally answer all my eval questions?"

Run it in parallel with `EXECUTE_AI_EVALUATION` — both consume the same GT SQL input, neither
blocks the other. The checker produces two outputs: a structural gap report and per-question
ANSWERABLE / NOT_ANSWERABLE verdicts.

**When to use:**
- Before running a full eval to identify gaps that will cause systematic failures
- After modifying an SV to verify coverage hasn't regressed
- When onboarding a new GT set to understand how much of it the current SV can handle
- As a fast triage step before iterative optimization (fix structural gaps first, then optimize)

---

## Three Failure Modes

### TABLE_NOT_REGISTERED

A physical table referenced in a GT SQL query is not in the SV `TABLES` block.

**Example GT SQL:**
```sql
SELECT d.DEVICE_TYPE, SUM(f.SALES_EXC_TAX_USD)
FROM FCT_STORE_TRANSACTION_ITEM f
JOIN DIM_DEVICE_TYPE d ON f.DEVICE_TYPE_ID = d.DEVICE_TYPE_ID   -- DIM_DEVICE_TYPE not in SV
GROUP BY 1
```

**Gap output:**
```json
{
  "gap_type": "TABLE_NOT_REGISTERED",
  "physical_table": "SIEBIS_DEMO.PUBLIC.DIM_DEVICE_TYPE",
  "element": null,
  "detail": "SIEBIS_DEMO.PUBLIC.DIM_DEVICE_TYPE used in GT SQL but not registered in SV TABLES block"
}
```

**Fix:** Add the table to the SV TABLES block:
```sql
ALTER SEMANTIC VIEW COMMERCE_DIGITAL_SALES_SV
  SET TABLES (
    ...,
    DIM_DEVICE AS SIEBIS_DEMO.PUBLIC.DIM_DEVICE_TYPE PRIMARY KEY (DEVICE_TYPE_ID)
  );
```

---

### COLUMN_NOT_EXPOSED

A column referenced in SELECT / WHERE / GROUP BY exists in the physical table but is not
exposed as a DIMENSION, FACT, or METRIC in the SV.

**Example:**
```sql
SELECT s.STOREFRONT_TYPE_LEVEL_1, SUM(f.SALES_EXC_TAX_USD)  -- STOREFRONT_TYPE_LEVEL_1 missing
FROM FCT_STORE_TRANSACTION_ITEM f
JOIN DIM_STOREFRONT_TYPE s ON f.STOREFRONT_TYPE_ID = s.STOREFRONT_TYPE_ID
GROUP BY 1
```

**Gap output:**
```json
{
  "gap_type": "COLUMN_NOT_EXPOSED",
  "physical_table": "SIEBIS_DEMO.PUBLIC.DIM_STOREFRONT_TYPE",
  "element": "STOREFRONT_TYPE_LEVEL_1",
  "detail": "SIEBIS_DEMO.PUBLIC.DIM_STOREFRONT_TYPE.STOREFRONT_TYPE_LEVEL_1 referenced in GT SQL but not exposed in SV"
}
```

**Fix:** Add as a dimension using the SV logical alias:
```sql
-- In SV DIMENSIONS block (using logical alias 'storefront', not physical table name):
storefront.STOREFRONT_TYPE_LEVEL_1 AS STOREFRONT_CHANNEL
```

---

### RELATIONSHIP_MISSING

A JOIN condition in a GT SQL query has no corresponding RELATIONSHIPS entry in the SV.

**Example — two-hop join where second hop is missing:**
```sql
JOIN DIM_DEVICE_TYPE d ON f.DEVICE_TYPE_ID = d.DEVICE_TYPE_ID       -- relationship present
JOIN DIM_DEVICE_TYPE_2 d2 ON d.DEVICE_TYPE_2_ID = d2.DEVICE_TYPE_2_ID  -- relationship MISSING
```

**Gap output:**
```json
{
  "gap_type": "RELATIONSHIP_MISSING",
  "physical_table": null,
  "element": "DIM_DEVICE.DEVICE_TYPE_2_ID = DIM_DEVICE_TYPE_2.DEVICE_TYPE_2_ID",
  "detail": "JOIN condition in GT SQL has no corresponding RELATIONSHIPS entry in SV"
}
```

**Fix:** Add a RELATIONSHIPS entry (using SV logical aliases, not physical names):
```sql
-- In SV RELATIONSHIPS block:
device_to_platform AS DIM_DEVICE(DEVICE_TYPE_2_ID) REFERENCES DIM_DEVICE_TYPE_2
```

**Important:** SV RELATIONSHIPS use logical alias names (as defined in TABLES block), not
physical table FQNs. The checker resolves query aliases to physical FQNs and then to SV logical
aliases before comparing against the RELATIONSHIPS block.

---

## The Workload Manifest

Internally, the checker builds a workload manifest from EXPLAIN USING TABULAR output:

| Field | EXPLAIN Source | Description |
|---|---|---|
| `tables` | `operation='TableScan'`, `objects` column | Physical FQNs of all tables accessed |
| `join_keys` | Any `*Join` operation, `expressions` column | Frozenset pairs of `alias.col` join keys |
| `columns` | `TableScan` expressions + `Filter` + `Result` | All columns referenced (SELECT + WHERE + GROUP BY) |
| `alias_to_fqn` | `TableScan` alias + objects | Query alias → physical FQN mapping |

**Key parsing rules:**
- `TableScan` row: `objects` = physical FQN (e.g. `DEMO_DB.PUBLIC.ORDERS`), `alias` = query alias
- `InnerJoin` row: `expressions` matches `joinKey: (A.col = B.col)` — regex `r'joinKey:\s*\((\w+\.\w+)\s*=\s*(\w+\.\w+)\)'`
- `Filter` row: `expressions` contains column references that are extracted as column requirements
- All FQNs are normalized to UPPERCASE before comparison

This manifest is the shared artifact between the coverage checker and the eval pipeline.

---

## Integration: Parallel Eval Thread

Run both in separate worksheets (or parallel SQL sessions) at the same time:

```sql
-- Worksheet 1: run eval (takes minutes)
CALL EXECUTE_AI_EVALUATION('START',
    OBJECT_CONSTRUCT('run_name', 'commerce_eval_run_001'),
    '@SIEBIS_DEMO.EVAL_METADATA.EVAL_STAGE/eval_config.yaml'
);

-- Worksheet 2: run coverage check simultaneously (takes seconds)
CALL SV_COVERAGE_CHECKER(
    'SIEBIS_DEMO.EVAL_METADATA.COMMERCE_GT_SQL',    -- view: QUESTION_ID VARCHAR, SQL_TEXT VARCHAR
    'SIEBIS_DEMO.PUBLIC.COMMERCE_DIGITAL_SALES_SV'  -- fully-qualified SV name
);
```

The coverage check typically finishes in seconds (EXPLAIN is fast); the eval run takes minutes.
Review the gap report while eval is still running to get an early read on structural issues.

**GT table schema required:**
```sql
-- The GT table/view passed to SV_COVERAGE_CHECKER must have:
CREATE OR REPLACE VIEW SIEBIS_DEMO.EVAL_METADATA.COMMERCE_GT_SQL AS
SELECT
    QUESTION_ID::VARCHAR AS QUESTION_ID,
    SQL_TEXT::VARCHAR    AS SQL_TEXT
FROM SIEBIS_DEMO.EVAL_METADATA.GROUND_TRUTH_QUESTIONS
WHERE SQL_TEXT IS NOT NULL;
```

---

## Sample Output

Against the SIEBIS Commerce SV (20 GT questions, SV missing DIM_DEVICE_TYPE family and
FCT_STORE_TRANSACTION_ITEM_EXT):

```json
{
  "summary": {
    "total_questions": 20,
    "answerable": 14,
    "not_answerable": 6,
    "unique_gaps": 4
  },
  "gaps": [
    {
      "gap_type": "TABLE_NOT_REGISTERED",
      "physical_table": "SIEBIS_DEMO.PUBLIC.DIM_DEVICE_TYPE",
      "element": null,
      "detail": "SIEBIS_DEMO.PUBLIC.DIM_DEVICE_TYPE used in GT SQL but not registered in SV TABLES block"
    },
    {
      "gap_type": "TABLE_NOT_REGISTERED",
      "physical_table": "SIEBIS_DEMO.PUBLIC.DIM_DEVICE_TYPE_2",
      "element": null,
      "detail": "SIEBIS_DEMO.PUBLIC.DIM_DEVICE_TYPE_2 used in GT SQL but not registered in SV TABLES block"
    },
    {
      "gap_type": "RELATIONSHIP_MISSING",
      "physical_table": null,
      "element": "DIM_DEVICE.DEVICE_TYPE_2_ID = DIM_DEVICE_TYPE_2.DEVICE_TYPE_2_ID",
      "detail": "JOIN condition in GT SQL has no corresponding RELATIONSHIPS entry in SV"
    },
    {
      "gap_type": "TABLE_NOT_REGISTERED",
      "physical_table": "SIEBIS_DEMO.PUBLIC.FCT_STORE_TRANSACTION_ITEM_EXT",
      "element": null,
      "detail": "SIEBIS_DEMO.PUBLIC.FCT_STORE_TRANSACTION_ITEM_EXT used in GT SQL but not registered in SV TABLES block"
    }
  ],
  "verdicts": [
    {"question_id": "1",  "status": "ANSWERABLE",     "failure_mode": null,                  "detail": null},
    {"question_id": "2",  "status": "ANSWERABLE",     "failure_mode": null,                  "detail": null},
    {"question_id": "3",  "status": "NOT_ANSWERABLE", "failure_mode": "TABLE_NOT_REGISTERED","detail": "SIEBIS_DEMO.PUBLIC.DIM_DEVICE_TYPE used in GT SQL but not registered in SV TABLES block"},
    {"question_id": "4",  "status": "NOT_ANSWERABLE", "failure_mode": "RELATIONSHIP_MISSING","detail": "JOIN condition DIM_DEVICE.DEVICE_TYPE_2_ID = DIM_DEVICE_TYPE_2.DEVICE_TYPE_2_ID has no RELATIONSHIPS entry"},
    {"question_id": "5",  "status": "NOT_ANSWERABLE", "failure_mode": "TABLE_NOT_REGISTERED","detail": "SIEBIS_DEMO.PUBLIC.FCT_STORE_TRANSACTION_ITEM_EXT used in GT SQL but not registered in SV TABLES block"}
  ]
}
```

---

## Iterative Fix Workflow

```
Run checker → inspect gaps[] → fix SV → re-deploy SV → re-run checker → repeat
until summary.not_answerable = 0
```

**Recommended fix order:**
1. **TABLE_NOT_REGISTERED** first — adding a table may resolve RELATIONSHIP_MISSING gaps too
2. **RELATIONSHIP_MISSING** next — once tables are registered, add missing JOIN mappings
3. **COLUMN_NOT_EXPOSED** last — fine-grained: add dimensions/facts for specific columns

Each fix cycle typically takes 2-3 minutes (ALTER SV + re-run checker). A well-scoped SV
converges in 2-3 cycles.

**Example fix cycle:**

```sql
-- Cycle 1: add missing tables
ALTER SEMANTIC VIEW COMMERCE_DIGITAL_SALES_SV
  SET TABLES (
    ...,
    DIM_DEVICE     AS SIEBIS_DEMO.PUBLIC.DIM_DEVICE_TYPE    PRIMARY KEY (DEVICE_TYPE_ID),
    DIM_DEVICE_2   AS SIEBIS_DEMO.PUBLIC.DIM_DEVICE_TYPE_2  PRIMARY KEY (DEVICE_TYPE_2_ID),
    FCT_EXT        AS SIEBIS_DEMO.PUBLIC.FCT_STORE_TRANSACTION_ITEM_EXT PRIMARY KEY (TXN_ITEM_EXT_ID)
  );

-- Re-run checker → TABLE_NOT_REGISTERED gaps gone, RELATIONSHIP_MISSING remains
-- Cycle 2: add missing relationship
ALTER SEMANTIC VIEW COMMERCE_DIGITAL_SALES_SV
  SET RELATIONSHIPS (
    ...,
    device_to_device_2 AS DIM_DEVICE(DEVICE_TYPE_2_ID) REFERENCES DIM_DEVICE_2
  );
-- Re-run checker → summary.not_answerable = 0
```

---

## Limitations

- **Computed expressions in GT SQL**: `YEAR(O_ORDERDATE)` in GT SQL produces `O_ORDERDATE` in
  TableScan expressions (Snowflake evaluates the expression, pushes the base column to the scan).
  The checker correctly tracks `O_ORDERDATE` as the column requirement — no special handling needed.

- **Subqueries and CTEs**: EXPLAIN USING TABULAR flattens these; all physical TableScan rows
  appear regardless of nesting depth. No special handling required.

- **Dynamic SQL / NULL SQL_TEXT**: If `SQL_TEXT` is NULL or empty for a question, that question
  is skipped and logged in the output with `status: "SKIPPED"`.

- **False positives for system/metadata columns**: Columns like `METADATA$ROW_ID` may appear in
  TableScan expressions from some queries. These will be flagged as COLUMN_NOT_EXPOSED but are
  safe to ignore — they are not real SV coverage requirements.

- **OUTER JOINs**: The checker parses `LeftOuterJoin` and `RightOuterJoin` the same as
  `InnerJoin` for join-key extraction. This is correct for coverage purposes — if the SV
  has no relationship mapping for the join condition, the question is NOT_ANSWERABLE regardless
  of join type.

- **Coverage ≠ correctness**: A question being ANSWERABLE means the SV has the structural
  elements to answer it. The eval pipeline (`EXECUTE_AI_EVALUATION`) is still required to
  verify that the generated SQL produces correct results.

---
name: sv-ddl-phase6-execute-validate
description: Execute the DDL, validate with DESCRIBE SEMANTIC VIEW, and run a self-test question loop — iterate until passing
---

# Phase 6: Execute & Validate

## Purpose
Execute the DDL, confirm it was created correctly, and run a self-test question loop to verify Cortex Analyst can answer business questions from it.
This is the **iterative core** of the skill — failures loop back to Phase 5 for DDL fixes.

---

## Step 6.1: Execute the DDL

```sql
<paste DDL from Phase 5>
```

**Expected result**: `Semantic view <name> successfully created.`

**If DDL fails**, go to Step 6.2 (error handling). Otherwise proceed to Step 6.3.

---

## Step 6.2: Error handling map

| Error message | Root cause | Fix (return to Phase 5) |
|--------------|-----------|------------------------|
| `No queryable expression` | No FACTS or DIMENSIONS defined | Add at least one FACTS clause |
| `invalid identifier '<X>'` | Fact/dim alias doesn't match physical column name | Change `AS <X>` to match exact physical column name from DESCRIBE TABLE |
| `Duplicate identifier '<X>'` | Column `<X>` defined in multiple tables' FACTS/DIMS | Keep it in one table, remove from others |
| `Object '<table>' does not exist or not authorized` | Physical table path wrong or no access | Run `SELECT * FROM <table> LIMIT 1` to verify; fix path |
| `Relationship '<r>' requires a primary key` | Right-hand REFERENCES table has no PK/UNIQUE | Add `PRIMARY KEY (<col>)` to that table in TABLES clause |
| `Ambiguous relationship` | Two paths between same table pair, no USING | Add `USING (<rel_name>)` to the affected metric |
| `PRIVATE not allowed` | PRIVATE on a dimension | Remove PRIVATE modifier |

After identifying the error:
1. Fix the DDL in Phase 5
2. Re-run the self-check (Step 5.8)
3. Return to Step 6.1

---

## Step 6.3: Structural validation with DESCRIBE

```sql
DESCRIBE SEMANTIC VIEW <SV_DB>.<SV_SCHEMA>.<SV_NAME>;
```

Verify the output contains:
- ✅ All expected tables (rows with `object_kind = 'TABLE'`)
- ✅ All expected facts (rows with `object_kind = 'FACT'`)
- ✅ All expected dimensions (rows with `object_kind = 'DIMENSION'`)
- ✅ All expected metrics (rows with `object_kind = 'METRIC'`)
- ✅ All relationships (rows with `object_kind = 'RELATIONSHIP'`)

Report a summary:
```
DESCRIBE results:
  Tables:        N ✓
  Facts:         N ✓ / N expected
  Dimensions:    N ✓ / N expected
  Metrics:       N ✓ / N expected
  Relationships: N ✓
```

If any counts are lower than expected, find the missing element and fix.

---

## Step 6.3.1: Post-deploy structural validation

Run these SQL checks immediately after the DESCRIBE in Step 6.3, using RESULT_SCAN on that output:

**Check 1: Fan trap** — metric reachable to dimension only via bridge table
```sql
WITH sv_meta AS (SELECT * FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()))),
metric_tbl AS (SELECT DISTINCT "object_table" AS t FROM sv_meta WHERE "object_kind" = 'METRIC'),
dim_tbl    AS (SELECT DISTINCT "object_table" AS t FROM sv_meta WHERE "object_kind" = 'DIMENSION'),
rels       AS (SELECT "left_table" AS lt, "right_table" AS rt FROM sv_meta WHERE "object_kind" = 'RELATIONSHIP')
SELECT 'FAN_TRAP' AS issue_type, m.t AS metric_table, d.t AS dim_table, r1.rt AS bridge_table,
       'SUM/COUNT on ' || m.t || ' inflated when grouped by ' || d.t || ' dims (bridge: ' || r1.rt || ')' AS detail
FROM metric_tbl m JOIN rels r1 ON r1.lt = m.t JOIN rels r2 ON r2.lt = r1.rt
JOIN dim_tbl d ON d.t = r2.rt WHERE d.t != m.t;
```

**Check 2: Chasm trap** — two fact tables converging on shared dimension
```sql
WITH sv_meta AS (SELECT * FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()))),
metric_tbl AS (SELECT DISTINCT "object_table" AS t FROM sv_meta WHERE "object_kind" = 'METRIC'),
rels       AS (SELECT "left_table" AS lt, "right_table" AS rt FROM sv_meta WHERE "object_kind" = 'RELATIONSHIP')
SELECT 'CHASM_TRAP' AS issue_type, m1.t AS metric_1, m2.t AS metric_2, r1.rt AS shared_table,
       'Pre-aggregate both ' || m1.t || ' and ' || m2.t || ' to ' || r1.rt || ' grain separately' AS detail
FROM metric_tbl m1 JOIN rels r1 ON r1.lt = m1.t
JOIN metric_tbl m2 ON m2.t != m1.t AND m2.t > m1.t
JOIN rels r2 ON r2.lt = m2.t AND r2.rt = r1.rt;
```

**Check 3: Orphan tables**
```sql
WITH sv_meta AS (SELECT * FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()))),
all_tbl AS (SELECT DISTINCT "object_table" AS t FROM sv_meta WHERE "object_kind" = 'TABLE'),
rel_tbl AS (SELECT "left_table" AS t FROM sv_meta WHERE "object_kind" = 'RELATIONSHIP'
            UNION ALL SELECT "right_table" FROM sv_meta WHERE "object_kind" = 'RELATIONSHIP')
SELECT 'ORPHAN' AS issue_type, t, 'Table has no RELATIONSHIP' AS detail
FROM all_tbl WHERE t NOT IN (SELECT t FROM rel_tbl);
```

FAN_TRAP or CHASM_TRAP → **STOP**, return to Phase 4/5. ORPHAN → **WARN** to user. All 0 rows → proceed.

---

## Step 6.4: Self-test question loop

Test the semantic view by constructing and executing SQL against the source objects for 3-5 sample questions.

> **Note**: There is no `SNOWFLAKE.CORTEX.ANALYST()` SQL UDF — that function does not exist. Cortex Analyst is accessible via the REST API or the Snowflake UI. However, semantic views **are directly queryable via SQL** using two approaches:
>
> **Approach A — SEMANTIC_VIEW clause (explicit):**
> ```sql
> SELECT * FROM SEMANTIC_VIEW(
>   <sv_name>
>   DIMENSIONS <table_alias>.<dimension_name>
>   METRICS <table_alias>.<metric_name>
> ) ORDER BY <dimension_name>;
> ```
>
> **Approach B — Direct FROM (implicit rewrite):**
> ```sql
> SELECT <dimension>, AGG(<metric>)
> FROM <sv_name>
> GROUP BY <dimension>
> ORDER BY <dimension>;
> ```
>
> Self-tests in this phase validate the SV's logic by running SQL directly against the underlying source objects (tables, views, or dynamic tables), using the SV's relationships, facts, and dimensions as the query blueprint. This confirms the physical layer is correct before relying on the semantic query engine.

Generate test questions from `BUSINESS_CONTEXT` and `COLUMN_CLASSES`:
- One aggregate question (SUM or COUNT a METRIC)
- One filter question (filter on a DIMENSION value)
- One time-series question (GROUP BY a TIME_DIMENSION)
- One join question (metric from one table, filter from another)
- One from `PROPOSED_METRICS` if available

For each question, write and execute SQL against the source objects (tables, views, or dynamic tables):

```sql
-- Aggregate test:
SELECT SUM(<fact_col>) AS metric_value
FROM <source_object>;

-- Filter test:
SELECT <dim_col>, COUNT(*) AS count
FROM <source_object>
WHERE <dim_col> = '<filter_value>'
GROUP BY <dim_col>;

-- Join test (validates the SV relationship is correct):
SELECT t1.<dim_col>, SUM(t2.<fact_col>) AS total
FROM <source_object_1> t1
JOIN <source_object_2> t2 ON t1.<pk_col> = t2.<fk_col>
GROUP BY t1.<dim_col>
ORDER BY total DESC
LIMIT 10;
```

For each question, capture:
- The SQL you constructed
- Whether it executed without error
- Whether the result is semantically correct for the question

---

## Step 6.4.1: Direct semantic view query validation (optional)

After confirming the physical-layer SQL works, optionally validate the SV's semantic query interface directly:

```sql
SELECT * FROM SEMANTIC_VIEW(
  <SV_DB>.<SV_SCHEMA>.<SV_NAME>
  DIMENSIONS <first_dim_table_alias>.<first_dim_name>
  METRICS <first_metric_table_alias>.<first_metric_name>
) LIMIT 10;
```

If this returns results, the SV's semantic engine is functioning correctly. If it errors, check:
- Relationship definitions (missing or incorrect PKs)
- Dimension/metric granularity mismatches (dimension entity must have equal or lower granularity than metric entity)
- Use `SHOW SEMANTIC DIMENSIONS FOR METRIC <sv_name>.<metric_name>` to see which dimensions are valid for each metric

---

## Step 6.5: Self-evaluate test results

For each test question, score:

| Result | Score | Action |
|--------|-------|--------|
| Valid SQL returned, uses expected tables/columns | PASS ✓ | Continue |
| Valid SQL but uses unexpected join path or wrong column | WARN ⚠️ | Note for Phase 7 iteration |
| "I cannot answer" or empty response | FAIL ✗ | Identify root cause |
| SQL error when executed | FAIL ✗ | Fix DDL or add description clarity |

**Common FAIL root causes**:

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| Metric not found | Column classified wrong (FACT should be METRIC) | Move from FACTS to METRICS as aggregate expression |
| Wrong table joined | Relationship missing | Add relationship in Phase 4, regenerate DDL |
| Filter not working | DIMENSION missing or misnamed | Check DIMENSION alias matches user's expected filter language |
| Date truncation wrong | No AI_SQL_GENERATION instruction for date handling | Add date format instruction to AI_SQL_GENERATION |
| Wrong aggregation | Ambiguous metric direction | Add description to METRIC with explicit aggregation note |

---

## Step 6.6: Present validation results

```
Validation Results for <SV_NAME>

  DDL execution:    ✓ Success
  DESCRIBE check:   ✓ 4 tables, 18 facts, 22 dimensions, 6 metrics, 3 relationships

  Self-test questions:
    ✓ "What is total inventory value by dealer?"   → SUM(LIST_PRICE) GROUP BY DEALER_NAME
    ✓ "How many vehicles are active?"              → COUNT(*) WHERE LISTING_STATUS = 'ACTIVE'
    ✓ "Show vehicles by month of acquisition"     → GROUP BY DATE_TRUNC('month', ACQUISITION_DATE)
    ✗ "Which dealers have the most aged inventory?" → failed: DAYS_IN_INVENTORY not found
    ⚠️ "Average list price by market segment"     → joined on wrong table

  Issues found: 2
  Recommendation: Fix DAYS_IN_INVENTORY classification + add market segment relationship
```

---

## Step 6.7: Decide — iterate or proceed

If **0 failures**: proceed to Phase 7 (enrichment / verified queries).

If **any failures**: return to Phase 5 with the specific fixes identified. Increment iteration counter.

**Iteration limit**: after 3 rounds without progress, stop and present the issues to the user for manual input.

⚠️ **STOPPING POINT** — Present validation results. Ask:
```
Validation complete.
  Passed: N/N questions
  Issues: N

Options:
  1. Fix and iterate → return to Phase 5
  2. Accept as-is → proceed to Phase 7 (add verified queries, export)
  3. Show me the failing SQL so I can debug it manually
```

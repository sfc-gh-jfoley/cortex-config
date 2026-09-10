# Failure Analysis Guide

Detailed guide for diagnosing semantic view evaluation failures by category. Use this after running `EXECUTE_AI_EVALUATION` to understand why VQRs scored below 1.0 and which mutation operator to apply.

---

## Failure Categories Overview

| Failure Pattern | Diagnosis | Fix (Mutation Operator) |
|---|---|---|
| Wrong table joined | Missing/wrong RELATIONSHIP in SV | `change_relationship` |
| Wrong column selected | Ambiguous descriptions, missing synonyms | `improve_description`, `add_synonym` |
| Wrong aggregation | Missing METRIC or wrong default_aggregation | `add_metric`, `refine_metric_expr` |
| Wrong time filter | No TIME_DIMENSION or wrong granularity | `add_time_dimension` |
| SQL syntax error | Invalid SV DDL (bad expression, wrong alias) | Manual DDL fix |
| Empty result set | Filter too restrictive or wrong table | `change_relationship`, `add_filter` |
| Analyst refuses | Question out of SV scope | `add_vqr` (teach by example) |
| Reference contaminated | Model applies metric filter; reference SQL does not | **Read-only analysis** (do not modify VQR) |

| FAN_TRAP | Generated SQL applies additive aggregate above many-to-one join; reference pre-aggregates | Move metric to bridge-table grain; see Section 9 |
| CHASM_TRAP | Generated SQL joins two fact tables on shared dim without per-fact CTEs | Pre-aggregate each fact to shared dimension grain; see Section 10 |
| JOIN_HALLUCINATION | Generated SQL joins on fewer or different columns than reference | `change_relationship`, add missing RELATIONSHIP to SV |
| GRANULARITY_MISMATCH | Generated SQL GROUP BY is at coarser level than reference | Add dimension at correct grain, or add guiding VQR |

---

## Automated Structural Analysis

Before manually reviewing individual VQRs, run EXPLAIN-based structural comparison for all failures. This auto-classifies most failure patterns faster than visual SQL comparison.

### Step A: Get failed VQRs with generated and reference SQL

```sql
WITH failures AS (
    SELECT
        INPUT           AS question,
        OUTPUT          AS generated_sql,
        GROUND_TRUTH    AS reference_sql,
        EVAL_AGG_SCORE  AS sql_correctness,
        ERROR           AS error_message
    FROM TABLE(SNOWFLAKE.LOCAL.GET_ANALYST_AI_EVALUATION_DATA(
        '<DB>', '<SCHEMA>', '<SV_NAME>', 'SEMANTIC VIEW', '<eval_name>'
    ))
    WHERE METRIC_NAME = 'sql_correctness'
      AND EVAL_AGG_SCORE < 1.0
)
SELECT * FROM failures;
```

### Step B: Run EXPLAIN on each pair

For each failed VQR, run in separate worksheets:
```sql
EXPLAIN USING TABULAR <generated_sql>;   -- paste as literal SQL
EXPLAIN USING TABULAR <reference_sql>;
```

### Step C: Classify by structural diff

| EXPLAIN signal | Category |
|---|---|
| Different `objects` in TableScan rows | **WRONG_TABLE** |
| Fewer or different join keys (joinkey column) | **JOIN_HALLUCINATION** |
| SUM/COUNT aggregate above a Join node not in reference plan | **FAN_TRAP** |
| Two separate Aggregate→TableScan paths converge at a Join; reference uses CTEs | **CHASM_TRAP** |
| Same tables/joins but GROUP BY columns differ | **GRANULARITY_MISMATCH** |
| Structurally identical plans but results differ | **DATA_FILTER_ERROR** or **REFERENCE_CONTAMINATED** |
| EXPLAIN fails on generated SQL | **SQL_SYNTAX_ERROR** |

---

### How to Identify

Compare `generated_sql` and `reference_sql` columns from eval results:

```sql
WITH raw AS (
  SELECT INPUT, OUTPUT, GROUND_TRUTH, ERROR, EVAL_AGG_SCORE, METRIC_STATUS, METRIC_CALLS
  FROM TABLE(SNOWFLAKE.LOCAL.GET_ANALYST_AI_EVALUATION_DATA(
    '<DB>', '<SCHEMA>', '<SV_FQN>', 'SEMANTIC VIEW', '<eval_name>'
  ))
  WHERE METRIC_NAME = 'sql_correctness'
)
SELECT
    INPUT AS question,
    OUTPUT AS generated_sql,
    GROUND_TRUTH AS reference_sql
FROM raw
WHERE EVAL_AGG_SCORE < 1.0;
```

**Signals:**
- Generated SQL uses `JOIN table_x` but reference uses `JOIN table_y`
- Generated SQL has more or fewer JOINs than reference
- Generated SQL joins on wrong columns (produces cartesian product or wrong matches)
- Result row count differs dramatically (10x or more)

**Example:**
```
Question: "What is revenue by customer segment?"
Generated: SELECT ... FROM orders JOIN products ON ...     ← wrong table
Reference: SELECT ... FROM orders JOIN customers ON ...   ← correct
```

### Root Cause Analysis

1. **Missing relationship:** Tables that should be joined are not connected in the SV RELATIONSHIPS section
2. **Ambiguous path:** Multiple join paths exist between tables; Analyst picks the wrong one
3. **Wrong join keys:** Relationship exists but uses wrong column pair
4. **Wrong join type:** INNER JOIN excludes rows that LEFT JOIN would include

### Investigation Steps

```sql
-- Check existing relationships
DESCRIBE SEMANTIC VIEW <SV_FQN>;
-- Look at RELATIONSHIPS section

-- Check if correct relationship exists
-- If missing: need change_relationship (add)
-- If wrong keys: need change_relationship (modify)
```

### Fix: `change_relationship`

**Add missing relationship:**
```sql
ALTER SEMANTIC VIEW <DB>.<SCHEMA>.<SV_NAME>
  ADD RELATIONSHIP orders_to_customers
    FROM orders (customer_id) REFERENCES customers (id)
    RELATIONSHIP_TYPE = MANY_TO_ONE;
```

**Modify wrong join type:**
```sql
ALTER SEMANTIC VIEW <DB>.<SCHEMA>.<SV_NAME>
  ALTER RELATIONSHIP orders_to_products
    SET RELATIONSHIP_TYPE = MANY_TO_ONE;
```

---

## 2. Wrong Column Selected

### How to Identify

**Signals:**
- Generated SQL uses correct tables and joins, but SELECTs or GROUPs BY the wrong column
- Column names are similar (e.g., `CREATED_DATE` vs `ORDER_DATE`, `STATUS` vs `ORDER_STATUS`)
- Generated SQL uses `column_a` where reference uses `column_b` from the same table

**Example:**
```
Question: "Show revenue by order date"
Generated: SELECT created_date, SUM(amount) ...   ← picked created_date (record creation)
Reference: SELECT order_date, SUM(amount) ...     ← correct (business date)
```

### Root Cause Analysis

1. **Ambiguous descriptions:** Two columns have similar/empty descriptions; Analyst can't differentiate
2. **Missing synonyms:** User phrasing ("order date") doesn't match column name (`ORDER_PLACED_AT`)
3. **Too many similar columns:** SV includes multiple date/status columns that confuse selection

### Investigation Steps

```sql
-- Examine column descriptions in SV DDL
DESCRIBE SEMANTIC VIEW <SV_FQN>;
-- Look for:
--   - Columns with empty descriptions
--   - Multiple columns with similar names
--   - Columns missing synonyms that match user phrasing
```

Compare the failed question's phrasing against column names and synonyms. If the user says "order date" but the column is `TRANSACTION_TIMESTAMP` with no synonyms, that's the gap.

### Fix: `improve_description` or `add_synonym`

**If column description is vague or missing:**
```sql
ALTER SEMANTIC VIEW <DB>.<SCHEMA>.<SV_NAME>
  ALTER COLUMN orders.created_date
    SET COMMENT = 'Internal record creation timestamp. NOT the business order date. Use ORDER_DATE for when the customer placed the order.';
```

**If user phrasing doesn't match column name:**
```sql
ALTER SEMANTIC VIEW <DB>.<SCHEMA>.<SV_NAME>
  ALTER COLUMN orders.order_placed_at
    SET SYNONYMS = ('order date', 'date ordered', 'purchase date');
```

**If too many confusing columns → consider `remove_column`:**
```sql
ALTER SEMANTIC VIEW <DB>.<SCHEMA>.<SV_NAME>
  DROP COLUMN orders.internal_audit_timestamp;
```

---

## 3. Wrong Aggregation

### How to Identify

**Signals:**
- Generated SQL uses correct tables and columns, but applies wrong aggregate function
- `SUM` vs `COUNT`, `AVG` vs `SUM`, missing `DISTINCT`, wrong `GROUP BY`
- Generated SQL has correct structure but produces numerically wrong results

**Example:**
```
Question: "What is the average order value?"
Generated: SELECT SUM(amount) / COUNT(*) ...         ← divides by all rows (including NULLs)
Reference: SELECT AVG(amount) ...                    ← correct
```

```
Question: "How many unique customers ordered?"
Generated: SELECT COUNT(customer_id) ...             ← counts all rows, not distinct
Reference: SELECT COUNT(DISTINCT customer_id) ...    ← correct
```

### Root Cause Analysis

1. **Missing metric:** No pre-defined metric for this calculation; Analyst improvises (badly)
2. **Wrong default_aggregation:** Metric exists but has wrong aggregation function
3. **Expression error:** Metric expression doesn't handle NULLs or join fanout correctly

### Investigation Steps

```sql
-- Check if relevant metric exists
DESCRIBE SEMANTIC VIEW <SV_FQN>;
-- Look in METRICS section for the concept the user is asking about

-- If metric exists, check its expression and default_aggregation
-- If no metric exists, this is an add_metric opportunity
```

### Fix: `add_metric` or `refine_metric_expr`

**Missing metric → `add_metric`:**
```sql
ALTER SEMANTIC VIEW <DB>.<SCHEMA>.<SV_NAME>
  ADD METRIC average_order_value
    EXPR = 'AVG(orders.amount)'
    DESCRIPTION = 'Average order value across all orders'
    DEFAULT_AGGREGATION = AVG;
```

**Wrong aggregation → `refine_metric_expr`:**
```sql
ALTER SEMANTIC VIEW <DB>.<SCHEMA>.<SV_NAME>
  ALTER METRIC total_unique_customers
    SET EXPR = 'COUNT(DISTINCT orders.customer_id)'
    SET DEFAULT_AGGREGATION = COUNT;
```

---

## 4. Wrong Time Filter

### How to Identify

**Signals:**
- Question asks about time period ("last 6 months", "this quarter", "year over year")
- Generated SQL has no WHERE clause on dates, or uses wrong date column
- Generated SQL truncates to wrong granularity (`DATE_TRUNC('YEAR', ...)` instead of `MONTH`)

**Example:**
```
Question: "Show monthly revenue trend for last 6 months"
Generated: SELECT * FROM orders WHERE created_at > '2025-11-01'   ← used wrong date, no grouping
Reference: SELECT DATE_TRUNC('MONTH', order_date), SUM(amount)    ← correct time dimension
           FROM orders WHERE order_date >= DATEADD('MONTH', -6, CURRENT_DATE())
           GROUP BY 1
```

### Root Cause Analysis

1. **No TIME_DIMENSION:** No date column is marked as `IS_TIME_DIMENSION => TRUE`; Analyst doesn't know which date to use for temporal queries
2. **Wrong date column selected:** Multiple dates exist; Analyst picks the technical one instead of business date
3. **Missing granularity guidance:** SV doesn't hint at expected time granularities

### Investigation Steps

```sql
-- Check for TIME_DIMENSION in SV DDL
DESCRIBE SEMANTIC VIEW <SV_FQN>;
-- Look for IS_TIME_DIMENSION = TRUE in any column definition

-- Count date/timestamp columns per table
-- If multiple: Analyst may be confused
```

### Fix: `add_time_dimension`

```sql
ALTER SEMANTIC VIEW <DB>.<SCHEMA>.<SV_NAME>
  ALTER COLUMN orders.order_date
    SET IS_TIME_DIMENSION = TRUE
    SET COMMENT = 'Primary time axis for order analysis. Use for all time-based trending, filtering, and aggregation.';
```

If multiple tables each have their own time dimension, mark the primary one per table:

```sql
-- orders table: order_date
ALTER SEMANTIC VIEW <DB>.<SCHEMA>.<SV_NAME>
  ALTER COLUMN orders.order_date SET IS_TIME_DIMENSION = TRUE;

-- customers table: signup_date
ALTER SEMANTIC VIEW <DB>.<SCHEMA>.<SV_NAME>
  ALTER COLUMN customers.signup_date SET IS_TIME_DIMENSION = TRUE;
```

---

## 5. SQL Syntax Error

### How to Identify

**Signals:**
- `error_message` column is non-NULL in eval results
- Generated SQL doesn't compile (syntax error, invalid identifier, type mismatch)
- `sql_correctness = 0.0` with an error trace

**Example:**
```
error_message: "SQL compilation error: invalid identifier 'ORDERS.REVNUE'"
```

### Root Cause Analysis

1. **Column typo in SV DDL:** Column referenced in a metric or filter expression doesn't exist
2. **Invalid expression syntax:** Metric expression has SQL errors
3. **Type mismatch:** Expression tries to aggregate a VARCHAR or compare incompatible types
4. **Alias conflict:** SV table alias doesn't match what's used in expressions

### Investigation Steps

```sql
-- Try to compile the generated SQL manually
-- The error message usually points directly at the issue

-- Check metric expressions in SV DDL
DESCRIBE SEMANTIC VIEW <SV_FQN>;
-- Validate that all column references in EXPR fields actually exist
```

### Fix: Manual DDL Fix

This category requires direct SV editing — no single mutation operator handles it cleanly:

```sql
-- Fix typo in metric expression
ALTER SEMANTIC VIEW <DB>.<SCHEMA>.<SV_NAME>
  ALTER METRIC total_revenue
    SET EXPR = 'SUM(orders.revenue)';  -- was 'orders.revnue' (typo)
```

---

## 6. Empty Result Set

### How to Identify

**Signals:**
- Generated SQL compiles and runs, but returns 0 rows
- Reference SQL returns rows (so data exists)
- Usually caused by overly restrictive filters or wrong table selection

**Example:**
```
Question: "Show active customers in APAC"
Generated: SELECT ... FROM customers WHERE status = 'ACTIVE' AND region = 'apac'
  -- Returns 0 (region values are uppercase: 'APAC')
Reference: SELECT ... FROM customers WHERE status = 'ACTIVE' AND region = 'APAC'
```

### Root Cause Analysis

1. **Case sensitivity:** Filter value doesn't match actual data (case mismatch)
2. **Wrong table:** Querying a table that doesn't have the expected rows
3. **Over-filtered:** Multiple filters combine to exclude all rows
4. **Missing relationship:** JOIN produces empty set due to no matching keys

### Investigation Steps

```sql
-- Check actual data values
SELECT DISTINCT region FROM customers LIMIT 20;
-- If case mismatch: add a named filter with correct casing

-- Check if relationship produces matches
SELECT COUNT(*) FROM table_a JOIN table_b ON ...;
-- If 0: relationship uses wrong keys
```

### Fix: `change_relationship` or `add_filter`

**Wrong join keys → `change_relationship`:**
```sql
ALTER SEMANTIC VIEW <DB>.<SCHEMA>.<SV_NAME>
  ALTER RELATIONSHIP cust_to_region
    SET FROM_COLUMN = 'region_code'  -- was 'region_id'
    SET TO_COLUMN = 'code';
```

**Need named filter with correct values → `add_filter`:**
```sql
ALTER SEMANTIC VIEW <DB>.<SCHEMA>.<SV_NAME>
  ADD FILTER active_apac_customers
    ON customers
    EXPR = "status = 'ACTIVE' AND region = 'APAC'"
    DESCRIPTION = 'Active customers in the APAC region';
```

---

## 7. Analyst Refuses to Answer

### How to Identify

**Signals:**
- `generated_sql` is NULL or empty
- `error_message` contains "I cannot answer this question" or "This question is outside the scope"
- `sql_correctness = 0.0` with no SQL generated

**Example:**
```
Question: "What is our customer churn rate?"
Generated SQL: (empty)
Error: "I cannot determine how to answer this question with the available semantic view."
```

### Root Cause Analysis

1. **Question truly out of scope:** The SV doesn't contain the data needed to answer
2. **Missing VQR for pattern:** Analyst hasn't seen a similar enough example
3. **Complex calculation:** Multi-step logic (e.g., churn = customers who were active last month but not this month) requires teaching by example

### Investigation Steps

Determine if the question IS answerable with the SV's tables:
- Do the required columns exist?
- Can the logic be expressed in SQL against these tables?

If YES: The issue is that Analyst needs a VQR example to learn the pattern.
If NO: The question is genuinely out of scope (not a failure).

### Fix: `add_vqr`

Teach Analyst by adding a verified query with the correct SQL:

```sql
-- ALTER SEMANTIC VIEW ... ADD VERIFIED QUERY is not supported (syntax error).
-- Use CREATE OR REPLACE with AI_VERIFIED_QUERIES appended as final clause.
-- See vqr-generator/SKILL.md Phase 5 for the correct apply workflow.
```

---

## 8. Reference-Contaminated Baseline

### How to Identify

**Signals:**
- `generated_sql` contains `CASE WHEN refunded_ind = 0` or `WHERE refunded_ind = 0`, but `reference_sql` does not
- The SV metric definition for the aggregated column includes a `CASE WHEN refunded_ind = 0` filter
- Numeric gap between generated and reference results is small (~0.1%–0.8%), consistent with known refund rates
- `sql_correctness < 1.0` despite the model generating business-correct SQL

**Example:**
```
Question: "What is total net revenue last month?"
Generated: SUM(CASE WHEN refunded_ind = 0 THEN sales_exc_tax_usd ELSE 0 END)
           ← matches TOTAL_NET_REVENUE_USD metric definition ✓
Reference: SUM(sales_exc_tax_usd)
           ← missing refund filter (contaminated baseline) ✗
sql_correctness: 0.0  ← model penalized for being correct
```

### Root Cause
1. VQR was authored before the metric filter was added
2. Inconsistent VQR authoring — some VQRs for the same metric include the filter; others do not
3. Cross-table semantic drift — metric correctly defined on one table; looser on another

### Investigation Steps

```sql
-- Confirm spot-check: run both SQL paths for 1 month
SELECT
  SUM(sales_exc_tax_usd)                                             AS reference_result,
  SUM(CASE WHEN refunded_ind = 0 THEN sales_exc_tax_usd ELSE 0 END) AS metric_result,
  reference_result - metric_result                                   AS gap,
  ROUND((gap / reference_result) * 100, 2)                          AS gap_pct
FROM <fact_table>
JOIN <date_dim> ON ...
WHERE relative_month_num = -1;
-- If gap_pct is 0.1%–0.8%: contaminated baseline confirmed
```

### Fix: Read-Only Analysis (Do Not Modify VQR)

VQR contamination is a **read-only finding**: do NOT apply mutations to the VQR. The model SQL is correct; the issue is with the VQR baseline.

**Options:**
1. **Exclude the contaminated VQR** from future optimization loops (see Step 3b in sv-evaluation/SKILL.md)
2. **Flag as REFERENCE_CONTAMINATED** and continue optimization focusing on non-contaminated VQRs
3. **Analyze separately:** Run a targeted eval excluding contaminated VQRs to get a clean SV quality score

---

## Decision Tree

Use this flowchart to quickly categorize a failure:

```
VQR scored < 1.0
  │
  ├── error_message IS NOT NULL?
  │     ├── YES: "cannot answer" / empty SQL → Category 7 (Analyst refuses) → add_vqr
  │     └── YES: SQL compilation error → Category 5 (Syntax error) → manual fix
  │
  ├── generated_sql returns 0 rows?
  │     └── YES → Category 6 (Empty result) → change_relationship / add_filter
  │
  ├── Wrong tables in FROM/JOIN?
  │     └── YES → Category 1 (Wrong table) → change_relationship
  │
  ├── Correct tables, wrong columns in SELECT/WHERE?
  │     └── YES → Category 2 (Wrong column) → improve_description / add_synonym
  │
  ├── Correct columns, wrong AGG or GROUP BY?
  │     └── YES → Category 3 (Wrong aggregation) → add_metric / refine_metric_expr
  │
  ├── Time/date related issue?
  │     └── YES → Category 4 (Wrong time filter) → add_time_dimension
  │
  └── generated_sql has refund filter, reference does NOT, metric requires it?
        └── YES → Category 8 (Contaminated reference) → **read-only analysis** (exclude/flag; do not modify)
```

---

## Severity Scoring

Assign severity to prioritize which failures to fix first:

| Severity | Criteria | Priority |
|---|---|---|
| **CRITICAL** | SQL error (Category 5) — SV DDL is broken | Fix immediately |
| **HIGH** | Wrong table (Category 1) — fundamentally wrong answer | Fix before other categories |
| **HIGH** | Analyst refuses (Category 7) on answerable question | Add VQR |
| **MEDIUM** | Wrong aggregation (Category 3) — correct direction, wrong numbers | Fix after HIGH |
| **MEDIUM** | Wrong time filter (Category 4) — temporal queries fail | Fix after HIGH |
| **LOW** | Wrong column (Category 2) — subtle difference | Fix last (or via GEPA) |
| **LOW** | Empty result (Category 6) — data/filter issue | Investigate data first |
| **INFO** | Reference contaminated (Category 8) — eval marks correct model behavior as wrong | Exclude/flag contaminated VQR; do not modify |

---

## Batch Analysis Pattern

When analyzing multiple failures, group by category to identify systemic issues:

```sql
-- Categorize all failures (manual classification after review)
WITH raw AS (
  SELECT INPUT, OUTPUT, GROUND_TRUTH, ERROR, EVAL_AGG_SCORE, METRIC_STATUS, METRIC_CALLS
  FROM TABLE(SNOWFLAKE.LOCAL.GET_ANALYST_AI_EVALUATION_DATA(
    '<DB>', '<SCHEMA>', '<SV_FQN>', 'SEMANTIC VIEW', '<eval_name>'
  ))
  WHERE METRIC_NAME = 'sql_correctness'
),
failures AS (
    SELECT
        INPUT AS question,
        OUTPUT AS generated_sql,
        GROUND_TRUTH AS reference_sql,
        EVAL_AGG_SCORE AS sql_correctness,
        ERROR AS error_message,
        CASE
            WHEN error_message LIKE '%cannot answer%' THEN 'analyst_refused'
            WHEN error_message IS NOT NULL THEN 'sql_error'
            WHEN generated_sql IS NULL THEN 'analyst_refused'
            ELSE 'logic_error'
        END AS failure_type
    FROM raw
    WHERE sql_correctness < 1.0
)
SELECT
    failure_type,
    COUNT(*) AS count,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 1) AS pct
FROM failures
GROUP BY failure_type
ORDER BY count DESC;
```

If one category dominates (>50% of failures), focus all mutation effort there first — it's likely a systemic SV design issue rather than per-VQR tuning.

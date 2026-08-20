---
name: sv-materialize
description: >
  Manage semantic view materializations to accelerate repeated Semantic SQL queries.
  Assess eligibility, design grain and staleness targets, create materializations,
  verify planner use via refresh history, and diagnose auto-suspend.
  NOT for Cortex Analyst accuracy — use sv-optimization for that.
triggers:
  - materialize SV
  - add materialization
  - sv materialization
  - speed up semantic view
  - SV is slow
  - precompute SV
  - SV query performance
  - MAX_STALENESS
  - IMMUTABLE WHERE
  - materialization auto-suspended
  - drop materialization
  - refresh materialization
---

> **SCOPE — READ BEFORE PROCEEDING**
>
> Materializations accelerate **Semantic SQL only** — queries via the `SEMANTIC_VIEW()` construct
> or standard SQL against the SV. **Cortex Analyst, Cortex Agents, and CoWork emit physical SQL
> directly against base tables and receive zero benefit from materializations.**
>
> If your workload is Analyst-driven, this skill will not help you. Use `sv-optimization` to
> improve Analyst accuracy instead.

# SV Materialize Skill

Pre-aggregate SV dimensions and metrics so repeated Semantic SQL queries hit a stored rollup
instead of scanning base tables. One fine-grained materialization can serve many coarser queries
via re-aggregation of additive metrics.

---

## When to Use

Materializations pay off when **all** of these hold:

- Consumers use Semantic SQL (`SEMANTIC_VIEW()` or direct SQL against the SV)
- Base tables are large enough that scans are slow (typically > 100M rows)
- Repeated queries share the same dimension/metric patterns
- You can tolerate staleness bounded by `MAX_STALENESS`

---

## Quick Command Reference

| What you want to do | Route |
|---|---|
| "Is a materialization worth it for my SV?" | → Phase 1: Assess |
| "Design a materialization for my SV" | → Phase 2: Design |
| "Create a materialization" | → Phase 3: Create |
| "Check if my materialization is being used" | → Phase 4: Verify |
| "My materialization auto-suspended" | → Phase 5: Diagnose |
| "Suspend / resume / drop a materialization" | → Phase 5: Manage |
| "Manage materializations declaratively (CI/CD)" | → Phase 5: YAML proc |

---

## Prerequisites

Required privileges before any materialization work:

```sql
-- Check current grants
SHOW GRANTS TO ROLE <your_role>;

-- Minimum required:
-- OWNERSHIP on the semantic view
-- ADD SEMANTIC VIEW MATERIALIZATION on the schema
-- USAGE on the warehouse that will build/refresh the materialization

-- Grant if missing:
GRANT ADD SEMANTIC VIEW MATERIALIZATION ON SCHEMA <db>.<schema> TO ROLE <role>;
```

> `SHOW MATERIALIZATIONS IN SEMANTIC VIEW <sv_name>` requires only SELECT on the SV.
> `ADD MATERIALIZATION` and `REFRESH MATERIALIZATION` require OWNERSHIP on the SV and
> USAGE on the warehouse.

---

## Phase 1: Assess

### Step 1A: Inspect current SV state

```sql
-- Check if MAX_STALENESS is already set (look for max_stalesness_sec column)
SELECT semantic_view_name, max_stalesness_sec
FROM SNOWFLAKE.ACCOUNT_USAGE.SEMANTIC_VIEWS
WHERE semantic_view_name = '<SV_NAME>'
  AND semantic_view_database_name = '<DB>';

-- List existing materializations (requires SELECT on SV)
SHOW MATERIALIZATIONS IN SEMANTIC VIEW <db>.<schema>.<sv_name>;

-- Get all metrics with expressions for additive classification
DESCRIBE SEMANTIC VIEW <db>.<schema>.<sv_name>;
-- From the result, filter: "object_kind" = 'METRIC' AND "property" = 'EXPRESSION'
```

### Step 1B: Classify metrics for materialization eligibility

Consult the **Additive Classification Reference** at the bottom of this skill.

Build three lists:
- `ADDITIVE_METRICS` — SUM, COUNT, MIN, MAX with no outer expression. These re-aggregate freely.
- `NON_ADDITIVE_METRICS` — AVG, COUNT(DISTINCT), APPROX_COUNT_DISTINCT, MEDIAN, PERCENTILE, any DISTINCT aggregation, expressions wrapping aggregations (e.g. `SUM(a)/COUNT(b)`). A materialization can only help queries at the exact stored grain.
- `CANNOT_MATERIALIZE` — Window function metrics, semi-additive metrics (NON ADDITIVE BY), metrics with USING clause. Exclude these from any materialization.

### Step 1C: Check base table sizes

```sql
SELECT TABLE_NAME, ROW_COUNT, BYTES / POWER(1024, 3) AS SIZE_GB
FROM <SV_DB>.INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = '<SV_SCHEMA>'
  AND TABLE_NAME IN (<list of SV source tables>)
ORDER BY BYTES DESC;
```

Materialization ROI is strongest when base tables are > 100M rows or > 10GB.

### Step 1D: Analyze query patterns

```sql
-- Find repeated Semantic SQL queries over the last 30 days
SELECT
    QUERY_TEXT,
    COUNT(*) AS execution_count,
    AVG(TOTAL_ELAPSED_TIME) / 1000.0 AS avg_seconds,
    COUNT(DISTINCT USER_NAME) AS distinct_users
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE QUERY_START_TIME >= DATEADD('day', -30, CURRENT_TIMESTAMP())
  AND QUERY_TYPE = 'SELECT'
  AND (
      QUERY_TEXT ILIKE '%SEMANTIC_VIEW(%'
      OR QUERY_TEXT ILIKE '%FROM <sv_name>%'
  )
GROUP BY QUERY_TEXT
HAVING COUNT(*) >= 3
ORDER BY execution_count DESC
LIMIT 30;
```

From the results, extract the dimension + metric patterns that repeat. These are your materialization candidates.

### Step 1E: Assessment verdict

| Signal | Weight |
|---|---|
| Base table > 100M rows | HIGH |
| Query avg > 10s | HIGH |
| Same dimension set appears in 5+ queries | HIGH |
| All hot metrics are additive | HIGH |
| Mix of additive + non-additive hot metrics | MEDIUM |
| Only non-additive hot metrics | LOW — materialization helps only at exact grain |
| All queries are < 1s already | SKIP — no benefit |

---

## Phase 2: Design

### Choose dimensions

Include all dimensions that appear together frequently in query patterns. Finer grain (more dimensions) = more queries covered; coarser grain (fewer dimensions) = smaller storage + faster refresh.

**Re-aggregation rule:** A materialization on (dim_A, dim_B) can serve queries on (dim_A only), (dim_B only), or (dim_A, dim_B). It cannot serve queries on (dim_C) unless dim_C is also materialized.

### Choose metrics

- Start with your `ADDITIVE_METRICS`. Include all that appear in hot queries — one materialization serves multiple granularities via re-aggregation.
- Add `NON_ADDITIVE_METRICS` only if you have repeated queries at exactly the stored grain. Each non-additive metric is grain-locked.
- Exclude `CANNOT_MATERIALIZE` metrics entirely.

### Set MAX_STALENESS

`MAX_STALENESS` must be set on the SV before any materialization can be added.

| Workload | Suggested MAX_STALENESS |
|---|---|
| Real-time dashboard | 300–900 (5–15 minutes) |
| Business reporting | 3600–14400 (1–4 hours) |
| Overnight batch analytics | 86400 (24 hours) |

> **Auto-suspend risk:** If background refreshes consistently take longer than `MAX_STALENESS`,
> Snowflake suspends the materialization. Start conservatively (higher value) and tighten later.
> Minimum is 120 seconds.

> **Note:** The DDL reference syntax uses an integer (seconds). Snowflake's user guide examples
> also show a string form (`'1 hour'`). Use the integer form to match the formal SQL reference.

### Add IMMUTABLE WHERE (strongly recommended)

Snowflake's docs strongly recommend specifying `IMMUTABLE WHERE` to reduce refresh cost. It identifies rows that **never change** — the refresh engine skips those rows on incremental refreshes.

Use a historical date cutoff:
```sql
IMMUTABLE WHERE (order_date < '2025-01-01')  -- historical rows never change
```

Use unqualified column names (without the entity prefix). The condition is evaluated on the SV query result, which uses unqualified names.

### Add WHERE filter (optional)

A `WHERE` filter on the materialization limits which rows are stored. Queries with an equal-or-more-restrictive filter can be rewritten to use the materialization.

```sql
WHERE (order_date >= DATEADD('year', -2, CURRENT_DATE()))  -- only last 2 years
```

**Critical distinction:**
- `WHERE` = row scope filter (what's stored; determines query eligibility)
- `IMMUTABLE WHERE` = refresh optimization hint (which rows to skip on incremental refresh; does NOT affect what's stored)

These are independent and can be combined.

### REFRESH_MODE

| Mode | Use when |
|---|---|
| `AUTO` (default) | Let Snowflake decide — recommended starting point |
| `FULL` | All metrics are non-additive or SV joins multiple entities |
| `INCREMENTAL` | Force incremental even for multi-entity joins (fails if not supported) |

---

## Phase 3: Create

```sql
-- Step 1: Set MAX_STALENESS on the SV (integer seconds, min 120)
-- Skip if already set (check Phase 1A results)
ALTER SEMANTIC VIEW <db>.<schema>.<sv_name>
  SET MAX_STALENESS = 3600;  -- 1 hour = 3600 seconds

-- Step 2: Add the materialization
ALTER SEMANTIC VIEW <db>.<schema>.<sv_name>
  ADD MATERIALIZATION <mat_name>
  WAREHOUSE = <wh>
  REFRESH_MODE = AUTO
  IMMUTABLE WHERE (<historical_condition>)
AS
  DIMENSIONS <entity>.<dim1> [, <entity>.<dim2>, ...]
  METRICS <entity>.<metric1> [, <entity>.<metric2>, ...]
  [WHERE (<row_filter>)];
```

**Example — revenue by customer and year:**
```sql
ALTER SEMANTIC VIEW revenue_analysis SET MAX_STALENESS = 3600;

ALTER SEMANTIC VIEW revenue_analysis
  ADD MATERIALIZATION cust_year_rollup
  WAREHOUSE = reporting_wh
  REFRESH_MODE = AUTO
  IMMUTABLE WHERE (order_year < 2025)
AS
  DIMENSIONS customers.customer_name, orders.order_year
  METRICS orders.total_revenue, orders.order_count;
```

**To update an existing materialization:** re-run `ADD MATERIALIZATION` with the same name and a different definition. Same definition = no-op; different definition = drop + replace.

**YAML-based management (declarative / CI/CD):**
```sql
CALL SYSTEM$MANAGE_SEMANTIC_VIEW_MATERIALIZATIONS_FROM_YAML(
  '<db>.<schema>.<sv_name>',
  $$
  materializations:
    - name: cust_year_rollup
      warehouse: reporting_wh
      dimensions:
        - table: customers
          name: customer_name
        - table: orders
          name: order_year
      metrics:
        - table: orders
          name: total_revenue
        - table: orders
          name: order_count
  $$
);

-- Drop all materializations:
-- CALL SYSTEM$MANAGE_SEMANTIC_VIEW_MATERIALIZATIONS_FROM_YAML('<sv>', 'materializations: []');
```

The YAML proc is idempotent and declarative — run it twice with the same spec and the second call is a no-op.

**IMPORTANT:** Use `CREATE OR ALTER SEMANTIC VIEW` (not `CREATE OR REPLACE`) when modifying the SV after materializations exist. `CREATE OR REPLACE` drops all materializations.

---

## Phase 4: Verify

Check that the materialization initialized and is ACTIVE:

```sql
-- Refresh history — look for state = 'ACTIVE' and recent INITIALIZE action
SELECT name, state, state_message, refresh_start_time, refresh_end_time,
       warehouse, refresh_action
FROM TABLE(INFORMATION_SCHEMA.SEMANTIC_VIEW_MATERIALIZATION_REFRESH_HISTORY(
  NAME => '<mat_name>'
))
ORDER BY refresh_start_time DESC
LIMIT 10;
```

Expected output after creation: one `INITIALIZE` action with `state = 'ACTIVE'`.

Subsequent refreshes show `REFRESH` or `NO_DATA` (no new data since last refresh) actions.

**Confirm planner is using it:** Run a representative query before and after materialization creation. Compare `TOTAL_ELAPSED_TIME` from `QUERY_HISTORY`. A 10x+ speedup on large tables confirms the planner is rewriting to the materialization.

```sql
SELECT query_text, total_elapsed_time, bytes_scanned
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE query_text ILIKE '%SEMANTIC_VIEW(<sv_name>%'
  AND query_start_time >= DATEADD('hour', -2, CURRENT_TIMESTAMP())
ORDER BY query_start_time DESC;
```

---

## Phase 5: Manage & Diagnose

### Check current materialization state

```sql
SHOW MATERIALIZATIONS IN SEMANTIC VIEW <db>.<schema>.<sv_name>;
```

### Diagnose auto-suspend

If `state = 'SUSPENDED'` in refresh history:

**Common causes (check in order):**
1. `MAX_STALENESS` too low — refreshes can't complete within the window
2. Non-additive metrics in a multi-entity join — AUTO resolves to FULL refresh, which may be slow
3. Base table too large for the warehouse size — scale up the refresh warehouse

**Fix:**
```sql
-- Raise MAX_STALENESS
ALTER SEMANTIC VIEW <sv_name> SET MAX_STALENESS = 7200;  -- double it

-- Resume the suspended materialization
ALTER SEMANTIC VIEW <sv_name> RESUME MATERIALIZATION <mat_name>;
```

Alternatively, add an `IMMUTABLE WHERE` clause to reduce the scope of incremental refreshes:
```sql
-- Re-add with IMMUTABLE WHERE
ALTER SEMANTIC VIEW <sv_name> ADD MATERIALIZATION <mat_name>
  WAREHOUSE = <wh>
  REFRESH_MODE = AUTO
  IMMUTABLE WHERE (<historical_cutoff>)
AS
  DIMENSIONS ...
  METRICS ...;
```

### Suspend for cost control

```sql
-- Pause background refresh (materialization still exists but not used for query rewrites)
ALTER SEMANTIC VIEW <sv_name> SUSPEND MATERIALIZATION <mat_name>;

-- Resume
ALTER SEMANTIC VIEW <sv_name> RESUME MATERIALIZATION <mat_name>;
```

### Manual refresh

```sql
-- Force an immediate refresh using the current session warehouse
ALTER SEMANTIC VIEW <sv_name> REFRESH MATERIALIZATION <mat_name>;
```

### Drop a materialization

```sql
ALTER SEMANTIC VIEW <sv_name> DROP MATERIALIZATION <mat_name>;
-- The SV itself is not affected. MAX_STALENESS can be unset after dropping all materializations.

-- Remove MAX_STALENESS after all materializations are dropped:
ALTER SEMANTIC VIEW <sv_name> UNSET MAX_STALENESS;
```

---

## DDL Reference

### ALTER SEMANTIC VIEW — full materialization syntax

```sql
-- Set / unset staleness (integer seconds; minimum 120)
ALTER SEMANTIC VIEW <name> SET MAX_STALENESS = <integer>;
ALTER SEMANTIC VIEW <name> UNSET MAX_STALENESS;  -- only allowed when no materializations exist

-- Add or replace materialization
ALTER SEMANTIC VIEW <name> ADD MATERIALIZATION <mat_name>
  WAREHOUSE = <wh>
  [ REFRESH_MODE = { AUTO | FULL | INCREMENTAL } ]
  [ IMMUTABLE WHERE ( <refresh_hint_condition> ) ]
AS
  DIMENSIONS <dim> [ , ... ]
  METRICS <metric> [ , ... ]
  [ WHERE ( <row_filter> ) ];

-- Lifecycle
ALTER SEMANTIC VIEW <name> DROP MATERIALIZATION <mat_name>;
ALTER SEMANTIC VIEW <name> SUSPEND MATERIALIZATION <mat_name>;
ALTER SEMANTIC VIEW <name> RESUME MATERIALIZATION <mat_name>;
ALTER SEMANTIC VIEW <name> REFRESH MATERIALIZATION <mat_name>;
```

> **MAX_STALENESS format:** The DDL reference specifies `<integer>` (seconds). Snowflake's user
> guide examples also show a string form (`'1 hour'`). Use the integer form for reliability.

### Monitoring

```sql
-- Refresh history for a specific materialization
SELECT * FROM TABLE(INFORMATION_SCHEMA.SEMANTIC_VIEW_MATERIALIZATION_REFRESH_HISTORY(
  NAME => '<mat_name>'
));
-- Columns: name, schema_name, database_name, state (ACTIVE/SUSPENDED),
--          state_message, refresh_start_time, refresh_end_time,
--          warehouse, refresh_action (INITIALIZE/REINITIALIZE/REFRESH/NO_DATA)

-- SV-level staleness setting
SELECT semantic_view_name, max_stalesness_sec
FROM SNOWFLAKE.ACCOUNT_USAGE.SEMANTIC_VIEWS
WHERE semantic_view_database_name = '<DB>';
```

---

## Additive Classification Reference

Use this table when classifying SV metrics in Phase 1B.

| Metric expression pattern | Additive? | Materialization behavior |
|---|---|---|
| `SUM(col)` | ✅ Yes | Re-aggregates across any dropped dimension |
| `COUNT(col)` (no DISTINCT) | ✅ Yes | Re-aggregates |
| `MIN(col)` | ✅ Yes | Re-aggregates |
| `MAX(col)` | ✅ Yes | Re-aggregates |
| `AVG(col)` | ❌ No | Only helps queries at exact stored grain |
| `COUNT(DISTINCT col)` | ❌ No | Only helps at exact stored grain |
| `APPROX_COUNT_DISTINCT(col)` | ❌ No | Only helps at exact stored grain |
| `MEDIAN(col)` | ❌ No | Only helps at exact stored grain |
| `PERCENTILE_CONT(p) WITHIN GROUP (ORDER BY col)` | ❌ No | Only helps at exact stored grain |
| `PERCENTILE_DISC(p) WITHIN GROUP (ORDER BY col)` | ❌ No | Only helps at exact stored grain |
| Any DISTINCT aggregation | ❌ No | Only helps at exact stored grain |
| Expression over aggregations: `SUM(a) / COUNT(b)`, `2 * SUM(x)` | ❌ No | Only helps at exact stored grain |
| Derived metric referencing a non-additive metric | ❌ No | Only helps at exact stored grain |
| Window function metric | 🚫 N/A | **Cannot materialize** |
| Semi-additive metric (NON ADDITIVE BY clause) | 🚫 N/A | **Cannot materialize** |
| Metric with USING (relationship specifier) | 🚫 N/A | **Cannot materialize** |

**Key insight:** "additive" means one stored rollup can answer coarser queries. Non-additive
materializations are still useful if the same exact grain is queried repeatedly — they just
can't serve queries at different granularities.

---

## Fallback Conditions

Queries fall back to base table scan (materialization is NOT used) when:
- No materialization covers the requested dimensions or metrics
- Materialization data exceeds `MAX_STALENESS` (is stale)
- A masking policy or row-access policy applies to a referenced column
- A non-additive metric needs re-aggregation (query is at a coarser grain than stored)
- The materialization is suspended
- The query's WHERE filter is less restrictive than the materialization's WHERE filter
- The query filters on a dimension not included in the materialization

---

## Integration with Toolkit

- **After sv-optimization**: when Analyst accuracy is maximized and query latency is the next concern
- **Flagged by sv-audit**: Section 9b surfaces repeated query patterns with additive metrics on large tables as materialization candidates
- **Monitored by sv-watch**: Check 6 surfaces auto-suspended materializations
- **Preserved by sv-ddl / sv-optimization**: use `CREATE OR ALTER` not `CREATE OR REPLACE` when materializations exist

---
name: sv-audit-phase11-audit-scan
description: Scan ACCOUNT_USAGE views to analyze query patterns, column access frequency, and detect gaps in the semantic view
---

# Phase 11: Audit Usage Scan

## Purpose
Query `SNOWFLAKE.ACCOUNT_USAGE` to understand how the underlying tables are actually used, then cross-reference with the semantic view definition to identify gaps: missing tables, missing columns, unused columns, and relationship gaps.

**Inputs required from Phase 10:** `SV_FQN`, `SV_DB`, `SV_SCHEMA`, `SV_TABLES`, `SV_COLUMNS`, `SV_RELATIONSHIPS`

---

## Step 11A: Query Pattern Analysis

Find SELECT queries that reference the same tables as the SV over the last 30 days:

**Multi-database handling:** Extract distinct database names from `SV_TABLES` (Phase 10 provides full FQNs). If the SV spans multiple databases, include all of them in the filter.

```python
# Extract distinct databases from SV_TABLES
DISTINCT_DATABASES = list(set(t.split('.')[0] for t in SV_TABLES))
```

**False positive prevention:** Short table names (< 5 characters like `T`, `S`, `DIM`) will match too broadly with bare ILIKE. Always use schema-qualified patterns (`SCHEMA.TABLE`) as the primary match. Only add unqualified fallback for table names with 5+ characters.

```sql
SELECT
    QUERY_ID,
    QUERY_TEXT,
    USER_NAME,
    START_TIME,
    EXECUTION_STATUS,
    TOTAL_ELAPSED_TIME
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE
  -- Note: SV tables may span multiple databases.
  -- Use per-table FQN from Phase 10 (SV_TABLES contains DB.SCHEMA.TABLE for each table)
  -- Filter queries that reference ANY of the SV's databases
  DATABASE_NAME IN (<DISTINCT_DATABASES_FROM_SV_TABLES>)
  AND QUERY_TYPE = 'SELECT'
  AND START_TIME >= DATEADD('day', -30, CURRENT_TIMESTAMP())
  AND EXECUTION_STATUS = 'SUCCESS'
  -- Use schema-qualified names to avoid false positives with short table names
  AND (
      QUERY_TEXT ILIKE '%<SCHEMA1>.<TABLE1>%'
      OR QUERY_TEXT ILIKE '%<SCHEMA2>.<TABLE2>%'
      -- ... for each table in the SV
      -- Fallback: also match unqualified if table name length >= 5 chars
      OR QUERY_TEXT ILIKE '% <TABLE_N> %'  -- only for tables with name.length >= 5
  )
ORDER BY START_TIME DESC
LIMIT 5000;
```

**Parse each query's text** to extract:

1. **Tables referenced** — identify any tables in FROM/JOIN clauses that are NOT in the SV
   - Store as `MISSING_TABLE_CANDIDATES` with co-occurrence counts
2. **JOIN patterns** — extract JOIN ON clauses between tables
   - Compare against `SV_RELATIONSHIPS`
   - Store unmatched joins as `RELATIONSHIP_GAPS`
3. **WHERE clause columns** — columns used in filters
   - These are strong DIMENSION candidates if not already in the SV
   - Store as `FILTER_COLUMNS` with frequency counts
4. **GROUP BY columns** — columns used for grouping
   - These are strong DIMENSION candidates
   - Store as `GROUPBY_COLUMNS` with frequency counts
5. **Aggregate functions** — columns wrapped in SUM(), AVG(), COUNT(), MIN(), MAX()
   - These are METRIC/MEASURE candidates if not already in the SV
   - Store as `AGGREGATE_COLUMNS` with function type and frequency

**Important:** Query text parsing is approximate — look for common SQL patterns but don't attempt full SQL parsing. Focus on high-frequency patterns.

### Zero query history fallback

If the QUERY_HISTORY query returns **zero rows** (ACCOUNT_USAGE is accessible but no queries match the SV's tables in the last 30 days):

```
⚠️ QUERY_HISTORY returned 0 results for the SV's underlying tables in the last 30 days.

This may be because:
  - The SV was recently created and has no usage yet
  - Queries run under a different database context (fully-qualified table names not matching)
  - The tables are shared/sample data with no active users

Falling back to STRUCTURAL ANALYSIS:
  - Step 11C: Detect missing tables via column name inference on SV columns
    (e.g., L_PARTKEY in the SV implies PART table should be included)
  - Step 11E: Scan neighboring tables in the same schema
  - Query-based findings (missing columns, unused columns, relationship gaps from 
    JOIN patterns) will be unavailable.
```

Set `QUERY_COUNT = 0`, `DISTINCT_USERS = 0`. Skip Steps 11A parsing and 11B entirely. Proceed directly to Step 11C (which uses column inference) and Step 11E (neighboring tables).

---

## Step 11B: Column Access Frequency

Use ACCESS_HISTORY for precise column-level usage data:

```sql
SELECT
    om.value:objectName::STRING AS TABLE_FQN,
    col.value:columnName::STRING AS COLUMN_NAME,
    COUNT(*) AS ACCESS_COUNT,
    COUNT(DISTINCT ah.USER_NAME) AS DISTINCT_USERS
FROM SNOWFLAKE.ACCOUNT_USAGE.ACCESS_HISTORY ah,
    LATERAL FLATTEN(input => ah.DIRECT_OBJECTS_ACCESSED) om,
    LATERAL FLATTEN(input => om.value:columns) col
WHERE ah.QUERY_START_TIME >= DATEADD('day', -30, CURRENT_TIMESTAMP())
  AND om.value:objectDomain::STRING = 'Table'
  AND om.value:objectName::STRING IN (
      '<SV_DB>.<SCHEMA>.<TABLE1>',
      '<SV_DB>.<SCHEMA>.<TABLE2>'
      -- repeat for each table in SV_TABLES (fully qualified)
  )
GROUP BY 1, 2
ORDER BY ACCESS_COUNT DESC;
```

**Cross-reference with `SV_COLUMNS`:**

- Columns with high `ACCESS_COUNT` that are **NOT in the SV** → store as `MISSING_COLUMNS` (candidates to add)
- Columns that **ARE in the SV** but have zero access → store as `UNUSED_COLUMNS` (candidates to remove)
- Columns with high `DISTINCT_USERS` get higher priority — many users = broad need

**If ACCESS_HISTORY query fails** (e.g., insufficient privileges, Standard Edition):

```
Note: ACCESS_HISTORY is not available (requires Enterprise Edition or higher,
plus IMPORTED PRIVILEGES on SNOWFLAKE database).

Falling back to QUERY_HISTORY-based analysis only.
Column access frequency will be estimated from query text patterns (Step 11A)
rather than precise column-level tracking.
```

Skip Step 11B and proceed to Step 11C. Use filter/groupby/aggregate columns from Step 11A as a proxy for missing column detection.

---

## Step 11C: Missing Table Detection

From Step 11A's parsed queries, identify tables that appear in JOINs with SV tables but are NOT in the SV definition.

For each candidate table:
- Count how many queries reference it alongside SV tables (`CO_QUERY_COUNT`)
- Identify the most common join key used
- Count distinct users who wrote queries involving this table

Rank candidates:

| Threshold | Classification |
|-----------|---------------|
| >= 50 co-queries | HIGH — strongly consider adding |
| 20-49 co-queries | MEDIUM — review with user |
| < 20 co-queries | LOW — likely ad-hoc usage |

Store as `MISSING_TABLES`:
```
{table_name, co_query_count, join_key, distinct_users, classification}
```

---

## Step 11D: Relationship Gap Detection

From Step 11A's parsed queries, find JOIN patterns between tables that ARE in the SV but do NOT have a matching RELATIONSHIP defined.

For each gap:
- Extract the JOIN condition (e.g., `ORDERS.CUSTOMER_ID = CUSTOMERS.CUSTOMER_ID`)
- Count frequency across queries
- Classify as `MANY_TO_ONE`, `ONE_TO_ONE`, or `UNKNOWN` based on column naming patterns

Compare against `SV_RELATIONSHIPS`:
- If a JOIN pattern exists in queries but not in the SV relationships → flag as gap
- If a SV relationship exists but never appears in queries → note as potentially unused (informational only — do NOT recommend removal of relationships)

Store as `RELATIONSHIP_GAPS`:
```
{from_table, from_column, to_table, to_column, frequency, inferred_type}
```

---

## Step 11E: Neighboring Table Scan

Check for tables in the same schema that are not included in the SV:

```sql
SELECT
    TABLE_NAME,
    ROW_COUNT,
    BYTES,
    LAST_ALTERED
FROM <SV_DB>.INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = '<SV_SCHEMA>'
  AND TABLE_TYPE = 'BASE TABLE'
  AND TABLE_NAME NOT IN ('<table1>', '<table2>', ...)
ORDER BY LAST_ALTERED DESC;
```

**Note:** Replace `<table1>, <table2>` with unqualified names of tables already in the SV.

This provides context for Step 11C — if a missing table candidate from query analysis also lives in the same schema, it strengthens the case for inclusion.

Store as `NEIGHBORING_TABLES`:
```
{table_name, row_count, bytes, last_altered}
```

---

## Step 11F: Compile scan results summary

Before proceeding to Phase 12, display a brief scan status:

```
Audit scan complete.

  Queries analyzed:      <N> (last 30 days)
  Distinct users:        <N>
  Missing table candidates:  <N> (tables joined with SV tables but not in SV)
  Missing column candidates: <N> (frequently accessed columns not in SV)
  Unused columns found:      <N> (SV columns with zero access in 30 days)
  Relationship gaps:         <N> (JOIN patterns without SV relationships)
  Neighboring tables:        <N> (same-schema tables not in SV)

Loading Phase 12 for detailed recommendations...
```

No user gate here — proceed directly to Phase 12.

---

## Output variables

| Variable | Contents |
|----------|----------|
| `QUERY_COUNT` | Number of queries analyzed |
| `DISTINCT_USERS` | Count of distinct users in query set |
| `MISSING_TABLE_CANDIDATES` | List: {table, co_query_count, join_key, distinct_users, classification} |
| `MISSING_COLUMNS` | List: {table_fqn, column_name, access_count, distinct_users} |
| `UNUSED_COLUMNS` | List: {table_fqn, column_name, classification_in_sv} |
| `FILTER_COLUMNS` | List: {column, table, frequency} — WHERE clause columns from query parsing |
| `GROUPBY_COLUMNS` | List: {column, table, frequency} — GROUP BY columns from query parsing |
| `AGGREGATE_COLUMNS` | List: {column, table, agg_function, frequency} — aggregated columns |
| `RELATIONSHIP_GAPS` | List: {from_table, from_col, to_table, to_col, frequency, inferred_type} |
| `NEIGHBORING_TABLES` | List: {table_name, row_count, bytes, last_altered} |
| `ACCESS_HISTORY_AVAILABLE` | Boolean — whether ACCESS_HISTORY was queryable |

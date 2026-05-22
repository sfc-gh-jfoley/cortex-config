# Account Usage Patterns

Common ACCOUNT_USAGE SQL patterns used across the semantic-view-toolkit. All queries use the structured JSON approach from `base_objects_accessed` — never query text parsing.

## Table Co-occurrence

Find tables that are frequently queried together (strong relationship signal).

```sql
-- Table co-occurrence pairs (last 90 days)
WITH query_tables AS (
    SELECT
        query_id,
        f.value:objectName::STRING AS table_fqn
    FROM snowflake.account_usage.access_history,
        LATERAL FLATTEN(input => base_objects_accessed) f
    WHERE f.value:objectDomain::STRING = 'Table'
        AND query_start_time >= DATEADD(day, -90, CURRENT_TIMESTAMP())
        AND SPLIT_PART(f.value:objectName::STRING, '.', 1) = :database_name
        AND SPLIT_PART(f.value:objectName::STRING, '.', 2) = :schema_name
),
pairs AS (
    SELECT
        a.table_fqn AS table_a,
        b.table_fqn AS table_b,
        COUNT(DISTINCT a.query_id) AS co_query_count,
        MIN(a.query_id) AS sample_query_id
    FROM query_tables a
    JOIN query_tables b
        ON a.query_id = b.query_id
        AND a.table_fqn < b.table_fqn
    GROUP BY 1, 2
    HAVING co_query_count >= 3
)
SELECT * FROM pairs ORDER BY co_query_count DESC;
```

## Column-Level Access Frequency

Identify which columns are most queried — helps prioritize which to include in semantic views.

```sql
-- Column access frequency (last 90 days)
SELECT
    obj.value:objectName::STRING AS table_fqn,
    col.value:columnName::STRING AS column_name,
    COUNT(DISTINCT query_id) AS query_count,
    COUNT(DISTINCT user_name) AS distinct_users,
    MAX(query_start_time) AS last_accessed
FROM snowflake.account_usage.access_history,
    LATERAL FLATTEN(input => base_objects_accessed) obj,
    LATERAL FLATTEN(input => obj.value:columns) col
WHERE query_start_time >= DATEADD(day, -90, CURRENT_TIMESTAMP())
    AND obj.value:objectDomain::STRING = 'Table'
    AND SPLIT_PART(obj.value:objectName::STRING, '.', 1) = :database_name
    AND SPLIT_PART(obj.value:objectName::STRING, '.', 2) = :schema_name
GROUP BY 1, 2
ORDER BY query_count DESC;
```

## Stale Table Detection

Find tables that haven't been accessed in N days — candidates for exclusion from semantic views.

```sql
-- Tables with no access in the last N days
WITH accessed_tables AS (
    SELECT DISTINCT
        f.value:objectName::STRING AS table_fqn
    FROM snowflake.account_usage.access_history,
        LATERAL FLATTEN(input => base_objects_accessed) f
    WHERE f.value:objectDomain::STRING = 'Table'
        AND query_start_time >= DATEADD(day, -:staleness_days, CURRENT_TIMESTAMP())
        AND SPLIT_PART(f.value:objectName::STRING, '.', 1) = :database_name
        AND SPLIT_PART(f.value:objectName::STRING, '.', 2) = :schema_name
),
all_tables AS (
    SELECT CONCAT(:database_name, '.', :schema_name, '.', table_name) AS table_fqn
    FROM information_schema.tables
    WHERE table_schema = :schema_name
        AND table_catalog = :database_name
        AND table_type = 'BASE TABLE'
)
SELECT a.table_fqn AS stale_table
FROM all_tables a
LEFT JOIN accessed_tables b ON a.table_fqn = b.table_fqn
WHERE b.table_fqn IS NULL
ORDER BY a.table_fqn;
```

## User Count Per Table

How many distinct users query each table — popularity signal for SV inclusion.

```sql
-- Distinct users per table (last 90 days)
SELECT
    f.value:objectName::STRING AS table_fqn,
    COUNT(DISTINCT user_name) AS user_count,
    COUNT(DISTINCT query_id) AS query_count,
    ROUND(query_count / NULLIF(user_count, 0), 1) AS queries_per_user
FROM snowflake.account_usage.access_history,
    LATERAL FLATTEN(input => base_objects_accessed) f
WHERE f.value:objectDomain::STRING = 'Table'
    AND query_start_time >= DATEADD(day, -90, CURRENT_TIMESTAMP())
    AND SPLIT_PART(f.value:objectName::STRING, '.', 1) = :database_name
    AND SPLIT_PART(f.value:objectName::STRING, '.', 2) = :schema_name
GROUP BY 1
ORDER BY user_count DESC;
```

## Common Query Patterns

Detect common WHERE clauses, GROUP BY, and aggregations — helps inform metric and filter design.

```sql
-- Common WHERE column usage (from column access with direct_objects_accessed)
-- Note: This uses direct_objects_accessed for the columns actually filtered on
SELECT
    obj.value:objectName::STRING AS table_fqn,
    col.value:columnName::STRING AS column_name,
    COUNT(DISTINCT query_id) AS filter_usage_count
FROM snowflake.account_usage.access_history,
    LATERAL FLATTEN(input => direct_objects_accessed) obj,
    LATERAL FLATTEN(input => obj.value:columns) col
WHERE query_start_time >= DATEADD(day, -90, CURRENT_TIMESTAMP())
    AND obj.value:objectDomain::STRING = 'Table'
    AND SPLIT_PART(obj.value:objectName::STRING, '.', 1) = :database_name
    AND SPLIT_PART(obj.value:objectName::STRING, '.', 2) = :schema_name
GROUP BY 1, 2
ORDER BY filter_usage_count DESC
LIMIT 50;
```

## Error Handling

### Standard Edition (No ACCESS_HISTORY)

```sql
-- Check if ACCESS_HISTORY is available
SELECT COUNT(*) AS row_count
FROM snowflake.account_usage.access_history
WHERE query_start_time >= DATEADD(day, -1, CURRENT_TIMESTAMP())
LIMIT 1;
-- If this errors with "insufficient privileges" or returns 0, ACCESS_HISTORY is unavailable
```

**Fallback strategy:**
- Skip co-occurrence analysis entirely
- Rely on INFORMATION_SCHEMA (always available) for:
  - Table structure (columns, data types)
  - Constraints (FK/PK/UNIQUE)
  - Table metadata (row count estimates from TABLE_STORAGE_METRICS)

### Insufficient Privileges

Common error: `SQL access control error: Insufficient privileges to operate on schema 'ACCOUNT_USAGE'`

**Resolution:** The querying role needs:
```sql
GRANT IMPORTED PRIVILEGES ON DATABASE SNOWFLAKE TO ROLE <role_name>;
```

### Data Latency

ACCOUNT_USAGE views have up to 45-minute latency. Recent queries may not appear.

**Best practice:**
- For initial discovery: 90-day lookback is sufficient
- For optimization (GEPA): 30-day lookback captures recent patterns
- Never assume real-time accuracy from ACCOUNT_USAGE

### Large Accounts (Performance)

For accounts with heavy query volume, ACCESS_HISTORY queries can be slow.

**Optimization tips:**
- Always include `query_start_time` filter (partition pruning)
- Use `LIMIT` for exploratory queries
- Materialize results into a temporary table for repeated access:

```sql
CREATE TEMPORARY TABLE tmp_access_summary AS
SELECT ... FROM snowflake.account_usage.access_history
WHERE query_start_time >= DATEADD(day, -90, CURRENT_TIMESTAMP());
```

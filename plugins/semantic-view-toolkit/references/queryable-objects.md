# Queryable Objects

Which Snowflake object types can be sources for semantic views, how to detect them, and design considerations for each.

## Supported Source Types

| Object Type | TABLE_TYPE Value | Suitable for SV | Notes |
|-------------|-----------------|-----------------|-------|
| Base Table | `BASE TABLE` | Yes | Primary source type |
| View | `VIEW` | Yes | May reference other databases |
| Dynamic Table | `BASE TABLE` with `IS_DYNAMIC = 'YES'` | Yes | Has TARGET_LAG metadata |
| Iceberg Table | `BASE TABLE` with `IS_ICEBERG = 'YES'` | Yes | Its own object type, not an external table |
| External Table | `EXTERNAL TABLE` | Yes | Raw/landing data; limited pushdown |
| Materialized View | `MATERIALIZED VIEW` | Yes | Pre-aggregated |

`INFORMATION_SCHEMA.TABLES` also exposes `IS_HYBRID`. Classify by the `IS_*` flags before
`TABLE_TYPE`, otherwise dynamic and Iceberg tables count as base tables.

## Base Tables

### Detection SQL

```sql
SELECT
    TABLE_CATALOG,
    TABLE_SCHEMA,
    TABLE_NAME,
    ROW_COUNT,
    BYTES,
    CREATED,
    LAST_ALTERED
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = :schema_name
    AND TABLE_TYPE = 'BASE TABLE'
ORDER BY TABLE_NAME;
```

### SV Design Notes

- Most straightforward source — all columns directly accessible
- Check for PK/FK constraints to inform relationship detection
- Row count and bytes useful for estimating query cost
- `LAST_ALTERED` indicates freshness

## Views

### Detection SQL

```sql
SELECT
    TABLE_CATALOG,
    TABLE_SCHEMA,
    TABLE_NAME,
    VIEW_DEFINITION,
    IS_SECURE,
    CREATED,
    LAST_ALTERED
FROM INFORMATION_SCHEMA.VIEWS
WHERE TABLE_SCHEMA = :schema_name
ORDER BY TABLE_NAME;
```

### SV Design Notes

- Views may reference tables in OTHER databases or schemas
- Secure views hide their definition — cannot inspect underlying logic
- Consider whether to use the view or its underlying tables:
  - **Use the view** when: it represents a business-defined entity (e.g., `ACTIVE_CUSTOMERS`)
  - **Use underlying tables** when: the view is a simple SELECT with no business logic
- Views don't have row counts in INFORMATION_SCHEMA (query `SHOW VIEWS` or run COUNT)
- Changing a view's definition doesn't require SV update (SV references view name, not definition)

### Cross-Database Views

If a view references tables in another database:
```sql
-- Check view dependencies (ACCOUNT_USAGE latency: up to 3 hours)
SELECT REFERENCED_DATABASE, REFERENCED_SCHEMA, REFERENCED_OBJECT_NAME, REFERENCED_OBJECT_DOMAIN
FROM SNOWFLAKE.ACCOUNT_USAGE.OBJECT_DEPENDENCIES
WHERE REFERENCING_DATABASE = :database_name
    AND REFERENCING_SCHEMA = :schema_name
    AND REFERENCING_OBJECT_NAME = :view_name;
```

## Dynamic Tables

### Detection SQL

```sql
-- Dynamic tables have their own metadata view
-- INFORMATION_SCHEMA.DYNAMIC_TABLES does not exist. Use SHOW DYNAMIC TABLES.
SHOW DYNAMIC TABLES IN SCHEMA <database>.<schema_name>
  ->> SELECT
        "name" AS TABLE_NAME,
        "database_name" AS DATABASE_NAME,
        "schema_name" AS SCHEMA_NAME,
        "target_lag" AS TARGET_LAG,
        "refresh_mode" AS REFRESH_MODE,
        "refresh_mode_reason" AS REFRESH_MODE_REASON,
        "data_timestamp" AS DATA_TIMESTAMP,
        "scheduling_state" AS SCHEDULING_STATE
      FROM $1
      ORDER BY "name";
```

### SV Design Notes

- **TARGET_LAG matters:** Dynamic tables have a defined freshness guarantee (minimum 1 minute)
  - Include TARGET_LAG in SV description so users understand data freshness
  - Example: `COMMENT = 'Aggregated daily sales (refreshed every 5 minutes)'`
- **Cannot be altered during refresh:** If a DT is refreshing, DDL operations on it may block
  - Not an issue for SV creation (reads metadata only)
  - Could affect VQR evaluation timing
- **Upstream dependencies:** DTs depend on other tables. Changes upstream may cascade.
- **SCHEDULING_STATE:** Check if DT is `ACTIVE` or `SUSPENDED` — suspended DTs may have stale data

### Freshness Metadata for SV

```sql
-- Get actual freshness of dynamic tables
SHOW DYNAMIC TABLES IN SCHEMA <database>.<schema_name>
  ->> SELECT
        "name" AS NAME,
        "target_lag" AS TARGET_LAG,
        "data_timestamp" AS DATA_TIMESTAMP,
        TIMESTAMPDIFF('minute', "data_timestamp", CURRENT_TIMESTAMP()) AS minutes_stale
      FROM $1;
```

## Iceberg Tables and External Tables

### Detection SQL

```sql
SELECT TABLE_NAME,
       CASE WHEN IS_ICEBERG = 'YES' THEN 'ICEBERG TABLE' ELSE TABLE_TYPE END AS OBJECT_TYPE
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = :schema_name
    AND (IS_ICEBERG = 'YES' OR TABLE_TYPE = 'EXTERNAL TABLE')
ORDER BY TABLE_NAME;
```

### SV Design Notes

- **Iceberg tables:**
  - Treat like base tables for SV purposes
  - Performance depends on file format and partitioning

- **External tables:**
  - May have limited pushdown capabilities
  - Large scans can be expensive
  - Consider materializing hot data into regular tables
  - Partition columns are valuable as SV dimensions (enable pruning)

- **Common patterns:**
  - External tables often represent raw/landing data
  - Best used via views that add business logic layer
  - Include partition columns as dimensions for query performance

### Performance Considerations

```sql
-- Check partition columns (useful as SV dimensions for pruning)
SHOW EXTERNAL TABLES IN SCHEMA :database.:schema;
-- PARTITION_COLUMNS field shows available partition keys
```

## Materialized Views

### Detection SQL

```sql
SELECT
    TABLE_NAME,
    IS_SECURE,
    CREATED,
    LAST_ALTERED
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = :schema_name
    AND TABLE_TYPE = 'MATERIALIZED VIEW'
ORDER BY TABLE_NAME;
```

```sql
-- Get materialized view definition and cluster info
SHOW MATERIALIZED VIEWS IN SCHEMA :database.:schema;
```

### SV Design Notes

- **Pre-aggregated data:** MVs often contain aggregations — may be metrics themselves
  - Example: An MV with `SUM(amount) GROUP BY date, product` → columns are already metrics
  - Define metrics on them carefully (avoid double-aggregation)
- **Automatic refresh:** MVs refresh automatically when base tables change
  - Good freshness characteristics for SV
  - No manual refresh needed
- **Limited transformations:** MVs have restrictions on what SQL they support
  - Cannot contain non-deterministic functions
  - Cannot reference other MVs
- **Cluster keys:** MVs may be clustered — their dimensions align with cluster keys

### Avoiding Double Aggregation

If an MV already contains aggregated data:
```sql
-- MV definition might be:
-- SELECT date, product_id, SUM(revenue) as total_revenue
-- FROM sales GROUP BY date, product_id

-- In SV, expose total_revenue as a fact and define the metric as SUM(total_revenue).
-- That is correct only for groupings at or above the MV grain (date, product_id).
-- Do not define AVG or COUNT metrics over the pre-aggregated column.
```

## Selection Guidance

### When to Use Each Type in an SV

| Scenario | Recommended Source |
|----------|-------------------|
| Transactional data (orders, events) | Base Table |
| Business-defined entities (active customers) | View |
| Near-real-time aggregations | Dynamic Table |
| Data lake / open table format | Iceberg Table |
| Raw files in a stage | External Table |
| Pre-computed summaries | Materialized View |

### Multi-Type Composition

A single semantic view can mix source types:
```sql
CREATE SEMANTIC VIEW sales_analytics
TABLES (
    orders AS DB.SCHEMA.ORDERS,                  -- Base table (transactions)
    cust AS DB.SCHEMA.ACTIVE_CUSTOMERS,          -- View (business logic)
    metrics AS DB.SCHEMA.DAILY_METRICS,          -- Dynamic table (near-real-time)
    products AS DB.SCHEMA.PRODUCT_CATALOG        -- Iceberg table (data lake)
)
...
```

### Discovery Priority

When scanning a schema for SV candidates, prioritize:
1. Tables with highest user access count (most queried)
2. Tables with declared relationships (FK/PK)
3. Tables with meaningful column names (not generic staging tables)
4. Exclude: staging tables (`STG_`), temporary tables, system tables

---

## Column Type Caveats

A column stored as `TEXT` that holds numbers makes `AVG()` and comparisons fail or return NULL.
Wrap it in the SV expression with `TRY_TO_DECIMAL(<col>)` (NULL on non-numeric rows, rather than an
error). VQR health checks do not detect this type mismatch.

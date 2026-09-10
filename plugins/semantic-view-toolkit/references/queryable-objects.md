# Queryable Objects

Which Snowflake object types can be sources for semantic views, how to detect them, and design considerations for each.

## Supported Source Types

| Object Type | TABLE_TYPE Value | Suitable for SV | Notes |
|-------------|-----------------|-----------------|-------|
| Base Table | `BASE TABLE` | Yes | Primary source type |
| View | `VIEW` | Yes | May reference other databases |
| Dynamic Table | — (separate view) | Yes | Has TARGET_LAG metadata |
| External Table | `EXTERNAL TABLE` | Yes | Iceberg or non-Iceberg |
| Materialized View | `MATERIALIZED VIEW` | Yes | Pre-aggregated |

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
-- Check view dependencies
SELECT *
FROM SNOWFLAKE.ACCOUNT_USAGE.OBJECT_DEPENDENCIES
WHERE REFERENCING_OBJECT_NAME = :view_name
    AND REFERENCING_SCHEMA = :schema_name;
```

## Dynamic Tables

### Detection SQL

```sql
-- Dynamic tables have their own metadata view
SELECT
    NAME AS TABLE_NAME,
    DATABASE_NAME,
    SCHEMA_NAME,
    TARGET_LAG,
    REFRESH_MODE,
    REFRESH_MODE_REASON,
    DATA_TIMESTAMP,
    SCHEDULING_STATE
FROM INFORMATION_SCHEMA.DYNAMIC_TABLES
WHERE SCHEMA_NAME = :schema_name
ORDER BY NAME;
```

### SV Design Notes

- **TARGET_LAG matters:** Dynamic tables have a defined freshness guarantee (minimum 1 minute)
  - Include TARGET_LAG in SV description so users understand data freshness
  - Example: `DESCRIPTION 'Aggregated daily sales (refreshed every 5 minutes)'`
- **Cannot be altered during refresh:** If a DT is refreshing, DDL operations on it may block
  - Not an issue for SV creation (reads metadata only)
  - Could affect VQR evaluation timing
- **Upstream dependencies:** DTs depend on other tables. Changes upstream may cascade.
- **SCHEDULING_STATE:** Check if DT is `ACTIVE` or `SUSPENDED` — suspended DTs may have stale data

### Freshness Metadata for SV

```sql
-- Get actual freshness of dynamic tables
SELECT
    NAME,
    TARGET_LAG,
    DATA_TIMESTAMP,
    TIMESTAMPDIFF('minute', DATA_TIMESTAMP, CURRENT_TIMESTAMP()) AS minutes_stale
FROM INFORMATION_SCHEMA.DYNAMIC_TABLES
WHERE SCHEMA_NAME = :schema_name;
```

## External Tables

### Detection SQL

```sql
-- List external tables and detect Iceberg format via TABLE_FORMAT column
SHOW EXTERNAL TABLES IN SCHEMA <database>.<schema_name>;
-- Check the TABLE_FORMAT column: 'ICEBERG' indicates an Iceberg external table.
-- IS_ICEBERG (or equivalent) column availability varies by Snowflake version;
-- use TABLE_FORMAT as the primary signal.
```

```sql
-- Alternative: query INFORMATION_SCHEMA for external table existence
SELECT
    TABLE_NAME,
    TABLE_TYPE
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = :schema_name
    AND TABLE_TYPE = 'EXTERNAL TABLE'
ORDER BY TABLE_NAME;
-- Then SHOW EXTERNAL TABLES to get format details for Iceberg detection.
```

### SV Design Notes

- **Iceberg External Tables:**
  - Full SQL support (same as base tables for SV purposes)
  - May have auto-refresh configured (check freshness)
  - Performance depends on file format and partitioning
  
- **Non-Iceberg External Tables:**
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
  - Set `default_aggregation = SUM` carefully (avoid double-aggregation)
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

-- In SV, mark total_revenue as a fact with SUM aggregation
-- But warn: querying "total revenue by product" would SUM the already-SUMmed values
-- Solution: Use the MV's columns as facts but set DEFAULT_AGGREGATION carefully
```

## Selection Guidance

### When to Use Each Type in an SV

| Scenario | Recommended Source |
|----------|-------------------|
| Transactional data (orders, events) | Base Table |
| Business-defined entities (active customers) | View |
| Near-real-time aggregations | Dynamic Table |
| Data lake / external data | External Table (Iceberg) |
| Pre-computed summaries | Materialized View |

### Multi-Type Composition

A single semantic view can mix source types:
```sql
CREATE OR REPLACE SEMANTIC VIEW sales_analytics
TABLES (
    DB.SCHEMA.ORDERS AS orders,           -- Base table (transactions)
    DB.SCHEMA.ACTIVE_CUSTOMERS AS cust,   -- View (business logic)
    DB.SCHEMA.DAILY_METRICS AS metrics,   -- Dynamic table (near-real-time)
    DB.SCHEMA.PRODUCT_CATALOG AS products -- External table (data lake)
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

## Domain-Specific Column Caveats

Some source tables have columns whose SQL type does not match their semantic type. These cause
silent failures in VQR SQL, eval scoring, and any arithmetic query.

### PSPS Domain (`PSPS_HISTORICAL`)

| Column | Stored Type | Semantic Type | Symptom | Correct Usage |
|---|---|---|---|---|
| `GEN_FUELLEVEL` | `TEXT` | Numeric percentage | `AVG()`, comparisons return NULL or error | `TRY_TO_DECIMAL(GEN_FUELLEVEL)` |

```sql
-- AVG fuel level (TEXT → DECIMAL required):
ROUND(AVG(TRY_TO_DECIMAL(GEN_FUELLEVEL)), 1) AS avg_fuel_pct

-- Filter by fuel level:
WHERE TRY_TO_DECIMAL(GEN_FUELLEVEL) < 50
```

Use `TRY_TO_DECIMAL` not `TO_DECIMAL` — returns NULL on non-numeric rows rather than erroring.

If this column appears in a VQR or eval SQL, the VQR health check (Check 2 in
`references/vqr-eval-health.md`) will not catch the type mismatch — add an explicit CAST in
the VQR SQL.

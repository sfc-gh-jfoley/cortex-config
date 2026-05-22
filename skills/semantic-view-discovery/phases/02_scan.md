---
name: sv-discovery-phase2-scan
description: Scan FK/PK constraints, infer relationships from column naming patterns, analyze query co-occurrence from ACCOUNT_USAGE, and collect column usage frequency
---

# Phase 2: Scan

## Purpose
Gather all available evidence about table relationships from four sources (in priority order):
1. Declared FK/PK constraints (real-time, highest trust)
2. Column name pattern inference (real-time, heuristic)
3. Query co-occurrence from QUERY_HISTORY (delayed, behavioral)
4. Column access frequency from ACCESS_HISTORY (delayed, behavioral)

---

## Scaling Check

Before proceeding, check the scope size:

- If `TOTAL_TABLE_COUNT` > 200 tables:
  ```
  ⚠️ Large database detected: <N> tables in scope.
  
  Column inference scales O(N²) with table count, and query history parsing 
  may be slow with this many tables.
  
  Options:
    A) Narrow scope to specific schemas (recommended for databases > 200 tables)
    B) Proceed anyway (may be slow but will still work)
    C) Skip column inference — rely on FK constraints + query history only
  ```
  Wait for user selection before proceeding.

- If `TOTAL_TABLE_COUNT` <= 200: proceed without interruption.

---

## Step 2A: FK/PK Constraint Scan (Real-time)

### Find all primary keys

```sql
SELECT
    tc.TABLE_SCHEMA,
    tc.TABLE_NAME,
    tc.CONSTRAINT_NAME,
    kcu.COLUMN_NAME
FROM <DISCOVERY_DB>.INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
JOIN <DISCOVERY_DB>.INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu
    ON tc.CONSTRAINT_NAME = kcu.CONSTRAINT_NAME
    AND tc.TABLE_SCHEMA = kcu.TABLE_SCHEMA
WHERE tc.CONSTRAINT_TYPE = 'PRIMARY KEY'
    AND tc.TABLE_SCHEMA IN (<DISCOVERY_SCHEMAS>)
ORDER BY tc.TABLE_SCHEMA, tc.TABLE_NAME;
```

Store results as `PRIMARY_KEYS`: map of `{schema.table → [pk_columns]}`.

**Error handling:** If these queries fail with "Object does not exist" (common for shared databases like SNOWFLAKE_SAMPLE_DATA where INFORMATION_SCHEMA.KEY_COLUMN_USAGE or TABLE_CONSTRAINTS may not be exposed), treat as zero constraints found and skip directly to Step 2B. Do NOT error out.

### Find all foreign keys with references

```sql
SELECT
    rc.CONSTRAINT_NAME,
    kcu.TABLE_SCHEMA  AS FK_SCHEMA,
    kcu.TABLE_NAME    AS FK_TABLE,
    kcu.COLUMN_NAME   AS FK_COLUMN,
    rc.UNIQUE_CONSTRAINT_NAME,
    kcu2.TABLE_SCHEMA AS PK_SCHEMA,
    kcu2.TABLE_NAME   AS PK_TABLE,
    kcu2.COLUMN_NAME  AS PK_COLUMN
FROM <DISCOVERY_DB>.INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS rc
JOIN <DISCOVERY_DB>.INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu
    ON rc.CONSTRAINT_NAME = kcu.CONSTRAINT_NAME
    AND rc.CONSTRAINT_SCHEMA = kcu.CONSTRAINT_SCHEMA
JOIN <DISCOVERY_DB>.INFORMATION_SCHEMA.KEY_COLUMN_USAGE kcu2
    ON rc.UNIQUE_CONSTRAINT_NAME = kcu2.CONSTRAINT_NAME
    AND rc.UNIQUE_CONSTRAINT_SCHEMA = kcu2.CONSTRAINT_SCHEMA
WHERE kcu.TABLE_SCHEMA IN (<DISCOVERY_SCHEMAS>);
```

Store FK pairs as confirmed relationships with **confidence = HIGH** (FK-declared).

**Note:** Snowflake does not enforce FK constraints, but many data modeling tools and ETL pipelines still create them as metadata. Even unenforced FKs are strong evidence of intended relationships.

If both queries return zero rows, inform the user:
```
No PK/FK constraints found in scope. This is common in Snowflake — constraints are often omitted.
Proceeding with column name inference and query co-occurrence analysis.
```

---

## Step 2B: Column Name FK Inference

Retrieve all columns that look like join keys:

```sql
SELECT
    c.TABLE_SCHEMA,
    c.TABLE_NAME,
    c.COLUMN_NAME,
    c.DATA_TYPE,
    c.ORDINAL_POSITION
FROM <DISCOVERY_DB>.INFORMATION_SCHEMA.COLUMNS c
JOIN <DISCOVERY_DB>.INFORMATION_SCHEMA.TABLES t
    ON c.TABLE_SCHEMA = t.TABLE_SCHEMA
    AND c.TABLE_NAME = t.TABLE_NAME
WHERE c.TABLE_SCHEMA IN (<DISCOVERY_SCHEMAS>)
    AND t.TABLE_TYPE = 'BASE TABLE'
    AND (
        c.COLUMN_NAME LIKE '%_ID'
        OR c.COLUMN_NAME LIKE '%_KEY'
        OR c.COLUMN_NAME LIKE '%_CODE'
        OR c.COLUMN_NAME LIKE '%_SK'
        OR c.COLUMN_NAME LIKE '%_NBR'
        OR c.COLUMN_NAME LIKE '%_NO'
        OR c.COLUMN_NAME = 'ID'
    )
ORDER BY c.TABLE_SCHEMA, c.TABLE_NAME, c.ORDINAL_POSITION;
```

Also retrieve all columns (needed for domain analysis in Phase 3):

```sql
SELECT
    c.TABLE_SCHEMA,
    c.TABLE_NAME,
    c.COLUMN_NAME,
    c.DATA_TYPE,
    c.IS_NULLABLE,
    c.ORDINAL_POSITION
FROM <DISCOVERY_DB>.INFORMATION_SCHEMA.COLUMNS c
JOIN <DISCOVERY_DB>.INFORMATION_SCHEMA.TABLES t
    ON c.TABLE_SCHEMA = t.TABLE_SCHEMA
    AND c.TABLE_NAME = t.TABLE_NAME
WHERE c.TABLE_SCHEMA IN (<DISCOVERY_SCHEMAS>)
    AND t.TABLE_TYPE = 'BASE TABLE'
ORDER BY c.TABLE_SCHEMA, c.TABLE_NAME, c.ORDINAL_POSITION;
```

### Matching rules (apply in order)

For every pair of tables (A, B) in scope:

1. **Exact FK column match**: Table A has column `CUSTOMER_ID`, Table B has column `CUSTOMER_ID` (and one of them has it as PK or the table is named `CUSTOMERS`) → candidate join on `CUSTOMER_ID`
2. **Table name + ID pattern**: Table A has column `CUSTOMER_ID`, Table B is named `CUSTOMERS` (or `CUSTOMER`) with column `ID` → candidate join `A.CUSTOMER_ID → B.ID`
3. **Suffix stripping**: Column `CUST_ID` in Table A matches Table B named `CUST` or `CUSTOMERS` with column `CUST_ID` or `ID`
4. **Common dimension prefixes**: `_KEY`, `_CODE`, `_SK`, `_NBR`, `_NO` follow the same logic as `_ID`

Store inferred relationships with **confidence = MEDIUM** (column name inference, no constraint declared).

---

## Step 2C: Query Co-occurrence (ACCOUNT_USAGE)

**Skip this step if `HAS_ACCOUNT_USAGE = false`.**

```sql
SELECT
    QUERY_ID,
    QUERY_TEXT,
    DATABASE_NAME,
    SCHEMA_NAME,
    START_TIME,
    USER_NAME,
    QUERY_TYPE
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE DATABASE_NAME = '<DISCOVERY_DB>'
    AND QUERY_TYPE = 'SELECT'
    AND START_TIME >= DATEADD('day', -30, CURRENT_TIMESTAMP())
    AND EXECUTION_STATUS = 'SUCCESS'
ORDER BY START_TIME DESC
LIMIT 10000;
```

### Parse query text for table references

For each query, extract table names referenced in FROM and JOIN clauses. Build a co-occurrence count for each table pair:

```
Co-occurrence matrix (top pairs):
  ORDERS ↔ CUSTOMERS:     234 co-queries
  ORDERS ↔ ORDER_ITEMS:   189 co-queries
  PRODUCTS ↔ ORDER_ITEMS: 156 co-queries
  SHIPMENTS ↔ ORDERS:      12 co-queries
```

### Confidence scoring from co-occurrence

Apply these thresholds:
- **≥ 50 co-queries** → HIGH confidence
- **10–49 co-queries** → MEDIUM confidence
- **< 10 co-queries** → LOW confidence

### FK boost rule

If a table pair has BOTH a column-name match (Step 2B) AND co-query evidence:
- Boost confidence by one tier (LOW → MEDIUM, MEDIUM → HIGH)
- A pair with FK constraint (Step 2A) stays HIGH regardless

### Latency note

QUERY_HISTORY has up to 45-minute latency. If the result set is empty or unexpectedly small:
```
QUERY_HISTORY returned few results. This may be due to:
  - Latency (up to 45 minutes for recent queries to appear)
  - Low query volume on this database in the last 30 days
  - Queries running under a different database context

Options:
  A) Extend the lookback window to 90 days
  B) Proceed with FK/column-name evidence only
```

---

## Step 2D: Column Usage Frequency (ACCESS_HISTORY)

**Skip this step if `HAS_ACCOUNT_USAGE = false`.**

```sql
SELECT
    om.value:objectName::STRING   AS OBJECT_NAME,
    col.value:columnName::STRING  AS COLUMN_NAME,
    COUNT(*)                      AS ACCESS_COUNT
FROM SNOWFLAKE.ACCOUNT_USAGE.ACCESS_HISTORY ah,
    LATERAL FLATTEN(input => ah.DIRECT_OBJECTS_ACCESSED) om,
    LATERAL FLATTEN(input => om.value:columns) col
WHERE ah.QUERY_START_TIME >= DATEADD('day', -30, CURRENT_TIMESTAMP())
    AND om.value:objectDomain::STRING = 'Table'
    AND om.value:objectName::STRING LIKE '<DISCOVERY_DB>.%'
GROUP BY 1, 2
ORDER BY ACCESS_COUNT DESC;
```

Store as `COLUMN_USAGE`: map of `{schema.table.column → access_count}`.

This data feeds into Phase 5 (handoff) to highlight the most-queried columns for each domain.

### Latency / edition note

ACCESS_HISTORY may have up to 3-hour latency and is available on Enterprise edition and above. If this query fails:
```
ACCESS_HISTORY is not available (requires Enterprise edition or higher).
Column usage frequency will not be included in the analysis.
Proceeding with constraint + co-occurrence data only.
```

Set `HAS_ACCESS_HISTORY = false` and continue.

---

## Step 2E: Scan summary

Present a brief summary before proceeding to analysis:

```
Scan complete:
  PK constraints found:      <N> tables with declared PKs
  FK constraints found:       <N> declared foreign key relationships
  Column-inferred joins:      <N> candidate relationships (name pattern matching)
  Query co-occurrence pairs:  <N> table pairs with shared queries (30-day window)
  Column usage entries:       <N> columns with access data

Total relationship evidence:  <N> unique table pairs with at least one signal

Loading Phase 3 for analysis...
```

---

## Output variables passed to next phases

| Variable | Contents |
|----------|----------|
| `PRIMARY_KEYS` | Map of `{schema.table → [pk_columns]}` |
| `FK_RELATIONSHIPS` | List of `{fk_table, fk_col, pk_table, pk_col, confidence: HIGH}` |
| `INFERRED_RELATIONSHIPS` | List of `{table_a, table_b, join_col, confidence: MEDIUM}` |
| `COOCCURRENCE_MATRIX` | Map of `{(table_a, table_b) → co_query_count}` |
| `COLUMN_USAGE` | Map of `{fully_qualified_column → access_count}` |
| `HAS_ACCESS_HISTORY` | Whether ACCESS_HISTORY data was collected |
| `ALL_COLUMNS` | Full column metadata for all tables in scope |

---
name: sv-discovery-phase1-connect-scope
description: Connect to the customer's Snowflake account, validate access, detect existing semantic views, enumerate all queryable object types, and scope the database/schemas to analyze
---

# Phase 1: Connect & Scope

## Purpose

Establish the target database, verify access to required metadata views, detect existing semantic view coverage, enumerate all queryable object types (not just base tables), and let the user scope which schemas to analyze.

---

## Step 1.1: Get Target Database

Ask the user (or detect from context):

```
Which database should I analyze for semantic view domains?

Provide the database name (e.g., ANALYTICS_DB, PROD_DW).
Optionally include a specific schema if you only want to analyze part of it (e.g., ANALYTICS_DB.SALES).
```

Store as:
- `DISCOVERY_DB` — database name (uppercase)
- `DISCOVERY_SCHEMAS` — list of schemas (empty = all non-system schemas)
- `SV_CONNECTION` — Snowflake connection to use (default: active connection)

---

## Step 1.2: Validate ACCESS_HISTORY Access

Run this query to confirm the current role can read ACCESS_HISTORY (which is the primary co-occurrence data source):

```sql
SELECT COUNT(*) AS ROW_CHECK
FROM SNOWFLAKE.ACCOUNT_USAGE.ACCESS_HISTORY
WHERE QUERY_START_TIME >= DATEADD('day', -1, CURRENT_TIMESTAMP())
LIMIT 1;
```

**If this fails** (insufficient privileges):
```
ACCESS_HISTORY is not available for the current role.

Discovery can still run using INFORMATION_SCHEMA only (FK/PK constraints + column name inference).
Query co-occurrence and column usage analysis will be skipped.

Options:
  A) Switch to a role with ACCESS_HISTORY access (e.g., ACCOUNTADMIN, or a role with IMPORTED PRIVILEGES on SNOWFLAKE database)
  B) Proceed with INFORMATION_SCHEMA only (reduced accuracy)
```

Store as:
- `HAS_ACCOUNT_USAGE` — `true` / `false`

---

## Step 1.3: Detect Existing Semantic Views

Before recommending new SVs, check what already exists:

```sql
SHOW SEMANTIC VIEWS IN DATABASE <DISCOVERY_DB>;
```

For table coverage, run `DESCRIBE SEMANTIC VIEW` for each SV returned above. It returns structured
rows (`object_kind`, `object_name`, `parent_entity`, `property`, `property_value`) in real time:

```sql
DESCRIBE SEMANTIC VIEW <sv_fqn>;
SELECT "object_name" AS logical_table,
       MAX(CASE WHEN "property" = 'BASE_TABLE_DATABASE_NAME' THEN "property_value" END) || '.' ||
       MAX(CASE WHEN "property" = 'BASE_TABLE_SCHEMA_NAME'   THEN "property_value" END) || '.' ||
       MAX(CASE WHEN "property" = 'BASE_TABLE_NAME'          THEN "property_value" END) AS table_fqn
FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()))
WHERE "object_kind" = 'TABLE'
GROUP BY "object_name";
```

A logical table defined as a SQL query has a `DEFINITION` property instead of `BASE_TABLE_*`;
record it as "query-defined" and do not count it as covering a base table. Use `GET_DDL` only when
you need the full DDL text.

Extract from each existing SV:
- Which tables it references (from the DESCRIBE rows above)

Store as:
- `EXISTING_SVS` — list of `{sv_fqn, tables_covered[]}`
- `COVERED_TABLES` — flat set of all table FQNs (uppercased, fully qualified) already in an existing SV

**FQN normalization:** Uppercase all table names when building `COVERED_TABLES` and when comparing against ACCESS_HISTORY results. This prevents false NOT_COVERED results from case differences.

Present to user:
```
Existing Semantic Views Found: <N>

| # | Semantic View | Tables Covered | Status |
|---|---|---|---|
| 1 | DB.SCHEMA.SALES_SV | ORDERS, CUSTOMERS, PRODUCTS | Active |
| 2 | DB.SCHEMA.MARKETING_SV | CAMPAIGNS, LEADS | Active |

Tables already covered: <N> of <total>
Tables NOT covered: <remaining> (these are discovery candidates)
```

If no existing SVs found:
```
No existing semantic views found in <DISCOVERY_DB>. All tables are discovery candidates.
```

---

## Step 1.4: Enumerate All Queryable Objects

Count objects by type (not just BASE TABLEs — see `../../../references/queryable-objects.md`):

```sql
-- One query for all types. Dynamic, Iceberg and hybrid tables are TABLE_TYPE = 'BASE TABLE'
-- rows; classify them with the IS_DYNAMIC / IS_ICEBERG / IS_HYBRID flags (each 'YES'/'NO').
SELECT
    TABLE_SCHEMA,
    CASE
        WHEN IS_DYNAMIC = 'YES' THEN 'DYNAMIC TABLE'
        WHEN IS_ICEBERG = 'YES' THEN 'ICEBERG TABLE'
        WHEN IS_HYBRID  = 'YES' THEN 'HYBRID TABLE'
        ELSE TABLE_TYPE
    END AS OBJECT_TYPE,
    COUNT(*) AS OBJECT_COUNT
FROM <DISCOVERY_DB>.INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA <> 'INFORMATION_SCHEMA'
    AND TABLE_TYPE IN ('BASE TABLE', 'EXTERNAL TABLE', 'VIEW', 'MATERIALIZED VIEW')
    -- AND TABLE_SCHEMA IN ('<SCHEMA1>', '<SCHEMA2>')   -- when DISCOVERY_SCHEMAS was given in Step 1.1
GROUP BY 1, 2
ORDER BY 1, 2;
```

Present comprehensive summary:

```
Database: ANALYTICS_DB

Schema          | Base Tables | Views | Dynamic | Iceberg | External | Mat Views | Total
----------------|-------------|-------|---------|---------|----------|-----------|------
SALES           |          15 |     5 |       2 |       0 |        0 |         1 |   23
MARKETING       |          10 |     3 |       1 |       0 |        0 |         1 |   15
STAGING         |           8 |     0 |       0 |       0 |        0 |         0 |    8
DATA_LAKE       |           0 |     2 |       0 |       3 |        2 |         0 |    7
                                                                                Total: 53

Already covered by existing SVs: 8 tables
Discovery candidates: 45 objects

Shall I analyze all schemas, or focus on specific ones?
(Staging schemas are often excluded — they typically contain intermediate data.)
```

### Zero Objects Early Exit

If the total count across all types is **zero**:

```
⚠️ No queryable objects found in <DISCOVERY_DB> (or the specified schemas).

Semantic views require tables, views, or dynamic tables as sources.

Possible reasons:
  - Insufficient privileges to see objects in this database
  - The specified schemas are empty
  - Objects exist but under a different database

Options:
  A) Try a different database or schema
  B) Check current role privileges
```

**GATE: Do NOT proceed to Phase 2 if TOTAL_OBJECT_COUNT = 0.**

---

## Step 1.5: List Schemas (if user didn't specify)

If user did not specify schemas, enumerate what's available:

```sql
SELECT
    SCHEMA_NAME,
    CREATED,
    LAST_ALTERED
FROM <DISCOVERY_DB>.INFORMATION_SCHEMA.SCHEMATA
WHERE SCHEMA_NAME NOT IN ('INFORMATION_SCHEMA')
ORDER BY LAST_ALTERED DESC;
```

---

## Step 1.6: Confirm Scope

**INTERACTIVE mode:** Mandatory gate — do NOT proceed until user confirms.
**AUTONOMOUS mode:** Auto-confirm unless there are concerns (>200 objects, or existing SVs cover >80% of tables).

Present the scope summary:

```
Discovery scope:
  Database:       <DISCOVERY_DB>
  Schemas:        <comma-separated list, or "all (N schemas)">
  Object count:   <total objects in scope> (base tables: N, views: N, DTs: N, external: N, MVs: N)
  Existing SVs:   <N> (covering <M> tables)
  ACCESS_HISTORY: <available / not available>
  Connection:     <SV_CONNECTION>
  Mode:           <AUTONOMOUS / INTERACTIVE>

Proceed with scanning? (yes / adjust)
```

Wait for explicit user confirmation (INTERACTIVE) or auto-proceed (AUTONOMOUS).

If user says "adjust", let them add/remove schemas and re-present the summary.

---

## Output Variables Passed to Next Phases

| Variable | Contents |
|----------|----------|
| `DISCOVERY_DB` | Target database name |
| `DISCOVERY_SCHEMAS` | List of schemas in scope |
| `SV_CONNECTION` | Active Snowflake connection |
| `HAS_ACCOUNT_USAGE` | Whether ACCESS_HISTORY is accessible |
| `TOTAL_OBJECT_COUNT` | Number of queryable objects in scope |
| `OBJECT_TYPE_COUNTS` | Breakdown by type per schema |
| `EXISTING_SVS` | List of existing SVs with their table coverage |
| `COVERED_TABLES` | Set of table FQNs already in existing SVs |
| `MODE` | AUTONOMOUS or INTERACTIVE |

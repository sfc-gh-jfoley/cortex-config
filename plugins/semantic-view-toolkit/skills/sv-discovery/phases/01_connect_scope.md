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

For each found SV, describe it to understand table coverage:

```sql
DESCRIBE SEMANTIC VIEW <DB>.<SCHEMA>.<SV_NAME>;
```

Extract from each existing SV:
- Which tables it references
- How many columns/metrics/VQRs it has
- Relationship definitions

Store as:
- `EXISTING_SVS` — list of `{sv_fqn, tables_covered[], column_count, vqr_count, relationship_count}`
- `COVERED_TABLES` — flat set of all table FQNs already in an existing SV

Present to user:
```
Existing Semantic Views Found: <N>

| # | Semantic View | Tables Covered | VQRs | Status |
|---|---|---|---|---|
| 1 | DB.SCHEMA.SALES_SV | ORDERS, CUSTOMERS, PRODUCTS | 12 | Active |
| 2 | DB.SCHEMA.MARKETING_SV | CAMPAIGNS, LEADS | 5 | Active |

Tables already covered: <N> of <total>
Tables NOT covered: <remaining> (these are discovery candidates)
```

If no existing SVs found:
```
No existing semantic views found in <DISCOVERY_DB>. All tables are discovery candidates.
```

---

## Step 1.4: Enumerate All Queryable Objects

Count objects by type (not just BASE TABLEs — see `references/queryable-objects.md`):

```sql
-- Base tables and materialized views
SELECT
    TABLE_SCHEMA,
    TABLE_TYPE,
    COUNT(*) AS OBJECT_COUNT
FROM <DISCOVERY_DB>.INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA NOT IN ('INFORMATION_SCHEMA')
    AND TABLE_TYPE IN ('BASE TABLE', 'EXTERNAL TABLE', 'MATERIALIZED VIEW')
GROUP BY TABLE_SCHEMA, TABLE_TYPE
ORDER BY TABLE_SCHEMA, TABLE_TYPE;
```

```sql
-- Views (separate query since they may reference other databases)
SELECT
    TABLE_SCHEMA,
    COUNT(*) AS VIEW_COUNT
FROM <DISCOVERY_DB>.INFORMATION_SCHEMA.VIEWS
WHERE TABLE_SCHEMA NOT IN ('INFORMATION_SCHEMA')
GROUP BY TABLE_SCHEMA;
```

```sql
-- Dynamic tables
SELECT
    SCHEMA_NAME,
    COUNT(*) AS DT_COUNT
FROM <DISCOVERY_DB>.INFORMATION_SCHEMA.DYNAMIC_TABLES
GROUP BY SCHEMA_NAME;
```

Present comprehensive summary:

```
Database: ANALYTICS_DB

Schema          | Base Tables | Views | Dynamic Tables | External | Mat Views | Total
----------------|-------------|-------|----------------|----------|-----------|------
SALES           |          15 |     5 |              2 |        0 |         1 |   23
MARKETING       |          10 |     3 |              1 |        0 |         1 |   15
STAGING         |           8 |     0 |              0 |        0 |         0 |    8
DATA_LAKE       |           0 |     2 |              0 |        5 |         0 |    7
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

**GUIDED mode:** Mandatory gate — do NOT proceed until user confirms.
**AUTOPILOT mode:** Auto-confirm unless there are concerns (>200 objects, or existing SVs cover >80% of tables).

Present the scope summary:

```
Discovery scope:
  Database:       <DISCOVERY_DB>
  Schemas:        <comma-separated list, or "all (N schemas)">
  Object count:   <total objects in scope> (base tables: N, views: N, DTs: N, external: N, MVs: N)
  Existing SVs:   <N> (covering <M> tables)
  ACCESS_HISTORY: <available / not available>
  Connection:     <SV_CONNECTION>
  Mode:           <AUTOPILOT / GUIDED>

Proceed with scanning? (yes / adjust)
```

Wait for explicit user confirmation (GUIDED) or auto-proceed (AUTOPILOT).

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
| `MODE` | AUTOPILOT or GUIDED |

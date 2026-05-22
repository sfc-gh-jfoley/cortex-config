---
name: sv-discovery-phase1-connect-scope
description: Connect to the customer's Snowflake account, validate access, and scope the database/schemas to analyze for semantic view domain discovery
---

# Phase 1: Connect & Scope

## Purpose
Establish the target database, verify access to required metadata views, and let the user scope which schemas to analyze. This phase produces the boundary for all subsequent scanning.

---

## Step 1.1: Get target database

Ask the user:

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

## Step 1.2: Validate ACCOUNT_USAGE access

Run this query to confirm the current role can read ACCOUNT_USAGE views:

```sql
SELECT COUNT(*) AS ROW_CHECK
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE START_TIME >= DATEADD('day', -1, CURRENT_TIMESTAMP())
LIMIT 1;
```

**If this fails** (insufficient privileges):
```
ACCOUNT_USAGE access is not available for the current role.

Discovery can still run using INFORMATION_SCHEMA only (FK/PK constraints + column name inference).
Query co-occurrence and column usage analysis will be skipped.

Options:
  A) Switch to a role with ACCOUNT_USAGE access (e.g., ACCOUNTADMIN, or a role with IMPORTED PRIVILEGES on SNOWFLAKE database)
  B) Proceed with INFORMATION_SCHEMA only (reduced accuracy)
```

Store as:
- `HAS_ACCOUNT_USAGE` — `true` / `false`

---

## Step 1.3: List schemas in database

If the user did not specify schemas, enumerate what's available:

```sql
SELECT
    SCHEMA_NAME,
    CREATED,
    LAST_ALTERED
FROM <DISCOVERY_DB>.INFORMATION_SCHEMA.SCHEMATA
WHERE SCHEMA_NAME NOT IN ('INFORMATION_SCHEMA')
ORDER BY LAST_ALTERED DESC;
```

Then count tables per schema to help the user decide scope:

```sql
SELECT
    TABLE_SCHEMA,
    COUNT(*) AS TABLE_COUNT
FROM <DISCOVERY_DB>.INFORMATION_SCHEMA.TABLES
WHERE TABLE_TYPE = 'BASE TABLE'
  AND TABLE_SCHEMA NOT IN ('INFORMATION_SCHEMA')
GROUP BY TABLE_SCHEMA
ORDER BY TABLE_COUNT DESC;
```

Present a summary:

```
Database: ANALYTICS_DB

Schema          | Tables | Last Altered
----------------|--------|-------------
SALES           |     23 | 2025-01-10
MARKETING       |     15 | 2025-01-09
STAGING         |      8 | 2025-01-10
RAW             |     42 | 2025-01-08

Found 4 schemas with 88 total tables.

Shall I analyze all schemas, or focus on specific ones?
(Staging/Raw schemas are often excluded — they typically contain intermediate data not suited for semantic views.)
```

### Zero tables early exit

If the table count query returns **zero rows** (no base tables in any schema in scope):

```
⚠️ No base tables found in <DISCOVERY_DB> (or the specified schemas).

Semantic views require base tables as source data. Views alone are not sufficient.

Possible reasons:
  - The database contains only views (check TABLE_TYPE in INFORMATION_SCHEMA.TABLES)
  - The specified schema has no tables
  - Insufficient privileges to see tables in this database

Options:
  A) Try a different database or schema
  B) Include views in the scan (note: views may reference tables in other databases)
```

**GATE: Do NOT proceed to Phase 2 if TOTAL_TABLE_COUNT = 0.**

---

## Step 1.4: Confirm scope

⚠️ **MANDATORY GATE — Do NOT proceed until user confirms.**

Present the scope summary:

```
Discovery scope confirmed:
  Database:     <DISCOVERY_DB>
  Schemas:      <comma-separated list, or "all (N schemas)">
  Table count:  <total tables in scope>
  ACCOUNT_USAGE: <available / not available>
  Connection:   <SV_CONNECTION>

Proceed with scanning? (yes / adjust)
```

Wait for explicit user confirmation before loading Phase 2.

If user says "adjust", let them add/remove schemas and re-present the summary.

---

## Output variables passed to next phases

| Variable | Contents |
|----------|----------|
| `DISCOVERY_DB` | Target database name |
| `DISCOVERY_SCHEMAS` | List of schemas in scope |
| `SV_CONNECTION` | Active Snowflake connection |
| `HAS_ACCOUNT_USAGE` | Whether ACCOUNT_USAGE views are accessible |
| `TOTAL_TABLE_COUNT` | Number of base tables in scope |

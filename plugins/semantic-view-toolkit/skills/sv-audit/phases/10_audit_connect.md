---
name: sv-audit-phase10-audit-connect
description: Connect to an existing semantic view, describe its structure, and establish the audit scope
---

# Phase 10: Audit Connect & Describe

## Purpose
Connect to an existing semantic view, parse its full definition, measure column coverage against underlying tables, and confirm the user wants to proceed with a usage-based audit.

This phase has **one mandatory stopping point** — user must confirm audit scope before proceeding.

---

## Step 10.1: Get the semantic view FQN

Ask the user:

```
Which semantic view do you want to audit?
Provide the fully qualified name: DB.SCHEMA.SV_NAME
```

Store as `SV_FQN` (e.g., `ANALYTICS_DB.PUBLIC.SALES_SV`).

Parse into components:
- `SV_DB` — database
- `SV_SCHEMA` — schema
- `SV_NAME` — semantic view name

---

## Step 10.2: Confirm access and describe

Run DESCRIBE to verify access and extract the full definition:

```sql
DESCRIBE SEMANTIC VIEW <SV_FQN>;
```

If this fails with an access error, **stop and report**:
```
Cannot access <SV_FQN>.
Check that your role has USAGE on the database/schema and SELECT on the semantic view.
```

---

## Step 10.3: Parse DESCRIBE output

Extract the following from the DESCRIBE result:

**Tables in the SV:**
- Table names (with their database.schema.table references)
- Store as `SV_TABLES` — list of FQNs

**Columns defined:**
- All columns with their classification (FACT, DIMENSION, MEASURE/METRIC, TIME_DIMENSION)
- Column data types
- Which table each column belongs to
- Store as `SV_COLUMNS` — dict keyed by `table.column`

**Relationships defined:**
- FROM table/column → TO table/column
- Relationship type (if specified)
- Store as `SV_RELATIONSHIPS` — list of relationship definitions

**Verified queries:**
- Any verified query representations (VQRs) defined
- Store as `SV_VQRS` — list of VQR names/descriptions

---

## Step 10.4: Measure column coverage

For each table in the SV, count total columns in the underlying source table:

```sql
SELECT
    TABLE_CATALOG,
    TABLE_SCHEMA,
    TABLE_NAME,
    COUNT(*) AS TOTAL_COLUMNS
FROM <SV_DB>.INFORMATION_SCHEMA.COLUMNS
WHERE (TABLE_SCHEMA, TABLE_NAME) IN (
    ('<schema1>', '<table1>'),
    ('<schema2>', '<table2>')
    -- repeat for each table in SV_TABLES
)
GROUP BY 1, 2, 3;
```

**Note:** If SV tables span multiple databases, run one query per database using that database's `INFORMATION_SCHEMA.COLUMNS`.

Calculate:
- `TOTAL_SV_COLUMNS` — number of columns defined in the SV
- `TOTAL_SOURCE_COLUMNS` — sum of columns across all underlying tables
- `COVERAGE_PCT` — `TOTAL_SV_COLUMNS / TOTAL_SOURCE_COLUMNS * 100`

---

## Step 10.5: Present audit scope summary

Display the following summary:

```
Semantic View Audit Scope
═════════════════════════

  Semantic View:    <SV_FQN>
  Tables:           <N> tables included
  Columns in SV:    <X> (out of <Y> total in underlying tables)
  Coverage:         <X>/<Y> = <Z>%
  Relationships:    <N> defined
  Verified Queries: <N> defined

  Tables:
    - <DB.SCHEMA.TABLE1>  (<A> of <B> columns included)
    - <DB.SCHEMA.TABLE2>  (<C> of <D> columns included)
    ...
```

---

## MANDATORY STOP — User Confirms Audit

Ask the user:

```
Proceed with usage-based audit?

This will query SNOWFLAKE.ACCOUNT_USAGE views (QUERY_HISTORY, ACCESS_HISTORY)
to analyze the last 30 days of query patterns against these tables.

Requirements:
  - IMPORTED PRIVILEGES on SNOWFLAKE database (for ACCOUNT_USAGE views)
  - ACCESS_HISTORY requires Enterprise Edition or higher

Proceed? (yes / no)
```

**Wait for user confirmation before loading Phase 11.**

If user says no, stop and report: "Audit cancelled. The describe summary above is available for reference."

---

## Step 10.6: Store audit context

After user confirms, store these variables for subsequent phases:

## Output variables

| Variable | Contents |
|----------|----------|
| `SV_FQN` | Fully qualified semantic view name |
| `SV_DB`, `SV_SCHEMA`, `SV_NAME` | Parsed components |
| `SV_TABLES` | List of FQN table references in the SV |
| `SV_COLUMNS` | Dict: table.column → {classification, data_type} |
| `SV_RELATIONSHIPS` | List of relationship definitions |
| `SV_VQRS` | List of verified query representations |
| `TOTAL_SV_COLUMNS` | Count of columns in the SV |
| `TOTAL_SOURCE_COLUMNS` | Count of columns in underlying tables |
| `COVERAGE_PCT` | Column coverage percentage |

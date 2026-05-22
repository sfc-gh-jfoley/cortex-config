---
name: sv-ddl-phase8-drift-monitor
description: Periodic drift detection for deployed semantic views — finds missing tables/columns from query history, scores gaps, generates remediation DDL, and offers scheduled recurrence
---

# Phase 8: Drift Monitor (Scheduled Maintenance)

## Purpose

Detect drift between a deployed semantic view and actual usage patterns. Runs as:
- **Manual check** — user invokes directly ("check drift on my SV")
- **Scheduled task** — weekly/monthly via CoCo cron

This phase can run standalone (without Phases 1-7) on any existing semantic view.

### Source object type considerations

The drift monitor works identically for all supported source types:
- **Tables**: Check `INFORMATION_SCHEMA.COLUMNS` for schema changes
- **Views**: Same approach — `INFORMATION_SCHEMA.COLUMNS` reports view columns
- **Dynamic tables**: Same approach — columns are visible in `INFORMATION_SCHEMA.COLUMNS`
- **Secure views**: Same approach, though column metadata may be restricted for non-owner roles

All supported source types respond to `DESCRIBE TABLE <fqn>` and appear in `INFORMATION_SCHEMA.COLUMNS`, so no branching is needed in the drift detection queries.

> **Future**: When composable semantic views (SV referencing another SV) become GA, drift detection for upstream SVs will need to use `DESCRIBE SEMANTIC VIEW` and `SHOW SEMANTIC FACTS/DIMS/METRICS` instead of `INFORMATION_SCHEMA.COLUMNS`. This is not yet implemented.

---

## Entry

Two paths into this phase:

### Path A: Continuation from Phase 7
SV context already available (`SV_DB`, `SV_SCHEMA`, `SV_NAME`, `SOURCE_OBJECTS`).
Skip to Step 8.2.

### Path B: Standalone invocation
Triggered by phrases like "check SV drift", "semantic view health check", "schedule SV maintenance".
Start at Step 8.1.

---

## Step 8.1: Identify the semantic view (standalone only)

Ask: "Which semantic view should I check for drift? Provide the fully qualified name (DB.SCHEMA.SV_NAME)."

Once provided:
```sql
DESCRIBE SEMANTIC VIEW <SV_DB>.<SV_SCHEMA>.<SV_NAME>;
```

Extract:
- `SOURCE_OBJECTS` — all objects (tables, views, dynamic tables) referenced in the SV
- `SV_COLUMNS` — all exposed facts + dimensions + metrics
- `SV_COLUMN_COUNT` — total column count

If DESCRIBE fails, the SV doesn't exist — stop and inform user.

---

## Step 8.2: Configure lookback window

Ask: "How far back should I look in query history? Default is 90 days."

Store as `LOOKBACK_DAYS` (default 90).

---

## Step 8.3: Measure query population

```sql
WITH sv_queries AS (
    SELECT query_id, user_name, query_text, start_time
    FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
    WHERE start_time >= DATEADD('days', -:LOOKBACK_DAYS, CURRENT_TIMESTAMP())
      AND execution_status = 'SUCCESS'
      AND query_type IN ('SELECT', 'CTAS', 'INSERT')
      AND (
          UPPER(query_text) LIKE '%<TABLE_1_SHORT>%'
          OR UPPER(query_text) LIKE '%<TABLE_2_SHORT>%'
          -- repeat per SV source object (use short name without DB.SCHEMA prefix)
      )
)
SELECT COUNT(DISTINCT query_id) AS total_queries,
       COUNT(DISTINCT user_name) AS unique_users
FROM sv_queries;
```

Store as `QUERY_POPULATION_SIZE`. If < 20 queries, warn: "Low query signal — results may be noisy. Proceed anyway?"

---

## Step 8.4: Detect missing tables

Find objects co-queried with SV source objects but not included in the SV.

```sql
WITH sv_queries AS (
    SELECT query_id, user_name, query_text
    FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
    WHERE start_time >= DATEADD('days', -:LOOKBACK_DAYS, CURRENT_TIMESTAMP())
      AND execution_status = 'SUCCESS'
      AND (UPPER(query_text) LIKE '%<TABLE_1_SHORT>%' OR ...)
),
table_refs AS (
    SELECT
        query_id,
        user_name,
        UPPER(REGEXP_SUBSTR(
            query_text,
            '(?:FROM|JOIN)\\s+(?:[A-Z0-9_$]+\\.){0,2}([A-Z0-9_$]+)',
            1, seq4.seq, 'ie', 1
        )) AS candidate_table
    FROM sv_queries
    CROSS JOIN TABLE(GENERATOR(ROWCOUNT => 20)) seq4
    WHERE candidate_table IS NOT NULL AND LENGTH(candidate_table) > 3
)
SELECT
    candidate_table,
    COUNT(DISTINCT query_id)  AS query_count,
    COUNT(DISTINCT user_name) AS unique_users,
    ROUND(query_count / :QUERY_POPULATION_SIZE * 100, 1) AS pct_of_queries
FROM table_refs
WHERE candidate_table NOT IN (<SV_TABLE_SHORT_NAMES>)
  AND candidate_table NOT IN ('SELECT','WHERE','FROM','JOIN','ON','AND','OR','AS','NULL','INTO','VALUES','SET','CASE','WHEN','THEN','ELSE','END')
GROUP BY 1
HAVING query_count >= 5
ORDER BY query_count DESC
LIMIT 15;
```

### Score each TABLE_GAP candidate

| Signal | Score |
|--------|-------|
| pct_of_queries >= 30% | +3 |
| pct_of_queries 10-29% | +2 |
| pct_of_queries 5-9% | +1 |
| unique_users >= 5 | +2 |
| candidate_col_count <= 10 | +1 (small table, low complexity) |
| candidate_col_count > 30 | -2 (large table, may confuse Analyst) |
| SV_COLUMN_COUNT + candidate_col_count > 100 | -3 (SV already large) |
| Table name contains _LOG, _AUDIT, _HIST, _STG, _RAW | -3 (ETL/audit pattern) |
| Direct FK join to existing SV table | +1 |

**Recommendation**: Score >= 4 → **ADD** | 1-3 → **REVIEW** | <= 0 → **SKIP**

---

## Step 8.5: Detect missing columns

Find columns referenced in queries but absent from the SV.

```sql
WITH sv_queries AS (
    SELECT query_id, user_name, query_text
    FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
    WHERE start_time >= DATEADD('days', -:LOOKBACK_DAYS, CURRENT_TIMESTAMP())
      AND execution_status = 'SUCCESS'
      AND (UPPER(query_text) LIKE '%<TABLE_1_SHORT>%' OR ...)
),
col_refs AS (
    SELECT
        query_id,
        user_name,
        UPPER(REGEXP_SUBSTR(
            query_text,
            '(?:SELECT|WHERE|AND|OR|GROUP BY|ORDER BY)[\\s,]+([A-Z_][A-Z0-9_]+)',
            1, seq4.seq, 'ie', 1
        )) AS candidate_col,
        CASE
            WHEN UPPER(query_text) LIKE '%WHERE%' || candidate_col || '%' THEN 'filter'
            WHEN UPPER(query_text) LIKE '%GROUP BY%' || candidate_col || '%' THEN 'group_by'
            ELSE 'select'
        END AS usage_context
    FROM sv_queries
    CROSS JOIN TABLE(GENERATOR(ROWCOUNT => 30)) seq4
    WHERE candidate_col IS NOT NULL AND LENGTH(candidate_col) > 3
)
SELECT
    candidate_col,
    COUNT(DISTINCT query_id)  AS query_count,
    COUNT(DISTINCT user_name) AS unique_users,
    LISTAGG(DISTINCT usage_context, ', ') WITHIN GROUP (ORDER BY usage_context) AS usage_contexts
FROM col_refs
WHERE candidate_col NOT IN (<SV_COLUMN_NAMES>)
  AND candidate_col NOT IN ('FROM','WHERE','JOIN','NULL','TRUE','FALSE','CASE','WHEN','THEN','ELSE','END','LIMIT','OFFSET','DESC','ASC','COUNT','SUM','AVG','MIN','MAX','DISTINCT')
GROUP BY 1
HAVING query_count >= 3
ORDER BY query_count DESC
LIMIT 20;
```

### Score each COLUMN_GAP candidate

| Signal | Score |
|--------|-------|
| usage_context includes 'filter' | +3 (users filter on this — Analyst needs it) |
| usage_context includes 'group_by' | +2 (important dimension) |
| unique_users >= 3 | +2 |
| query_count >= 10 | +1 |
| Column name matches ETL patterns (_ID suffix on non-key, _TS, _SEQ, _HASH) | -2 |
| Column name matches PII patterns (EMAIL, SSN, PHONE, DOB) | -2 (note: access risk) |

**Recommendation**: Score >= 4 → **ADD** | 1-3 → **REVIEW** | <= 0 → **SKIP**

---

## Step 8.6: Detect schema drift (new source columns)

For each source object in the SV, compare INFORMATION_SCHEMA columns against what's exposed:

```sql
SELECT c.column_name, c.data_type, c.ordinal_position
FROM <DB>.INFORMATION_SCHEMA.COLUMNS c
WHERE c.table_schema = '<SCHEMA>'
  AND c.table_name = '<TABLE>'
  AND UPPER(c.column_name) NOT IN (<SV_COLUMNS_FROM_THIS_TABLE>)
ORDER BY c.ordinal_position;
```

New columns found here are **schema drift** — the table grew but the SV wasn't updated.

Score: same COLUMN_GAP framework, but add +1 for "column exists in source but never exposed" (intentional coverage gap signal).

---

## Step 8.7: Dimension enrichment check

For VARCHAR dimensions already in the SV, check if COMMENT contains sample_values:

```sql
-- Get current SV dimension descriptions
DESCRIBE SEMANTIC VIEW <SV_FQN>;
```

For each VARCHAR/TEXT dimension where COMMENT does NOT contain pipe-separated values, fetch top 10:
```sql
SELECT DISTINCT <col> FROM <source_table> WHERE <col> IS NOT NULL ORDER BY 1 LIMIT 10;
```

**Recommendation**: Always **ADD** sample values — zero downside, improves literal matching.

---

## Step 8.8: Present drift manifest

Present all findings in a single table:

```
╔══════════════════════════════════════════════════════════════╗
║  DRIFT REPORT: <SV_FQN>                                     ║
║  Lookback: <LOOKBACK_DAYS> days | Queries analyzed: <N>      ║
╚══════════════════════════════════════════════════════════════╝

TABLE GAPS:
  [ADD]    PAYMENT_DETAILS     (score: 5, 34% of queries, 8 users)
  [REVIEW] AUDIT_LOG_SUMMARY   (score: 2, 12% of queries, 3 users)
  [SKIP]   ETL_LOAD_STATUS     (score: -1, 6% of queries, 1 user)

COLUMN GAPS:
  [ADD]    CUSTOMER_SEGMENT    (score: 6, filter+group_by, 12 queries, 5 users)
  [ADD]    REGION_CODE         (score: 4, filter, 8 queries, 4 users)
  [REVIEW] INTERNAL_FLAG       (score: 2, select only, 4 queries, 2 users)

SCHEMA DRIFT (new source columns):
  [ADD]    ORDERS.DELIVERY_DATE  (DATE, added to source, not in SV)
  [SKIP]   ORDERS._ETL_HASH      (VARCHAR, ETL pattern)

DIMENSION ENRICHMENT:
  [ADD]    ORDER_STATUS — missing sample_values (top 10: PENDING, SHIPPED, ...)
  [ADD]    CUSTOMER_TIER — missing sample_values (top 10: GOLD, SILVER, ...)
```

**⚠️ STOPPING POINT** — Wait for user to approve/reject each item.

Ask: "Which items should I apply? Reply with numbers, 'all ADD', or specific selections."

---

## Step 8.9: Generate remediation DDL

For approved items:

### New columns → ALTER SEMANTIC VIEW
```sql
ALTER SEMANTIC VIEW <SV_FQN>
  ADD DIMENSION <table_alias>.<col_name>
  AS <col_name>
  COMMENT = '<auto-generated description>';
```

### New tables → CREATE OR REPLACE
If a new source object is approved, a full `CREATE OR REPLACE SEMANTIC VIEW` is needed (new logical tables can't be ALTERed in). Use the existing DDL from `GET_DDL('SEMANTIC_VIEW', '<SV_FQN>')` as the base, add the new object + its columns.

### Sample values → ALTER COMMENT
```sql
ALTER SEMANTIC VIEW <SV_FQN>
  ALTER DIMENSION <table_alias>.<dim_name>
  SET COMMENT = '<description> | Sample values: VAL1, VAL2, VAL3, ...';
```

Ask: "Want me to create a rollback clone first?" (per DDL rule). Then execute approved DDL.

---

## Step 8.10: Offer scheduled recurrence

After drift check completes (or if no drift found):

Ask: "Want to schedule this drift check to run automatically?"

Options:
- **Weekly** — every Monday at 9:00 AM
- **Monthly** — 1st of each month at 9:00 AM
- **Custom** — user provides cron expression
- **Skip** — no schedule

If scheduled, create via cron:
```
cron_create:
  schedule: "0 9 * * 1"  (weekly Monday) or "0 9 1 * *" (monthly 1st)
  prompt: "Run Phase 8 drift check on <SV_FQN> with lookback <LOOKBACK_DAYS> days. Present findings and wait for approval before applying changes."
```

Confirm: "Drift check scheduled: <schedule description>. I'll check <SV_FQN> and present findings for your approval each time."

> **Note**: CoCo cron jobs are session-scoped with 3-day expiry. For persistent scheduling, use `/loop` instead. Mention this to the user.

---

## Step 8.11: Summary

```
✅ Drift Check Complete

  Semantic View:    <SV_FQN>
  Lookback:         <LOOKBACK_DAYS> days
  Queries analyzed: <N>

  Findings:
    Table gaps:     N (M applied)
    Column gaps:    N (M applied)
    Schema drift:   N (M applied)
    Enrichments:    N (M applied)

  Schedule: <weekly/monthly/none>

  Next check: <date or "manual">
```

---
name: sv-watch
description: >
  Monitor semantic views for drift, schema changes, coverage decay, and VQR staleness.
  Detects when source tables change, new tables appear that should be covered,
  or verified queries become stale. Cron-compatible for scheduled checks.
triggers:
  - watch semantic views
  - sv drift
  - monitor SV
  - schema changed
  - new tables appeared
  - SV maintenance
  - drift detection
  - stale VQR
---

# SV Watch Skill

## When to Use

Use this skill for ongoing production maintenance of semantic views:
- Source table schemas changed (new/dropped/renamed columns)
- New tables appeared in SV schemas that aren't covered
- VQRs reference time-relative concepts that have drifted
- Column usage patterns shifted (popular columns not in SV)
- Source objects dropped or replaced

---

## Execution Modes

### Manual (One-shot)
```
$semantic-view-toolkit
"Watch my SVs for drift"
```
Runs once, reports findings, suggests actions.

### Scheduled (Cron)
```
$semantic-view-toolkit
"Set up weekly drift monitoring for my SVs"
```
Creates a cron job that runs watch checks and alerts on findings.

---

## Watch Checks

### Check 1: Schema Drift
Compare current DESCRIBE SEMANTIC VIEW against source table schemas:
- **New columns**: source table has columns not in SV → candidate additions
- **Dropped columns**: SV references columns that no longer exist → CRITICAL
- **Type changes**: column data type changed in source → potential breakage
- **Renamed columns**: column disappeared + new similarly-named column appeared → likely rename

```sql
-- Get current source columns
SELECT TABLE_CATALOG, TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME, DATA_TYPE
FROM <DB>.INFORMATION_SCHEMA.COLUMNS
WHERE (TABLE_SCHEMA, TABLE_NAME) IN (
    -- tables from DESCRIBE SEMANTIC VIEW
);

-- Compare against SV_COLUMNS from DESCRIBE
```

### Check 2: Coverage Decay
Tables in the same schemas as SV sources that are now actively queried but not covered:

```sql
-- Tables queried in last 30 days that share schema with SV tables
WITH sv_schemas AS (...),
queried_tables AS (
    SELECT DISTINCT obj.value:objectName::VARCHAR AS table_fqn
    FROM SNOWFLAKE.ACCOUNT_USAGE.ACCESS_HISTORY ah,
        LATERAL FLATTEN(input => ah.BASE_OBJECTS_ACCESSED) obj
    WHERE ah.QUERY_START_TIME >= DATEADD('day', -30, CURRENT_TIMESTAMP())
)
SELECT qt.table_fqn
FROM queried_tables qt
WHERE qt.table_fqn NOT IN (SELECT fqn FROM sv_tables)
  AND SPLIT_PART(qt.table_fqn, '.', 2) IN (SELECT schema_name FROM sv_schemas);
```

### Check 3: VQR Staleness
Detect VQRs with time-relative references that may have drifted:
- Pattern match VQR SQL for: `CURRENT_DATE`, `DATEADD`, `last_month`, `this_quarter`
- Flag VQRs older than 90 days with relative date references
- Suggest converting to absolute dates or refreshing

### Check 4: Source Object Health
- Dynamic Tables: check REFRESH_STATUS (is it failing?)
- External Tables: check if files still exist
- Views: check if underlying tables still exist

```sql
-- DT health check
SELECT NAME, REFRESH_STATUS, REFRESH_STATUS_MESSAGE, TARGET_LAG
FROM INFORMATION_SCHEMA.DYNAMIC_TABLES
WHERE NAME IN (-- DT names from SV sources);
```

### Check 5: Usage Pattern Shift
Compare column access patterns from last 30 days vs previous 30 days:
- Columns with growing access that aren't in SV → suggest adding
- SV columns with declining access → informational (don't auto-remove)

---

## Output Format

```
# SV Watch Report: <SV_FQN>
# Run: <timestamp>

## CRITICAL (Immediate Action Required)
- [DROPPED_COLUMN] Column ORDERS.STATUS no longer exists in source table
  → SV will fail on queries referencing this column
  → Fix: ALTER SEMANTIC VIEW to remove or remap

## WARNING (Review Recommended)
- [NEW_COLUMNS] 3 new columns in ORDERS table not in SV:
    - SHIPPING_METHOD (VARCHAR) — added 2025-01-15
    - ESTIMATED_DELIVERY (DATE) — added 2025-01-15
    - IS_EXPEDITED (BOOLEAN) — added 2025-01-20
  → Consider adding if relevant to SV domain

- [COVERAGE_DECAY] Table RETURNS (same schema) now gets 45 queries/day
    but is not in any semantic view
  → Consider adding to SV or creating new SV

## INFO (No Action Required)
- [VQR_STALE] VQR "What were last month's sales?" is 95 days old
    with relative date reference
  → Consider refreshing or converting to absolute date

- [USAGE_SHIFT] Column ORDERS.PRIORITY access up 340% vs previous period
    (already in SV as dimension)
  → No action needed — already covered
```

---

## Persistence

Watch results are stored in `_SV_TOOLKIT_META.WATCH_LOG`:

```sql
CREATE TABLE IF NOT EXISTS <DB>._SV_TOOLKIT_META.WATCH_LOG (
    RUN_TIMESTAMP TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP(),
    SV_FQN VARCHAR,
    CHECK_TYPE VARCHAR,  -- SCHEMA_DRIFT, COVERAGE_DECAY, VQR_STALE, SOURCE_HEALTH, USAGE_SHIFT
    SEVERITY VARCHAR,    -- CRITICAL, WARNING, INFO
    FINDING VARCHAR,
    RECOMMENDED_ACTION VARCHAR,
    RESOLVED BOOLEAN DEFAULT FALSE,
    RESOLVED_TIMESTAMP TIMESTAMP_LTZ
);
```

---

## Cron Integration

```python
# Example cron setup (weekly Monday 6am)
cron_create(
    schedule="0 6 * * 1",
    prompt="Run sv-watch on all semantic views in ANALYTICS_DB. Report findings."
)
```

---

## Integration with Toolkit

- **Triggers sv-audit**: CRITICAL/WARNING findings can feed into sv-audit for deeper analysis
- **Triggers sv-optimization**: repeated drift patterns suggest optimization opportunities
- **Fed by sv-ddl**: after creating/modifying a SV, set up watch
- **Independent**: can run standalone without any prior toolkit usage

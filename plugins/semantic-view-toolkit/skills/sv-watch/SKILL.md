---
name: sv-watch
description: >
  Monitor semantic views for drift, schema changes, coverage decay, and VQR staleness.
  Detects when source tables change, new tables appear that should be covered,
  or verified queries become stale. Owns drift monitoring for the toolkit. Read-only;
  any fix goes through a candidate copy and gate SV-PROMOTE.
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

## Execution Mode

Inherits the session mode declared at the toolkit router. Never re-asks.

- **INTERACTIVE** (one-shot manual runs): Check findings are presented and recommendations require user confirmation before any action is taken.
- **AUTONOMOUS / Scheduled**: All watch checks (Checks 1–6) run automatically. `CREATE TABLE IF NOT EXISTS` on `WATCH_LOG` runs without prompting (gate `WATCH-METADATA-SETUP`, AUTO_REMEDIATE). Drift findings, including CRITICAL ones, are logged and the run continues (gate `WATCH-DRIFT-ALERT`, AUTO_RESOLVE); the report lists CRITICAL findings first so the next human review sees them.

**This skill never changes a semantic view.** It reports. A fix is made on a `cand` candidate
copy and reaches production only through gate `SV-PROMOTE` (OPERATOR_REQUIRED in both modes;
see `../../references/candidate-promotion.md`). Existing VQRs are read-only (`SV-VQR-MUTATE`):
report VQR findings as observations, never offer to rewrite them.

---

## Run Modes

### Manual (One-shot)
```
$semantic-view-toolkit
"Watch my SVs for drift"
```
Runs once, reports findings, suggests actions.

### Recurring
See [Scheduling](#scheduling). Session-based schedules end with the session, so recurring
monitoring needs a Snowflake task or a manual cadence.

---

## Watch Checks

### Check 1: Schema Drift
Compare the SV's columns (from `DESCRIBE SEMANTIC VIEW`) against its source tables. Get the
source tables from `INFORMATION_SCHEMA.SEMANTIC_TABLES` in the SV's database, then read each
source's own database `INFORMATION_SCHEMA.COLUMNS` (sources can live in other databases):
- **New columns**: source table has columns not in SV → candidate additions
- **Dropped columns**: SV references columns that no longer exist → CRITICAL
- **Type changes**: column data type changed in source → potential breakage
- **Renamed columns**: column disappeared + new similarly-named column appeared → likely rename

```sql
-- 1. Source tables of the SV
SELECT base_table_catalog, base_table_schema, base_table_name
FROM <SV_DB>.INFORMATION_SCHEMA.SEMANTIC_TABLES
WHERE semantic_view_schema = '<SV_SCHEMA>' AND semantic_view_name = '<SV_NAME>';

-- 2. Current columns, once per distinct base_table_catalog (<SRC_DB>)
SELECT table_catalog, table_schema, table_name, column_name, data_type
FROM <SRC_DB>.INFORMATION_SCHEMA.COLUMNS
WHERE (table_schema, table_name) IN (('<SRC_SCHEMA>', '<SRC_TABLE>') /* , ... */);

-- 3. Compare against the DESCRIBE SEMANTIC VIEW output for <SV_FQN>
```

### Check 2: Coverage Decay
Tables in the same schemas as SV sources that are now actively queried but not covered:

`ACCESS_HISTORY` requires Enterprise Edition and has up to a few hours of latency. Keep the
30-day bound; the scan is expensive on busy accounts.

```sql
-- Tables queried in the last 30 days, in the same database AND schema as an SV source,
-- that are not SV sources themselves
WITH sv_sources AS (
    SELECT DISTINCT base_table_catalog, base_table_schema, base_table_name
    FROM <SV_DB>.INFORMATION_SCHEMA.SEMANTIC_TABLES
    WHERE semantic_view_schema = '<SV_SCHEMA>' AND semantic_view_name = '<SV_NAME>'
),
sv_schemas AS (
    SELECT DISTINCT base_table_catalog AS db, base_table_schema AS sch FROM sv_sources
),
queried AS (
    SELECT obj.value:"objectName"::VARCHAR AS table_fqn, COUNT(*) AS queries_30d
    FROM SNOWFLAKE.ACCOUNT_USAGE.ACCESS_HISTORY ah,
         LATERAL FLATTEN(input => ah.base_objects_accessed) obj
    WHERE ah.query_start_time >= DATEADD('day', -30, CURRENT_TIMESTAMP())
      AND obj.value:"objectDomain"::VARCHAR = 'Table'
    GROUP BY 1
)
SELECT q.table_fqn, q.queries_30d
FROM queried q
JOIN sv_schemas s
  ON SPLIT_PART(q.table_fqn, '.', 1) = s.db AND SPLIT_PART(q.table_fqn, '.', 2) = s.sch
WHERE NOT EXISTS (
    SELECT 1 FROM sv_sources t
    WHERE q.table_fqn = t.base_table_catalog || '.' || t.base_table_schema || '.' || t.base_table_name)
ORDER BY q.queries_30d DESC;
```

`SPLIT_PART` assumes unquoted identifiers without dots; quoted names need manual review.

### Check 3: VQR Staleness
Detect VQRs with time-relative references that may have drifted:
- Read VQRs from `DESCRIBE SEMANTIC VIEW` (`AI_VERIFIED_QUERY` rows; the `VERIFIED_AT` property is epoch seconds)
- Pattern match VQR SQL for: `CURRENT_DATE`, `DATEADD`, `last_month`, `this_quarter`
- Flag VQRs whose `VERIFIED_AT` is older than 90 days and that use relative date references
- Report only. Do not suggest rewriting or refreshing them (`SV-VQR-MUTATE`); the owner decides

### Check 4: Source Object Health
- Dynamic Tables: check SCHEDULING_STATE (is it ACTIVE or SUSPENDED?)
- External Tables: check if files still exist
- Views: check if underlying tables still exist

```sql
-- DT health check. INFORMATION_SCHEMA.DYNAMIC_TABLES() also exists, as a table function
-- (refresh metadata for the last 7 days); SHOW gives the current scheduling state.
SHOW DYNAMIC TABLES IN DATABASE <SRC_DB>
  ->> SELECT "name" AS NAME, "scheduling_state" AS SCHEDULING_STATE, "target_lag" AS TARGET_LAG
      FROM $1
      WHERE "name" IN (-- DT names from SV sources);
```

### Check 5: Usage Pattern Shift
Compare column access patterns from last 30 days vs previous 30 days:
- Columns with growing access that aren't in SV → suggest adding
- SV columns with declining access → informational (don't auto-remove)

### Check 6: Materialization Health

For SVs that have `MAX_STALENESS` set (indicating materializations may exist), check that
all materializations are ACTIVE and refreshing within their staleness window.

```sql
-- Check if any SV has MAX_STALENESS set
SELECT semantic_view_name, semantic_view_database_name, semantic_view_schema_name,
       max_stalesness_sec
FROM SNOWFLAKE.ACCOUNT_USAGE.SEMANTIC_VIEWS
WHERE max_stalesness_sec IS NOT NULL
  AND semantic_view_database_name = '<DB>'
  AND deleted IS NULL;
```

For each SV with MAX_STALENESS set, list its materializations first (needs only SELECT on the SV):

```sql
SHOW MATERIALIZATIONS IN SEMANTIC VIEW <SV_FQN>;
-- Flag rows with "state" = 'SUSPENDED'; "suspend_reason" says why, "stale_by" says when it goes stale
```

Then, for drill-down on a listed name, run the history function in the SV's database (the
function takes a materialization name, not an SV name; check the result belongs to this SV if
names repeat across SVs in that database):

```sql
USE DATABASE <SV_DB>;
-- Check refresh history — flag SUSPENDED state or long gaps between refreshes
SELECT name, state, state_message,
       refresh_start_time, refresh_end_time,
       warehouse, refresh_action
FROM TABLE(INFORMATION_SCHEMA.SEMANTIC_VIEW_MATERIALIZATION_REFRESH_HISTORY(
  NAME => '<mat_name from SHOW MATERIALIZATIONS>'
))
ORDER BY refresh_start_time DESC
LIMIT 5;
```

**Flag as WARNING when:**
- `state = 'SUSPENDED'` in `SHOW MATERIALIZATIONS` — refresh failure, falling behind MAX_STALENESS, or manual suspend (see `suspend_reason`)
- Last successful refresh timestamp is > 2× MAX_STALENESS ago

**Flag as INFO when:**
- `refresh_action = 'NO_DATA'` consistently — no new data arriving; materialization is current
- Refresh duration is approaching MAX_STALENESS — staleness risk increasing

**Output format for Check 6:**
```
## WARNING (Materialization Health)
- [MAT_SUSPENDED] Materialization 'cust_year_rollup' on sv_revenue is SUSPENDED
    suspend_reason: <from SHOW MATERIALIZATIONS>
    Last refresh: <timestamp>
  → Likely cause: MAX_STALENESS too tight, or the refresh warehouse too small
  → Next step: route to sv-materialize (its changes to production go through SV-PROMOTE)
```

---

## Output Format

```
# SV Watch Report: <SV_FQN>
# Run: <timestamp>

## CRITICAL (Immediate Action Required)
- [DROPPED_COLUMN] Column ORDERS.STATUS no longer exists in source table
  → SV will fail on queries referencing this column
  → Fix: remove or remap it on a `cand` candidate copy, evaluate, then gate SV-PROMOTE

## WARNING (Review Recommended)
- [NEW_COLUMNS] 3 new columns in ORDERS table not in SV:
    - SHIPPING_METHOD (VARCHAR)
    - ESTIMATED_DELIVERY (DATE)
    - IS_EXPEDITED (BOOLEAN)
  → Consider adding if relevant to SV domain

- [COVERAGE_DECAY] Table RETURNS (same schema) now gets 45 queries/day
    but is not in any semantic view
  → Consider adding to SV or creating new SV

## INFO (No Action Required)
- [VQR_STALE] VQR "What were last month's sales?" VERIFIED_AT is 95 days old
    and uses a relative date reference
  → Observation only (SV-VQR-MUTATE); the SV owner decides whether to re-verify it

- [USAGE_SHIFT] Column ORDERS.PRIORITY access up 340% vs previous period
    (already in SV as dimension)
  → No action needed — already covered
```

---

## Persistence

Watch results are stored in `_SV_TOOLKIT_META.WATCH_LOG`:

> **Note (INTERACTIVE mode only):** When creating `_SV_TOOLKIT_META` for the first time
> in INTERACTIVE mode (gate `META-ROLLBACK-CLONE`), offer: "Want me to create a rollback clone first?
> (`CREATE DATABASE <db>_RESTORE CLONE <db>`)"
> In AUTONOMOUS/scheduled mode, `CREATE TABLE IF NOT EXISTS` is additive and idempotent
> — no prompt; scheduled runs must not block on this.

```sql
CREATE TABLE IF NOT EXISTS <DB>._SV_TOOLKIT_META.WATCH_LOG (
    RUN_ID VARCHAR,      -- one id per watch run
    FINDING_KEY VARCHAR, -- stable key, e.g. CHECK_TYPE || ':' || object; dedupe across runs on this
    RUN_TIMESTAMP TIMESTAMP_LTZ DEFAULT CURRENT_TIMESTAMP(),
    SV_FQN VARCHAR,
    CHECK_TYPE VARCHAR,  -- SCHEMA_DRIFT, COVERAGE_DECAY, VQR_STALE, SOURCE_HEALTH, USAGE_SHIFT, MAT_HEALTH
    SEVERITY VARCHAR,    -- CRITICAL, WARNING, INFO
    FINDING VARCHAR,
    RECOMMENDED_ACTION VARCHAR,
    RESOLVED BOOLEAN DEFAULT FALSE,
    RESOLVED_TIMESTAMP TIMESTAMP_LTZ
);
```

---

## Scheduling

Cortex Code session schedules (`/loop`, session cron tools) run only while the session lives and
may expire; do not present them as recurring monitoring. Offer one of:

1. **Manual cadence** (default): the user runs "Run sv-watch on <SV_FQN>" weekly. This skill owns
   the checks; there is no separate drift phase elsewhere.
2. **Snowflake task**: a `CREATE TASK ... SCHEDULE = 'USING CRON 0 9 * * 1 <tz>'` that runs the
   deterministic SQL checks (1, 4, 6) and inserts rows into `WATCH_LOG`. The toolkit does not
   ship this task; writing one is a new object and needs the user's approval, a warehouse, and
   `CREATE TASK` + `EXECUTE TASK`. Checks 2, 3 and 5 still need an agent run to interpret.
3. **Event-table alerts for materializations**: `ALTER SEMANTIC VIEW <SV> ALTER MATERIALIZATION
   <name> SET LOG_EVENT_LEVEL = 'INFO'` (see the materializations guide); this is a change to the
   SV and goes through `SV-PROMOTE`.

---

## Integration with Toolkit

- **Triggers sv-audit**: CRITICAL/WARNING findings can feed into sv-audit for deeper analysis
- **Triggers sv-iterative-optimizer**: repeated drift patterns suggest optimization opportunities
- **Triggers sv-materialize**: MAT_HEALTH SUSPENDED findings route to sv-materialize for diagnosis
- **Fed by sv-ddl**: after sv-ddl creates or promotes an SV, set up watch (sv-ddl has no drift phase of its own)
- **Independent**: can run standalone without any prior toolkit usage

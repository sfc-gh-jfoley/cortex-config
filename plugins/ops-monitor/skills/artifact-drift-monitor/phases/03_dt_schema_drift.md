---
name: artifact-drift-monitor-phase3
description: DT source-schema drift — score each new/changed/dropped column with ADD/SKIP reasoning
---

# Phase 3: Dynamic Table Schema Drift Detection

Inputs: `ARTIFACT_NAME`, `DT_SOURCE_TABLES`, `DT_COLUMNS`, `DT_SELECT_STAR`, `LOOKBACK_DAYS`

Critical for streaming and CDC sources (Kafka, Snowpipe Streaming, AppendOnly tables).

---

## Step 3.1: Get current DT output columns

```sql
SELECT
    column_name,
    data_type,
    numeric_precision,
    numeric_scale,
    character_maximum_length,
    is_nullable,
    ordinal_position
FROM <DT_DB>.INFORMATION_SCHEMA.COLUMNS
WHERE table_schema = '<DT_SCHEMA>'
  AND table_name   = '<DT_SHORT_NAME>'
ORDER BY ordinal_position;
```

Also fetch DT metadata:
```sql
SHOW DYNAMIC TABLES LIKE '<DT_SHORT_NAME>' IN SCHEMA <DT_DB>.<DT_SCHEMA>;
```
Extract: `created_on`, `data_timestamp` (last refresh), `scheduling_state`, `target_lag`.

Store as `DT_CURRENT_COLUMNS`.

---

## Step 3.2: Get source table current columns

For each table in `DT_SOURCE_TABLES`:

```sql
SELECT
    column_name,
    data_type,
    numeric_precision,
    numeric_scale,
    character_maximum_length,
    is_nullable,
    ordinal_position,
    column_default
FROM <SOURCE_DB>.INFORMATION_SCHEMA.COLUMNS
WHERE table_schema = '<SOURCE_SCHEMA>'
  AND table_name   = '<SOURCE_TABLE>'
ORDER BY ordinal_position;
```

Store as `SOURCE_COLUMNS_MAP`.

---

## Step 3.3: Diff and score new columns

### Case A: Explicit column list DT
Columns added to the source after DT creation are silently excluded.

### Case B: SELECT * DT
⚠️ `SELECT *` in a DT is frozen at creation time — new source columns are NOT picked up automatically. Must recreate the DT to capture them.

```sql
-- Find columns in source but NOT in DT output
WITH dt_cols AS (
    SELECT column_name
    FROM <DT_DB>.INFORMATION_SCHEMA.COLUMNS
    WHERE table_name = '<DT_SHORT_NAME>' AND table_schema = '<DT_SCHEMA>'
),
source_cols AS (
    SELECT column_name, data_type, is_nullable, ordinal_position
    FROM <SOURCE_DB>.INFORMATION_SCHEMA.COLUMNS
    WHERE table_name = '<SOURCE_TABLE>' AND table_schema = '<SOURCE_SCHEMA>'
)
SELECT
    s.column_name,
    s.data_type,
    s.is_nullable,
    s.ordinal_position,
    'NEW_IN_SOURCE' AS drift_type
FROM source_cols s
LEFT JOIN dt_cols d ON UPPER(s.column_name) = UPPER(d.column_name)
WHERE d.column_name IS NULL
ORDER BY s.ordinal_position;
```

### Scoring each new column

Apply business-signal scoring to each new column found:

| Signal | Score adjustment |
|--------|----------------|
| Column name is business-sounding (no audit/ETL pattern) | +3 |
| Column name contains `AMOUNT`, `PRICE`, `STATUS`, `TYPE`, `DATE`, `NAME`, `CODE`, `ID`, `COUNT` | +2 (likely a useful fact or dimension) |
| Data type is VARCHAR, NUMBER, DATE, TIMESTAMP (queryable) | +1 |
| Column added near end of ordinal list (recently appended) | +1 (suggests intentional schema evolution) |
| Column name contains audit/ETL patterns: `_AT`, `_ETL`, `_LOAD`, `_BATCH`, `_DW_`, `_TS_`, `SRC_`, `META_` | -3 (internal pipeline column) |
| Data type is VARIANT, OBJECT, ARRAY | -2 (not directly queryable in DT SELECT without extraction) |
| Column name contains PII patterns: `EMAIL`, `SSN`, `PHONE`, `DOB`, `ADDRESS` | -2 (access concern — flag for review) |
| `is_nullable = YES` and column is early in ordinal (existed at creation) | -1 (may be an old column missed due to case sensitivity) |
| 100% NULL rate in source (probe if possible) | -3 (no data yet — premature to add) |

**Check for 100% NULL rate** (optional probe if source is accessible):
```sql
SELECT COUNT_IF(<column_name> IS NOT NULL) AS non_null_count
FROM <SOURCE_TABLE>
LIMIT 1000;
```
If non_null_count = 0 → mark as SKIP "column exists but has no values yet".

**Recommendation**:
- Score >= 4: **ADD** — business column, clean type, not an audit field
- Score 1–3: **REVIEW** — ambiguous; user should confirm
- Score <= 0: **SKIP** — audit/ETL column, complex type, or no data

Store each as:
```json
{
  "type": "NEW_COLUMN",
  "source_table": "<TABLE>",
  "column_name": "<COL>",
  "data_type": "<TYPE>",
  "ordinal_position": N,
  "score": N,
  "recommendation": "ADD|REVIEW|SKIP",
  "add_reason": "...",
  "skip_reason": "..."
}
```

---

## Step 3.4: Score type changes

```sql
WITH dt_cols AS (
    SELECT column_name, data_type, numeric_precision, numeric_scale, character_maximum_length
    FROM <DT_DB>.INFORMATION_SCHEMA.COLUMNS
    WHERE table_name = '<DT_SHORT_NAME>' AND table_schema = '<DT_SCHEMA>'
),
source_cols AS (
    SELECT column_name, data_type, numeric_precision, numeric_scale, character_maximum_length
    FROM <SOURCE_DB>.INFORMATION_SCHEMA.COLUMNS
    WHERE table_name = '<SOURCE_TABLE>' AND table_schema = '<SOURCE_SCHEMA>'
)
SELECT
    d.column_name,
    d.data_type AS dt_type, s.data_type AS source_type,
    d.numeric_precision AS dt_prec, s.numeric_precision AS src_prec,
    CASE
        WHEN d.data_type <> s.data_type                THEN 'TYPE_CHANGE'
        WHEN d.numeric_precision < s.numeric_precision THEN 'PRECISION_WIDENED'
        WHEN d.numeric_scale <> s.numeric_scale        THEN 'SCALE_CHANGED'
        WHEN d.character_maximum_length < s.character_maximum_length THEN 'LENGTH_WIDENED'
    END AS drift_type
FROM dt_cols d
JOIN source_cols s ON UPPER(d.column_name) = UPPER(s.column_name)
WHERE drift_type IS NOT NULL;
```

| Drift type | Severity | Recommendation | Reason |
|-----------|----------|---------------|--------|
| `TYPE_CHANGE` | **HIGH** | **ADD** (fix cast) | DT refresh will fail or silently truncate — act now |
| `PRECISION_WIDENED` | **MED** | **REVIEW** | Values may overflow DT column on next refresh |
| `SCALE_CHANGED` | **MED** | **REVIEW** | Decimal precision loss possible |
| `LENGTH_WIDENED` | **LOW** | **REVIEW** | May truncate long strings |

---

## Step 3.5: Dropped columns — always HIGH + ADD (remove)

```sql
WITH dt_cols AS (
    SELECT column_name FROM <DT_DB>.INFORMATION_SCHEMA.COLUMNS
    WHERE table_name = '<DT_SHORT_NAME>' AND table_schema = '<DT_SCHEMA>'
),
source_cols AS (
    SELECT column_name FROM <SOURCE_DB>.INFORMATION_SCHEMA.COLUMNS
    WHERE table_name = '<SOURCE_TABLE>' AND table_schema = '<SOURCE_SCHEMA>'
)
SELECT d.column_name AS dropped_column, 'DROPPED_IN_SOURCE' AS drift_type
FROM dt_cols d
LEFT JOIN source_cols s ON UPPER(d.column_name) = UPPER(s.column_name)
WHERE s.column_name IS NULL;
```

Dropped columns always get: severity=**HIGH**, recommendation=**ADD** (meaning: add the fix — remove from DT DDL immediately). DT refresh will fail on the next cycle.

---

## Step 3.6: Refresh health check

⚠️ `DYNAMIC_TABLE_REFRESH_HISTORY` is a large ACCOUNT_USAGE view. Always include both a `name` filter AND a tight time window. Start with 3 days; if that returns results, expand to 7 days. If the query times out even with filters, record `REFRESH_HEALTH = "timeout"`, note it as a warning, and continue — do NOT block Phase 6.

**Probe (3-day window first):**
```sql
SELECT
    name, state, state_message,
    refresh_start_time, refresh_end_time,
    DATEDIFF('minute', refresh_start_time, refresh_end_time) AS duration_min,
    rows_inserted, rows_deleted
FROM SNOWFLAKE.ACCOUNT_USAGE.DYNAMIC_TABLE_REFRESH_HISTORY
WHERE name = '<DT_SHORT_NAME>'
  AND refresh_start_time >= DATEADD('days', -3, CURRENT_TIMESTAMP())
ORDER BY refresh_start_time DESC
LIMIT 20;
```

If the 3-day probe succeeds and returns ≥1 row, use that result. If it succeeds but returns 0 rows, try a 7-day window. If it times out entirely, fall back to the SHOW output from Step 3.1 (`data_timestamp`, `scheduling_state`) as a lighter health signal.

Flag if `state = 'FAILED'` or most recent refresh is > 2× `target_lag` old (stale).
Store as `REFRESH_HEALTH`.

---

## Step 3.7: Streaming/CDC source DDL events

```sql
SELECT query_start_time, query_type, query_text, user_name
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE start_time >= DATEADD('days', -:LOOKBACK_DAYS, CURRENT_TIMESTAMP())
  AND execution_status = 'SUCCESS'
  AND query_type IN ('ALTER_TABLE','CREATE_TABLE','CREATE_TABLE_AS_SELECT')
  AND UPPER(query_text) LIKE '%<SOURCE_TABLE_SHORT>%'
ORDER BY query_start_time DESC
LIMIT 10;
```

If recent `ALTER TABLE ADD COLUMN` events exist → add context note: "source schema evolved on <date>".

---

## Step 3.8: Compile SCHEMA_DRIFT

Build consolidated drift report and pass all scored suggestions to Phase 6 as `GAP_SUGGESTIONS`.

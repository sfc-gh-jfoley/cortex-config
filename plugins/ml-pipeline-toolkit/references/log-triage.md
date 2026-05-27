# ML Pipeline Log Triage

5-step diagnostic flow for ML pipeline and model monitor failures. Always run in order — fastest signal first.

---

## Step 1: Model Monitor Status (Fastest)

```sql
-- Survey all monitors
SHOW MODEL MONITORS IN DATABASE <DATABASE>;
-- State: ACTIVE | SUSPENDED | PARTIALLY_SUSPENDED | UNKNOWN

-- Full diagnostics (SHOW does not expose error fields — DESC does)
DESC MODEL MONITOR <MONITOR_NAME>;
-- Key fields:
-- aggregation_status:              JSON — ACTIVE or SUSPENDED per component
-- aggregation_last_error:          JSON — exact SQL error that caused suspension
-- aggregation_last_data_timestamp: JSON — last successful refresh per component
```

**If SUSPENDED:**
1. Read `aggregation_last_error` JSON for root cause
2. Fix root cause (column removed, schema changed, access revoked, type mismatch)
3. `ALTER MODEL MONITOR <name> RESUME;`

> Trigger: **5 consecutive refresh failures** → auto-suspend.

---

## Step 2: Pipeline Task Failures

```sql
SELECT name, state, error_message, scheduled_time, next_scheduled_time
FROM SNOWFLAKE.ACCOUNT_USAGE.TASK_HISTORY
WHERE state = 'FAILED'
  AND scheduled_time > DATEADD('day', -7, CURRENT_TIMESTAMP())
ORDER BY scheduled_time DESC
LIMIT 50;
```

---

## Step 3: Python Exception Logs

```sql
-- First: discover configured event table
SHOW PARAMETERS LIKE 'EVENT_TABLE' IN ACCOUNT;
```

> ⚠️ If empty/null: event table not configured. Python exceptions from stored procs and notebooks
> are **not persisted**. Warn user:
> *"To enable: `ALTER ACCOUNT SET EVENT_TABLE = <db>.<schema>.<table>`"*
> Skip to Step 4.

If event table is configured (use name from `SHOW PARAMETERS` result):

```sql
SELECT
    timestamp,
    record_type,
    value:severity::STRING    AS severity,
    value:message::STRING     AS message,
    resource_attributes:db.user::STRING                 AS executed_by,
    resource_attributes:"snow.executable.name"::STRING  AS procedure_name
FROM <event_table>
WHERE record_type IN ('LOG', 'SPAN_EVENT')
  AND timestamp > DATEADD('hour', -24, CURRENT_TIMESTAMP())
  AND (
      value:severity::STRING IN ('ERROR', 'FATAL')
      OR record_type = 'SPAN_EVENT'
  )
ORDER BY timestamp DESC
LIMIT 100;
```

---

## Step 4: Inference Query Errors

```sql
SELECT start_time, query_text, error_message, execution_status, warehouse_name
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE error_message IS NOT NULL
  AND start_time > DATEADD('day', -1, CURRENT_TIMESTAMP())
  AND (
      query_text ILIKE '%predict%'
      OR query_text ILIKE '%model_version%'
      OR query_text ILIKE '%DATA_AGENT_RUN%'
      OR query_text ILIKE '%create_service%'
  )
ORDER BY start_time DESC
LIMIT 50;
```

---

## Step 5: Upstream Data Quality

```sql
SELECT *
FROM SNOWFLAKE.LOCAL.DATA_QUALITY_MONITORING_LOGS
WHERE status != 'SUCCESS'
  AND scheduled_time > DATEADD('day', -7, CURRENT_TIMESTAMP())
ORDER BY scheduled_time DESC;
```

---

## Remediation Decision Tree

```
Monitor SUSPENDED   → aggregation_last_error → fix root cause → ALTER MONITOR RESUME
Task FAILED         → TASK_HISTORY error_message → fix dependency → re-enable task
Python exception    → event table → fix stored proc/notebook → rerun
Query error         → QUERY_HISTORY → common: missing BIND SERVICE ENDPOINT, expired token
DQ failure          → DATA_QUALITY_MONITORING_LOGS → fix upstream table or DMF
```

---

## Monitor Auto-Suspension Recovery

```sql
-- 5 consecutive failures trigger auto-suspend
-- 1. Read the error:
DESC MODEL MONITOR <name>;
-- Find: aggregation_last_error (JSON with root cause)

-- 2. Fix root cause (see common causes below)

-- 3. Resume:
ALTER MODEL MONITOR <name> RESUME;
```

**Common root causes:**

| Symptom in `aggregation_last_error` | Fix |
|------|-----|
| Column does not exist | Schema changed; update inference log or monitor |
| Insufficient privileges | Re-grant SELECT on source/baseline table |
| Data type mismatch | Cast column in inference log to expected type |
| Table does not exist | Table renamed/dropped; recreate or point to new table |

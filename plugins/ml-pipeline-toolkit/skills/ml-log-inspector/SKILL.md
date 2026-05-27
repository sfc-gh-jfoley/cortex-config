---
name: ml-log-inspector
description: "Diagnose ML pipeline and model monitor failures. Use when: a model monitor is suspended, a training pipeline failed, inference queries are erroring, getting unexplained bad predictions, or tracing a breakdown anywhere in the ML lifecycle."
---

## ml-log-inspector

Systematic 5-step triage for diagnosing ML pipeline and model monitor failures. Always run in order — fastest signal first.

---

### Step 1: Check Model Monitor Status

```sql
-- Survey all monitors
SHOW MODEL MONITORS IN DATABASE <DATABASE>;
-- State values: ACTIVE | SUSPENDED | PARTIALLY_SUSPENDED | UNKNOWN

-- Get full detail (only DESC has error fields — SHOW does not)
DESC MODEL MONITOR <MONITOR_NAME>;
-- Key fields:
-- aggregation_status:              JSON — check for SUSPENDED values per component
-- aggregation_last_error:          JSON — exact SQL error that caused suspension
-- aggregation_last_data_timestamp: JSON — when each component last refreshed
-- monitor_state:                   overall state
```

If `aggregation_status` shows SUSPENDED:
1. Read `aggregation_last_error` for root cause
2. Fix root cause (schema change, column removed, access revoked, data type mismatch)
3. `ALTER MODEL MONITOR <name> RESUME;`

---

### Step 2: Pipeline Task Failures

```sql
SELECT
    name,
    state,
    error_message,
    scheduled_time,
    next_scheduled_time
FROM SNOWFLAKE.ACCOUNT_USAGE.TASK_HISTORY
WHERE state = 'FAILED'
  AND scheduled_time > DATEADD('day', -7, CURRENT_TIMESTAMP())
ORDER BY scheduled_time DESC
LIMIT 50;
```

---

### Step 3: Python Exception Logs

```sql
-- FIRST: discover the configured event table
SHOW PARAMETERS LIKE 'EVENT_TABLE' IN ACCOUNT;
```

> ⚠️ If the result is **empty or null**: event table is not configured on this account.
> Python exceptions from stored procs and notebooks are **not persisted**.
> Skip to Step 4 and warn the user:
> *"To enable: `ALTER ACCOUNT SET EVENT_TABLE = <db>.<schema>.<table>`"*

If event table is configured (use name from `SHOW PARAMETERS` result):
```sql
SELECT
    timestamp,
    record_type,
    value:severity::STRING    AS severity,
    value:message::STRING     AS message,
    resource_attributes:db.user::STRING                        AS executed_by,
    resource_attributes:"snow.executable.name"::STRING         AS procedure_name
FROM <event_table_from_parameter>
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

### Step 4: Inference Query Errors

```sql
SELECT
    start_time,
    query_text,
    error_message,
    execution_status,
    warehouse_name
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

### Step 5: Upstream Data Quality

```sql
SELECT *
FROM SNOWFLAKE.LOCAL.DATA_QUALITY_MONITORING_LOGS
WHERE status != 'SUCCESS'
  AND scheduled_time > DATEADD('day', -7, CURRENT_TIMESTAMP())
ORDER BY scheduled_time DESC;
```

---

### Remediation Decision Tree

```
Monitor SUSPENDED   → read aggregation_last_error → fix root cause → ALTER MONITOR RESUME
Task FAILED         → check error_message in TASK_HISTORY → fix upstream dependency → re-enable task
Python exception    → read event table → fix stored proc / notebook code → rerun
Query error         → check QUERY_HISTORY → common: missing BIND SERVICE ENDPOINT, expired token
DQ failure          → check DATA_QUALITY_MONITORING_LOGS → fix upstream table or DMF
```

---

### Monitor Auto-Suspension Recovery

```sql
-- Trigger: 5 consecutive refresh failures → auto-suspend
DESC MODEL MONITOR <name>;
-- Read: aggregation_last_error JSON field for exact failure reason
-- Fix the root cause first, THEN resume:
ALTER MODEL MONITOR <name> RESUME;
```

Common root causes:
| Error Type | Fix |
|---|---|
| Column does not exist | Schema changed; update monitor or source table |
| Access denied | Re-grant privileges on source or baseline table |
| Data type mismatch | Cast column in inference log to expected type |
| Source table not found | Table renamed/dropped; recreate or point to new table |

---

### Success Criteria

- [ ] Root cause identified from one of the 5 surfaces
- [ ] Monitor resumed (if suspended)
- [ ] Failing task re-enabled after fix
- [ ] Inference queries returning results without error

---
name: ml-watch
description: "Set up ongoing monitoring, scheduled retraining triggers, and freshness SLAs for Snowflake ML models and feature pipelines. Use when: automating model refresh when data drifts or freshness SLA is violated, scheduling retraining tasks, monitoring Dynamic Table feature view lag."
---

## ml-watch

Automate ongoing ML health monitoring: scheduled retraining, data freshness SLAs, drift alerts, and monitor health watchdogs.

---

### Pattern 1: Scheduled Retraining Task DAG

```sql
-- Root task: check data freshness daily
CREATE TASK check_data_freshness
    WAREHOUSE = <WAREHOUSE>
    SCHEDULE  = 'USING CRON 0 6 * * * UTC'  -- daily at 6 AM UTC
    COMMENT   = 'Check if training data is fresh enough to trigger retraining'
AS
    CALL SYSTEM$SEND_EMAIL(
        '<email>',
        'Retraining check',
        (
            SELECT 'Rows since last retrain: ' || COUNT(*)
            FROM <SOURCE_TABLE>
            WHERE created_at > (SELECT MAX(retrained_at) FROM <RETRAIN_LOG>)
        )
    );

-- Retraining task (triggered by root)
CREATE TASK retrain_model
    WAREHOUSE = <WAREHOUSE>
    AFTER     check_data_freshness
AS
    CALL <DATABASE>.<SCHEMA>.RETRAIN_PROCEDURE();

-- Enable DAG (tasks default to SUSPENDED)
ALTER TASK retrain_model      RESUME;
ALTER TASK check_data_freshness RESUME;
```

---

### Pattern 2: Stream-Triggered Retraining (Data Arrival)

```sql
-- Create stream on source table
CREATE STREAM training_data_stream ON TABLE <SOURCE_TABLE>;

-- Trigger task only when new rows arrive
CREATE TASK trigger_on_new_data
    WAREHOUSE = <WAREHOUSE>
    SCHEDULE  = '5 MINUTES'
    WHEN      SYSTEM$STREAM_HAS_DATA('training_data_stream')
AS
    CALL <DATABASE>.<SCHEMA>.RETRAIN_PROCEDURE();

ALTER TASK trigger_on_new_data RESUME;
```

---

### Pattern 3: Feature View Freshness SLA Check

```sql
-- Check Dynamic Table refresh lag across all feature views
SELECT
    name,
    target_lag,
    last_completed_refresh_data_timestamp,
    DATEDIFF('minute', last_completed_refresh_data_timestamp, CURRENT_TIMESTAMP()) AS lag_minutes,
    last_completed_refresh_state
FROM INFORMATION_SCHEMA.DYNAMIC_TABLES
WHERE schema_name = '<FEATURE_STORE_SCHEMA>'
ORDER BY lag_minutes DESC;

-- Alert if any DT exceeds SLA
CREATE ALERT feature_freshness_alert
    WAREHOUSE = <WAREHOUSE>
    SCHEDULE  = '30 MINUTES'
    IF (EXISTS (
        SELECT 1 FROM INFORMATION_SCHEMA.DYNAMIC_TABLES
        WHERE schema_name = '<FEATURE_STORE_SCHEMA>'
          AND DATEDIFF('minute', last_completed_refresh_data_timestamp, CURRENT_TIMESTAMP()) > 60
          AND last_completed_refresh_state = 'FAILED'
    ))
    THEN CALL SYSTEM$SEND_EMAIL(
        '<email>',
        'Feature Freshness Alert',
        'Dynamic Table lag > 60 min or refresh failed in feature store schema'
    );

ALTER ALERT feature_freshness_alert RESUME;
```

---

### Pattern 4: Model Monitor Health Watchdog

```sql
CREATE TASK monitor_health_watchdog
    WAREHOUSE = <WAREHOUSE>
    SCHEDULE  = 'USING CRON 0 8 * * * UTC'
AS
DECLARE
    suspended_count INTEGER;
BEGIN
    SHOW MODEL MONITORS IN DATABASE <DATABASE>;

    SELECT COUNT(*) INTO :suspended_count
    FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()))
    WHERE "state" != 'ACTIVE';

    IF (:suspended_count > 0) THEN
        CALL SYSTEM$SEND_EMAIL(
            '<email>',
            'Model Monitor Alert',
            :suspended_count || ' model monitor(s) suspended. Run DESC MODEL MONITOR to diagnose.'
        );
    END IF;
    RETURN 'checked';
END;

ALTER TASK monitor_health_watchdog RESUME;
```

---

### Monitor Task Health

```sql
SELECT
    name,
    state,
    error_message,
    scheduled_time
FROM SNOWFLAKE.ACCOUNT_USAGE.TASK_HISTORY
WHERE name IN ('check_data_freshness', 'retrain_model', 'monitor_health_watchdog')
  AND scheduled_time > DATEADD('day', -7, CURRENT_TIMESTAMP())
ORDER BY scheduled_time DESC;
```

---

### Success Criteria

- [ ] Retraining task DAG enabled (`SHOW TASKS` shows STARTED state)
- [ ] At least one run visible in `TASK_HISTORY` after enabling
- [ ] Freshness alert created and tested with a forced DT suspension
- [ ] Monitor watchdog task scheduled and confirmed in `TASK_HISTORY`
- [ ] Email notifications received for test condition trigger

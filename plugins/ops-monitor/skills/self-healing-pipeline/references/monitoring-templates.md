# Monitoring Templates

Additional detection capabilities beyond task/DT failure detection.

## DT Lag Drift Alert

Detects dynamic tables that are "working" but consistently missing their target lag.

```sql
CREATE OR REPLACE ALERT {DB}.{SCHEMA}.ALERT_DT_LAG_DRIFT
  SCHEDULE = '15 MINUTE'
  IF (EXISTS (
    SELECT 1
    FROM TABLE(INFORMATION_SCHEMA.DYNAMIC_TABLES())
    WHERE SCHEDULING_STATE:"state"::VARCHAR = 'ACTIVE'
      AND DATA_TIMESTAMP < DATEADD('second', -2 * TARGET_LAG_SEC, CURRENT_TIMESTAMP())
  ))
THEN
  BEGIN
    LET lagging_dts VARCHAR;
    SELECT LISTAGG(
        NAME || ' (lag: ' || DATEDIFF('second', DATA_TIMESTAMP, CURRENT_TIMESTAMP()) || 's, target: ' || TARGET_LAG_SEC || 's)',
        '\n'
    ) INTO :lagging_dts
    FROM TABLE(INFORMATION_SCHEMA.DYNAMIC_TABLES())
    WHERE SCHEDULING_STATE:"state"::VARCHAR = 'ACTIVE'
      AND DATA_TIMESTAMP < DATEADD('second', -2 * TARGET_LAG_SEC, CURRENT_TIMESTAMP());

    CALL {DB}.{SCHEMA}.SP_SEND_ALERT(
        'DT Lag Drift Warning',
        'The following dynamic tables are exceeding 2x their target lag:\n' || :lagging_dts
    );
  END;

ALTER ALERT {DB}.{SCHEMA}.ALERT_DT_LAG_DRIFT RESUME;
```

## Cost Guardrail Alert

Tracks LLM calls per run and alerts if exceeding threshold.

```sql
CREATE OR REPLACE ALERT {DB}.{SCHEMA}.ALERT_COST_ANOMALY
  SCHEDULE = '30 MINUTE'
  IF (EXISTS (
    SELECT 1
    FROM (
        SELECT
            DATE_TRUNC('hour', CREATED_AT) AS hour_window,
            COUNT(*) AS llm_calls,
            COUNT(DISTINCT FAILURE_ID) AS unique_failures
        FROM {DB}.{SCHEMA}.HEALING_AUDIT_LOG
        WHERE ACTION_TYPE IN ('DIAGNOSE', 'DIAGNOSE_DT')
          AND LLM_MODEL_USED != 'RUNBOOK'
          AND CREATED_AT > DATEADD('hour', -1, CURRENT_TIMESTAMP())
        GROUP BY 1
    )
    WHERE llm_calls > {MAX_LLM_CALLS_PER_HOUR}
  ))
THEN
  BEGIN
    LET call_count NUMBER;
    SELECT COUNT(*) INTO :call_count
    FROM {DB}.{SCHEMA}.HEALING_AUDIT_LOG
    WHERE ACTION_TYPE IN ('DIAGNOSE', 'DIAGNOSE_DT')
      AND LLM_MODEL_USED != 'RUNBOOK'
      AND CREATED_AT > DATEADD('hour', -1, CURRENT_TIMESTAMP());

    CALL {DB}.{SCHEMA}.SP_SEND_ALERT(
        'Cost Alert: ' || :call_count || ' LLM calls in past hour',
        'The self-healing agent made ' || :call_count || ' LLM calls in the past hour, exceeding the threshold of {MAX_LLM_CALLS_PER_HOUR}.'
        || '\nThis may indicate a fix loop or a surge in new failure types.'
        || '\nConsider: suspending the agent, adding runbook entries for common errors, or raising the confidence threshold.'
    );
  END;

ALTER ALERT {DB}.{SCHEMA}.ALERT_COST_ANOMALY RESUME;
```

## Data Quality Check (Post-Fix)

After a fix is applied and verified, compare basic data quality metrics before/after.

```sql
CREATE OR REPLACE PROCEDURE {DB}.{SCHEMA}.SP_CHECK_DATA_QUALITY(
    P_FAILURE_ID VARCHAR,
    P_OBJECT_DB VARCHAR,
    P_OBJECT_SCHEMA VARCHAR,
    P_OBJECT_NAME VARCHAR,
    P_OBJECT_TYPE VARCHAR
)
RETURNS VARCHAR
LANGUAGE SQL
AS
$$
DECLARE
    row_count NUMBER;
    quality_result VARCHAR DEFAULT 'PASS';
    check_sql VARCHAR;
BEGIN
    IF (P_OBJECT_TYPE = 'DYNAMIC_TABLE') THEN
        check_sql := 'SELECT COUNT(*) FROM ' || P_OBJECT_DB || '.' || P_OBJECT_SCHEMA || '.' || P_OBJECT_NAME;
    ELSE
        -- For tasks, check the target table if identifiable from the task definition
        RETURN 'SKIP: task data quality check requires target table identification';
    END IF;

    EXECUTE IMMEDIATE :check_sql INTO :row_count;

    -- Flag if DT is empty after fix (likely regression)
    IF (row_count = 0 AND P_OBJECT_TYPE = 'DYNAMIC_TABLE') THEN
        quality_result := 'WARNING: DT has 0 rows after fix — possible regression';

        CALL {DB}.{SCHEMA}.SP_SEND_ALERT(
            'Data Quality Warning: ' || P_OBJECT_NAME,
            P_OBJECT_NAME || ' has 0 rows after the self-healing fix was applied.'
            || '\nThis may indicate the fix caused a regression.'
            || '\nReview the fix in HEALING_AUDIT_LOG for FAILURE_ID: ' || P_FAILURE_ID
        );
    END IF;

    INSERT INTO {DB}.{SCHEMA}.HEALING_AUDIT_LOG
        (FAILURE_ID, ACTION_TYPE, TASK_NAME, EXECUTION_RESULT)
    VALUES
        (:P_FAILURE_ID, 'DATA_QUALITY_CHECK', :P_OBJECT_NAME,
         'rows=' || :row_count || ' result=' || :quality_result);

    RETURN quality_result;
END;
$$;
```

## Circuit Breaker

Prevents the agent from running amok. If too many consecutive failures or fix loops detected, auto-suspends.

```sql
CREATE OR REPLACE PROCEDURE {DB}.{SCHEMA}.SP_CHECK_CIRCUIT_BREAKER()
RETURNS VARCHAR
LANGUAGE SQL
AS
$$
DECLARE
    recent_escalations NUMBER;
    recent_fix_loops NUMBER;
    threshold NUMBER DEFAULT {CIRCUIT_BREAKER_THRESHOLD};
BEGIN
    -- Count escalations in last hour
    SELECT COUNT(*) INTO :recent_escalations
    FROM {DB}.{SCHEMA}.PIPELINE_FAILURES
    WHERE STATUS = 'ESCALATED'
      AND DETECTED_AT > DATEADD('hour', -1, CURRENT_TIMESTAMP());

    -- Count objects with > 3 fix attempts (fix loops)
    SELECT COUNT(*) INTO :recent_fix_loops
    FROM {DB}.{SCHEMA}.PIPELINE_FAILURES
    WHERE FIX_ATTEMPTS >= 3
      AND STATUS NOT IN ('RESOLVED')
      AND DETECTED_AT > DATEADD('hour', -2, CURRENT_TIMESTAMP());

    IF (recent_escalations > threshold OR recent_fix_loops > 3) THEN
        -- Suspend the agent
        EXECUTE IMMEDIATE 'ALTER TASK {DB}.{SCHEMA}.SELF_HEALING_AGENT SUSPEND';

        CALL {DB}.{SCHEMA}.SP_SEND_ALERT(
            'CIRCUIT BREAKER: Self-Healing Agent Suspended',
            'The agent has been auto-suspended due to:\n'
            || '- Escalations in past hour: ' || recent_escalations || ' (threshold: ' || threshold || ')\n'
            || '- Fix loops detected: ' || recent_fix_loops
            || '\n\nManual intervention required. Resume with: ALTER TASK {DB}.{SCHEMA}.SELF_HEALING_AGENT RESUME'
        );

        INSERT INTO {DB}.{SCHEMA}.HEALING_AUDIT_LOG
            (FAILURE_ID, ACTION_TYPE, EXECUTION_RESULT)
        VALUES
            (NULL, 'CIRCUIT_BREAKER', 'Agent suspended. Escalations: ' || recent_escalations || ' Fix loops: ' || recent_fix_loops);

        RETURN 'CIRCUIT_BREAKER_TRIPPED';
    END IF;

    RETURN 'OK';
END;
$$;
```

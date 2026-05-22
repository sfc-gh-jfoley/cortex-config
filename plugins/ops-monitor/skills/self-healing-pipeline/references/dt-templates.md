# Dynamic Table SQL Templates

All templates use `{DB}`, `{SCHEMA}`, `{MONITORED_DB}`, `{MONITORED_SCHEMA}` placeholders.

## SP_DETECT_DT_FAILURES

Scans `DYNAMIC_TABLE_REFRESH_HISTORY` for failed/upstream-failed refreshes.

```sql
CREATE OR REPLACE PROCEDURE {DB}.{SCHEMA}.SP_DETECT_DT_FAILURES()
RETURNS VARCHAR
LANGUAGE SQL
AS
$$
DECLARE
    failures_found NUMBER DEFAULT 0;
    c1 CURSOR FOR
        SELECT
            NAME,
            DATABASE_NAME,
            SCHEMA_NAME,
            STATE,
            STATE_CODE,
            STATE_MESSAGE,
            QUERY_ID,
            DATA_TIMESTAMP
        FROM TABLE({MONITORED_DB}.INFORMATION_SCHEMA.DYNAMIC_TABLE_REFRESH_HISTORY(
            NAME_PREFIX => '{MONITORED_DB}.{MONITORED_SCHEMA}.',
            ERROR_ONLY => TRUE,
            DATA_TIMESTAMP_START => DATEADD('hour', -1, CURRENT_TIMESTAMP()),
            RESULT_LIMIT => 100
        ))
        WHERE STATE IN ('FAILED', 'UPSTREAM_FAILED')
          AND NOT EXISTS (
              SELECT 1 FROM {DB}.{SCHEMA}.PIPELINE_FAILURES pf
              WHERE pf.OBJECT_NAME = NAME
                AND pf.OBJECT_DATABASE = DATABASE_NAME
                AND pf.OBJECT_SCHEMA = SCHEMA_NAME
                AND pf.SCHEDULED_TIME = DATA_TIMESTAMP
          );
BEGIN
    FOR rec IN c1 DO
        INSERT INTO {DB}.{SCHEMA}.PIPELINE_FAILURES
            (OBJECT_NAME, OBJECT_DATABASE, OBJECT_SCHEMA, OBJECT_TYPE,
             ERROR_CODE, ERROR_MESSAGE, SCHEDULED_TIME)
        VALUES
            (rec.NAME, rec.DATABASE_NAME, rec.SCHEMA_NAME, 'DYNAMIC_TABLE',
             rec.STATE_CODE, rec.STATE || ': ' || rec.STATE_MESSAGE, rec.DATA_TIMESTAMP);
        failures_found := failures_found + 1;
    END FOR;

    RETURN 'Detected ' || failures_found || ' new DT failures';
END;
$$;
```

## SP_DIAGNOSE_DT_FAILURE

Diagnoses a dynamic table failure. For `UPSTREAM_FAILED`, walks the graph to find the root cause DT.

```sql
CREATE OR REPLACE PROCEDURE {DB}.{SCHEMA}.SP_DIAGNOSE_DT_FAILURE()
RETURNS VARCHAR
LANGUAGE SQL
AS
$$
DECLARE
    diagnosed NUMBER DEFAULT 0;
    max_per_run NUMBER DEFAULT {MAX_FIXES_PER_RUN};
    c1 CURSOR FOR
        SELECT FAILURE_ID, OBJECT_NAME, OBJECT_DATABASE, OBJECT_SCHEMA, ERROR_MESSAGE
        FROM {DB}.{SCHEMA}.PIPELINE_FAILURES
        WHERE STATUS = 'NEW' AND OBJECT_TYPE = 'DYNAMIC_TABLE'
        ORDER BY DETECTED_AT ASC
        LIMIT :max_per_run;
    dt_ddl VARCHAR;
    schema_context VARCHAR;
    upstream_info VARCHAR;
    root_cause_dt VARCHAR;
    llm_model VARCHAR;
    llm_prompt VARCHAR;
    llm_response VARCHAR;
    generated_sql VARCHAR;
    confidence NUMBER;
    guardrail_result VARCHAR;
    runbook_fix VARCHAR;
    runbook_confidence NUMBER;
BEGIN
    FOR rec IN c1 DO
        UPDATE {DB}.{SCHEMA}.PIPELINE_FAILURES
        SET STATUS = 'DIAGNOSING', FIX_ATTEMPTS = FIX_ATTEMPTS + 1
        WHERE FAILURE_ID = rec.FAILURE_ID;

        -- For UPSTREAM_FAILED, find the root cause DT
        IF (CONTAINS(rec.ERROR_MESSAGE, 'UPSTREAM_FAILED')) THEN
            -- Walk the DT graph to find the actual failing DT
            SELECT LISTAGG(NAME || ' [' || g.SCHEDULING_STATE:"state"::VARCHAR || ']', ' → ')
            INTO :upstream_info
            FROM TABLE(INFORMATION_SCHEMA.DYNAMIC_TABLE_GRAPH_HISTORY())  g,
                 TABLE(FLATTEN(g.INPUTS)) inp
            WHERE inp.VALUE:"name"::VARCHAR = rec.OBJECT_DATABASE || '.' || rec.OBJECT_SCHEMA || '.' || rec.OBJECT_NAME
               OR g.NAME = rec.OBJECT_NAME;

            -- Find the actual root failure in the chain
            SELECT rh.NAME INTO :root_cause_dt
            FROM TABLE({MONITORED_DB}.INFORMATION_SCHEMA.DYNAMIC_TABLE_REFRESH_HISTORY(
                NAME_PREFIX => '{MONITORED_DB}.{MONITORED_SCHEMA}.',
                ERROR_ONLY => TRUE,
                DATA_TIMESTAMP_START => DATEADD('hour', -2, CURRENT_TIMESTAMP())
            )) rh
            WHERE rh.STATE = 'FAILED'
              AND rh.NAME IN (
                  SELECT inp.VALUE:"name"::VARCHAR
                  FROM TABLE(INFORMATION_SCHEMA.DYNAMIC_TABLE_GRAPH_HISTORY()) g,
                       TABLE(FLATTEN(g.INPUTS)) inp
                  WHERE g.QUALIFIED_NAME LIKE '%' || rec.OBJECT_NAME || '%'
              )
            LIMIT 1;

            IF (root_cause_dt IS NOT NULL) THEN
                -- Redirect diagnosis to the actual root cause DT
                -- Update error message to include graph context
                UPDATE {DB}.{SCHEMA}.PIPELINE_FAILURES
                SET ERROR_MESSAGE = rec.ERROR_MESSAGE || ' | ROOT_CAUSE_DT: ' || root_cause_dt || ' | GRAPH: ' || upstream_info
                WHERE FAILURE_ID = rec.FAILURE_ID;
            END IF;
        END IF;

        -- Check runbook
        SELECT FIX_TEMPLATE, CONFIDENCE INTO :runbook_fix, :runbook_confidence
        FROM {DB}.{SCHEMA}.ERROR_RUNBOOK
        WHERE CONTAINS(rec.ERROR_MESSAGE, ERROR_PATTERN)
        LIMIT 1;

        IF (runbook_fix IS NOT NULL) THEN
            generated_sql := REPLACE(REPLACE(runbook_fix, '{TASK_NAME}', rec.OBJECT_NAME), '{DT_NAME}', rec.OBJECT_NAME);
            confidence := runbook_confidence;
            llm_model := 'RUNBOOK';

            UPDATE {DB}.{SCHEMA}.ERROR_RUNBOOK
            SET TIMES_USED = TIMES_USED + 1, LAST_USED = CURRENT_TIMESTAMP()
            WHERE CONTAINS(rec.ERROR_MESSAGE, ERROR_PATTERN);
        ELSE
            -- Get DT definition
            SELECT GET_DDL('DYNAMIC_TABLE', rec.OBJECT_DATABASE || '.' || rec.OBJECT_SCHEMA || '.' || COALESCE(root_cause_dt, rec.OBJECT_NAME))
            INTO :dt_ddl;

            -- Get schema context
            SELECT LISTAGG(TABLE_NAME || ' (' || COLUMN_NAME || ' ' || DATA_TYPE || ')', ', ')
            INTO :schema_context
            FROM {MONITORED_DB}.INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = rec.OBJECT_SCHEMA
            LIMIT 200;

            llm_model := CASE
                WHEN CONTAINS(rec.ERROR_MESSAGE, 'UPSTREAM_FAILED') THEN 'llama3.1-70b'
                WHEN CONTAINS(rec.ERROR_MESSAGE, 'does not exist') THEN 'llama3.1-8b'
                ELSE 'llama3.1-70b'
            END;

            llm_prompt := 'You are a Snowflake SQL expert. A dynamic table refresh failed.\n\n'
                || 'DYNAMIC TABLE DEFINITION:\n' || dt_ddl || '\n\n'
                || 'ERROR:\n' || rec.ERROR_MESSAGE || '\n\n'
                || 'UPSTREAM GRAPH:\n' || COALESCE(upstream_info, 'N/A') || '\n\n'
                || 'AVAILABLE OBJECTS IN SCHEMA:\n' || schema_context || '\n\n'
                || 'Generate ONLY the executable SQL fix. For DT issues, you can use CREATE OR REPLACE DYNAMIC TABLE or ALTER DYNAMIC TABLE.\n'
                || 'Respond with a confidence score (0-1) on the first line, then the SQL on subsequent lines.';

            SELECT SNOWFLAKE.CORTEX.COMPLETE(:llm_model, :llm_prompt) INTO :llm_response;

            confidence := TRY_TO_NUMBER(SPLIT_PART(llm_response, '\n', 1));
            generated_sql := SUBSTR(llm_response, POSITION('\n' IN llm_response) + 1);

            IF (confidence IS NULL) THEN
                confidence := 0.5;
                generated_sql := llm_response;
            END IF;
        END IF;

        CALL {DB}.{SCHEMA}.SP_CHECK_GUARDRAILS(:generated_sql, :confidence) INTO :guardrail_result;

        INSERT INTO {DB}.{SCHEMA}.HEALING_AUDIT_LOG
            (FAILURE_ID, ACTION_TYPE, TASK_NAME, LLM_MODEL_USED, PROMPT_SENT,
             LLM_RESPONSE, GENERATED_SQL, GUARDRAIL_RESULT, CONFIDENCE_SCORE)
        VALUES
            (rec.FAILURE_ID, 'DIAGNOSE_DT', rec.OBJECT_NAME, llm_model, llm_prompt,
             llm_response, generated_sql, guardrail_result, confidence);

        IF (guardrail_result = 'PASS') THEN
            CALL {DB}.{SCHEMA}.SP_EXECUTE_FIX(:rec.FAILURE_ID, :generated_sql);
            CALL {DB}.{SCHEMA}.SP_VERIFY_DT_FIX(:rec.FAILURE_ID, :rec.OBJECT_DATABASE, :rec.OBJECT_SCHEMA, :rec.OBJECT_NAME);
        ELSEIF (guardrail_result = 'REVIEW') THEN
            UPDATE {DB}.{SCHEMA}.PIPELINE_FAILURES SET STATUS = 'PENDING_REVIEW' WHERE FAILURE_ID = rec.FAILURE_ID;
        ELSE
            UPDATE {DB}.{SCHEMA}.PIPELINE_FAILURES SET STATUS = 'ESCALATED' WHERE FAILURE_ID = rec.FAILURE_ID;
        END IF;

        diagnosed := diagnosed + 1;
    END FOR;

    RETURN 'Diagnosed ' || diagnosed || ' DT failures';
END;
$$;
```

## SP_VERIFY_DT_FIX

Refreshes the fixed DT, then walks downstream DTs to ensure the full DAG is healthy.

```sql
CREATE OR REPLACE PROCEDURE {DB}.{SCHEMA}.SP_VERIFY_DT_FIX(
    P_FAILURE_ID VARCHAR,
    P_DT_DB VARCHAR,
    P_DT_SCHEMA VARCHAR,
    P_DT_NAME VARCHAR
)
RETURNS VARCHAR
LANGUAGE SQL
AS
$$
DECLARE
    verify_result VARCHAR;
    downstream_name VARCHAR;
    downstream_state VARCHAR;
    all_downstream_ok BOOLEAN DEFAULT TRUE;
    c_downstream CURSOR FOR
        SELECT g.NAME, g.DATABASE_NAME, g.SCHEMA_NAME
        FROM TABLE(INFORMATION_SCHEMA.DYNAMIC_TABLE_GRAPH_HISTORY()) g,
             TABLE(FLATTEN(g.INPUTS)) inp
        WHERE inp.VALUE:"name"::VARCHAR LIKE '%' || P_DT_NAME || '%';
BEGIN
    -- Step 1: Refresh the fixed DT
    BEGIN
        EXECUTE IMMEDIATE 'ALTER DYNAMIC TABLE ' || P_DT_DB || '.' || P_DT_SCHEMA || '.' || P_DT_NAME || ' REFRESH';
        CALL SYSTEM$WAIT(15);

        SELECT STATE INTO :verify_result
        FROM TABLE(INFORMATION_SCHEMA.DYNAMIC_TABLE_REFRESH_HISTORY(
            NAME => P_DT_DB || '.' || P_DT_SCHEMA || '.' || P_DT_NAME,
            RESULT_LIMIT => 1
        ))
        ORDER BY REFRESH_START_TIME DESC
        LIMIT 1;
    EXCEPTION
        WHEN OTHER THEN
            verify_result := 'VERIFY_FAILED: ' || SQLERRM;
    END;

    INSERT INTO {DB}.{SCHEMA}.HEALING_AUDIT_LOG
        (FAILURE_ID, ACTION_TYPE, TASK_NAME, EXECUTION_RESULT)
    VALUES
        (:P_FAILURE_ID, 'VERIFY_DT', :P_DT_NAME, :verify_result);

    IF (verify_result != 'SUCCEEDED') THEN
        UPDATE {DB}.{SCHEMA}.PIPELINE_FAILURES SET STATUS = 'ESCALATED' WHERE FAILURE_ID = :P_FAILURE_ID;
        RETURN 'DT fix failed verification: ' || verify_result;
    END IF;

    -- Step 2: Walk downstream DTs and verify each one refreshes
    FOR ds IN c_downstream DO
        BEGIN
            EXECUTE IMMEDIATE 'ALTER DYNAMIC TABLE ' || ds.DATABASE_NAME || '.' || ds.SCHEMA_NAME || '.' || ds.NAME || ' REFRESH';
            CALL SYSTEM$WAIT(10);

            SELECT STATE INTO :downstream_state
            FROM TABLE(INFORMATION_SCHEMA.DYNAMIC_TABLE_REFRESH_HISTORY(
                NAME => ds.DATABASE_NAME || '.' || ds.SCHEMA_NAME || '.' || ds.NAME,
                RESULT_LIMIT => 1
            ))
            ORDER BY REFRESH_START_TIME DESC
            LIMIT 1;

            INSERT INTO {DB}.{SCHEMA}.HEALING_AUDIT_LOG
                (FAILURE_ID, ACTION_TYPE, TASK_NAME, EXECUTION_RESULT)
            VALUES
                (:P_FAILURE_ID, 'VERIFY_DOWNSTREAM_DT', ds.NAME, :downstream_state);

            IF (downstream_state != 'SUCCEEDED') THEN
                all_downstream_ok := FALSE;
            END IF;
        EXCEPTION
            WHEN OTHER THEN
                all_downstream_ok := FALSE;
                INSERT INTO {DB}.{SCHEMA}.HEALING_AUDIT_LOG
                    (FAILURE_ID, ACTION_TYPE, TASK_NAME, EXECUTION_RESULT)
                VALUES
                    (:P_FAILURE_ID, 'VERIFY_DOWNSTREAM_DT', ds.NAME, 'FAILED: ' || SQLERRM);
        END;
    END FOR;

    IF (all_downstream_ok) THEN
        UPDATE {DB}.{SCHEMA}.PIPELINE_FAILURES
        SET STATUS = 'RESOLVED', RESOLVED_AT = CURRENT_TIMESTAMP()
        WHERE FAILURE_ID = :P_FAILURE_ID;
        RETURN 'DT and all downstream DTs verified';
    ELSE
        UPDATE {DB}.{SCHEMA}.PIPELINE_FAILURES SET STATUS = 'ESCALATED' WHERE FAILURE_ID = :P_FAILURE_ID;
        RETURN 'DT fixed but downstream failures remain — escalated';
    END IF;
END;
$$;
```

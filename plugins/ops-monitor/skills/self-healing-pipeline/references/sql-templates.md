# SQL Templates for Self-Healing Pipeline Agent

All templates use `{DB}`, `{SCHEMA}`, `{WAREHOUSE}`, `{MONITORED_DB}`, `{MONITORED_SCHEMA}` placeholders.

**NOTE**: The unified `SP_DETECT_FAILURES` (task + DT detection) is in `task-dag-templates.md`. The version below is the task-only legacy version for reference.

## SP_DETECT_FAILURES (task-only, legacy)

```sql
CREATE OR REPLACE PROCEDURE {DB}.{SCHEMA}.SP_DETECT_FAILURES()
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
            ERROR_CODE,
            ERROR_MESSAGE,
            SCHEDULED_TIME
        FROM TABLE({MONITORED_DB}.INFORMATION_SCHEMA.TASK_HISTORY(
            SCHEDULED_TIME_RANGE_START => DATEADD('hour', -1, CURRENT_TIMESTAMP()),
            RESULT_LIMIT => 100
        ))
        WHERE STATE = 'FAILED'
          AND NOT EXISTS (
              SELECT 1 FROM {DB}.{SCHEMA}.PIPELINE_FAILURES pf
              WHERE pf.TASK_NAME = NAME
                AND pf.SCHEDULED_TIME = SCHEDULED_TIME
          );
BEGIN
    FOR rec IN c1 DO
        INSERT INTO {DB}.{SCHEMA}.PIPELINE_FAILURES
            (TASK_NAME, TASK_DATABASE, TASK_SCHEMA, ERROR_CODE, ERROR_MESSAGE, SCHEDULED_TIME)
        VALUES
            (rec.NAME, rec.DATABASE_NAME, rec.SCHEMA_NAME, rec.ERROR_CODE, rec.ERROR_MESSAGE, rec.SCHEDULED_TIME);
        failures_found := failures_found + 1;
    END FOR;

    IF (failures_found > 0) THEN
        CALL {DB}.{SCHEMA}.SP_DIAGNOSE_FAILURE();
    END IF;

    RETURN 'Detected ' || failures_found || ' new failures';
END;
$$;
```

## SP_DIAGNOSE_FAILURE

```sql
CREATE OR REPLACE PROCEDURE {DB}.{SCHEMA}.SP_DIAGNOSE_FAILURE()
RETURNS VARCHAR
LANGUAGE SQL
AS
$$
DECLARE
    diagnosed NUMBER DEFAULT 0;
    max_per_run NUMBER DEFAULT {MAX_FIXES_PER_RUN};
    c1 CURSOR FOR
        SELECT FAILURE_ID, TASK_NAME, TASK_DATABASE, TASK_SCHEMA, ERROR_MESSAGE
        FROM {DB}.{SCHEMA}.PIPELINE_FAILURES
        WHERE STATUS = 'NEW'
        ORDER BY DETECTED_AT ASC
        LIMIT :max_per_run;
    runbook_fix VARCHAR;
    runbook_confidence NUMBER;
    task_ddl VARCHAR;
    schema_context VARCHAR;
    llm_model VARCHAR;
    llm_prompt VARCHAR;
    llm_response VARCHAR;
    generated_sql VARCHAR;
    confidence NUMBER;
    guardrail_result VARCHAR;
BEGIN
    FOR rec IN c1 DO
        UPDATE {DB}.{SCHEMA}.PIPELINE_FAILURES
        SET STATUS = 'DIAGNOSING', FIX_ATTEMPTS = FIX_ATTEMPTS + 1
        WHERE FAILURE_ID = rec.FAILURE_ID;

        -- Check runbook first
        SELECT FIX_TEMPLATE, CONFIDENCE INTO :runbook_fix, :runbook_confidence
        FROM {DB}.{SCHEMA}.ERROR_RUNBOOK
        WHERE CONTAINS(rec.ERROR_MESSAGE, ERROR_PATTERN)
        LIMIT 1;

        IF (runbook_fix IS NOT NULL) THEN
            generated_sql := REPLACE(runbook_fix, '{TASK_NAME}', rec.TASK_NAME);
            confidence := runbook_confidence;
            llm_model := 'RUNBOOK';

            UPDATE {DB}.{SCHEMA}.ERROR_RUNBOOK
            SET TIMES_USED = TIMES_USED + 1, LAST_USED = CURRENT_TIMESTAMP()
            WHERE CONTAINS(rec.ERROR_MESSAGE, ERROR_PATTERN);
        ELSE
            -- Get task definition
            SELECT GET_DDL('TASK', rec.TASK_DATABASE || '.' || rec.TASK_SCHEMA || '.' || rec.TASK_NAME)
            INTO :task_ddl;

            -- Get schema context
            SELECT LISTAGG(TABLE_NAME || ' (' || COLUMN_NAME || ' ' || DATA_TYPE || ')', ', ')
            INTO :schema_context
            FROM {MONITORED_DB}.INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = rec.TASK_SCHEMA
            LIMIT 200;

            -- Select model based on error complexity
            llm_model := CASE
                WHEN CONTAINS(rec.ERROR_MESSAGE, 'does not exist') THEN 'llama3.1-8b'
                WHEN CONTAINS(rec.ERROR_MESSAGE, 'type') OR CONTAINS(rec.ERROR_MESSAGE, 'schema') THEN 'llama3.1-70b'
                ELSE 'llama3.1-70b'
            END;

            llm_prompt := 'You are a Snowflake SQL expert. A scheduled task failed.\n\n'
                || 'TASK DEFINITION:\n' || task_ddl || '\n\n'
                || 'ERROR:\n' || rec.ERROR_MESSAGE || '\n\n'
                || 'AVAILABLE OBJECTS IN SCHEMA:\n' || schema_context || '\n\n'
                || 'Generate ONLY the executable SQL fix. No explanation. '
                || 'Respond with a confidence score (0-1) on the first line, then the SQL on subsequent lines.';

            SELECT SNOWFLAKE.CORTEX.COMPLETE(:llm_model, :llm_prompt) INTO :llm_response;

            -- Parse confidence and SQL from response
            confidence := TRY_TO_NUMBER(SPLIT_PART(llm_response, '\n', 1));
            generated_sql := SUBSTR(llm_response, POSITION('\n' IN llm_response) + 1);

            IF (confidence IS NULL) THEN
                confidence := 0.5;
                generated_sql := llm_response;
            END IF;
        END IF;

        -- Check guardrails (now passes error message and object type for runbook-aware decisions)
        CALL {DB}.{SCHEMA}.SP_CHECK_GUARDRAILS(:generated_sql, :confidence, rec.ERROR_MESSAGE, 'TASK')
        INTO :guardrail_result;

        -- Log everything
        INSERT INTO {DB}.{SCHEMA}.HEALING_AUDIT_LOG
            (FAILURE_ID, ACTION_TYPE, TASK_NAME, LLM_MODEL_USED, PROMPT_SENT,
             LLM_RESPONSE, GENERATED_SQL, GUARDRAIL_RESULT, CONFIDENCE_SCORE)
        VALUES
            (rec.FAILURE_ID, 'DIAGNOSE', rec.TASK_NAME, llm_model, llm_prompt,
             llm_response, generated_sql, guardrail_result, confidence);

        IF (guardrail_result = 'PASS') THEN
            CALL {DB}.{SCHEMA}.SP_EXECUTE_FIX(:rec.FAILURE_ID, :generated_sql);
            CALL {DB}.{SCHEMA}.SP_VERIFY_TASK_DAG(:rec.FAILURE_ID, :rec.TASK_DATABASE, :rec.TASK_SCHEMA, :rec.TASK_NAME);
        ELSEIF (STARTS_WITH(guardrail_result, 'REVIEW')) THEN
            LET guardrail_reason VARCHAR := SPLIT_PART(guardrail_result, ':', 2);
            UPDATE {DB}.{SCHEMA}.PIPELINE_FAILURES SET STATUS = 'PENDING_REVIEW' WHERE FAILURE_ID = rec.FAILURE_ID;
            CALL {DB}.{SCHEMA}.SP_CREATE_REVIEW(
                rec.FAILURE_ID, rec.TASK_NAME, 'TASK', rec.ERROR_MESSAGE,
                generated_sql, confidence, guardrail_reason, llm_model, llm_response
            );
        ELSE
            UPDATE {DB}.{SCHEMA}.PIPELINE_FAILURES SET STATUS = 'ESCALATED' WHERE FAILURE_ID = rec.FAILURE_ID;
            CALL {DB}.{SCHEMA}.SP_SEND_ALERT(
                'Pipeline Escalation: ' || rec.TASK_NAME,
                'Task ' || rec.TASK_NAME || ' has been escalated.\nError: ' || rec.ERROR_MESSAGE
                || '\nGuardrail: ' || guardrail_result
            );
        END IF;

        diagnosed := diagnosed + 1;
    END FOR;

    RETURN 'Diagnosed ' || diagnosed || ' failures';
END;
$$;
```

## SP_CHECK_GUARDRAILS

**Philosophy: Conservative by default.** Only safe, reversible, read-only or idempotent operations auto-execute. ALTER operations require the error pattern to exist in the runbook first. Everything else goes to human review.

```sql
CREATE OR REPLACE PROCEDURE {DB}.{SCHEMA}.SP_CHECK_GUARDRAILS(
    P_FIX_SQL VARCHAR,
    P_CONFIDENCE NUMBER,
    P_ERROR_MESSAGE VARCHAR DEFAULT NULL,
    P_OBJECT_TYPE VARCHAR DEFAULT NULL
)
RETURNS VARCHAR
LANGUAGE SQL
AS
$$
DECLARE
    sql_upper VARCHAR;
    confidence_threshold NUMBER DEFAULT {CONFIDENCE_THRESHOLD};
    has_runbook_match BOOLEAN DEFAULT FALSE;
    guardrail_reason VARCHAR;
BEGIN
    sql_upper := UPPER(P_FIX_SQL);

    -- TIER 1: ALWAYS BLOCK — destructive, irreversible, or security-sensitive
    IF (CONTAINS(sql_upper, 'DROP DATABASE') OR
        CONTAINS(sql_upper, 'DROP SCHEMA') OR
        CONTAINS(sql_upper, 'DROP TABLE') OR
        CONTAINS(sql_upper, 'DROP VIEW') OR
        CONTAINS(sql_upper, 'DROP DYNAMIC TABLE') OR
        CONTAINS(sql_upper, 'DROP TASK') OR
        CONTAINS(sql_upper, 'TRUNCATE') OR
        CONTAINS(sql_upper, 'DELETE FROM') OR
        CONTAINS(sql_upper, 'GRANT ') OR
        CONTAINS(sql_upper, 'REVOKE ') OR
        CONTAINS(sql_upper, 'CREATE USER') OR
        CONTAINS(sql_upper, 'ALTER USER') OR
        CONTAINS(sql_upper, 'CREATE ROLE') OR
        CONTAINS(sql_upper, 'DROP ROLE')) THEN
        RETURN 'BLOCK:BLOCKED_OPERATION';
    END IF;

    -- TIER 2: ALTER operations — only auto-execute if the error pattern is known in the runbook
    IF (CONTAINS(sql_upper, 'ALTER ') AND NOT CONTAINS(sql_upper, 'ALTER TASK') AND NOT CONTAINS(sql_upper, 'ALTER DYNAMIC TABLE')) OR
       (CONTAINS(sql_upper, 'ALTER TASK') AND CONTAINS(sql_upper, 'MODIFY AS')) OR
       (CONTAINS(sql_upper, 'CREATE OR REPLACE')) THEN

        -- Check if we have a runbook entry for this error pattern
        IF (P_ERROR_MESSAGE IS NOT NULL) THEN
            SELECT TRUE INTO :has_runbook_match
            FROM {DB}.{SCHEMA}.ERROR_RUNBOOK
            WHERE CONTAINS(:P_ERROR_MESSAGE, ERROR_PATTERN)
              AND (OBJECT_TYPE = :P_OBJECT_TYPE OR OBJECT_TYPE = 'ALL')
              AND CONFIDENCE >= 0.8
            LIMIT 1;
        END IF;

        IF (has_runbook_match AND P_CONFIDENCE >= confidence_threshold) THEN
            RETURN 'PASS';
        ELSE
            RETURN 'REVIEW:BLOCKED_OPERATION';
        END IF;
    END IF;

    -- TIER 3: SAFE operations — auto-execute with sufficient confidence
    -- ALTER TASK RESUME, ALTER TASK SET WAREHOUSE, ALTER DYNAMIC TABLE REFRESH,
    -- ALTER TASK SUSPEND, SELECT, EXECUTE TASK, SYSTEM$TASK_DEPENDENTS_ENABLE
    IF (CONTAINS(sql_upper, 'ALTER TASK') AND (CONTAINS(sql_upper, 'RESUME') OR CONTAINS(sql_upper, 'SET WAREHOUSE') OR CONTAINS(sql_upper, 'SUSPEND'))) OR
       (CONTAINS(sql_upper, 'ALTER DYNAMIC TABLE') AND CONTAINS(sql_upper, 'REFRESH')) OR
       (CONTAINS(sql_upper, 'EXECUTE TASK')) OR
       (CONTAINS(sql_upper, 'SYSTEM$TASK_DEPENDENTS_ENABLE')) OR
       (STARTS_WITH(sql_upper, 'SELECT')) THEN

        IF (P_CONFIDENCE >= confidence_threshold) THEN
            RETURN 'PASS';
        ELSE
            RETURN 'REVIEW:LOW_CONFIDENCE';
        END IF;
    END IF;

    -- TIER 4: Everything else — review by default
    IF (P_CONFIDENCE < confidence_threshold) THEN
        RETURN 'REVIEW:LOW_CONFIDENCE';
    END IF;

    RETURN 'REVIEW:UNKNOWN_OPERATION';
END;
$$;
```

**Guardrail result format**: `PASS`, `BLOCK:<reason>`, or `REVIEW:<reason>`. The reason is passed to SP_CREATE_REVIEW for context-aware remediation steps.

**To promote an operation from REVIEW to AUTO**: add a runbook entry with the error pattern and confidence >= 0.8. The guardrail will then allow ALTER operations for that known pattern.

## SP_EXECUTE_FIX

```sql
CREATE OR REPLACE PROCEDURE {DB}.{SCHEMA}.SP_EXECUTE_FIX(
    P_FAILURE_ID VARCHAR,
    P_FIX_SQL VARCHAR
)
RETURNS VARCHAR
LANGUAGE SQL
AS
$$
DECLARE
    exec_result VARCHAR;
BEGIN
    BEGIN
        EXECUTE IMMEDIATE :P_FIX_SQL;
        exec_result := 'SUCCESS';
    EXCEPTION
        WHEN OTHER THEN
            exec_result := 'FAILED: ' || SQLERRM;
    END;

    INSERT INTO {DB}.{SCHEMA}.HEALING_AUDIT_LOG
        (FAILURE_ID, ACTION_TYPE, GENERATED_SQL, EXECUTION_RESULT)
    VALUES
        (:P_FAILURE_ID, 'EXECUTE', :P_FIX_SQL, :exec_result);

    IF (exec_result = 'SUCCESS') THEN
        UPDATE {DB}.{SCHEMA}.PIPELINE_FAILURES SET STATUS = 'FIX_APPLIED' WHERE FAILURE_ID = :P_FAILURE_ID;
    ELSE
        UPDATE {DB}.{SCHEMA}.PIPELINE_FAILURES SET STATUS = 'ESCALATED' WHERE FAILURE_ID = :P_FAILURE_ID;
    END IF;

    RETURN exec_result;
END;
$$;
```

## SP_VERIFY_FIX (legacy — replaced by SP_VERIFY_TASK_DAG in task_dag_templates.md)

```sql
CREATE OR REPLACE PROCEDURE {DB}.{SCHEMA}.SP_VERIFY_FIX(
    P_FAILURE_ID VARCHAR,
    P_TASK_DB VARCHAR,
    P_TASK_SCHEMA VARCHAR,
    P_TASK_NAME VARCHAR
)
RETURNS VARCHAR
LANGUAGE SQL
AS
$$
DECLARE
    verify_result VARCHAR;
BEGIN
    BEGIN
        EXECUTE IMMEDIATE 'EXECUTE TASK ' || P_TASK_DB || '.' || P_TASK_SCHEMA || '.' || P_TASK_NAME;
        -- Wait briefly then check result
        CALL SYSTEM$WAIT(10);

        SELECT STATE INTO :verify_result
        FROM TABLE(INFORMATION_SCHEMA.TASK_HISTORY(
            TASK_NAME => :P_TASK_NAME,
            SCHEDULED_TIME_RANGE_START => DATEADD('minute', -2, CURRENT_TIMESTAMP()),
            RESULT_LIMIT => 1
        ));
    EXCEPTION
        WHEN OTHER THEN
            verify_result := 'VERIFY_FAILED: ' || SQLERRM;
    END;

    IF (verify_result = 'SUCCEEDED') THEN
        UPDATE {DB}.{SCHEMA}.PIPELINE_FAILURES
        SET STATUS = 'RESOLVED', RESOLVED_AT = CURRENT_TIMESTAMP()
        WHERE FAILURE_ID = :P_FAILURE_ID;
    ELSE
        UPDATE {DB}.{SCHEMA}.PIPELINE_FAILURES
        SET STATUS = 'ESCALATED'
        WHERE FAILURE_ID = :P_FAILURE_ID;
    END IF;

    INSERT INTO {DB}.{SCHEMA}.HEALING_AUDIT_LOG
        (FAILURE_ID, ACTION_TYPE, TASK_NAME, EXECUTION_RESULT)
    VALUES
        (:P_FAILURE_ID, 'VERIFY', :P_TASK_NAME, :verify_result);

    RETURN verify_result;
END;
$$;
```

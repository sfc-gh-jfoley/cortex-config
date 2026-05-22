# Task DAG SQL Templates

Templates for DAG-aware task verification. After fixing a task, the agent walks the full DAG to ensure all downstream tasks succeed.

## SP_VERIFY_TASK_DAG

Replaces the simple `SP_VERIFY_FIX`. Uses `EXECUTE TASK ... RETRY LAST` for task graphs, then walks `TASK_DEPENDENTS()` to verify downstream tasks.

```sql
CREATE OR REPLACE PROCEDURE {DB}.{SCHEMA}.SP_VERIFY_TASK_DAG(
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
    root_task_name VARCHAR;
    is_root BOOLEAN DEFAULT FALSE;
    child_name VARCHAR;
    child_state VARCHAR;
    all_children_ok BOOLEAN DEFAULT TRUE;
    fqn VARCHAR;
    c_children CURSOR FOR
        SELECT NAME, DATABASE_NAME, SCHEMA_NAME
        FROM TABLE(INFORMATION_SCHEMA.TASK_DEPENDENTS(
            TASK_NAME => :fqn,
            RECURSIVE => TRUE
        ))
        WHERE NAME != :P_TASK_NAME;
BEGIN
    fqn := P_TASK_DB || '.' || P_TASK_SCHEMA || '.' || P_TASK_NAME;

    -- Determine if this task is a root task or child task
    SELECT COUNT(*) INTO :is_root
    FROM TABLE(INFORMATION_SCHEMA.TASK_DEPENDENTS(
        TASK_NAME => :fqn,
        RECURSIVE => FALSE
    ))
    WHERE ARRAY_SIZE(PARSE_JSON(PREDECESSORS)) = 0
      AND NAME = P_TASK_NAME;

    -- Step 1: Re-execute the task/DAG
    IF (is_root) THEN
        -- Root task: use EXECUTE TASK RETRY LAST to resume from failure point
        BEGIN
            EXECUTE IMMEDIATE 'EXECUTE TASK ' || fqn || ' RETRY LAST';
        EXCEPTION
            WHEN OTHER THEN
                -- RETRY LAST requires last run to be FAILED; fall back to regular execute
                EXECUTE IMMEDIATE 'EXECUTE TASK ' || fqn;
        END;
    ELSE
        -- Child task: find the root task and retry the whole graph
        SELECT NAME INTO :root_task_name
        FROM TABLE(INFORMATION_SCHEMA.TASK_DEPENDENTS(
            TASK_NAME => :fqn,
            RECURSIVE => FALSE
        ))
        WHERE ARRAY_SIZE(PARSE_JSON(PREDECESSORS)) = 0
        LIMIT 1;

        IF (root_task_name IS NOT NULL) THEN
            BEGIN
                EXECUTE IMMEDIATE 'EXECUTE TASK ' || P_TASK_DB || '.' || P_TASK_SCHEMA || '.' || root_task_name || ' RETRY LAST';
            EXCEPTION
                WHEN OTHER THEN
                    EXECUTE IMMEDIATE 'EXECUTE TASK ' || P_TASK_DB || '.' || P_TASK_SCHEMA || '.' || root_task_name;
            END;
        ELSE
            EXECUTE IMMEDIATE 'EXECUTE TASK ' || fqn;
        END IF;
    END IF;

    -- Wait for execution
    CALL SYSTEM$WAIT(15);

    -- Step 2: Check the fixed task itself
    SELECT STATE INTO :verify_result
    FROM TABLE(INFORMATION_SCHEMA.TASK_HISTORY(
        TASK_NAME => :P_TASK_NAME,
        SCHEDULED_TIME_RANGE_START => DATEADD('minute', -3, CURRENT_TIMESTAMP()),
        RESULT_LIMIT => 1
    ));

    INSERT INTO {DB}.{SCHEMA}.HEALING_AUDIT_LOG
        (FAILURE_ID, ACTION_TYPE, TASK_NAME, EXECUTION_RESULT)
    VALUES
        (:P_FAILURE_ID, 'VERIFY_TASK', :P_TASK_NAME, :verify_result);

    IF (verify_result != 'SUCCEEDED') THEN
        UPDATE {DB}.{SCHEMA}.PIPELINE_FAILURES SET STATUS = 'ESCALATED' WHERE FAILURE_ID = :P_FAILURE_ID;
        RETURN 'Task fix failed verification: ' || verify_result;
    END IF;

    -- Step 3: Walk downstream child tasks and verify each one
    FOR child IN c_children DO
        CALL SYSTEM$WAIT(10);

        BEGIN
            SELECT STATE INTO :child_state
            FROM TABLE(INFORMATION_SCHEMA.TASK_HISTORY(
                TASK_NAME => child.NAME,
                SCHEDULED_TIME_RANGE_START => DATEADD('minute', -5, CURRENT_TIMESTAMP()),
                RESULT_LIMIT => 1
            ));

            INSERT INTO {DB}.{SCHEMA}.HEALING_AUDIT_LOG
                (FAILURE_ID, ACTION_TYPE, TASK_NAME, EXECUTION_RESULT)
            VALUES
                (:P_FAILURE_ID, 'VERIFY_DOWNSTREAM_TASK', child.NAME, :child_state);

            IF (child_state != 'SUCCEEDED' AND child_state != 'SKIPPED') THEN
                all_children_ok := FALSE;
            END IF;
        EXCEPTION
            WHEN OTHER THEN
                all_children_ok := FALSE;
                INSERT INTO {DB}.{SCHEMA}.HEALING_AUDIT_LOG
                    (FAILURE_ID, ACTION_TYPE, TASK_NAME, EXECUTION_RESULT)
                VALUES
                    (:P_FAILURE_ID, 'VERIFY_DOWNSTREAM_TASK', child.NAME, 'CHECK_FAILED: ' || SQLERRM);
        END;
    END FOR;

    IF (all_children_ok) THEN
        UPDATE {DB}.{SCHEMA}.PIPELINE_FAILURES
        SET STATUS = 'RESOLVED', RESOLVED_AT = CURRENT_TIMESTAMP()
        WHERE FAILURE_ID = :P_FAILURE_ID;
        RETURN 'Task and all downstream tasks verified';
    ELSE
        UPDATE {DB}.{SCHEMA}.PIPELINE_FAILURES SET STATUS = 'ESCALATED' WHERE FAILURE_ID = :P_FAILURE_ID;
        RETURN 'Task fixed but downstream task failures remain — escalated';
    END IF;
END;
$$;
```

## Updated SP_DETECT_FAILURES (unified)

Replaces the original. Now detects both task failures AND dynamic table failures in a single pass.

```sql
CREATE OR REPLACE PROCEDURE {DB}.{SCHEMA}.SP_DETECT_FAILURES()
RETURNS VARCHAR
LANGUAGE SQL
AS
$$
DECLARE
    task_failures NUMBER DEFAULT 0;
    dt_failures NUMBER DEFAULT 0;
    total NUMBER DEFAULT 0;
    c_tasks CURSOR FOR
        SELECT
            NAME, DATABASE_NAME, SCHEMA_NAME,
            ERROR_CODE, ERROR_MESSAGE, SCHEDULED_TIME
        FROM TABLE({MONITORED_DB}.INFORMATION_SCHEMA.TASK_HISTORY(
            SCHEDULED_TIME_RANGE_START => DATEADD('hour', -1, CURRENT_TIMESTAMP()),
            RESULT_LIMIT => 100
        ))
        WHERE STATE = 'FAILED'
          AND NOT EXISTS (
              SELECT 1 FROM {DB}.{SCHEMA}.PIPELINE_FAILURES pf
              WHERE pf.OBJECT_NAME = NAME
                AND pf.SCHEDULED_TIME = SCHEDULED_TIME
                AND pf.OBJECT_TYPE = 'TASK'
          );
    c_dts CURSOR FOR
        SELECT
            NAME, DATABASE_NAME, SCHEMA_NAME,
            STATE_CODE, STATE, STATE_MESSAGE, DATA_TIMESTAMP
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
                AND pf.SCHEDULED_TIME = DATA_TIMESTAMP
                AND pf.OBJECT_TYPE = 'DYNAMIC_TABLE'
          );
BEGIN
    -- Detect task failures
    FOR rec IN c_tasks DO
        INSERT INTO {DB}.{SCHEMA}.PIPELINE_FAILURES
            (OBJECT_NAME, OBJECT_DATABASE, OBJECT_SCHEMA, OBJECT_TYPE,
             ERROR_CODE, ERROR_MESSAGE, SCHEDULED_TIME)
        VALUES
            (rec.NAME, rec.DATABASE_NAME, rec.SCHEMA_NAME, 'TASK',
             rec.ERROR_CODE, rec.ERROR_MESSAGE, rec.SCHEDULED_TIME);
        task_failures := task_failures + 1;
    END FOR;

    -- Detect dynamic table failures
    FOR rec IN c_dts DO
        INSERT INTO {DB}.{SCHEMA}.PIPELINE_FAILURES
            (OBJECT_NAME, OBJECT_DATABASE, OBJECT_SCHEMA, OBJECT_TYPE,
             ERROR_CODE, ERROR_MESSAGE, SCHEDULED_TIME)
        VALUES
            (rec.NAME, rec.DATABASE_NAME, rec.SCHEMA_NAME, 'DYNAMIC_TABLE',
             rec.STATE_CODE, rec.STATE || ': ' || rec.STATE_MESSAGE, rec.DATA_TIMESTAMP);
        dt_failures := dt_failures + 1;
    END FOR;

    total := task_failures + dt_failures;

    -- Route to appropriate diagnosis procedures
    IF (task_failures > 0) THEN
        CALL {DB}.{SCHEMA}.SP_DIAGNOSE_FAILURE();
    END IF;

    IF (dt_failures > 0) THEN
        CALL {DB}.{SCHEMA}.SP_DIAGNOSE_DT_FAILURE();
    END IF;

    RETURN 'Detected ' || total || ' failures (' || task_failures || ' tasks, ' || dt_failures || ' DTs)';
END;
$$;
```

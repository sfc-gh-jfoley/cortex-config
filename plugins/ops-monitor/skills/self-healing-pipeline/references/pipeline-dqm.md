---
name: self-healing-pipeline-dqm
description: Data quality monitoring for self-healing pipelines. Covers freshness, row counts, schema drift, anomaly detection, and schema evolution awareness.
---

# Data Quality Monitoring (DQM)

Add data quality checks to a self-healing pipeline. These checks run post-fix to catch regressions, and independently to detect data quality degradation.

## When to Use

- After building a pipeline (compound follow-up)
- Adding quality checks to an existing agent
- Investigating data quality issues in monitored pipelines
- Setting up schema evolution detection

## Workflow

### Step 1: Assess Current State

**Ask** user:
1. What data quality concerns do they have? (staleness, empty tables, schema changes, anomalies)
2. Which objects need quality checks? (all monitored, or specific tables/DTs)
3. Tolerance levels (e.g., acceptable staleness, minimum row counts)

**Scan existing quality setup:**
```sql
-- Check if SP_CHECK_DATA_QUALITY exists
SHOW PROCEDURES LIKE 'SP_CHECK_DATA_QUALITY' IN {DB}.{SCHEMA};

-- Check recent quality check results
SELECT * FROM {DB}.{SCHEMA}.HEALING_AUDIT_LOG
WHERE ACTION_TYPE = 'DATA_QUALITY_CHECK'
ORDER BY CREATED_AT DESC LIMIT 20;
```

**STOP**: Confirm scope.

### Step 2: Post-Fix Quality Checks

The core quality check runs after every fix to catch regressions. **Load** `references/monitoring-templates.md` for `SP_CHECK_DATA_QUALITY`.

This procedure:
1. Counts rows in the fixed object
2. Flags 0-row DTs as potential regressions
3. Sends an alert if quality fails
4. Logs the check to HEALING_AUDIT_LOG

It is called by `SP_VERIFY_DT_FIX` and `SP_VERIFY_TASK_DAG` after downstream verification.

If this procedure doesn't exist yet, create it per `references/monitoring-templates.md`.

### Step 3: Freshness Monitoring

Track whether tables/DTs are being updated on expected schedules.

```sql
CREATE OR REPLACE PROCEDURE {DB}.{SCHEMA}.SP_CHECK_FRESHNESS()
RETURNS VARCHAR
LANGUAGE SQL
AS
$$
DECLARE
    stale_count NUMBER DEFAULT 0;
    c1 CURSOR FOR
        SELECT NAME, DATABASE_NAME, SCHEMA_NAME,
               DATA_TIMESTAMP,
               TARGET_LAG_SEC,
               DATEDIFF('second', DATA_TIMESTAMP, CURRENT_TIMESTAMP()) AS actual_lag_sec
        FROM TABLE(INFORMATION_SCHEMA.DYNAMIC_TABLES())
        WHERE DATABASE_NAME = '{MONITORED_DB}'
          AND SCHEMA_NAME = '{MONITORED_SCHEMA}'
          AND SCHEDULING_STATE:"state"::VARCHAR = 'ACTIVE'
          AND DATA_TIMESTAMP < DATEADD('second', -3 * TARGET_LAG_SEC, CURRENT_TIMESTAMP());
BEGIN
    FOR rec IN c1 DO
        INSERT INTO {DB}.{SCHEMA}.HEALING_AUDIT_LOG
            (ACTION_TYPE, TASK_NAME, EXECUTION_RESULT)
        VALUES
            ('FRESHNESS_CHECK', rec.NAME,
             'STALE: actual_lag=' || rec.actual_lag_sec || 's, target=' || rec.TARGET_LAG_SEC || 's (3x exceeded)');
        stale_count := stale_count + 1;
    END FOR;

    IF (stale_count > 0) THEN
        CALL {DB}.{SCHEMA}.SP_SEND_ALERT(
            'Freshness Alert: ' || stale_count || ' stale objects',
            stale_count || ' dynamic tables are exceeding 3x their target lag. Check HEALING_AUDIT_LOG for details.'
        );
    END IF;

    RETURN 'Freshness check complete: ' || stale_count || ' stale objects';
END;
$$;
```

### Step 4: Row Count Monitoring

Track row counts over time to detect unexpected drops or empty tables.

```sql
CREATE OR REPLACE PROCEDURE {DB}.{SCHEMA}.SP_CHECK_ROW_COUNTS()
RETURNS VARCHAR
LANGUAGE SQL
AS
$$
DECLARE
    alerts NUMBER DEFAULT 0;
    c1 CURSOR FOR
        SELECT TABLE_NAME, ROW_COUNT
        FROM {MONITORED_DB}.INFORMATION_SCHEMA.TABLES
        WHERE TABLE_SCHEMA = '{MONITORED_SCHEMA}'
          AND TABLE_TYPE = 'BASE TABLE'
          AND ROW_COUNT = 0;
BEGIN
    FOR rec IN c1 DO
        INSERT INTO {DB}.{SCHEMA}.HEALING_AUDIT_LOG
            (ACTION_TYPE, TASK_NAME, EXECUTION_RESULT)
        VALUES
            ('ROW_COUNT_CHECK', rec.TABLE_NAME, 'WARNING: 0 rows');
        alerts := alerts + 1;
    END FOR;

    IF (alerts > 0) THEN
        CALL {DB}.{SCHEMA}.SP_SEND_ALERT(
            'Row Count Alert: ' || alerts || ' empty tables',
            alerts || ' tables in ' || '{MONITORED_DB}.{MONITORED_SCHEMA}' || ' have 0 rows.'
        );
    END IF;

    RETURN 'Row count check complete: ' || alerts || ' alerts';
END;
$$;
```

### Step 5: Schema Drift Detection

Detect when table schemas change unexpectedly. Useful for catching upstream schema evolution.

```sql
CREATE OR REPLACE PROCEDURE {DB}.{SCHEMA}.SP_CHECK_SCHEMA_DRIFT()
RETURNS VARCHAR
LANGUAGE SQL
AS
$$
DECLARE
    drift_count NUMBER DEFAULT 0;
    snapshot_exists BOOLEAN DEFAULT FALSE;
BEGIN
    -- Check if we have a baseline snapshot
    SELECT TRUE INTO :snapshot_exists
    FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_SCHEMA = '{SCHEMA}' AND TABLE_NAME = 'SCHEMA_BASELINE'
    LIMIT 1;

    IF (NOT snapshot_exists) THEN
        -- Create baseline snapshot
        CREATE TABLE IF NOT EXISTS {DB}.{SCHEMA}.SCHEMA_BASELINE AS
        SELECT TABLE_CATALOG, TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME, DATA_TYPE, ORDINAL_POSITION
        FROM {MONITORED_DB}.INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = '{MONITORED_SCHEMA}';
        RETURN 'Baseline snapshot created. Run again to detect drift.';
    END IF;

    -- Detect new columns
    INSERT INTO {DB}.{SCHEMA}.HEALING_AUDIT_LOG (ACTION_TYPE, TASK_NAME, EXECUTION_RESULT)
    SELECT 'SCHEMA_DRIFT', TABLE_NAME || '.' || COLUMN_NAME, 'NEW_COLUMN: ' || DATA_TYPE
    FROM {MONITORED_DB}.INFORMATION_SCHEMA.COLUMNS c
    WHERE c.TABLE_SCHEMA = '{MONITORED_SCHEMA}'
      AND NOT EXISTS (
          SELECT 1 FROM {DB}.{SCHEMA}.SCHEMA_BASELINE b
          WHERE b.TABLE_NAME = c.TABLE_NAME AND b.COLUMN_NAME = c.COLUMN_NAME
      );

    GET_DML_RESULT_COUNT(drift_count);

    -- Detect removed columns
    INSERT INTO {DB}.{SCHEMA}.HEALING_AUDIT_LOG (ACTION_TYPE, TASK_NAME, EXECUTION_RESULT)
    SELECT 'SCHEMA_DRIFT', TABLE_NAME || '.' || COLUMN_NAME, 'REMOVED_COLUMN'
    FROM {DB}.{SCHEMA}.SCHEMA_BASELINE b
    WHERE b.TABLE_SCHEMA = '{MONITORED_SCHEMA}'
      AND NOT EXISTS (
          SELECT 1 FROM {MONITORED_DB}.INFORMATION_SCHEMA.COLUMNS c
          WHERE c.TABLE_NAME = b.TABLE_NAME AND c.COLUMN_NAME = b.COLUMN_NAME
              AND c.TABLE_SCHEMA = '{MONITORED_SCHEMA}'
      );

    -- Detect type changes
    INSERT INTO {DB}.{SCHEMA}.HEALING_AUDIT_LOG (ACTION_TYPE, TASK_NAME, EXECUTION_RESULT)
    SELECT 'SCHEMA_DRIFT', c.TABLE_NAME || '.' || c.COLUMN_NAME,
           'TYPE_CHANGED: ' || b.DATA_TYPE || ' → ' || c.DATA_TYPE
    FROM {MONITORED_DB}.INFORMATION_SCHEMA.COLUMNS c
    JOIN {DB}.{SCHEMA}.SCHEMA_BASELINE b
        ON b.TABLE_NAME = c.TABLE_NAME AND b.COLUMN_NAME = c.COLUMN_NAME
    WHERE c.TABLE_SCHEMA = '{MONITORED_SCHEMA}'
      AND c.DATA_TYPE != b.DATA_TYPE;

    -- Update baseline
    CREATE OR REPLACE TABLE {DB}.{SCHEMA}.SCHEMA_BASELINE AS
    SELECT TABLE_CATALOG, TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME, DATA_TYPE, ORDINAL_POSITION
    FROM {MONITORED_DB}.INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = '{MONITORED_SCHEMA}';

    IF (drift_count > 0) THEN
        CALL {DB}.{SCHEMA}.SP_SEND_ALERT(
            'Schema Drift Detected',
            'Schema changes detected in ' || '{MONITORED_DB}.{MONITORED_SCHEMA}' || '. Check HEALING_AUDIT_LOG for ACTION_TYPE = SCHEMA_DRIFT.'
        );
    END IF;

    RETURN 'Schema drift check complete';
END;
$$;
```

### Step 6: Schema Evolution Awareness

For tables using `ENABLE_SCHEMA_EVOLUTION = TRUE` with `MATCH_BY_COLUMN_NAME` on COPY INTO:

- Schema evolution is NOT supported by tasks — task SQL breaks when source schema evolves
- DTs can handle some schema changes but may need refresh
- New runbook patterns for schema evolution failures:

```sql
INSERT INTO {DB}.{SCHEMA}.ERROR_RUNBOOK (ERROR_PATTERN, ERROR_CATEGORY, OBJECT_TYPE, FIX_TEMPLATE, DESCRIPTION, CONFIDENCE) VALUES
('invalid identifier', 'SCHEMA_EVOLUTION', 'ALL', 'SELECT ''NEEDS_LLM_SCHEMA_EVOLUTION_FIX''', 'Column reference invalid after schema evolution — LLM should check current schema and update query', 0.3),
('column .* not found', 'SCHEMA_EVOLUTION', 'ALL', 'SELECT ''NEEDS_LLM_SCHEMA_EVOLUTION_FIX''', 'Column removed or renamed after schema evolution — LLM should inspect current schema', 0.3);
```

### Step 7: Schedule DQM Checks

Create a task to run quality checks on schedule:

```sql
CREATE OR REPLACE TASK {DB}.{SCHEMA}.DQM_CHECKS
  WAREHOUSE = {WAREHOUSE}
  SCHEDULE = '60 MINUTE'
AS
BEGIN
    CALL {DB}.{SCHEMA}.SP_CHECK_FRESHNESS();
    CALL {DB}.{SCHEMA}.SP_CHECK_ROW_COUNTS();
    CALL {DB}.{SCHEMA}.SP_CHECK_SCHEMA_DRIFT();
END;

ALTER TASK {DB}.{SCHEMA}.DQM_CHECKS RESUME;
```

**STOP**: Confirm DQM checks are running. Review first results.

## Stopping Points

- Step 1: Scope confirmed
- Step 7: DQM checks running, first results reviewed

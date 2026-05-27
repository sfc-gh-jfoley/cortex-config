---
name: ml-observability
description: "Monitor deployed Snowflake models for drift, performance degradation, and data quality issues. Use when: attaching a model monitor to production inference, querying drift metrics, checking performance over time, setting up drift alerts."
---

## ml-observability

Attach a model monitor to production inference tables and query drift, performance, and statistical metrics.

---

> ⚠️ **SUPPORTED TASKS ONLY:** `TABULAR_BINARY_CLASSIFICATION` and `TABULAR_REGRESSION`.
> Multi-class classification is **NOT supported** by model monitors. Using an unsupported task will cause monitor creation to fail.

---

### Phase 1: Prepare Inference Log Table

The monitor reads from an inference log table that must contain:
- ID column
- TIMESTAMP column (`TIMESTAMP_NTZ` type)
- Feature columns (inputs to the model)
- Prediction column(s) (class, score, or both)
- Actual / ground truth column(s) — optional at prediction time; required for performance metrics

```sql
CREATE TABLE IF NOT EXISTS <DATABASE>.<SCHEMA>.<INFERENCE_LOG> (
    prediction_id   STRING,
    event_ts        TIMESTAMP_NTZ,
    -- feature columns
    feature_1       FLOAT,
    feature_2       STRING,
    -- predictions
    pred_class      NUMBER,
    pred_score      FLOAT,
    -- ground truth (populate when labels arrive)
    actual_class    NUMBER
);
```

---

### Phase 2: Create Model Monitor

```sql
CREATE MODEL MONITOR <MONITOR_NAME> WITH
    MODEL              = <DATABASE>.<SCHEMA>.<MODEL_NAME>
    VERSION            = '<VERSION>'
    FUNCTION           = 'predict'
    SOURCE             = <DATABASE>.<SCHEMA>.<INFERENCE_LOG>
    WAREHOUSE          = <WAREHOUSE>
    REFRESH_INTERVAL   = '1 hour'       -- min: 60 seconds
    AGGREGATION_WINDOW = '1 day'        -- min / only supported unit: days
    TIMESTAMP_COLUMN   = event_ts
    BASELINE           = <DATABASE>.<SCHEMA>.<TRAINING_SNAPSHOT>  -- required for drift metrics
    ID_COLUMNS         = ('prediction_id')
    PREDICTION_CLASS_COLUMNS = ('pred_class')
    PREDICTION_SCORE_COLUMNS = ('pred_score')
    ACTUAL_CLASS_COLUMNS     = ('actual_class')
    SEGMENT_COLUMNS          = ('region');  -- optional; max 5, STRING type, < 25 unique values each
```

> ⚠️ **WARN:** `BASELINE` is a **snapshot embedded at creation** — it is NOT a live reference. To update: `ALTER MODEL MONITOR <name> SET BASELINE = '<new_table>'`.
> ⚠️ **WARN:** Core config (model, source table, column assignments) is **IMMUTABLE** after creation. To change: `DROP` and recreate.
> ⚠️ **WARN:** Max **250 monitors** per account.

---

### Phase 3: Query Drift Metrics

```sql
-- Requires BASELINE set on monitor
SELECT * FROM TABLE(MODEL_MONITOR_DRIFT_METRIC(
    '<MONITOR_NAME>',
    'JENSEN_SHANNON',  -- JENSEN_SHANNON | WASSERSTEIN | POPULATION_STABILITY_INDEX | DIFFERENCE_OF_MEANS
    '<feature_col>',
    '1 DAY',
    DATEADD('DAY', -30, CURRENT_DATE()),
    CURRENT_DATE(),
    NULL
));
```

### Phase 4: Query Performance Metrics

```sql
-- Requires actual columns populated in inference log
SELECT * FROM TABLE(MODEL_MONITOR_PERFORMANCE_METRIC(
    '<MONITOR_NAME>',
    'F1_SCORE',  -- Binary clf: ROC_AUC | CLASSIFICATION_ACCURACY | PRECISION | RECALL | F1_SCORE
                 -- Regression: RMSE | MAE | MAPE | MSE
    '1 DAY',
    DATEADD('DAY', -30, CURRENT_DATE()),
    CURRENT_DATE(),
    NULL
));
```

### Phase 5: Query Statistical Metrics

```sql
-- Null counts, volume, etc.
SELECT * FROM TABLE(MODEL_MONITOR_STAT_METRIC(
    '<MONITOR_NAME>',
    'COUNT_NULL',  -- COUNT_NULL | COUNT_DISTINCT | etc.
    '<feature_col>',
    '1 DAY',
    DATEADD('DAY', -30, CURRENT_DATE()),
    CURRENT_DATE(),
    NULL
));
```

---

### Phase 6: Set Up Drift Alert

```sql
CREATE ALERT drift_alert
    WAREHOUSE = <WAREHOUSE>
    SCHEDULE  = '1 DAY'
    IF (EXISTS (
        SELECT 1 FROM TABLE(MODEL_MONITOR_DRIFT_METRIC(
            '<MONITOR_NAME>', 'POPULATION_STABILITY_INDEX', '<feature_col>',
            '1 DAY', DATEADD('DAY', -1, CURRENT_DATE()), CURRENT_DATE(), NULL
        ))
        WHERE METRIC_VALUE > 0.2  -- PSI > 0.2 = significant drift
    ))
    THEN CALL SYSTEM$SEND_EMAIL('<email>', 'Model Drift Alert', 'PSI > 0.2 detected');

ALTER ALERT drift_alert RESUME;
```

---

### Monitor Diagnosis / Recovery

```sql
DESC MODEL MONITOR <MONITOR_NAME>;
-- aggregation_status: JSON — ACTIVE or SUSPENDED per component
-- aggregation_last_error: JSON — root cause SQL error
-- Auto-suspends after 5 consecutive refresh failures

-- After fixing root cause:
ALTER MODEL MONITOR <MONITOR_NAME> RESUME;
```

For full triage, route to **ml-log-inspector**.

---

### Success Criteria

- [ ] `SHOW MODEL MONITORS` shows monitor in ACTIVE state
- [ ] `MODEL_MONITOR_DRIFT_METRIC` returns data (if baseline set and data exists)
- [ ] `MODEL_MONITOR_PERFORMANCE_METRIC` returns data (if actuals populated)
- [ ] Alert created and tested

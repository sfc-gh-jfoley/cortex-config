---
name: ml-functions
description: "AutoML in SQL using Snowflake Cortex ML Functions. No Python training required. Use when: forecasting time-series data, detecting anomalies, classifying records, or running root cause / driver analysis entirely in SQL."
---

## ml-functions

Run AutoML directly in SQL using Snowflake Cortex ML Functions. No Python, no notebooks, no training infrastructure.

---

> ⚠️ **CRITICAL:**
> - `session.call()` is **INCOMPATIBLE** with ML function models. Always use `session.sql()` for Snowpark invocation.
> - `AUTOCOMMIT` must be **enabled** (it is by default in Snowsight/notebooks).
> - All persisted ML models are **IMMUTABLE**. To update: `DROP` and recreate.

---

### Function Overview

| Function | Use Case | Stateful? |
|---|---|---|
| `SNOWFLAKE.ML.FORECAST` | Predict future time-series values | Yes — persisted model object |
| `SNOWFLAKE.ML.ANOMALY_DETECTION` | Flag outliers vs trained baseline | Yes — persisted model object |
| `SNOWFLAKE.ML.CLASSIFICATION` | Classify records (binary or multi-class) | Yes — persisted model object |
| `SNOWFLAKE.ML.TOP_INSIGHTS` | Root cause / driver analysis between two groups | No — stateless instance |

> Cannot clone, share, or replicate `ANOMALY_DETECTION` or `CLASSIFICATION` models across roles/accounts.

---

### FORECAST

```sql
-- Create model
CREATE SNOWFLAKE.ML.FORECAST my_model(
    INPUT_DATA        => TABLE(my_view),
    TIMESTAMP_COLNAME => 'date',
    TARGET_COLNAME    => 'sales'
    -- SERIES_COLNAME => 'store_id'  -- uncomment for multi-series forecasting
);

-- Run forecast
CALL my_model!FORECAST(FORECASTING_PERIODS => 7);

-- Save results to table
CREATE TABLE my_forecasts AS
    SELECT * FROM TABLE(my_model!FORECAST(FORECASTING_PERIODS => 7));
-- Returns: SERIES, TS, FORECAST, LOWER_BOUND, UPPER_BOUND
```

**Limits:**
- Standard WH: ≤ 5M rows
- For larger datasets: use Snowpark-optimized warehouse
- Minimum granularity: 1 second

---

### ANOMALY_DETECTION

```sql
-- Create model (train on historical data)
CREATE SNOWFLAKE.ML.ANOMALY_DETECTION my_model(
    INPUT_DATA        => TABLE(train_view),
    TIMESTAMP_COLNAME => 'date',
    TARGET_COLNAME    => 'value',
    LABEL_COLNAME     => 'is_anomaly'  -- optional boolean: TRUE = known anomaly in training set
);

-- Detect anomalies on new data
CALL my_model!DETECT_ANOMALIES(
    INPUT_DATA        => TABLE(test_view),
    TIMESTAMP_COLNAME => 'date',
    TARGET_COLNAME    => 'value',
    CONFIG_OBJECT     => {'prediction_interval': 0.9999}  -- higher = less sensitive
);
```

**Limits / Gotchas:**
- Minimum **12 rows per series** (2–11 rows: naive result = last observed value)
- Test timestamps **must be strictly after** training timestamps

---

### CLASSIFICATION

```sql
-- Train
CREATE OR REPLACE SNOWFLAKE.ML.CLASSIFICATION my_model(
    INPUT_DATA     => SYSTEM$REFERENCE('TABLE', 'training_data'),
    TARGET_COLNAME => 'label'
);

-- Predict
SELECT my_model!PREDICT(INPUT_DATA => {*}) FROM test_data;

-- Evaluate + explain
CALL my_model!SHOW_EVALUATION_METRICS();
CALL my_model!SHOW_FEATURE_IMPORTANCE();
CALL my_model!SHOW_TRAINING_LOGS();
```

**Limits:**
- Supports **binary AND multi-class** classification (up to 255 classes)
- Algorithm: GBM
- Max ~1,000 columns; ~600M rows on M Snowpark-optimized warehouse

---

### TOP_INSIGHTS (Stateless — no model creation needed)

```sql
-- Create stateless instance
CREATE SNOWFLAKE.ML.TOP_INSIGHTS IF NOT EXISTS my_insights();

-- Prepare: FALSE = control group (baseline), TRUE = test group
CREATE OR REPLACE VIEW labeled_data AS
    SELECT metric, dim_country, dim_vertical,
           ds >= DATEADD(month, -1, CURRENT_DATE()) AS label
    FROM input_table;

-- Find drivers
CALL my_insights!GET_DRIVERS(
    INPUT_DATA     => TABLE(labeled_data),
    LABEL_COLNAME  => 'label',
    METRIC_COLNAME => 'metric'
);
-- Returns per segment: METRIC_CONTROL, METRIC_TEST, CONTRIBUTION, RELATIVE_CONTRIBUTION, GROWTH_RATE
```

**Limits:**
- ~1M rows × 1,000 cols before memory exhaustion
- Cast numeric dims to `STRING` to use as categorical dimension columns

---

### Success Criteria

- [ ] Model created without error (`SHOW SNOWFLAKE.ML.FORECAST IN SCHEMA` confirms)
- [ ] Inference/prediction call returns results
- [ ] Results saved to a table for downstream use
- [ ] For CLASSIFICATION: evaluation metrics reviewed before deploying predictions

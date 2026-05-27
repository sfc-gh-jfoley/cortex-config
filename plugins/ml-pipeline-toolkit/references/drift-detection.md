# Drift Detection SQL Patterns

SQL patterns for querying all three model monitor metric functions.

---

## Before Querying: Check Monitor Health

```sql
-- Always check status before querying metrics
DESC MODEL MONITOR <name>;
-- Key JSON fields (only in DESC, not SHOW):
-- aggregation_status:              ACTIVE | SUSPENDED per metric component
-- aggregation_last_error:          exact SQL error that caused suspension
-- aggregation_last_data_timestamp: when each component last had fresh data
-- monitor_state:                   overall ACTIVE | SUSPENDED
```

If `aggregation_status` contains SUSPENDED, metric functions will return empty or stale results.
Run `ALTER MODEL MONITOR <name> RESUME;` after fixing the root cause.

---

## Drift Metrics (Requires BASELINE)

```sql
SELECT * FROM TABLE(MODEL_MONITOR_DRIFT_METRIC(
    '<monitor_name>',
    'JENSEN_SHANNON',                          -- drift method (see below)
    '<feature_column>',
    '1 DAY',                                   -- aggregation window
    DATEADD('DAY', -30, CURRENT_DATE()),        -- start date
    CURRENT_DATE(),                            -- end date
    NULL                                       -- segment filter (or JSON object)
));
```

**Drift Methods:**
| Method | Best For |
|--------|----------|
| `JENSEN_SHANNON` | Categorical and continuous; bounded 0–1 |
| `WASSERSTEIN` | Continuous distributions; magnitude-sensitive |
| `POPULATION_STABILITY_INDEX` | Production monitoring standard; PSI > 0.2 = significant |
| `DIFFERENCE_OF_MEANS` | Simple numeric mean shift detection |

---

## Performance Metrics (Requires Actuals in Source Table)

```sql
SELECT * FROM TABLE(MODEL_MONITOR_PERFORMANCE_METRIC(
    '<monitor_name>',
    'F1_SCORE',                                -- metric name (see below)
    '1 DAY',
    DATEADD('DAY', -30, CURRENT_DATE()),
    CURRENT_DATE(),
    NULL
));
```

**Binary Classification Metrics:** `ROC_AUC` | `CLASSIFICATION_ACCURACY` | `PRECISION` | `RECALL` | `F1_SCORE`

**Regression Metrics:** `RMSE` | `MAE` | `MAPE` | `MSE`

---

## Statistical Metrics

```sql
SELECT * FROM TABLE(MODEL_MONITOR_STAT_METRIC(
    '<monitor_name>',
    'COUNT_NULL',                              -- stat metric name
    '<feature_column>',
    '1 DAY',
    DATEADD('DAY', -30, CURRENT_DATE()),
    CURRENT_DATE(),
    NULL
));
```

---

## Segment-Specific Queries

To filter to a specific segment, replace the trailing `NULL` with a JSON filter (one segment pair per call):

```sql
SELECT * FROM TABLE(MODEL_MONITOR_DRIFT_METRIC(
    '<monitor_name>', 'JENSEN_SHANNON', '<feature>',
    '1 DAY', DATEADD('DAY', -30, CURRENT_DATE()), CURRENT_DATE(),
    '{"SEGMENTS":[{"column":"region","value":"US"}]}'
));
```

---

## Monitor Limits

| Limit | Value |
|-------|-------|
| Monitors per account | 250 |
| Feature columns per monitor | 500 |
| Segment columns per monitor | 5 (STRING type only) |
| Unique values per segment column | 25 |
| Minimum aggregation window | 1 day |
| Minimum refresh interval | 60 seconds |

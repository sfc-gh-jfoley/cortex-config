---
name: adaptive-warehouse-monitor
description: Monitor Adaptive Warehouse performance, credit usage, scaling events, and revert criteria. Calculate ROI vs. standard warehouse.
---

# Adaptive Warehouse Monitor Sub-Skill

Monitor Adaptive Warehouse performance, credit consumption, and scaling behavior. Determine if Adaptive is delivering ROI or if revert to standard is recommended.

## Overview

This sub-skill guides you through:
1. **Phase 1**: Query `WAREHOUSE_METERING_HISTORY` to track credit burn and scaling events
2. **Phase 2**: Establish baseline performance metrics (latency, throughput, credits/query)
3. **Phase 3**: Define revert criteria (when to convert back to standard)
4. **Phase 4**: Set up continuous monitoring and alerts
5. **Phase 5**: Calculate cost-benefit ROI and ROI decision logic

---

## Phase 1: Collect Metering Data

### Query 1: Weekly Credit Trend

```sql
-- Track weekly credit usage and scaling patterns
SELECT
  DATE_TRUNC(week, START_TIME) as week,
  COUNT(DISTINCT START_TIME) as scaling_events,
  AVG(CREDITS_USED) as avg_credits_per_interval,
  MAX(CREDITS_USED) as peak_credits_per_interval,
  MIN(CREDITS_USED) as min_credits_per_interval,
  SUM(CREDITS_USED) as total_credits_week,
  STDDEV(CREDITS_USED) as variance_credits
FROM SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY
WHERE WAREHOUSE_NAME = 'adaptive_wh'
  AND START_TIME > DATEADD(week, -12, CURRENT_TIMESTAMP)
GROUP BY DATE_TRUNC(week, START_TIME)
ORDER BY week DESC;
```

**Interpretation**:
- **High variance (`variance_credits` large)**: Workload is variable; Adaptive is helping
- **Low variance**: Workload is sustained; Standard may be more economical
- **min_credits_per_interval near 0**: Warehouse is auto-suspending (cost savings)

### Query 2: Scaling Events and Compute Nodes

```sql
-- Observe how often warehouse scales and to what sizes
SELECT
  DATE_TRUNC(day, START_TIME) as day,
  COUNT(*) as scaling_events_per_day,
  AVG(NUM_COMPUTE_NODES_REQUESTED) as avg_nodes,
  MAX(NUM_COMPUTE_NODES_REQUESTED) as peak_nodes,
  MIN(NUM_COMPUTE_NODES_REQUESTED) as min_nodes
FROM SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY
WHERE WAREHOUSE_NAME = 'adaptive_wh'
  AND START_TIME > DATEADD(day, -30, CURRENT_TIMESTAMP)
GROUP BY DATE_TRUNC(day, START_TIME)
ORDER BY day DESC;
```

**Interpretation**:
- **Frequent scaling (many events)**: Workload is dynamic; Adaptive is responding
- **Rare scaling**: Workload may be sustained (consider Standard)
- **Peak nodes = min nodes**: No scaling happening; fixed warehouse might be cheaper

### Query 3: Auto-Suspend Activity

```sql
-- Check if auto-suspend is saving credits
SELECT
  DATE_TRUNC(day, START_TIME) as day,
  SUM(CASE WHEN CREDITS_USED = 0 THEN 1 ELSE 0 END) as suspend_periods,
  COUNT(*) as total_periods,
  ROUND(100.0 * SUM(CASE WHEN CREDITS_USED = 0 THEN 1 ELSE 0 END) / COUNT(*), 2) as suspend_percent
FROM SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY
WHERE WAREHOUSE_NAME = 'adaptive_wh'
  AND START_TIME > DATEADD(day, -30, CURRENT_TIMESTAMP)
GROUP BY DATE_TRUNC(day, START_TIME)
ORDER BY day DESC;
```

**Interpretation**:
- **High suspend_percent (> 30%)**: Auto-suspend is saving significant credits
- **Low suspend_percent (< 5%)**: Workload is always active; consider longer AUTO_SUSPEND timeout or Standard warehouse

---

## Phase 2: Establish Baseline Metrics

### Metric 1: Query Latency

```sql
-- Compare query latency on Adaptive vs. expected baseline
SELECT
  DATE_TRUNC(hour, START_TIME) as hour,
  WAREHOUSE_NAME,
  COUNT(*) as query_count,
  AVG(EXECUTION_TIME) as avg_execution_ms,
  MAX(EXECUTION_TIME) as max_execution_ms,
  PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY EXECUTION_TIME) as p95_execution_ms
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE WAREHOUSE_NAME = 'adaptive_wh'
  AND START_TIME > DATEADD(day, -7, CURRENT_TIMESTAMP)
GROUP BY DATE_TRUNC(hour, START_TIME), WAREHOUSE_NAME
ORDER BY hour DESC;
```

**Baseline targets** (by workload):
- **OLTP (interactive)**: p95 < 1 second
- **Reporting**: p95 < 5 seconds
- **Batch ETL**: p95 < 30 seconds

**If actual > baseline**: Investigate scaling delays or query optimization.

### Metric 2: Throughput (Queries per Hour)

```sql
-- Track query throughput on Adaptive warehouse
SELECT
  DATE_TRUNC(hour, START_TIME) as hour,
  COUNT(*) as queries_per_hour,
  AVG(QUEUE_TIME) as avg_queue_time_ms,
  SUM(EXECUTION_TIME) / 1000.0 / 60.0 as total_compute_minutes
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE WAREHOUSE_NAME = 'adaptive_wh'
  AND START_TIME > DATEADD(day, -7, CURRENT_TIMESTAMP)
GROUP BY DATE_TRUNC(hour, START_TIME)
ORDER BY hour DESC;
```

**Interpretation**:
- **High queue_time**: Warehouse not scaling fast enough; increase `MAX_QUERY_PERFORMANCE_LEVEL`
- **Low queue_time**: Warehouse is responsive (good)
- **Consistent throughput**: Predictable workload; may not benefit from Adaptive

### Metric 3: Credits per Query

```sql
-- Calculate efficiency: credits consumed per query
WITH query_costs AS (
  SELECT
    QUERY_ID,
    WAREHOUSE_NAME,
    EXECUTION_TIME,
    WAREHOUSE_SIZE,
    -- Rough estimate: 1 credit = 60 seconds of compute on Small (1 credit/hour)
    (EXECUTION_TIME / 1000.0 / 3600.0) as estimated_credits
  FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
  WHERE WAREHOUSE_NAME = 'adaptive_wh'
    AND START_TIME > DATEADD(day, -7, CURRENT_TIMESTAMP)
)
SELECT
  AVG(estimated_credits) as avg_credits_per_query,
  MAX(estimated_credits) as max_credits_per_query,
  PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY estimated_credits) as p95_credits_per_query
FROM query_costs;
```

**Baseline**: Compare to credit/query on standard warehouse of same size for same workload.

---

## Phase 3: Define Revert Criteria

Establish clear decision points for converting back to standard warehouse.

### Criterion 1: Cost Threshold (Most Important)

```sql
-- Calculate cost difference: Adaptive vs. estimated Standard equivalent
WITH adaptive_cost AS (
  SELECT
    SUM(CREDITS_USED) as adaptive_total_credits,
    COUNT(*) as periods
  FROM SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY
  WHERE WAREHOUSE_NAME = 'adaptive_wh'
    AND START_TIME > DATEADD(day, -30, CURRENT_TIMESTAMP)
),
standard_cost AS (
  -- Estimate: if same workload on Standard Large (3 credits/hour)
  SELECT
    (30 * 24 * 3) as estimated_standard_credits  -- 30 days × 24 hours × 3 credits/hr
)
SELECT
  adaptive_total_credits,
  estimated_standard_credits,
  ROUND(100.0 * (estimated_standard_credits - adaptive_total_credits) / estimated_standard_credits, 2) as savings_percent,
  (estimated_standard_credits - adaptive_total_credits) * 4 as estimated_savings_dollars  -- $4/credit
FROM adaptive_cost, standard_cost;
```

**Revert if**:
- Savings < 10% (not worth the complexity)
- Credits > estimated Standard equivalent (Adaptive actively hurting)

### Criterion 2: Latency Regression

```sql
-- Check if Adaptive latency is significantly worse than baseline
-- (Baseline should be from standard warehouse or pre-Adaptive monitoring)

SELECT
  PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY EXECUTION_TIME) as p95_latency_ms
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE WAREHOUSE_NAME = 'adaptive_wh'
  AND START_TIME > DATEADD(day, -7, CURRENT_TIMESTAMP);

-- Compare to baseline:
-- IF p95_latency > baseline_p95_latency * 1.5 (50% regression) THEN consider revert
```

**Revert if**:
- p95 latency > 1.5× baseline (significant degradation)
- Max latency consistently > SLA (not meeting service level)

### Criterion 3: Sustained High-Concurrency Detection

```sql
-- If workload is actually sustained (not variable), Standard may be better
SELECT
  DATE_TRUNC(hour, START_TIME) as hour,
  AVG(NUM_COMPUTE_NODES_REQUESTED) as avg_nodes,
  STDDEV(NUM_COMPUTE_NODES_REQUESTED) as variance_nodes
FROM SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY
WHERE WAREHOUSE_NAME = 'adaptive_wh'
  AND START_TIME > DATEADD(day, -30, CURRENT_TIMESTAMP)
GROUP BY DATE_TRUNC(hour, START_TIME);

-- IF variance_nodes < 1.0 (very low variance) AND avg_nodes >= 5 THEN sustained high load
-- THEN revert to Standard (no scaling benefit)
```

**Revert if**:
- Variance < 1 node AND average > 5 nodes (sustained at high level)
- Means workload doesn't benefit from dynamic scaling

### Criterion 4: Scaling Overhead Issues

```sql
-- Check for excessive scaling events that might indicate thrashing
SELECT
  DATE_TRUNC(hour, START_TIME) as hour,
  COUNT(*) as scaling_events_per_hour
FROM SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY
WHERE WAREHOUSE_NAME = 'adaptive_wh'
  AND START_TIME > DATEADD(day, -7, CURRENT_TIMESTAMP)
GROUP BY DATE_TRUNC(hour, START_TIME)
ORDER BY scaling_events_per_hour DESC
LIMIT 10;

-- IF scaling_events_per_hour > 24 (more than 1 event per minute) THEN thrashing
-- Workload is too erratic; scaling overhead hurts performance
```

**Revert if**:
- Scaling events > 24/hour (thrashing detected)
- Suggests workload variability is hurting performance

---

## Phase 4: Set Up Continuous Monitoring

### Alert 1: High Credit Usage (Anomaly Detection)

```sql
-- Create alert if Adaptive uses more credits than expected
CREATE OR REPLACE ALERT adaptive_wh_high_credits
  WAREHOUSE = monitoring_wh
  CONDITION = (
    SELECT COUNT(*) as high_credit_hours
    FROM SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY
    WHERE WAREHOUSE_NAME = 'adaptive_wh'
      AND START_TIME > DATEADD(hour, -1, CURRENT_TIMESTAMP)
      AND CREDITS_USED > 5  -- Adjust threshold based on your baseline
  ) > 3  -- Alert if > 3 high-credit intervals in past hour
  THEN CALL SYSTEM$SEND_EMAIL(
    '<your-email@company.com>',
    'Adaptive Warehouse High Credit Alert',
    'Adaptive warehouse is using more credits than expected. Check revert criteria.'
  );

ALTER ALERT adaptive_wh_high_credits RESUME;
```

### Alert 2: Scaling Thrashing

```sql
-- Create alert if warehouse is scaling too frequently
CREATE OR REPLACE ALERT adaptive_wh_thrashing
  WAREHOUSE = monitoring_wh
  CONDITION = (
    SELECT COUNT(*) as events_per_hour
    FROM SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY
    WHERE WAREHOUSE_NAME = 'adaptive_wh'
      AND START_TIME > DATEADD(hour, -1, CURRENT_TIMESTAMP)
  ) > 24  -- More than 1 event per minute
  THEN CALL SYSTEM$SEND_EMAIL(
    '<your-email@company.com>',
    'Adaptive Warehouse Thrashing Detected',
    'Too many scaling events. Workload may be too erratic for Adaptive.'
  );

ALTER ALERT adaptive_wh_thrashing RESUME;
```

### Alert 3: Latency Regression

```sql
-- Create alert if query latency increases significantly
CREATE OR REPLACE ALERT adaptive_wh_latency
  WAREHOUSE = monitoring_wh
  CONDITION = (
    SELECT PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY EXECUTION_TIME)
    FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
    WHERE WAREHOUSE_NAME = 'adaptive_wh'
      AND START_TIME > DATEADD(hour, -1, CURRENT_TIMESTAMP)
  ) > 10000  -- Adjust threshold based on your SLA
  THEN CALL SYSTEM$SEND_EMAIL(
    '<your-email@company.com>',
    'Adaptive Warehouse Latency Alert',
    'Query latency has increased. Check scaling parameters or revert to Standard.'
  );

ALTER ALERT adaptive_wh_latency RESUME;
```

### Dashboard Query (Optional)

```sql
-- Create a single query for a dashboard to monitor all metrics
SELECT
  'Credit Usage' as metric,
  (SELECT SUM(CREDITS_USED) FROM SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY 
   WHERE WAREHOUSE_NAME = 'adaptive_wh' AND START_TIME > DATEADD(day, -7, CURRENT_TIMESTAMP)) as value,
  'credits' as unit
UNION ALL
SELECT
  'Avg Query Latency (p95)',
  (SELECT PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY EXECUTION_TIME) 
   FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY 
   WHERE WAREHOUSE_NAME = 'adaptive_wh' AND START_TIME > DATEADD(day, -1, CURRENT_TIMESTAMP)),
  'ms'
UNION ALL
SELECT
  'Scaling Events (24h)',
  (SELECT COUNT(*) FROM SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY 
   WHERE WAREHOUSE_NAME = 'adaptive_wh' AND START_TIME > DATEADD(day, -1, CURRENT_TIMESTAMP)),
  'events'
UNION ALL
SELECT
  'Auto-Suspend Percent',
  ROUND(100.0 * (SELECT SUM(CASE WHEN CREDITS_USED = 0 THEN 1 ELSE 0 END) 
                 FROM SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY 
                 WHERE WAREHOUSE_NAME = 'adaptive_wh' AND START_TIME > DATEADD(day, -1, CURRENT_TIMESTAMP)) /
                (SELECT COUNT(*) FROM SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY 
                 WHERE WAREHOUSE_NAME = 'adaptive_wh' AND START_TIME > DATEADD(day, -1, CURRENT_TIMESTAMP)), 2),
  '%'
ORDER BY metric;
```

---

## Phase 5: Calculate ROI and Make Decision

### ROI Calculation

```sql
-- Calculate comprehensive ROI: Adaptive vs. Standard warehouse
WITH adaptive_stats AS (
  SELECT
    SUM(CREDITS_USED) as adaptive_total_credits,
    COUNT(DISTINCT WAREHOUSE_NAME) as warehouse_count,
    COUNT(*) as metering_periods
  FROM SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY
  WHERE WAREHOUSE_NAME = 'adaptive_wh'
    AND START_TIME > DATEADD(day, -30, CURRENT_TIMESTAMP)
),
standard_estimate AS (
  -- Estimate equivalent Standard Large (3 credits/hour) for same duration
  SELECT
    DATEDIFF(hour, 
      (SELECT MIN(START_TIME) FROM SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY WHERE WAREHOUSE_NAME = 'adaptive_wh'),
      (SELECT MAX(START_TIME) FROM SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY WHERE WAREHOUSE_NAME = 'adaptive_wh')
    ) * 3 as standard_equivalent_credits
)
SELECT
  (SELECT adaptive_total_credits FROM adaptive_stats) as adaptive_monthly_credits,
  (SELECT standard_equivalent_credits FROM standard_estimate) as estimated_standard_credits,
  ROUND(((SELECT standard_equivalent_credits FROM standard_estimate) - (SELECT adaptive_total_credits FROM adaptive_stats)) * 4, 2) as estimated_monthly_savings_dollars,
  ROUND(100.0 * ((SELECT standard_equivalent_credits FROM standard_estimate) - (SELECT adaptive_total_credits FROM adaptive_stats)) / (SELECT standard_equivalent_credits FROM standard_estimate), 2) as savings_percent
FROM adaptive_stats, standard_estimate;
```

### ROI Decision Logic

```
IF savings_percent >= 30%:
  RECOMMENDATION: KEEP ADAPTIVE
  "Adaptive is saving 30%+ on credits. Continue using."

ELSE IF savings_percent >= 10% AND latency_p95 <= baseline_p95 * 1.2:
  RECOMMENDATION: KEEP ADAPTIVE with tuning
  "Modest savings (10–30%), acceptable latency. Fine-tune scaling parameters and monitor."

ELSE IF savings_percent < 10% OR latency_p95 > baseline_p95 * 1.5:
  RECOMMENDATION: REVERT TO STANDARD
  "Low savings or high latency regression. Revert to Standard warehouse."

ELSE IF thrashing_detected OR sustained_high_concurrency:
  RECOMMENDATION: REVERT TO STANDARD
  "Workload characteristics (thrashing or sustained) don't benefit from Adaptive. Use Standard."
```

---

## Troubleshooting: Monitoring Issues

### Issue: "WAREHOUSE_METERING_HISTORY is empty"

**Cause**: Warehouse hasn't run any queries yet or data hasn't aged into ACCOUNT_USAGE.

**Solution**:
```sql
-- Run a test query to generate metering data
USE WAREHOUSE adaptive_wh;
SELECT 1;

-- Wait 5–10 minutes, then re-query WAREHOUSE_METERING_HISTORY
```

### Issue: "Cannot create alert (privilege denied)"

**Cause**: Current role lacks `CREATE ALERT` privilege.

**Solution**:
```sql
-- Contact admin to grant privilege
-- GRANT CREATE ALERT ON ACCOUNT TO ROLE <your_role>;
-- Or create alerts in a monitoring role with higher privileges
```

### Issue: "Latency metrics are inconsistent"

**Cause**: Query mix changed (different query types between periods).

**Solution**:
- Filter by query pattern: `WHERE QUERY_TEXT LIKE '%my_stable_query%'`
- Or compare only within business hours to exclude batch jobs
- Establish baseline with controlled workload before evaluating Adaptive

---

## Next Steps

- **Decision is to keep Adaptive?** Fine-tune scaling parameters based on Phase 2 metrics
- **Decision is to revert?** Run: `ALTER WAREHOUSE adaptive_wh TYPE = STANDARD;`
- **Unsure?** Run this sub-skill again after 2–4 weeks of monitoring to collect more data
- **Need to optimize queries?** Use `ops-monitor` / `self-healing-pipeline` skill for query optimization before re-evaluating Adaptive

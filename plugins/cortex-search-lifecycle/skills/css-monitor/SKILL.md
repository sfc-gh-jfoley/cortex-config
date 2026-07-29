---
name: css-monitor
description: >
  Monitor Cortex Search Service health and performance. Query ACCOUNT_USAGE views for service
  status and cost tracking. Track guardrails violations via CORTEX_AI_GUARDRAILS_USAGE_HISTORY
  (GA Jun 16, 2026). Use when investigating performance issues, monitoring costs, or ensuring
  guardrails compliance.
triggers:
  - css monitor
  - search service monitoring
  - cortex search monitoring
  - search guardrails
  - guardrails violations
  - search service health
  - search performance
  - search cost tracking
  - cortex search health
---

# CSS Monitor: Monitor Search Service Health and Guardrails

Complete workflow for monitoring Cortex Search Service status, usage, guardrails compliance, and performance issues.

---

## When to Use This Sub-Skill

Use **css-monitor** when:
- Checking search service status (READY, INDEXING, FAILED, etc.)
- Monitoring monthly credit usage and cost trends
- Analyzing guardrails violations (rate limits, concurrency, resource constraints)
- Investigating search performance issues or slowdowns
- Tracking index freshness (target_lag adherence)
- Troubleshooting service health

**Do NOT use this sub-skill for:**
- Creating search services (use `$cortex-search-lifecycle:css-setup`)
- Setting budgets (use `$cortex-search-lifecycle:css-budgets`)
- Querying search results (use agents or cortex_search_result())

---

## Quick Start: 5-Minute Health Check

### Step 1: Service Status

```sql
-- Check if service is READY and indexing is progressing
SELECT 
  name,
  state,
  indexing_progress_pct,
  created_on,
  last_index_update_ts,
  DATEDIFF(hour, last_index_update_ts, CURRENT_TIMESTAMP()) as hours_since_refresh
FROM ACCOUNT_USAGE.CORTEX_SEARCH_SERVICES
WHERE name = 'product_search';

-- Expected state: READY (100% progress)
-- If INDEXING: Wait for completion
-- If FAILED: Check error logs and service DDL
```

### Step 2: Monthly Cost

```sql
-- What's my search spending this month?
SELECT 
  SUM(cumulative_credits_used) as total_credits_used,
  ROUND(total_credits_used * 2, 2) as estimated_cost_usd,  -- Assume $2/credit
  COUNT(*) as num_services
FROM ACCOUNT_USAGE.CORTEX_SEARCH_SERVICES
WHERE DATE(created_on) >= DATE_TRUNC('month', CURRENT_TIMESTAMP());
```

### Step 3: Guardrails Violations

```sql
-- Any rate limit or resource violations this week?
SELECT 
  violation_type,
  COUNT(*) as violation_count,
  SUM(violation_count) as total_violations
FROM CORTEX_AI_GUARDRAILS_USAGE_HISTORY
WHERE violation_date >= CURRENT_DATE() - INTERVAL '7 days'
GROUP BY violation_type
ORDER BY total_violations DESC;
```

### Step 4: Health Summary

```sql
-- One-liner status dashboard
SELECT 
  CASE WHEN state = 'READY' THEN '✓ OK' ELSE '⚠ ' || state END as service_status,
  CASE WHEN hours_since_refresh <= 1 THEN '✓ Fresh' ELSE '⚠ Stale (' || hours_since_refresh || 'h)' END as index_freshness,
  CASE WHEN pct_budget_used <= 80 THEN '✓ OK' ELSE '⚠ High (' || pct_budget_used || '%)' END as budget_status,
  CASE WHEN daily_violations = 0 THEN '✓ OK' ELSE '⚠ ' || daily_violations || ' violations' END as guardrails_status
FROM (
  SELECT 
    s.name,
    s.state,
    DATEDIFF(hour, s.last_index_update_ts, CURRENT_TIMESTAMP()) as hours_since_refresh,
    ROUND(100.0 * s.cumulative_credits_used / COALESCE(b.monthly_limit, 100), 1) as pct_budget_used,
    COALESCE(g.violation_count, 0) as daily_violations
  FROM ACCOUNT_USAGE.CORTEX_SEARCH_SERVICES s
  LEFT JOIN ACCOUNT_USAGE.CORTEX_SEARCH_SERVICE_BUDGETS b ON s.name = b.service_name
  LEFT JOIN (
    SELECT service_name, COUNT(*) as violation_count
    FROM CORTEX_AI_GUARDRAILS_USAGE_HISTORY
    WHERE violation_date = CURRENT_DATE()
    GROUP BY service_name
  ) g ON s.name = g.service_name
  WHERE s.name = 'product_search'
);
```

---

## Complete Monitoring Queries

### Service Status and Index Progress

```sql
-- Monitor service lifecycle: INIT → INDEXING → READY
SELECT 
  name,
  state,
  indexing_progress_pct,
  created_on,
  last_index_update_ts,
  DATEDIFF(minute, last_index_update_ts, CURRENT_TIMESTAMP()) as minutes_since_refresh,
  CASE 
    WHEN state = 'READY' AND indexing_progress_pct = 100 THEN 'Healthy'
    WHEN state = 'INDEXING' THEN 'Indexing (' || indexing_progress_pct || '%)'
    WHEN state = 'FAILED' THEN 'Failed - check service DDL'
    ELSE 'Other: ' || state
  END as health_status
FROM ACCOUNT_USAGE.CORTEX_SEARCH_SERVICES
WHERE name LIKE '%'  -- All services, or filter by name pattern
ORDER BY created_on DESC;
```

### Monthly Cost and Budget Tracking

```sql
-- See which services are most expensive
SELECT 
  name,
  cumulative_credits_used,
  ROUND(cumulative_credits_used * 2, 2) as estimated_cost_usd,
  DATEDIFF(day, created_on, CURRENT_TIMESTAMP()) as days_deployed,
  ROUND(cumulative_credits_used / NULLIF(DATEDIFF(day, created_on, CURRENT_TIMESTAMP()), 0), 2) as avg_credits_per_day,
  ROUND(avg_credits_per_day * 30, 2) as projected_monthly_credits,
  ROUND(projected_monthly_credits * 2, 2) as projected_monthly_cost_usd,
  target_lag
FROM ACCOUNT_USAGE.CORTEX_SEARCH_SERVICES
ORDER BY cumulative_credits_used DESC;
```

### Compare Spending to Budget

```sql
-- Budget compliance: Who's over or approaching limits?
SELECT 
  s.name,
  b.budget_name,
  b.monthly_limit,
  b.monthly_credits_used,
  ROUND(100.0 * b.monthly_credits_used / b.monthly_limit, 1) as pct_of_limit,
  CASE 
    WHEN b.monthly_credits_used >= b.monthly_limit THEN 'OVER LIMIT - Service may be suspended'
    WHEN b.monthly_credits_used >= 0.9 * b.monthly_limit THEN 'WARNING - Approaching limit'
    WHEN b.monthly_credits_used >= 0.75 * b.monthly_limit THEN 'CAUTION - At 75%'
    ELSE 'OK'
  END as status,
  b.enforcement_action,
  b.month
FROM ACCOUNT_USAGE.CORTEX_SEARCH_SERVICES s
LEFT JOIN ACCOUNT_USAGE.CORTEX_SEARCH_SERVICE_BUDGETS b ON s.name = b.service_name
WHERE b.month >= DATE_TRUNC('month', CURRENT_TIMESTAMP())
ORDER BY pct_of_limit DESC;
```

### Guardrails Violations: Rate Limiting

```sql
-- Are we hitting rate limits? (requests per second exceeded)
SELECT 
  service_name,
  violation_date,
  violation_type,
  COUNT(*) as violation_count,
  MIN(violation_timestamp) as first_violation,
  MAX(violation_timestamp) as last_violation,
  DATEDIFF(hour, first_violation, last_violation) as hours_span,
  ROUND(violation_count::FLOAT / NULLIF(DATEDIFF(hour, first_violation, last_violation), 0), 2) as violations_per_hour
FROM CORTEX_AI_GUARDRAILS_USAGE_HISTORY
WHERE violation_type = 'RATE_LIMIT'
  AND violation_date >= CURRENT_DATE() - INTERVAL '7 days'
GROUP BY service_name, violation_date, violation_type
ORDER BY violation_date DESC, violation_count DESC;
```

### Guardrails Violations: Concurrency Limits

```sql
-- Are we hitting concurrency limits? (too many simultaneous queries)
SELECT 
  service_name,
  violation_date,
  violation_type,
  COUNT(*) as violation_count,
  MIN(violation_timestamp) as first_violation,
  MAX(violation_timestamp) as last_violation,
  DATEDIFF(minute, first_violation, last_violation) as minutes_span,
  ROUND(violation_count::FLOAT / NULLIF(DATEDIFF(minute, first_violation, last_violation), 0), 2) as violations_per_minute
FROM CORTEX_AI_GUARDRAILS_USAGE_HISTORY
WHERE violation_type = 'CONCURRENCY_LIMIT'
  AND violation_date >= CURRENT_DATE() - INTERVAL '7 days'
GROUP BY service_name, violation_date, violation_type
ORDER BY violation_date DESC, violation_count DESC;
```

### Guardrails Violations: Resource Constraints

```sql
-- Resource exhaustion (memory, CPU, disk)?
SELECT 
  service_name,
  violation_date,
  violation_type,
  COUNT(*) as violation_count,
  MIN(violation_timestamp) as first_violation,
  MAX(violation_timestamp) as last_violation
FROM CORTEX_AI_GUARDRAILS_USAGE_HISTORY
WHERE violation_type IN ('RESOURCE_CONSTRAINT', 'MEMORY_LIMIT', 'CPU_LIMIT', 'DISK_LIMIT')
  AND violation_date >= CURRENT_DATE() - INTERVAL '7 days'
GROUP BY service_name, violation_date, violation_type
ORDER BY violation_date DESC, violation_count DESC;
```

### All Guardrails Violations Summary

```sql
-- Comprehensive violation report (last 30 days)
SELECT 
  service_name,
  violation_type,
  COUNT(*) as violation_count,
  COUNT(DISTINCT violation_date) as days_with_violations,
  MIN(violation_date) as first_violation_date,
  MAX(violation_date) as last_violation_date,
  ROUND(100.0 * violation_count / SUM(violation_count) OVER (PARTITION BY service_name), 1) as pct_of_service_violations
FROM CORTEX_AI_GUARDRAILS_USAGE_HISTORY
WHERE violation_date >= CURRENT_DATE() - INTERVAL '30 days'
GROUP BY service_name, violation_type
ORDER BY violation_count DESC;
```

---

## Troubleshooting Queries

### Service Stuck in INDEXING State

```sql
-- Check if service is taking too long to index
SELECT 
  name,
  state,
  indexing_progress_pct,
  created_on,
  CURRENT_TIMESTAMP() as now,
  DATEDIFF(hour, created_on, now) as hours_elapsed,
  CASE 
    WHEN hours_elapsed > 12 AND indexing_progress_pct < 100 THEN 'Stuck - investigate warehouse or table size'
    WHEN hours_elapsed > 4 AND indexing_progress_pct < 50 THEN 'Slow - consider larger warehouse'
    ELSE 'Normal progress'
  END as diagnosis
FROM ACCOUNT_USAGE.CORTEX_SEARCH_SERVICES
WHERE state = 'INDEXING'
ORDER BY created_on DESC;

-- Remediation:
-- 1. Check warehouse size: Is it too small?
-- 2. Check table size: Is the source table very large?
-- 3. Cancel and re-create with larger warehouse: ALTER WAREHOUSE search_wh SET WAREHOUSE_SIZE = XL;
```

### Service in FAILED State

```sql
-- What went wrong?
SELECT 
  name,
  state,
  created_on,
  error_message,  -- May contain DDL syntax error or permission issue
  source_table_name,
  warehouse_name
FROM ACCOUNT_USAGE.CORTEX_SEARCH_SERVICES
WHERE state = 'FAILED';

-- Common causes:
-- - Warehouse doesn't exist or role lacks USAGE privilege
-- - Source table doesn't exist or role lacks SELECT privilege
-- - Column type not supported (only VARCHAR/STRING/TEXT)
-- - DDL syntax error in CREATE statement

-- Check privilege error:
SELECT * FROM ACCOUNT_USAGE.LOGIN_HISTORY
WHERE USER_NAME = CURRENT_USER()
  AND ERROR_MESSAGE LIKE '%CORTEX SEARCH SERVICE%'
ORDER BY EVENT_TIMESTAMP DESC LIMIT 10;
```

### Index Freshness: Falling Behind target_lag

```sql
-- Is the search index stale?
SELECT 
  name,
  target_lag,
  last_index_update_ts,
  CURRENT_TIMESTAMP() as now,
  DATEDIFF(minute, last_index_update_ts, now) as minutes_since_update,
  CASE 
    WHEN target_lag = 'NEVER' THEN 'Never refreshes (OK if intended)'
    WHEN target_lag = '1 minute' AND minutes_since_update > 2 THEN 'LATE - Behind 1-minute target'
    WHEN target_lag = '1 hour' AND minutes_since_update > 90 THEN 'LATE - Behind 1-hour target'
    WHEN target_lag = '24 hours' AND minutes_since_update > 1440 THEN 'LATE - Behind 24-hour target'
    ELSE 'OK'
  END as freshness_status
FROM ACCOUNT_USAGE.CORTEX_SEARCH_SERVICES
ORDER BY minutes_since_update DESC;

-- If LATE:
-- - Check warehouse availability (suspended or down?)
-- - Check if source table has significant updates
-- - Consider increasing warehouse size or reducing target_lag requirement
```

### High Cost: Identify Expensive Services

```sql
-- Which services are costing the most? (by target_lag)
SELECT 
  name,
  target_lag,
  cumulative_credits_used,
  ROUND(cumulative_credits_used * 2, 2) as estimated_cost_usd,
  CASE target_lag
    WHEN '1 minute' THEN 'Very High'
    WHEN '5 minutes' THEN 'High'
    WHEN '1 hour' THEN 'Medium'
    WHEN '24 hours' THEN 'Low'
    WHEN 'NEVER' THEN 'Minimal'
    ELSE 'Other'
  END as cost_level,
  'Consider increasing target_lag or using smaller columns' as optimization_suggestion
FROM ACCOUNT_USAGE.CORTEX_SEARCH_SERVICES
ORDER BY cumulative_credits_used DESC;
```

---

## Setting Up Ongoing Monitoring

### Create a Monitoring Table (Optional)

```sql
-- Store daily metrics for trend analysis
CREATE TABLE IF NOT EXISTS monitoring.cortex_search.daily_metrics (
  captured_date DATE,
  service_name VARCHAR,
  state VARCHAR,
  indexing_progress_pct FLOAT,
  cumulative_credits_used FLOAT,
  rate_limit_violations INT,
  concurrency_violations INT,
  resource_violations INT,
  PRIMARY KEY (captured_date, service_name)
);

-- Populate daily via task
CREATE OR REPLACE TASK monitoring.cortex_search.collect_metrics
  WAREHOUSE = admin_wh
  SCHEDULE = 'USING CRON 0 1 * * * America/Los_Angeles'  -- Run at 1 AM daily
AS
INSERT INTO monitoring.cortex_search.daily_metrics
SELECT 
  CURRENT_DATE(),
  s.name,
  s.state,
  s.indexing_progress_pct,
  s.cumulative_credits_used,
  COALESCE(g1.violation_count, 0),
  COALESCE(g2.violation_count, 0),
  COALESCE(g3.violation_count, 0)
FROM ACCOUNT_USAGE.CORTEX_SEARCH_SERVICES s
LEFT JOIN (
  SELECT service_name, COUNT(*) as violation_count
  FROM CORTEX_AI_GUARDRAILS_USAGE_HISTORY
  WHERE violation_date = CURRENT_DATE() - 1 AND violation_type = 'RATE_LIMIT'
  GROUP BY service_name
) g1 ON s.name = g1.service_name
LEFT JOIN (
  SELECT service_name, COUNT(*) as violation_count
  FROM CORTEX_AI_GUARDRAILS_USAGE_HISTORY
  WHERE violation_date = CURRENT_DATE() - 1 AND violation_type = 'CONCURRENCY_LIMIT'
  GROUP BY service_name
) g2 ON s.name = g2.service_name
LEFT JOIN (
  SELECT service_name, COUNT(*) as violation_count
  FROM CORTEX_AI_GUARDRAILS_USAGE_HISTORY
  WHERE violation_date = CURRENT_DATE() - 1 AND violation_type IN ('RESOURCE_CONSTRAINT', 'MEMORY_LIMIT', 'CPU_LIMIT')
  GROUP BY service_name
) g3 ON s.name = g3.service_name;

ALTER TASK monitoring.cortex_search.collect_metrics RESUME;
```

### Query Trends

```sql
-- Weekly trend: Are violations getting worse?
SELECT 
  DATE_TRUNC('week', captured_date) as week,
  service_name,
  AVG(cumulative_credits_used) as avg_credits_used,
  SUM(rate_limit_violations) as weekly_rate_limit_violations,
  SUM(concurrency_violations) as weekly_concurrency_violations,
  SUM(resource_violations) as weekly_resource_violations
FROM monitoring.cortex_search.daily_metrics
WHERE captured_date >= CURRENT_DATE() - INTERVAL '30 days'
GROUP BY week, service_name
ORDER BY week DESC;
```

---

## Actionable Recommendations

| Finding | Root Cause | Action |
|---------|-----------|--------|
| Service in INDEXING >4h | Table too large or warehouse too small | Increase warehouse size; see css-setup |
| Rate limit violations | Too many concurrent queries | Reduce concurrency; implement request queuing |
| High cost ($100+/month) | Frequent refreshes or large table | Increase target_lag; reduce indexed columns; see css-setup |
| Index falls behind target_lag | Warehouse suspended or busy | Enable AUTO_RESUME; consider dedicated warehouse |
| Concurrency violations | Peak usage times | Implement request throttling; increase budget limits |

---

## Support and Related Skills

For more information:
- `$cortex-search-lifecycle:css-setup` — Configure service freshness and warehouse
- `$cortex-search-lifecycle:css-budgets` — Set budget limits and enforcement
- `$cost-intelligence` — Track search costs with other Cortex services
- `$cortex-agent-toolkit` — Query search results with agents

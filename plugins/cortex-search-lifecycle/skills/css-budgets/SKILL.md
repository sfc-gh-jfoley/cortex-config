---
name: css-budgets
description: >
  Manage Cortex Search Service budgets and resource governance. Set monthly credit limits,
  configure enforcement actions (revoke/suspend, alert, webhook), track budget consumption.
  GA as of Jul 3, 2026. Use when preventing runaway search costs or enforcing spend limits.
triggers:
  - search service budgets
  - css budgets
  - search budgets
  - cortex search budgets
  - resource budgets
  - search spending limits
  - credit limits
  - budget enforcement
  - search cost control
---

# CSS Budgets: Manage Search Service Budgets

Complete workflow for setting monthly credit limits and automating budget enforcement for Cortex Search Services (GA Jul 3, 2026).

---

## When to Use This Sub-Skill

Use **css-budgets** when:
- Setting monthly credit limits per search service
- Preventing runaway search costs
- Automating budget enforcement actions (suspend, alert, webhook)
- Tracking search spending against budgets
- Managing cost governance across multiple search services

**Do NOT use this sub-skill for:**
- Creating search services (use `$cortex-search-lifecycle:css-setup`)
- Monitoring guardrails violations (use `$cortex-search-lifecycle:css-monitor`)
- Querying search results (use agents or cortex_search_result())

---

## Quick Start: Set a Monthly Budget in 3 Steps

### Step 1: Calculate Your Budget

```sql
-- Estimate: How much do you want to spend per month on search services?
-- Example: $100/month budget, with search credits at $2/credit

-- $100 per month = 50 credits (assuming $2/credit)
-- Budget: 50 credits

-- Cost breakdown:
-- - High freshness (target_lag = 1 hour): ~$20-50/month per service
-- - Medium freshness (target_lag = 4 hours): ~$5-20/month per service
-- - Low freshness (target_lag = 24 hours): ~$1-5/month per service

-- You can set different budgets for different services
-- Service A (real-time): 30 credits/month ($60)
-- Service B (daily): 10 credits/month ($20)
-- Service C (archives): 5 credits/month ($10)
-- TOTAL: 45 credits/month ($90)
```

### Step 2: Create Resource Budget

```sql
-- Create a named budget with monthly credit limit
CREATE RESOURCE BUDGET product_search_budget
  MONTHLY_LIMIT = 50  -- 50 credits = $100 at $2/credit
  ON CORTEX_SEARCH_SERVICES;

-- You can create multiple budgets for different services
CREATE RESOURCE BUDGET support_tickets_budget
  MONTHLY_LIMIT = 100  -- Real-time support data = higher cost
  ON CORTEX_SEARCH_SERVICES;

CREATE RESOURCE BUDGET archives_budget
  MONTHLY_LIMIT = 10  -- Static archives = low cost
  ON CORTEX_SEARCH_SERVICES;
```

### Step 3: Attach Budget to Service and Set Enforcement

```sql
-- Attach budget to search service with enforcement action
ALTER CORTEX SEARCH SERVICE product_search
SET RESOURCE_BUDGET = 'product_search_budget'
    ENFORCEMENT_ACTION = 'REVOKE';  -- Suspend service if budget exceeded

-- Or use NOTIFY (alert only, don't suspend)
ALTER CORTEX SEARCH SERVICE support_tickets_search
SET RESOURCE_BUDGET = 'support_tickets_budget'
    ENFORCEMENT_ACTION = 'NOTIFY';  -- Alert but keep service running

-- Or use WEBHOOK (custom action via webhook)
ALTER CORTEX SEARCH SERVICE archives_search
SET RESOURCE_BUDGET = 'archives_budget'
    ENFORCEMENT_ACTION = 'WEBHOOK'
    WEBHOOK_URL = 'https://your-webhook-endpoint.com/budget-alert';
```

---

## Resource Budget DDL Reference

### CREATE RESOURCE BUDGET Syntax

```sql
CREATE [OR REPLACE] RESOURCE BUDGET <budget_name>
  MONTHLY_LIMIT = <credit_limit>
  ON CORTEX_SEARCH_SERVICES
  [COMMENT = 'description'];
```

### ALTER CORTEX SEARCH SERVICE with Budget

```sql
ALTER CORTEX SEARCH SERVICE <service_name>
SET RESOURCE_BUDGET = '<budget_name>'
    ENFORCEMENT_ACTION = 'REVOKE' | 'NOTIFY' | 'WEBHOOK'
    [WEBHOOK_URL = 'https://...']  -- Required if ENFORCEMENT_ACTION = 'WEBHOOK'
    [WEBHOOK_HEADERS = '...']       -- Optional: custom headers
    [WEBHOOK_BODY = '...'];         -- Optional: custom payload
```

### Parameters

| Parameter | Required | Options | Description |
|-----------|----------|---------|-------------|
| `budget_name` | Yes | String | Unique name for budget |
| `MONTHLY_LIMIT` | Yes | Integer | Credit limit per month (1-1000000) |
| `ENFORCEMENT_ACTION` | Yes | REVOKE, NOTIFY, WEBHOOK | Action when limit exceeded |
| `WEBHOOK_URL` | Conditional | URL | Endpoint for WEBHOOK action |
| `service_name` | Yes | String | Target search service name |

### Enforcement Actions

| Action | Behavior | Use Case |
|--------|----------|----------|
| `REVOKE` | Suspend service (stop new searches) | Strict cost control |
| `NOTIFY` | Alert via email/webhook, keep running | Soft limit, monitoring |
| `WEBHOOK` | POST to custom endpoint | Integration with billing system |

---

## Complete Examples

### Example 1: Strict Budget (Suspend on Overspend)

```sql
-- Create budget: $100/month max (50 credits)
CREATE RESOURCE BUDGET products_strict_budget
  MONTHLY_LIMIT = 50
  COMMENT = 'Product search: $100 max per month. Auto-suspend if exceeded.';

-- Attach to service with REVOKE (strict enforcement)
ALTER CORTEX SEARCH SERVICE product_search
SET RESOURCE_BUDGET = 'products_strict_budget'
    ENFORCEMENT_ACTION = 'REVOKE';

-- Behavior: When monthly spend hits 50 credits, service is suspended
-- Users will see: "Service suspended due to budget limit"
-- Admin must manually resume: ALTER CORTEX SEARCH SERVICE product_search SET STATE = 'RUNNING'
```

### Example 2: Soft Budget (Alert Only)

```sql
-- Create budget: $500/month with alerts only
CREATE RESOURCE BUDGET company_search_budget
  MONTHLY_LIMIT = 250  -- 250 credits = $500
  COMMENT = 'All search services combined budget with alerts.';

-- Attach with NOTIFY (soft limit)
ALTER CORTEX SEARCH SERVICE product_search
SET RESOURCE_BUDGET = 'company_search_budget'
    ENFORCEMENT_ACTION = 'NOTIFY';

-- Behavior: Alerts sent when budget exceeded, but service keeps running
-- Owners can investigate and adjust if needed
```

### Example 3: Multiple Services with Separate Budgets

```sql
-- Scenario: 3 search services, each with own budget

-- Service 1: Real-time support tickets ($100/month)
CREATE RESOURCE BUDGET support_budget MONTHLY_LIMIT = 50 ON CORTEX_SEARCH_SERVICES;
ALTER CORTEX SEARCH SERVICE support_tickets_search
SET RESOURCE_BUDGET = 'support_budget'
    ENFORCEMENT_ACTION = 'REVOKE';

-- Service 2: Product catalog ($30/month)
CREATE RESOURCE BUDGET products_budget MONTHLY_LIMIT = 15 ON CORTEX_SEARCH_SERVICES;
ALTER CORTEX SEARCH SERVICE products_search
SET RESOURCE_BUDGET = 'products_budget'
    ENFORCEMENT_ACTION = 'REVOKE';

-- Service 3: Archives ($10/month)
CREATE RESOURCE BUDGET archives_budget MONTHLY_LIMIT = 5 ON CORTEX_SEARCH_SERVICES;
ALTER CORTEX SEARCH SERVICE archives_search
SET RESOURCE_BUDGET = 'archives_budget'
    ENFORCEMENT_ACTION = 'NOTIFY';
```

### Example 4: Custom Webhook for Billing Integration

```sql
-- Create budget
CREATE RESOURCE BUDGET webhook_budget
  MONTHLY_LIMIT = 100
  COMMENT = 'Send budget alerts to billing system webhook.';

-- Attach with WEBHOOK action
ALTER CORTEX SEARCH SERVICE product_search
SET RESOURCE_BUDGET = 'webhook_budget'
    ENFORCEMENT_ACTION = 'WEBHOOK'
    WEBHOOK_URL = 'https://billing.example.com/cortex-search-alerts'
    WEBHOOK_HEADERS = '{"Authorization": "Bearer secret_token", "Content-Type": "application/json"}'
    WEBHOOK_BODY = '{"service_name": "product_search", "credits_used": <credits>, "monthly_limit": 100, "alert_type": "budget_exceeded"}';

-- Webhook fires when service hits 100 credits
-- Billing system receives alert and can trigger downstream actions
```

---

## Monitoring Budget Consumption

### View Budget Status

```sql
-- Check all budgets and their consumption
SELECT 
  budget_name,
  monthly_limit,
  monthly_credits_used,
  ROUND(100.0 * monthly_credits_used / monthly_limit, 1) as pct_of_limit,
  CASE 
    WHEN monthly_credits_used >= monthly_limit THEN 'EXCEEDED'
    WHEN monthly_credits_used >= 0.9 * monthly_limit THEN 'WARNING (>90%)'
    ELSE 'OK'
  END as status,
  month,
  last_updated_at
FROM ACCOUNT_USAGE.CORTEX_SEARCH_SERVICE_BUDGETS
ORDER BY pct_of_limit DESC;
```

### Track Spending by Service

```sql
-- See which search services are using the most credits
SELECT 
  name as service_name,
  cumulative_credits_used,
  DATEDIFF(day, created_on, CURRENT_TIMESTAMP()) as days_deployed,
  ROUND(cumulative_credits_used / DATEDIFF(day, created_on, CURRENT_TIMESTAMP()), 2) as avg_credits_per_day,
  ROUND(avg_credits_per_day * 30, 2) as projected_monthly_credits
FROM ACCOUNT_USAGE.CORTEX_SEARCH_SERVICES
ORDER BY cumulative_credits_used DESC;
```

### Budget Alerts and Enforcement History

```sql
-- Check if any services have been suspended due to budget limits
SELECT 
  service_name,
  budget_name,
  enforcement_action,
  action_triggered_at,
  credits_used_at_trigger,
  monthly_limit
FROM ACCOUNT_USAGE.CORTEX_SEARCH_SERVICE_BUDGET_ENFORCEMENT
WHERE action_triggered_at >= CURRENT_DATE() - INTERVAL '30 days'
ORDER BY action_triggered_at DESC;
```

---

## Best Practices

### 1. Set Realistic Budgets

**DO:**
- Base budgets on actual usage or cost targets
- Start conservative, adjust upward if needed
- Use NOTIFY for initial limits, upgrade to REVOKE once you understand spending

```sql
-- Start with soft limit to learn actual costs
CREATE RESOURCE BUDGET products_soft MONTHLY_LIMIT = 100 ON CORTEX_SEARCH_SERVICES;
ALTER CORTEX SEARCH SERVICE product_search
SET RESOURCE_BUDGET = 'products_soft' ENFORCEMENT_ACTION = 'NOTIFY';

-- Monitor for a month, then tighten if safe
-- ALTER RESOURCE BUDGET products_soft SET MONTHLY_LIMIT = 50;
```

**DON'T:**
- Set unrealistic limits (too low = frequent suspensions)
- Use REVOKE without understanding your workload first
- Forget to monitor budget consumption

### 2. Tiered Budgets by Freshness

```sql
-- Real-time services: higher budget
CREATE RESOURCE BUDGET realtime_budget MONTHLY_LIMIT = 200 ON CORTEX_SEARCH_SERVICES;

-- Regular services: medium budget
CREATE RESOURCE BUDGET regular_budget MONTHLY_LIMIT = 50 ON CORTEX_SEARCH_SERVICES;

-- Archives: low budget
CREATE RESOURCE BUDGET archive_budget MONTHLY_LIMIT = 10 ON CORTEX_SEARCH_SERVICES;

-- Attach each to corresponding service based on target_lag
```

### 3. Coordinate with Accounting

```sql
-- Work with finance to set budgets
-- Factors to consider:
-- - Search freshness requirements (target_lag)
-- - Table size and update frequency
-- - Number of concurrent users
-- - Acceptable cost per month

-- Example calculation:
-- - Small table, hourly refresh: ~$5/month
-- - Medium table, hourly refresh: ~$20/month
-- - Large table, real-time refresh: ~$100-500/month
```

---

## Troubleshooting

| Problem | Cause | Solution |
|---------|-------|----------|
| "CREATE RESOURCE BUDGET not allowed" | Missing privilege | GRANT CREATE RESOURCE BUDGET ON ACCOUNT to role |
| "Service suspended unexpectedly" | Budget limit exceeded | Check ACCOUNT_USAGE.CORTEX_SEARCH_SERVICE_BUDGETS; increase limit or disable REVOKE |
| "Webhook not firing" | Invalid URL or headers | Test webhook manually; check WEBHOOK_URL and headers syntax |
| "Budget shows $0 spent" | Service just created or very new | Wait 24 hours for metrics to populate |
| "Can't find budget in system" | Budget not attached to service | Confirm budget name and use ALTER CORTEX SEARCH SERVICE to attach |

---

## After Budgets: Next Steps

1. **Monitor daily consumption** — Set up alerting for high spend
   - See `$cortex-search-lifecycle:css-monitor` for query patterns

2. **Optimize search costs** — Adjust target_lag or columns if over budget
   - See `$cortex-search-lifecycle:css-setup` for configuration options

3. **Track trends** — Compare monthly spend to budget over time
   - Use ACCOUNT_USAGE.CORTEX_SEARCH_SERVICE_BUDGETS for reports

4. **Adjust budgets seasonally** — Increase during busy periods, decrease during slow times
   - Use ALTER RESOURCE BUDGET to update limits

---

## Support and Related Skills

For more information:
- `$cortex-search-lifecycle:css-setup` — Configure search service freshness
- `$cortex-search-lifecycle:css-monitor` — Monitor usage and guardrails
- `$cost-intelligence` — Track search costs alongside other Snowflake services

# Cortex Search Service (CSS) Lifecycle Plugin

Complete workflow for creating, managing, and monitoring Snowflake Cortex Search Services. This plugin provides three sub-skills covering the full CSS lifecycle from setup through budget enforcement to operational monitoring.

## Three Sub-Skills

### 1. **css-setup**: Create and Configure Search Services

DDL patterns for CREATE CORTEX SEARCH SERVICE with warehouse selection, target_lag configuration, and source table setup best practices.

**Use when:**
- Setting up semantic search for the first time
- Creating a search service for a new table
- Configuring index freshness (target_lag: 1 min to 24 hours)
- Selecting columns to index

**Key topics:**
- CREATE CORTEX SEARCH SERVICE syntax and required parameters
- Warehouse sizing for search index computation
- target_lag tradeoffs: freshness vs. resource usage
- Column selection best practices
- GA feature availability (Jul 2, 2026)

---

### 2. **css-budgets**: Manage Search Service Budgets

Resource budgets for Cortex Search Services (GA Jul 3, 2026). Set monthly credit limits and automate enforcement actions.

**Use when:**
- Setting monthly credit limits per search service
- Preventing runaway search costs
- Automating budget enforcement (revoke, notify, or webhook)
- Tracking search spending against budgets

**Key topics:**
- CREATE/ALTER RESOURCE BUDGET syntax
- Monthly credit limits per service
- Enforcement actions: REVOKE (suspend), NOTIFY (alert), or webhook
- Budget consumption tracking
- Cost governance and resource quotas

---

### 3. **css-monitor**: Monitor Service Health and Guardrails

ACCOUNT_USAGE queries for Cortex Search Services and CORTEX_AI_GUARDRAILS_USAGE_HISTORY view (GA Jun 16, 2026) for compliance and performance analysis.

**Use when:**
- Checking search service status and usage
- Analyzing guardrails violations (rate limiting, resource constraints)
- Investigating search performance issues
- Monitoring index freshness and cache hit rates

**Key topics:**
- ACCOUNT_USAGE.CORTEX_SEARCH_SERVICES: service status, indexing progress, credit usage
- CORTEX_AI_GUARDRAILS_USAGE_HISTORY: rate limits, concurrency limits, resource violations
- Health check queries
- Performance troubleshooting
- Cost estimation from usage patterns

---

## Example Workflows

### Setup: Create a Search Service for Product Descriptions

```sql
-- Select source table with searchable content
SELECT * FROM products WHERE product_id IS NOT NULL LIMIT 100;

-- Check table size and columns
SELECT 
  COUNT(*) as row_count,
  DATALENGTH(product_description) as avg_content_size
FROM products;

-- Create search service with 4-hour target_lag
CREATE CORTEX SEARCH SERVICE product_search ON products(product_id, product_description)
  WAREHOUSE = compute_wh
  TARGET_LAG = '4 hours';

-- Service is ready when state = READY
SELECT name, state, indexing_progress_pct FROM ACCOUNT_USAGE.CORTEX_SEARCH_SERVICES 
WHERE name = 'product_search';
```

### Budgets: Enforce $100/month Credit Limit

```sql
-- Create resource budget: $100 max per month (assume $2/credit)
CREATE RESOURCE BUDGET product_search_budget
  MONTHLY_LIMIT = 50  -- 50 credits = $100 at $2/credit
  ON CORTEX_SEARCH_SERVICES;

-- Attach budget to service: auto-suspend if limit exceeded
ALTER CORTEX SEARCH SERVICE product_search 
SET RESOURCE_BUDGET = 'product_search_budget'
    ENFORCEMENT_ACTION = 'REVOKE';  -- suspend service on overspend

-- Track consumption
SELECT 
  service_name,
  budget_name,
  monthly_credits_used,
  monthly_limit,
  ROUND(100.0 * monthly_credits_used / monthly_limit, 1) as pct_used
FROM ACCOUNT_USAGE.CORTEX_SEARCH_SERVICE_BUDGETS
WHERE month = CURRENT_DATE::DATE;
```

### Monitor: Check Service Health and Guardrails

```sql
-- Service health: state, indexing progress, last update
SELECT 
  name,
  state,
  indexing_progress_pct,
  created_on,
  last_index_update_ts,
  cumulative_credits_used,
  DATEDIFF(hour, last_index_update_ts, CURRENT_TIMESTAMP()) as hours_since_last_index
FROM ACCOUNT_USAGE.CORTEX_SEARCH_SERVICES
WHERE name = 'product_search';

-- Guardrails violations: rate limits, concurrency, resource constraints
SELECT 
  service_name,
  violation_type,  -- 'RATE_LIMIT', 'CONCURRENCY_LIMIT', 'RESOURCE_CONSTRAINT'
  violation_count,
  first_violation_time,
  last_violation_time,
  ROUND(violation_count::FLOAT / DATEDIFF(hour, first_violation_time, last_violation_time), 2) as violations_per_hour
FROM CORTEX_AI_GUARDRAILS_USAGE_HISTORY
WHERE service_name = 'product_search'
  AND violation_date >= CURRENT_DATE() - INTERVAL '7 days'
GROUP BY service_name, violation_type
ORDER BY violation_count DESC;

-- Cost estimation: credits used + projected monthly spend
SELECT 
  name,
  cumulative_credits_used,
  DATEDIFF(day, created_on, CURRENT_TIMESTAMP()) as days_deployed,
  ROUND(cumulative_credits_used / DATEDIFF(day, created_on, CURRENT_TIMESTAMP()) * 30, 2) as projected_monthly_credits,
  ROUND(projected_monthly_credits * 2, 2) as projected_monthly_cost_usd
FROM ACCOUNT_USAGE.CORTEX_SEARCH_SERVICES
WHERE name = 'product_search';
```

---

## Common Issues and Remediation

| Issue | Cause | Solution |
|-------|-------|----------|
| Service stuck in INDEXING | Large table or slow warehouse | Use css-setup: increase warehouse size or lower target_lag |
| Rate limit violations | Too many concurrent queries | Use css-monitor: check query volume; use css-budgets to enforce limits |
| Index not fresh | target_lag exceeded | Use css-monitor: check warehouse availability; increase compute or reduce target_lag |
| Budget exceeded unexpectedly | Expensive queries or unoptimized indexing | Use css-monitor: analyze query patterns; use css-budgets: adjust limits or enforcement action |
| Service in FAILED state | DDL error or resource exhaustion | Use css-setup: check CREATE statement syntax; see activation.md for prerequisites |

---

## Prerequisites Checklist

- [ ] Account has Cortex Search Service enabled (GA Jul 2, 2026)
- [ ] Source table exists with VARCHAR/STRING/TEXT columns
- [ ] Warehouse available and has sufficient compute
- [ ] Role has `CREATE CORTEX SEARCH SERVICE` privilege
- [ ] For budgets: Role has `CREATE RESOURCE BUDGET` privilege
- [ ] For monitoring: Account has `MONITOR` grant (ACCOUNT_USAGE access)
- [ ] For guardrails: CORTEX_AI_GUARDRAILS_USAGE_HISTORY is available (GA Jun 16, 2026)

See `PREREQUISITES.md` for detailed setup and permission configuration.

---

## Positioning in the Skill Ecosystem

**Input sources:**
- `$semantic-view-toolkit` — structured data to index
- `$data-governance` — classify columns for search inclusion

**Output consumers:**
- `$cortex-agent-toolkit` — agents query search results
- `$cowork` — investigations use search results
- `$sql-author` — SQL queries on search endpoints

**Related skills:**
- `cost-intelligence` — track search spending alongside other services
- `workload-performance-analysis` — analyze query performance
- `data-quality` — monitor search index quality

---

## Entry Points

**Via skill-loader:**
```bash
$cortex-search-lifecycle
# Router prompts for sub-skill: setup, budgets, or monitor
```

**Direct sub-skill:**
```bash
$cortex-search-lifecycle:css-setup
$cortex-search-lifecycle:css-budgets
$cortex-search-lifecycle:css-monitor
```

---

## Support

For detailed workflows, see the three sub-skill files:
- `skills/css-setup/SKILL.md`
- `skills/css-budgets/SKILL.md`
- `skills/css-monitor/SKILL.md`

For prerequisites and permission setup, see `PREREQUISITES.md`.

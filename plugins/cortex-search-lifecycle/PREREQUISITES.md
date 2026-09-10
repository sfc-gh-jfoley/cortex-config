# Cortex Search Service (CSS) Lifecycle Plugin — Prerequisites

Complete setup checklist and permission requirements for Cortex Search Service lifecycle management.

---

## Account-Level Setup

### 1. Verify Cortex Search Service is Available

Check your account's Cortex Search Service status:

```sql
-- Check if CSS is enabled in your account
SELECT SYSTEM$CORTEX_SEARCH_SERVICE_STATUS();
-- Output: enabled, region-available, or disabled

-- Verify GA dates
SELECT CURRENT_TIMESTAMP() as now, '2026-07-02'::TIMESTAMP as css_ga_date;
-- CSS is GA if current_timestamp >= 2026-07-02

-- Check which features are available
SELECT 
  'CORTEX_SEARCH_SERVICES' as feature,
  SYSTEM$FEATURE_FLAG('CORTEX_SEARCH_SERVICES_ENABLED') as enabled
UNION ALL
SELECT
  'CORTEX_AI_GUARDRAILS_TRACKING',
  SYSTEM$FEATURE_FLAG('CORTEX_AI_GUARDRAILS_TRACKING_ENABLED');
```

### 2. Check Your Deployment Region

Cortex Search Services are GA in all regions, but verify your region is supported:

```sql
SELECT 
  CURRENT_REGION() as current_region,
  CURRENT_ACCOUNT() as account_name,
  CURRENT_DATABASE() as default_db;
-- All regions supported; no region gating for CSS
```

---

## Role and Privilege Setup

### 3. Grant Privileges for CSS Setup

Role privileges needed to create search services:

```sql
-- As ACCOUNTADMIN or role with GRANT privileges:

-- Grant CREATE CORTEX SEARCH SERVICE privilege
GRANT CREATE CORTEX SEARCH SERVICE ON SCHEMA <schema_name> TO ROLE <role_name>;

-- Grant USAGE on warehouse where search index will run
GRANT USAGE ON WAREHOUSE <warehouse_name> TO ROLE <role_name>;

-- Grant USAGE on database/schema containing source table
GRANT USAGE ON DATABASE <db_name> TO ROLE <role_name>;
GRANT USAGE ON SCHEMA <db_name>.<schema_name> TO ROLE <role_name>;

-- Grant SELECT on source table (to read data for indexing)
GRANT SELECT ON TABLE <db_name>.<schema_name>.<table_name> TO ROLE <role_name>;

-- Example: Grant all required privileges to DATA_ENGINEER role
GRANT CREATE CORTEX SEARCH SERVICE ON SCHEMA analytics.search TO ROLE DATA_ENGINEER;
GRANT USAGE ON WAREHOUSE compute_wh TO ROLE DATA_ENGINEER;
GRANT USAGE ON DATABASE analytics TO ROLE DATA_ENGINEER;
GRANT USAGE ON SCHEMA analytics.search TO ROLE DATA_ENGINEER;
GRANT SELECT ON ALL TABLES IN SCHEMA analytics.search TO ROLE DATA_ENGINEER;
```

### 4. Grant Privileges for CSS Budgets

Role privileges needed to create and manage budgets:

```sql
-- As ACCOUNTADMIN:

-- Grant CREATE SNOWFLAKE.CORE.BUDGET (account-level)
GRANT CREATE SNOWFLAKE.CORE.BUDGET ON SCHEMA <budget_schema> TO ROLE <role_name>;

-- Grant USAGE on budget schema
GRANT USAGE ON DATABASE <budget_db> TO ROLE <role_name>;
GRANT USAGE ON SCHEMA <budget_db>.<budget_schema> TO ROLE <role_name>;

-- Example: Grant budget management to ADMIN role
GRANT CREATE SNOWFLAKE.CORE.BUDGET ON SCHEMA budgets_db.budgets_schema TO ROLE ADMIN;
GRANT USAGE ON DATABASE budgets_db TO ROLE ADMIN;
GRANT USAGE ON SCHEMA budgets_db.budgets_schema TO ROLE ADMIN;
```

### 5. Grant Privileges for CSS Monitor

Role privileges needed to monitor search services and guardrails:

```sql
-- As ACCOUNTADMIN:

-- Grant MONITOR (read ACCOUNT_USAGE views)
GRANT MONITOR ON ACCOUNT TO ROLE <role_name>;

-- Grant SELECT on ACCOUNT_USAGE schema
GRANT SELECT ON ALL VIEWS IN DATABASE snowflake.account_usage TO ROLE <role_name>;

-- Example: Grant monitoring to ANALYST role
GRANT MONITOR ON ACCOUNT TO ROLE ANALYST;
GRANT SELECT ON ALL VIEWS IN DATABASE snowflake.account_usage TO ROLE ANALYST;
```

---

## Source Table Setup

### 6. Prepare Source Table for Search Indexing

Source table requirements:

- **Columns**: At least one VARCHAR, STRING, or TEXT column for semantic search
- **Size**: No hard limit, but larger tables = longer indexing + higher compute
- **Data quality**: Optional, but recommended to filter NULL/empty values
- **Access**: Service must have SELECT privilege on table

Example: Prepare a products table for search indexing

```sql
-- Create source table if not exists
CREATE TABLE IF NOT EXISTS analytics.search.products (
  product_id INT PRIMARY KEY,
  product_name VARCHAR,
  product_description VARCHAR,  -- This will be indexed for search
  category VARCHAR,
  price FLOAT,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
);

-- Insert sample data
INSERT INTO analytics.search.products VALUES
  (1, 'Widget A', 'High-quality widget for industrial use', 'Widgets', 99.99, CURRENT_TIMESTAMP()),
  (2, 'Gadget B', 'Portable gadget for everyday tasks', 'Gadgets', 49.99, CURRENT_TIMESTAMP());

-- Verify table is ready
SELECT COUNT(*) as row_count FROM analytics.search.products;
SELECT DATALENGTH(product_description) as avg_desc_size FROM analytics.search.products;
```

### 7. Select Columns for Search Indexing

CSS requires explicit column selection (unlike some search engines):

```sql
-- Recommended: 1-3 relevant columns for semantic search
-- Bad: Indexing too many columns = slower indexing, higher cost
-- Bad: Indexing non-text columns (CSS is text-based)

-- GOOD: Index only product_description (most relevant for search)
-- CREATE CORTEX SEARCH SERVICE product_search ON products(product_description)

-- ALSO GOOD: Index description + name
-- CREATE CORTEX SEARCH SERVICE product_search ON products(product_name, product_description)

-- BAD: Don't index numeric or date columns unless cast to VARCHAR
-- CREATE CORTEX SEARCH SERVICE product_search ON products(product_id, price, created_at)

-- BAD: Don't index too many columns
-- CREATE CORTEX SEARCH SERVICE product_search ON products(product_name, product_description, category, ...)
```

---

## Warehouse Setup

### 8. Prepare Warehouse for Search Index Computation

Warehouse requirements and recommendations:

```sql
-- Create or verify a warehouse for search indexing (separate from query warehouse recommended)
CREATE WAREHOUSE IF NOT EXISTS search_index_wh
  WAREHOUSE_SIZE = MEDIUM
  AUTO_SUSPEND = 60
  AUTO_RESUME = TRUE;

-- For large tables (>10M rows), use LARGE or XL
-- For small tables (<100K rows), use SMALL

-- Size guide:
-- SMALL (1 credit/min): <100K rows, test tables
-- MEDIUM (2 credits/min): 100K-10M rows, typical production
-- LARGE (4 credits/min): 10M-100M rows
-- XL (8 credits/min): >100M rows or very wide tables

-- Grant warehouse access to search role
GRANT USAGE ON WAREHOUSE search_index_wh TO ROLE DATA_ENGINEER;
```

### 9. Understand target_lag

`target_lag` controls how fresh your search index is:

```
target_lag = '1 minute'   -> Refresh every 1 min (high cost, always fresh)
target_lag = '1 hour'     -> Refresh every 1 hour (medium cost, reasonable freshness)
target_lag = '24 hours'   -> Refresh daily (low cost, good for static data)
```

**Recommended defaults:**
- Real-time chat/support data: `target_lag = '5 minutes'`
- Product catalogs: `target_lag = '1 hour'` or `'4 hours'`
- Historical archives: `target_lag = '24 hours'` or never-refresh

---

## Budget and Governance Setup (Optional)

### 10. Set Up Resource Budgets for CSS

If using css-budgets sub-skill, prepare budget configuration:

```sql
-- Create a budget: $100/month max (assume $2/credit = 50 credits)
CREATE SNOWFLAKE.CORE.BUDGET search_budget()
  SET MONTHLY_LIMIT = 50
  SET CURRENCY = 'USD';

-- Attach budget to search service via tag
ALTER CORTEX SEARCH SERVICE product_search 
SET TAG cortex_search_budget = 'search_budget';

-- View budget status
SELECT * FROM INFORMATION_SCHEMA.BUDGETS WHERE BUDGET_NAME = 'search_budget';
```

### 11. Cost Estimation

Before creating search service, estimate monthly cost:

```sql
-- Estimate: Large table = $50-200/month depending on index freshness
-- Formula: credits_per_day = (table_rows * avg_description_bytes) / 10_000_000
--          monthly_cost = credits_per_day * 30 * 2  (assume $2/credit)

-- For products table: 1M rows, avg 500 bytes per description
-- ~ 50 credits/day * $2 = $100/day for frequent refresh (1 hour target_lag)
-- ~ 5 credits/day * $2 = $10/day for daily refresh (24 hour target_lag)
```

---

## Monitoring Setup (Optional)

### 12. Prepare ACCOUNT_USAGE Access

For css-monitor sub-skill, ensure you have ACCOUNT_USAGE access:

```sql
-- Verify role has MONITOR privilege (read-only ACCOUNT_USAGE)
SHOW GRANTS TO ROLE <role_name>;
-- Look for: MONITOR | ON ACCOUNT

-- If not present, grant as ACCOUNTADMIN:
GRANT MONITOR ON ACCOUNT TO ROLE <role_name>;

-- Test access: Run a simple query
SELECT * FROM ACCOUNT_USAGE.CORTEX_SEARCH_SERVICES LIMIT 1;
```

### 13. Optional: Create Monitoring Dashboard

For ongoing health monitoring, create a dashboard database:

```sql
-- Create monitoring database (optional)
CREATE DATABASE IF NOT EXISTS monitoring;
CREATE SCHEMA IF NOT EXISTS monitoring.cortex_search;

-- Create table to store historical search service metrics
CREATE TABLE IF NOT EXISTS monitoring.cortex_search.service_metrics (
  captured_at TIMESTAMP,
  service_name VARCHAR,
  service_state VARCHAR,
  indexing_progress_pct FLOAT,
  cumulative_credits_used FLOAT,
  last_index_update_ts TIMESTAMP,
  PRIMARY KEY (captured_at, service_name)
);

-- Create materialized view to auto-populate metrics (optional, requires task)
-- See css-monitor SKILL.md for query patterns
```

---

## Pre-Flight Checklist

Before using any css-* sub-skill, verify:

- [ ] Account has Cortex Search Service GA (Jul 2, 2026 or later)
- [ ] Role has `CREATE CORTEX SEARCH SERVICE` privilege
- [ ] Source table exists with VARCHAR/STRING/TEXT columns
- [ ] Warehouse exists and has sufficient compute (SMALL to XL)
- [ ] Role has `USAGE` on warehouse
- [ ] Role has `SELECT` on source table
- [ ] For budgets: Role has `CREATE SNOWFLAKE.CORE.BUDGET` privilege
- [ ] For monitoring: Role has `MONITOR` privilege
- [ ] ACCOUNT_USAGE.CORTEX_SEARCH_SERVICES view is queryable
- [ ] CORTEX_AI_GUARDRAILS_USAGE_HISTORY view is available (GA Jun 16, 2026)

---

## Troubleshooting Setup Issues

| Issue | Check | Solution |
|-------|-------|----------|
| "CREATE CORTEX SEARCH SERVICE not allowed" | Privilege | Run Step 3: Grant CREATE CORTEX SEARCH SERVICE privilege |
| "Warehouse does not exist or not authorized" | Warehouse access | Run Step 8: GRANT USAGE ON WAREHOUSE |
| "Source table does not exist" | Table setup | Run Step 6: Create table with VARCHAR/STRING column |
| "ACCOUNT_USAGE views not accessible" | MONITOR grant | Run Step 5: GRANT MONITOR ON ACCOUNT |
| "Cortex Search Service GA not available" | Region/account | Check Step 2: Verify account and region support |

---

## Permissions Reference

**Minimal privilege set for css-setup:**
```sql
GRANT CREATE CORTEX SEARCH SERVICE ON SCHEMA analytics.search TO ROLE DATA_ENGINEER;
GRANT USAGE ON WAREHOUSE search_index_wh TO ROLE DATA_ENGINEER;
GRANT USAGE ON DATABASE analytics TO ROLE DATA_ENGINEER;
GRANT USAGE ON SCHEMA analytics.search TO ROLE DATA_ENGINEER;
GRANT SELECT ON TABLE analytics.search.products TO ROLE DATA_ENGINEER;
```

**Minimal privilege set for css-budgets:**
```sql
GRANT CREATE SNOWFLAKE.CORE.BUDGET ON SCHEMA <budget_schema> TO ROLE ADMIN;
GRANT ALTER ON CORTEX SEARCH SERVICE IN SCHEMA analytics.search TO ROLE ADMIN;
```

**Minimal privilege set for css-monitor:**
```sql
GRANT MONITOR ON ACCOUNT TO ROLE ANALYST;
GRANT SELECT ON ALL VIEWS IN DATABASE snowflake.account_usage TO ROLE ANALYST;
```

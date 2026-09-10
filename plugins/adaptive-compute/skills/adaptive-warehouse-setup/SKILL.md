---
name: adaptive-warehouse-setup
description: Create or convert warehouses to Adaptive type with Phase 0 region check, scaling configuration, and validation.
---

# Adaptive Warehouse Setup Sub-Skill

Set up Adaptive Warehouses end-to-end: from region validation through conversion or creation, scaling configuration, and validation.

## Overview

This sub-skill guides you through:
1. **Phase 0**: Verify AWS region (mandatory gate)
2. **Phase 1**: Create new Adaptive warehouse OR convert existing standard warehouse
3. **Phase 2**: Configure scaling limits and performance parameters
4. **Phase 3**: Validate configuration and confirm type=ADAPTIVE
5. **Phase 4**: Rollback guidance (if needed, convert back to standard)

---

## Phase 0: AWS Region Validation (Mandatory)

Before proceeding, the plugin performs this check automatically.

### Check: Cloud Provider
```sql
SELECT CURRENT_CLOUD() AS cloud;
```

**Expected output**: `AWS`

**If not AWS** (e.g., Azure or GCP):
```
❌ Adaptive Warehouses are AWS-only (as of Jun 16, 2024 GA).

Current deployment: <CLOUD>

Supported clouds: AWS (us-east-1, us-west-2, eu-west-1, ap-southeast-1, ap-southeast-2)

Next steps:
  • If on Azure/GCP: Use ops-monitor skill for standard warehouse optimization
  • If planning AWS migration: This plugin will be available after migration
```

### Check: Region Support
```sql
SELECT CURRENT_REGION() AS region;
```

**Expected output** (supported AWS region):
- `us-east-1` ✅
- `us-west-2` ✅
- `eu-west-1` ✅
- `ap-southeast-1` ✅
- `ap-southeast-2` ✅

**If unsupported AWS region**:
```
⚠️ Adaptive Warehouses are not yet available in your region: <REGION>

Supported AWS regions (as of Jun 16, 2024):
  ✅ us-east-1, us-west-2, eu-west-1, ap-southeast-1, ap-southeast-2

Next steps:
  1. Check for regional rollout: contact Snowflake support for timeline
  2. Or: migrate your Snowflake account to a supported region
  3. Or: use standard warehouse with ops-monitor skill for optimization
```

---

## Phase 1: Create or Convert Warehouse

Choose your path: create new Adaptive warehouse OR convert existing standard warehouse.

### Option 1a: Create New Adaptive Warehouse

```sql
-- Create new Adaptive warehouse
CREATE WAREHOUSE adaptive_wh
  TYPE = ADAPTIVE
  WAREHOUSE_SIZE = MEDIUM            -- Starting compute level (S, M, L, XL, etc.)
  MAX_QUERY_PERFORMANCE_LEVEL = 5    -- Maximum compute nodes
  QUERY_THROUGHPUT_MULTIPLIER = 10   -- Query parallelism multiplier
  AUTO_SUSPEND = 300                 -- Auto-suspend after 5 min idle (in seconds)
  AUTO_RESUME = true                 -- Auto-resume when query submitted
  INITIALLY_SUSPENDED = false;       -- Start in resumed state
```

**Parameters explained:**
- `TYPE = ADAPTIVE` — Defines warehouse as Adaptive (not Standard)
- `WAREHOUSE_SIZE = MEDIUM` — Starting compute level; Adaptive can scale down to 1 or up to MAX_QUERY_PERFORMANCE_LEVEL
- `MAX_QUERY_PERFORMANCE_LEVEL = 5` — Maximum number of compute nodes; adjust based on expected peak concurrency
- `QUERY_THROUGHPUT_MULTIPLIER = 10` — Controls query parallelism within each node
- `AUTO_SUSPEND = 300` — Suspend warehouse after 5 min idle (saves credits); adjust based on usage pattern
- `AUTO_RESUME = true` — Resume automatically when query submitted

### Option 1b: Convert Existing Standard Warehouse

```sql
-- First, verify warehouse is standard type and idle
SELECT NAME, TYPE, STATE
FROM SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSES
WHERE NAME = 'your_warehouse_name';
-- Should show: TYPE = STANDARD, STATE = SUSPENDED (or running but no active queries)

-- Suspend warehouse to ensure clean conversion
ALTER WAREHOUSE your_warehouse_name SUSPEND;

-- Wait 1 minute for active queries to complete
-- Then convert to Adaptive
ALTER WAREHOUSE your_warehouse_name
  TYPE = ADAPTIVE
  SET MAX_QUERY_PERFORMANCE_LEVEL = 5
  SET QUERY_THROUGHPUT_MULTIPLIER = 10
  SET AUTO_SUSPEND = 300
  SET AUTO_RESUME = true;
```

**Important: No data loss during conversion** — the warehouse retains all objects and permissions; only the scaling behavior changes.

---

## Phase 2: Configure Scaling Limits and Parameters

After creating or converting, fine-tune scaling behavior based on your workload.

### Set Max Compute (Peak Scaling Limit)

```sql
-- Determine max based on expected peak concurrency
-- Rough guide:
--   • Dev/test: MAX_QUERY_PERFORMANCE_LEVEL = 3–5
--   • Analytics: MAX_QUERY_PERFORMANCE_LEVEL = 8–10
--   • High-concurrency SaaS: MAX_QUERY_PERFORMANCE_LEVEL = 10–15

ALTER WAREHOUSE adaptive_wh
  SET MAX_QUERY_PERFORMANCE_LEVEL = 8;
```

**Factor**: If you expect 10 concurrent queries during peak, set MAX to 8–10 (1 node per query typically, with headroom).

### Set Query Throughput Multiplier

```sql
-- Controls query parallelism within each compute node
-- Higher = more parallelism = better for complex queries
-- Lower = simpler queries, less overhead

-- For complex analytical queries:
ALTER WAREHOUSE adaptive_wh
  SET QUERY_THROUGHPUT_MULTIPLIER = 15;

-- For simple queries:
ALTER WAREHOUSE adaptive_wh
  SET QUERY_THROUGHPUT_MULTIPLIER = 5;
```

### Set Auto-Suspend Idle Timeout

```sql
-- Choose idle timeout based on your pattern
-- 5 min (300 sec): aggressive cost savings, may suspend mid-session
-- 15 min (900 sec): balanced (recommended)
-- 60 min (3600 sec): very lenient, fewer suspend/resume cycles

ALTER WAREHOUSE adaptive_wh
  SET AUTO_SUSPEND = 900;  -- 15 min idle
```

### Set Auto-Resume Behavior

```sql
-- Auto-resume when new query submitted (recommended: true)
ALTER WAREHOUSE adaptive_wh
  SET AUTO_RESUME = true;

-- Or manual resume (requires admin action; not recommended for production):
ALTER WAREHOUSE adaptive_wh
  SET AUTO_RESUME = false;
```

---

## Phase 3: Validate Configuration

### Check Warehouse Type is Adaptive

```sql
SHOW WAREHOUSES LIKE 'adaptive_wh';
```

**Expected output**:
```
name             | type     | size   | state    | auto_suspend | auto_resume | ...
adaptive_wh      | ADAPTIVE | MEDIUM | RUNNING  | 300          | true        | ...
```

**Key columns to verify**:
- `type`: ADAPTIVE ✅
- `auto_suspend`: 300 (or your configured value)
- `auto_resume`: true ✅

### Verify Adaptive Properties

```sql
DESCRIBE WAREHOUSE adaptive_wh;
```

**Look for**:
- `TYPE = ADAPTIVE`
- `MAX_QUERY_PERFORMANCE_LEVEL = 5` (or your value)
- `QUERY_THROUGHPUT_MULTIPLIER = 10` (or your value)

### Test Warehouse with Simple Query

```sql
-- Use warehouse for a test query
USE WAREHOUSE adaptive_wh;

SELECT COUNT(*) FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY LIMIT 1;
```

**Expected**: Query completes successfully (warehouse auto-resumed if suspended).

### Check Scaling Events

```sql
-- After running some queries, observe if warehouse scaled
SELECT
  WAREHOUSE_NAME,
  START_TIME,
  END_TIME,
  CREDITS_USED_COMPUTE,
  CREDITS_USED,
  NUM_COMPUTE_NODES_REQUESTED
FROM SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY
WHERE WAREHOUSE_NAME = 'adaptive_wh'
ORDER BY START_TIME DESC
LIMIT 10;
```

**Expected**:
- `NUM_COMPUTE_NODES_REQUESTED` varies (e.g., 2 to 5 depending on query demand)
- `CREDITS_USED` varies based on compute nodes allocated

---

## Phase 4: Rollback Procedure (If Needed)

If you decide Adaptive isn't working for your workload, revert to standard in one command.

### Convert Back to Standard

```sql
-- Convert Adaptive → Standard
ALTER WAREHOUSE adaptive_wh
  TYPE = STANDARD
  SET WAREHOUSE_SIZE = MEDIUM;  -- Specify fixed size
```

**No data loss**: All warehouse objects, permissions, and data remain intact.

### When to Revert

Revert to standard if:
- **Costs increased** instead of decreased (workload is sustained, not variable)
- **Latency degraded** during peak (queries struggling with dynamic scaling)
- **Scaling overhead** is hurting performance (too many scale-up/down events)
- **Sustained high-concurrency** (not spiky; fixed warehouse is better)

### Verification After Revert

```sql
SHOW WAREHOUSES LIKE 'adaptive_wh';
-- TYPE column should show: STANDARD (not ADAPTIVE)
```

---

## Troubleshooting: Setup Issues

### Issue: "Warehouse type change failed"

**Cause**: Warehouse has active queries or open connections.

**Solution**:
```sql
-- Suspend warehouse to close connections
ALTER WAREHOUSE adaptive_wh SUSPEND;

-- Wait 30 seconds for connections to drain
SYSTEM$WAIT(30);

-- Try conversion again
ALTER WAREHOUSE adaptive_wh TYPE = ADAPTIVE;
```

### Issue: "MAX_QUERY_PERFORMANCE_LEVEL too high"

**Cause**: Set value exceeds your license or account limit.

**Solution**:
```sql
-- Check account warehouse limit
SHOW PARAMETERS LIKE 'MAX_WAREHOUSE_NODES' IN ACCOUNT;

-- Reduce MAX_QUERY_PERFORMANCE_LEVEL to fit within limit
ALTER WAREHOUSE adaptive_wh SET MAX_QUERY_PERFORMANCE_LEVEL = 5;
```

### Issue: "Cannot convert from STANDARD to ADAPTIVE"

**Cause**: Warehouse type conversion not supported in your account (early release).

**Solution**:
1. Contact Snowflake support to enable Adaptive Warehouse for your account
2. Or create a new Adaptive warehouse instead: `CREATE WAREHOUSE ... TYPE = ADAPTIVE`

### Issue: "Region check failed"

**Cause**: Adaptive Warehouses not available in your region yet.

**Solution**:
1. Check supported regions: us-east-1, us-west-2, eu-west-1, ap-southeast-1, ap-southeast-2
2. If on different AWS region: wait for rollout or contact support
3. If on non-AWS: use standard warehouse with ops-monitor skill

---

## Phase 5: Recommended Next Steps

After successfully creating or converting to Adaptive:

### Monitor Scaling and Credit Usage

```sql
-- Observe warehouse behavior for 1–2 weeks
SELECT
  DATE_TRUNC(hour, START_TIME) as hour,
  COUNT(*) as scaling_events,
  SUM(CREDITS_USED) as total_credits
FROM SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY
WHERE WAREHOUSE_NAME = 'adaptive_wh'
GROUP BY DATE_TRUNC(hour, START_TIME)
ORDER BY hour DESC;
```

### Evaluate Cost-Benefit

Compare cost before and after conversion:
- **Before**: Standard warehouse credits/month
- **After**: Adaptive warehouse credits/month
- **Savings**: (Before - After) / Before × 100%

If savings < 10%, consider reverting to standard.

### Set Up Monitoring Alerts

See [adaptive-warehouse-monitor sub-skill](./adaptive-warehouse-monitor/SKILL.md) for Phase 4 (alert setup).

### Optimize Scaling Parameters

Based on 1–2 weeks of monitoring, fine-tune:
- `MAX_QUERY_PERFORMANCE_LEVEL` (increase if queries queue, decrease if over-scaled)
- `QUERY_THROUGHPUT_MULTIPLIER` (increase for complex queries, decrease for simple)
- `AUTO_SUSPEND` (decrease for cost savings, increase for availability)

---

## Verification Checklist

After completing all phases:

- [ ] Phase 0 check passed (AWS, supported region)
- [ ] Warehouse created with `TYPE = ADAPTIVE` OR converted from standard
- [ ] `SHOW WAREHOUSES` confirms `type = ADAPTIVE`
- [ ] Scaling limits configured (`MAX_QUERY_PERFORMANCE_LEVEL`, `QUERY_THROUGHPUT_MULTIPLIER`)
- [ ] Test query completed successfully
- [ ] `WAREHOUSE_METERING_HISTORY` shows scaling events (NUM_COMPUTE_NODES_REQUESTED varies)
- [ ] Rollback procedure documented (know how to revert if needed)

---

## Next Steps

- **Done with setup?** Proceed to [adaptive-warehouse-monitor sub-skill](./adaptive-warehouse-monitor/SKILL.md) to track credit usage and ROI
- **Want to compare with standard warehouse?** See [adaptive-vs-standard.md reference](../references/adaptive-vs-standard.md)
- **Need to optimize queries first?** Use `ops-monitor` / `self-healing-pipeline` skill before converting

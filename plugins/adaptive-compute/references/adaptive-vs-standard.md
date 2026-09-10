# Adaptive vs. Standard Warehouses: Decision Matrix

This reference helps you decide whether to use Adaptive Warehouses or standard warehouses for your workload.

---

## Feature Comparison Table

| Feature | Adaptive Warehouse | Standard Warehouse |
|---------|-------------------|-------------------|
| **Scaling** | Automatic (seconds) | Manual (via ALTER) |
| **Min compute** | Configurable (1–10 credits min) | Fixed (all compute is allocated) |
| **Max compute** | Configurable | N/A (single fixed size) |
| **Idle behavior** | Auto-suspend to zero credits | Continues accruing credits (manual suspend required) |
| **Burst handling** | Scales out in seconds | Requires manual resize or query queue |
| **Query latency** | Consistent (scales to demand) | Predictable (fixed resources) |
| **Credit cost** | Variable (dynamic scaling) | Fixed (by size and uptime) |
| **Setup complexity** | Simple (one TYPE parameter) | Simple (one SIZE parameter) |
| **Cost during idle** | Zero (auto-suspend) | Ongoing (unless manually suspended) |
| **Cloud availability** | AWS only (as of Jun 16, 2024) | All clouds (AWS, Azure, GCP) |
| **Region availability** | 5 AWS regions (us-east-1, us-west-2, eu-west-1, ap-southeast-1, ap-southeast-2) | All regions |
| **Best for** | Variable/spiky workloads | Predictable/sustained workloads |
| **Worst for** | Sustained high-concurrency | Variable workloads (wasteful sizing) |

---

## Cost Comparison by Workload Pattern

### Pattern 1: Dev/Test (Spiky, Variable Concurrency)
```
Workload: 3 hours peak (10 concurrent queries), 5 hours idle, repeated daily

Standard Medium (1.5 credits/hour):
  • Always-on: 1.5 × 24 hours × 30 days = 1,080 credits/month = $4,320/month
  • With manual suspend: 1.5 × 8 hours × 30 days = 360 credits/month = $1,440/month
  
Adaptive (1–5 credits range, avg 0.5):
  • Auto-scales and auto-suspends
  • Average: 0.5 × 24 hours × 30 days = 360 credits/month = $1,440/month
  
Result: Adaptive = Standard (with manual suspend)
Advantage: Adaptive requires NO manual management; Standard requires discipline to suspend
```

### Pattern 2: ETL Pipeline (Predictable, Off-Peak Idle)
```
Workload: 6am–8am peak (10 concurrent), 2pm–4pm peak (10 concurrent), rest idle

Standard Large (3 credits/hour):
  • Always-on: 3 × 24 × 30 = 2,160 credits/month = $8,640/month
  • With manual suspend: 3 × 4 hours × 30 days = 360 credits/month = $1,440/month
  
Adaptive (2–10 credits, avg 0.5):
  • Auto-scales during peaks, auto-suspends during idle
  • Average: 0.5 × 24 × 30 = 360 credits/month = $1,440/month
  
Result: Adaptive = Standard (with discipline)
Advantage: Adaptive doesn't require manual suspend/resume (fire-and-forget)
```

### Pattern 3: Analytics (Sustained + Bursty)
```
Workload: Baseline 2 concurrent (scheduled reports), spikes to 8 concurrent (ad-hoc queries)

Standard Large (3 credits/hour):
  • 3 × 24 × 30 = 2,160 credits/month = $8,640/month
  
Adaptive (2–10 credits, avg 2.5):
  • Baseline: 2 credits
  • Bursts: scales to 8 credits (seconds)
  • Average: 2.5 × 24 × 30 = 1,800 credits/month = $7,200/month
  
Result: Adaptive saves ~20% ($1,440/month)
Advantage: Better latency during bursts, lower cost than over-sized fixed warehouse
```

### Pattern 4: Sustained High-Concurrency (Not Ideal for Adaptive)
```
Workload: Consistent 8 concurrent queries, 24/7

Standard Large (8 credits/hour):
  • 8 × 24 × 30 = 5,760 credits/month = $23,040/month
  
Adaptive (6–10 credits, sustained 8):
  • Always at near-max: 8 × 24 × 30 = 5,760 credits/month = $23,040/month
  • Overhead: Dynamic scaling adds 5–10% overhead
  
Result: Adaptive ≈ Standard or slightly MORE expensive
Recommendation: Use Standard warehouse for sustained load (no scaling benefit)
```

---

## Decision Tree: Which Should I Use?

```
Q1: Is your workload variable or unpredictable?
  ├─ YES (spiky, bursty, off-peak idle) → Go to Q2
  └─ NO (sustained, predictable) → Use STANDARD WAREHOUSE

Q2: Are you on AWS?
  ├─ YES → Go to Q3
  └─ NO (Azure/GCP) → Use STANDARD WAREHOUSE (Adaptive not available)

Q3: Is your AWS region supported?
  ├─ YES (us-east-1, us-west-2, eu-west-1, ap-southeast-1, ap-southeast-2) → Go to Q4
  └─ NO (other AWS region) → Use STANDARD WAREHOUSE (wait for rollout)

Q4: Do you have budget or cost concerns?
  ├─ YES → Try ADAPTIVE WAREHOUSE (likely 50–80% cost savings)
  └─ NO → Use whichever you prefer (both work)

Q5: Do you have latency SLA during peak?
  ├─ YES (must be fast during spikes) → ADAPTIVE WAREHOUSE (auto-scales in seconds)
  └─ NO → Either works; pick ADAPTIVE if budget-conscious

RECOMMENDATION: → Use ADAPTIVE WAREHOUSE
```

---

## When to Use Adaptive Warehouse

✅ **Best for:**
- Variable workload (traffic spikes and idle periods)
- Dev/test environments (variable, cost-sensitive)
- SaaS multi-tenant (per-tenant warehouses with variable usage)
- Reporting + ad-hoc queries (mixed predictable + unpredictable)
- Cost optimization priority (savings often 50–80%)
- AWS deployment (only available cloud currently)
- Latency-sensitive during spikes (auto-scales faster than manual resize)

✅ **Good fit if:**
- You're on supported AWS region
- Your workload has >20% idle time or >30% variance in concurrency
- You want hands-off warehouse management (auto-scaling, auto-suspend)
- You're willing to monitor and potentially revert if savings aren't realized

---

## When to Use Standard Warehouse

✅ **Best for:**
- Sustained, predictable workload (constant concurrency 24/7)
- Workload with zero idle periods
- Azure or GCP (Adaptive not available yet)
- Unsupported AWS region (waiting for rollout)
- Query latency is highly predictable and must be verified
- Heavy batch processing (consistent throughput)

✅ **Good fit if:**
- You want deterministic costs (no variability)
- You prefer manual control (explicit sizing)
- Your workload doesn't have idle periods (auto-suspend won't help)
- You're on non-AWS cloud

---

## Migration Path: Standard → Adaptive

If you're currently using standard warehouses and want to try Adaptive:

### Phase 1: Assess Workload
```sql
-- Analyze last 30 days of warehouse usage
SELECT
  WAREHOUSE_NAME,
  AVG(CREDITS_USED) as avg_credits_per_hour,
  MAX(CREDITS_USED) as peak_credits_per_hour,
  MIN(CREDITS_USED) as min_credits_per_hour,
  STDDEV(CREDITS_USED) as variance
FROM SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY
WHERE WAREHOUSE_NAME = 'your_warehouse'
  AND START_TIME > DATEADD(day, -30, CURRENT_TIMESTAMP)
GROUP BY WAREHOUSE_NAME;
```

**Indicators for Adaptive:**
- High variance (STDDEV >> AVG) → Good candidate
- Peaks >> baseline (MAX >> AVG) → Good candidate
- Many hours with low usage → Good candidate (auto-suspend saves credits)

### Phase 2: Test Adaptive (Parallel Run)
```sql
-- Create new Adaptive warehouse alongside standard
CREATE WAREHOUSE adaptive_test_wh
  TYPE = ADAPTIVE
  WAREHOUSE_SIZE = MEDIUM
  MAX_QUERY_PERFORMANCE_LEVEL = 5
  AUTO_SUSPEND = 300;

-- Route subset of queries to Adaptive (e.g., dev/test)
-- Monitor credit usage for 1–2 weeks
```

### Phase 3: Compare Costs
```sql
-- Compare credit usage: standard vs. Adaptive
SELECT
  'standard_wh' as warehouse_type,
  SUM(CREDITS_USED) as total_credits
FROM SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY
WHERE WAREHOUSE_NAME = 'standard_wh'
  AND START_TIME > DATEADD(day, -7, CURRENT_TIMESTAMP)

UNION ALL

SELECT
  'adaptive_test_wh' as warehouse_type,
  SUM(CREDITS_USED) as total_credits
FROM SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY
WHERE WAREHOUSE_NAME = 'adaptive_test_wh'
  AND START_TIME > DATEADD(day, -7, CURRENT_TIMESTAMP);
```

### Phase 4: Convert or Revert
```sql
-- Option A: Looks good, convert production
ALTER WAREHOUSE your_warehouse TYPE = ADAPTIVE;

-- Option B: Doesn't help, revert
ALTER WAREHOUSE adaptive_test_wh TYPE = STANDARD;
```

---

## Troubleshooting: Is Adaptive Right?

### Symptom: "I converted to Adaptive but don't see cost savings"

**Likely causes:**
1. Workload is actually sustained (not variable) → use Standard
2. Queries are slow/unoptimized → fix with ops-monitor first
3. Scaling overhead outweighs benefits → revert to Standard

**Solution**:
```sql
-- Revert to standard
ALTER WAREHOUSE your_warehouse TYPE = STANDARD;

-- Start with query optimization (ops-monitor skill)
-- Then try Adaptive after baseline queries are optimized
```

### Symptom: "Adaptive warehouse has latency spikes"

**Likely causes:**
1. Scaling down during query execution
2. Not enough max compute (queries queuing)

**Solution**:
```sql
-- Increase max compute level
ALTER WAREHOUSE your_warehouse SET MAX_QUERY_PERFORMANCE_LEVEL = 10;

-- Increase idle timeout (scale down slower)
ALTER WAREHOUSE your_warehouse SET AUTO_SUSPEND = 600;  -- 10 min instead of 5 min
```

### Symptom: "Adaptive warehouse not scaling up fast enough"

**Likely cause**: Query throughput multiplier too low

**Solution**:
```sql
-- Increase throughput multiplier
ALTER WAREHOUSE your_warehouse SET QUERY_THROUGHPUT_MULTIPLIER = 15;
```

---

## Cost-Benefit ROI Calculation

To decide if Adaptive is worth your effort:

```sql
-- Calculate current cost
WITH current_usage AS (
  SELECT
    SUM(CREDITS_USED) as current_monthly_credits
  FROM SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY
  WHERE WAREHOUSE_NAME = 'your_warehouse'
    AND START_TIME > DATEADD(day, -30, CURRENT_TIMESTAMP)
)
-- Estimate Adaptive cost (assume 40% average utilization for variable workloads)
SELECT
  current_monthly_credits,
  current_monthly_credits * 0.4 as estimated_adaptive_cost,
  current_monthly_credits * 0.6 as estimated_savings_per_month,
  current_monthly_credits * 0.6 * 12 as estimated_savings_per_year
FROM current_usage;
```

**Break-even analysis**:
- If estimated annual savings > $1,000 → Try Adaptive
- If estimated annual savings < $100 → Stick with Standard (not worth the effort)

---

## Summary Table

| Workload Type | Recommendation | Savings Potential | Effort | Risk |
|---|---|---|---|---|
| Spiky/variable | Adaptive | 50–80% | Low | Low (easy to revert) |
| Sustained/high-concurrency | Standard | 0% | — | N/A (no scaling benefit) |
| Dev/test | Adaptive | 60–90% | Low | Low |
| Multi-tenant SaaS | Adaptive | 40–70% | Medium | Low |
| Reporting + ad-hoc | Adaptive | 30–50% | Low | Low |
| Batch processing | Standard | — | — | — |
| Azure/GCP | Standard | — | — | — |

---

## Next Steps

- **Ready to convert to Adaptive?** → [adaptive-warehouse-setup sub-skill](../skills/adaptive-warehouse-setup/SKILL.md)
- **Want to monitor existing Adaptive?** → [adaptive-warehouse-monitor sub-skill](../skills/adaptive-warehouse-monitor/SKILL.md)
- **Want to optimize Standard warehouse instead?** → `ops-monitor` / `self-healing-pipeline` skill

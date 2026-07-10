---
name: adaptive-compute
description: Adaptive Warehouse provisioning and monitoring. Convert or create warehouses with automatic scaling, credit optimization, and performance monitoring (AWS regions only).
---

# Adaptive Compute Plugin

## Overview

Adaptive Warehouses enable **automatic scaling and credit optimization** for variable workloads. Instead of manually resizing warehouses, Adaptive Warehouses dynamically adjust compute resources based on query demand and automatically pause during idle periods.

**Key advantage**: Pay only for compute you use, with automatic scaling that responds in seconds to workload changes.

**Availability**: AWS regions only (GA as of Jun 16, 2024). Azure and GCP support coming in future releases.

---

## When to Use This Plugin

| Scenario | Use Adaptive? | Alternative |
|----------|---------------|-------------|
| Unpredictable query patterns (variable concurrency) | ✅ Yes — auto-scales in seconds | Manual resize (reactive, slower) |
| Cost-sensitive workloads with spiky traffic | ✅ Yes — pay only for what you use | Large fixed warehouse (wasteful during off-peak) |
| Dev/test environment with variable load | ✅ Yes — auto-shutdown saves credits | Standard warehouse (manual management) |
| You're on AWS (us-east-1, us-west-2, eu-west-1, etc.) | ✅ Yes — available now | Standard warehouse (on non-AWS regions) |
| High-concurrency, low-latency SLA needed | ⚠️ Maybe — test first; not replacement for query optimization | Standard warehouse + query tuning |
| Heavy batch processing (predictable, scheduled) | ❌ No — standard warehouse is more economical | Standard warehouse (fixed size) |
| You're on Azure or GCP | ❌ No — not available yet | Standard warehouse (use ops-monitor for tuning) |

**Not sure?** See `adaptive-vs-standard.md` for a decision matrix.

---

## Sub-Skills

### ⚙️ [adaptive-warehouse-setup](./skills/adaptive-warehouse-setup/SKILL.md)
Create or convert warehouses to Adaptive type:
1. **Phase 0**: Verify AWS region (mandatory gate; non-AWS routes to error message)
2. **Phase 1**: Create new Adaptive warehouse or convert existing standard warehouse
3. **Phase 2**: Configure scaling limits (`MAX_QUERY_PERFORMANCE_LEVEL`, `QUERY_THROUGHPUT_MULTIPLIER`)
4. **Phase 3**: Validate configuration and confirm type=ADAPTIVE
5. **Phase 4**: Rollback procedure (convert back to standard if needed)

### 📊 [adaptive-warehouse-monitor](./skills/adaptive-warehouse-monitor/SKILL.md)
Monitor performance, credit usage, and scaling behavior:
1. **Phase 1**: Query `WAREHOUSE_METERING_HISTORY` to track credit burn and scaling events
2. **Phase 2**: Establish baseline metrics (query latency, throughput, credits per query)
3. **Phase 3**: Define revert criteria (when to convert back to standard)
4. **Phase 4**: Set up continuous monitoring and alerts
5. **Phase 5**: Calculate cost-benefit ROI (Adaptive vs. standard)

---

## Quick Decision Tree

```
You want to set up or optimize warehouse scaling?
│
├─ YES, I want automatic scaling → Go to adaptive-warehouse-setup
│   └─ Phase 0 checks if you're on AWS
│      ├─ YES (AWS) → Proceed with conversion/creation
│      └─ NO (Azure/GCP) → Use standard warehouse + ops-monitor skill
│
├─ YES, I want to monitor credit usage → Go to adaptive-warehouse-monitor
│   └─ Tracks scaling events, baseline metrics, cost-benefit
│
└─ NOT SURE which approach → See adaptive-vs-standard.md
```

---

## Adaptive vs. Standard Warehouses

| Aspect | Adaptive Warehouse | Standard Warehouse |
|--------|-------------------|-------------------|
| **Scaling** | Automatic (seconds to adjust compute) | Manual (requires resizing command) |
| **Credit efficiency** | High (only pay for compute used) | Variable (depends on sizing strategy) |
| **Idle behavior** | Auto-suspends to save credits | Runs continuously if not manually suspended |
| **Setup complexity** | Simple (one command, AWS only) | Simple (one command, all clouds) |
| **Query latency** | Fast (scales out for burst traffic) | Predictable (fixed compute) |
| **Workload fit** | Variable/unpredictable traffic | Predictable, steady traffic |
| **Availability** | AWS regions only (as of Jun 16, 2024) | All regions (AWS, Azure, GCP) |
| **Cost predictability** | Lower min, higher burst (dynamic) | Fixed cost (static sizing) |
| **Operational burden** | Low (auto-scaling) | Medium (manual tuning required) |

---

## Architecture: How Adaptive Warehouses Work

```
Query submitted to Adaptive Warehouse
  │
  ├─ Snowflake analyzes queue and current demand
  │
  ├─ IF concurrency increasing
  │   └─ Automatically allocate more compute clusters (up to MAX_QUERY_PERFORMANCE_LEVEL)
  │
  ├─ IF query latency above threshold
  │   └─ Increase parallelism within current clusters
  │
  ├─ Query executes (now with scaled resources)
  │
  ├─ After query completes, if idle
  │   └─ Gradually suspend unused clusters over 5-10 min
  │
  └─ Warehouse transitions to suspended state (no credits consumed)
```

**Key differences from standard warehouse**:
- Standard: You set compute size (XS, S, M, L, XL); size is fixed
- Adaptive: You set min/max compute range; size adjusts dynamically within range

---

## Positioning: Complementary to Query Optimization

Adaptive Warehouses are **not a replacement for query optimization**. They work best when:
1. Queries are reasonably optimized (good clustering, pruning, indexes)
2. Workload is variable (not sustained high concurrency)
3. You want to reduce operational overhead (auto-scaling vs. manual tuning)

**For sustained performance issues** (high latency, cache misses):
- Start with query optimization (see `ops-monitor` / `self-healing-pipeline` skill)
- Then layer Adaptive Warehouse for variable traffic handling

**For cost optimization**:
- Adaptive Warehouse saves credits during idle periods
- ops-monitor `self-healing-pipeline` optimizes query cost
- Together: best cost + performance combination

---

## Cross-References

### Arriving from ops-monitor?
If you're following the `self-healing-pipeline` skill and hit "When Warehouse Resizing Isn't Enough," **Adaptive Warehouses might be your answer**. This plugin provides setup and monitoring for the Adaptive approach.

### Need query optimization first?
If your queries are slow or expensive regardless of warehouse size, start with the `ops-monitor` / `self-healing-pipeline` skill to optimize before converting to Adaptive.

### Need standard warehouse tuning?
For Azure or GCP users (where Adaptive is not yet available), use the `ops-monitor` skill for warehouse cluster scaling and resource management.

---

## Prerequisites Check

Before proceeding to adaptive-warehouse-setup:
- ✅ Your Snowflake account is deployed on AWS
- ✅ Your region is in the supported list (see activation.md)
- ✅ You have warehouse admin role or equivalent privileges
- ✅ Cortex Code version >= 2026-07 (Adaptive Warehouse GA)
- ✅ Your existing warehouse is standard type (if converting)

---

## AWS Regions Supported (Adaptive Warehouse GA)

- `us-east-1` (N. Virginia)
- `us-west-2` (N. Oregon)
- `eu-west-1` (Ireland)
- `ap-southeast-1` (Singapore)
- `ap-southeast-2` (Sydney)

**Support for Azure and GCP regions:** Coming in future releases. See `ops-monitor` skill for standard warehouse optimization in the meantime.

---

## Getting Started

### 5-Minute Quick Start

```sql
-- 1. Check your region (Phase 0 auto-checks this)
SELECT CURRENT_REGION();

-- 2. Create new Adaptive Warehouse
CREATE WAREHOUSE adaptive_wh
  TYPE = ADAPTIVE
  WAREHOUSE_SIZE = MEDIUM
  MAX_QUERY_PERFORMANCE_LEVEL = 5
  QUERY_THROUGHPUT_MULTIPLIER = 10
  AUTO_SUSPEND = 300  -- 5 min idle
  AUTO_RESUME = true;

-- 3. Validate
SHOW WAREHOUSES LIKE 'adaptive_wh';
-- TYPE column should show: ADAPTIVE

-- 4. Monitor (see adaptive-warehouse-monitor)
SELECT
  WAREHOUSE_NAME,
  CREDITS_USED,
  CREDITS_USED_CLOUD_SERVICES,
  CREDITS_USED_COMPUTE,
  WAREHOUSE_METERING_HISTORY
FROM SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY
WHERE WAREHOUSE_NAME = 'adaptive_wh'
ORDER BY START_TIME DESC
LIMIT 10;
```

---

## Cost Estimate Examples

### Scenario 1: Dev/Test (3 hours peak, 5 hours idle)
| Warehouse | Avg Usage | Peak Size | Est. Daily Cost | Est. Monthly |
|-----------|-----------|-----------|-----------------|--------------|
| Standard (Large) | 2L continuous | 2L | 2.4 credits | $720 |
| Adaptive (2–10L) | 0.5L average | 10L burst | 0.6 credits | $180 |
| **Savings** | — | — | **$1.8/day** | **$540/mo** |

### Scenario 2: Production ETL (predictable 6am-8am, 2pm-4pm)
| Warehouse | Daily Usage | Peak Size | Est. Daily Cost | Est. Monthly |
|-----------|-------------|-----------|-----------------|--------------|
| Standard (Medium) | 4M fixed | 4M | 1.92 credits | $576 |
| Adaptive (2–8M) | 1.5M average | 8M burst | 0.72 credits | $216 |
| **Savings** | — | — | **$1.2/day** | **$360/mo** |

*(Credit costs: $4 per credit; examples use Mid-tier pricing as of 2026)*

---

## Troubleshooting: Is Adaptive Right for You?

**Problem**: "I converted to Adaptive but see higher credits than standard warehouse."

**Possible causes**:
- Workload is actually steady/high (Adaptive doesn't help sustained load)
- Queries are unoptimized (Adaptive amplifies inefficiency)
- Burst traffic is very infrequent (fixed small warehouse might be cheaper)

**Solution**: See `adaptive-warehouse-monitor` Phase 3 (revert criteria) to evaluate if revert to standard is better.

---

## Next Steps

1. **Ready to set up?** → [adaptive-warehouse-setup sub-skill](./skills/adaptive-warehouse-setup/SKILL.md)
2. **Want to monitor existing Adaptive warehouse?** → [adaptive-warehouse-monitor sub-skill](./skills/adaptive-warehouse-monitor/SKILL.md)
3. **Comparing Adaptive vs. Standard?** → [adaptive-vs-standard.md reference](./references/adaptive-vs-standard.md)
4. **First time? Check prerequisites** → [PREREQUISITES.md](./PREREQUISITES.md)
5. **Unsure if AWS region is supported?** → [activation.md](./.cortex-plugin/activation.md)

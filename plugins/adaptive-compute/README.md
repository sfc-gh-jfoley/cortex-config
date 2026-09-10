# Adaptive Compute Plugin

## Overview

Adaptive Warehouses are Snowflake's solution for **automatic scaling and credit optimization** on variable workloads. Instead of manually managing warehouse size, Adaptive Warehouses automatically adjust compute resources in seconds based on query demand and auto-suspend during idle periods.

**Availability**: AWS regions only (GA as of Jun 16, 2024). Azure and GCP support coming in future releases.

---

## The Problem Adaptive Warehouses Solve

### ❌ Traditional Approach (Manual Management)
```
Workload spikes 3x        → Manual: contact admin
                          → Admin resizes warehouse
                          → Wait 2-3 minutes for resize
                          → Queries now run faster
                          → 4 hours later: workload drops
                          → Manual: resize back down
                          → During idle: still paying for large warehouse
```

### ✅ Adaptive Warehouse Approach (Automatic Scaling)
```
Workload spikes 3x        → Adaptive: auto-scales in seconds
                          → Queries run fast
                          → 4 hours later: workload drops
                          → Adaptive: auto-scales down
                          → During idle: auto-suspends (no credits)
```

**Benefits:**
- **Speed**: Responds in seconds (vs. minutes for manual resize)
- **Cost**: Pay only for compute you use; auto-suspend saves credits during idle
- **Simplicity**: No manual management; set min/max and let Snowflake scale
- **Predictability**: Latency remains stable even during traffic spikes

---

## Use Cases

### 1. Dev/Test Environments
```
Problem: Developers need variable compute for testing, but manual sizing wastes credits during idle.

Solution:
  ├─ Set Adaptive warehouse with wide scaling range (2–10 credits)
  ├─ Auto-suspend after 5 min idle
  └─ Dev team: scales up for intensive tests, suspends automatically
  
Result: 60–80% credit savings vs. fixed large warehouse
```

### 2. Data Pipelines with Variable Concurrency
```
Problem: ETL pipelines have burst phases (peak: 10 concurrent queries, off-peak: 0 queries).
         Fixed warehouse: either wasteful or too slow.

Solution:
  ├─ Adaptive warehouse: scales from 2 to 10 compute nodes
  ├─ Peak load: scales to 10 nodes in seconds
  ├─ Off-peak: scales to 2 nodes, then auto-suspends
  └─ Throughput multiplier tuned for max parallelism
  
Result: Latency stable during peaks, cost minimized during off-peak
```

### 3. Analytics Workloads (Reporting + Ad-Hoc Queries)
```
Problem: Regular reports (predictable) + ad-hoc queries (unpredictable = variable concurrency).

Solution:
  ├─ Adaptive warehouse instead of large fixed warehouse
  ├─ Reports get consistent performance (auto-scales if needed)
  ├─ Ad-hoc queries don't contend; Adaptive provides headroom
  └─ Idle periods: auto-suspend saves credits
  
Result: Better interactive experience, lower sustained costs
```

### 4. Multi-Tenant SaaS (Per-Tenant Warehouses)
```
Problem: Each tenant has a warehouse; usage varies wildly by tenant and time of day.
         Fixed-size: some overprovisioned, others underprovisioned.

Solution:
  ├─ Convert all per-tenant warehouses to Adaptive type
  ├─ Each scales independently to match tenant demand
  ├─ Shared credit pool or per-tenant budgets (via alert/monitoring)
  └─ Auto-suspend: unused tenant warehouses consume zero credits
  
Result: Better utilization, fair cost allocation, improved tenant experience
```

---

## Cost Comparison: Adaptive vs. Standard

### Small Workload (Dev/Test, 8 hrs/day usage)
```
Standard Medium warehouse (1.5L):
  • 1.5 credits/hour × 8 hours × 22 days = 264 credits/month
  • Cost: $1,056/month (@ $4/credit)

Adaptive (1–5L range):
  • Average 0.5L × 8 hours × 22 days = 88 credits/month
  • Cost: $352/month
  • Savings: $704/month (67% reduction)
```

### Medium Workload (Analytics, variable concurrency)
```
Standard Large warehouse (3L continuous):
  • 3 credits/hour × 24 hours × 30 days = 2,160 credits/month
  • Cost: $8,640/month

Adaptive (2–8L range, 30% avg utilization):
  • Average 0.6L × 24 hours × 30 days = 432 credits/month
  • Cost: $1,728/month
  • Savings: $6,912/month (80% reduction)
```

### High-Performance Workload (Sustained, predictable)
```
Standard Large warehouse (3L):
  • Cost: $8,640/month

Adaptive (3–10L range, sustained peak):
  • Average 3L × 24 hours × 30 days = 2,160 credits/month
  • Cost: $8,640/month
  • Savings: $0 (no savings; use standard instead)

← Recommendation: Use standard warehouse for sustained high-concurrency workloads
```

---

## High-Level Flow

```
1. Check Your AWS Region
   └─ Phase 0: Verify region is supported (us-east-1, us-west-2, eu-west-1, etc.)

2. Create or Convert to Adaptive
   ├─ CREATE WAREHOUSE ... TYPE = ADAPTIVE (new warehouse)
   ├─ ALTER WAREHOUSE ... TYPE = ADAPTIVE (convert existing)
   └─ Set scaling limits: MAX_QUERY_PERFORMANCE_LEVEL, QUERY_THROUGHPUT_MULTIPLIER

3. Configure Scaling Behavior
   ├─ MIN compute: smallest size Adaptive can scale down to
   ├─ MAX compute: largest size Adaptive can scale up to
   └─ Idle timeout: when to auto-suspend

4. Monitor Scaling and Credits
   ├─ Track credit burn in WAREHOUSE_METERING_HISTORY
   ├─ Observe scaling events (how often it scales up/down)
   └─ Establish baseline metrics for ROI calculation

5. Tune or Revert
   ├─ If Adaptive is saving credits: keep tuning scaling parameters
   ├─ If Adaptive is not helping: revert to standard warehouse
   └─ If sustained high concurrency: standard warehouse is better
```

---

## Risk Mitigation

### Risk: "What if Adaptive makes performance worse?"

**Mitigation**: Adaptive monitoring sub-skill includes Phase 4 (revert criteria). If sustained latency degradation, you can revert to standard warehouse in one command:

```sql
ALTER WAREHOUSE adaptive_wh TYPE = STANDARD;
```

### Risk: "What if costs increase unexpectedly?"

**Mitigation**: Monitor Phase 1 tracks credit usage. Set alerts for cost anomalies. Adaptive-warehouse-monitor Phase 3 defines "cost threshold" beyond which revert is recommended.

### Risk: "What if I'm on Azure or GCP?"

**Mitigation**: This plugin gates on AWS regions. If you're on non-AWS, use `ops-monitor` skill for warehouse tuning on standard warehouses.

### Risk: "What if workload is sustained/high-concurrency?"

**Mitigation**: Adaptive helps variable workloads, not sustained load. Recommendation: Use standard warehouse + ops-monitor `self-healing-pipeline` for query optimization.

---

## Adaptive vs. Standard: Quick Decision Matrix

| Question | Answer | Recommendation |
|----------|--------|-----------------|
| Is your workload variable (spiky)? | Yes | Try Adaptive |
| Is your workload sustained/high-concurrency? | Yes | Use Standard |
| Are you on AWS? | Yes | Can use Adaptive |
| Are you on Azure/GCP? | Yes | Use Standard (for now) |
| Is your cost per query high? | Yes | Start with query optimization (ops-monitor), then Adaptive |
| Do you want zero-touch auto-scaling? | Yes | Use Adaptive |
| Do you need predictable costs? | Yes | Use Standard (with fixed sizing) |
| Do you have variable idle periods? | Yes | Use Adaptive (auto-suspend saves credits) |

**Bottom line**: If variable workload + AWS = try Adaptive. If not, use Standard + ops-monitor.

---

## Next Steps

- **Ready to set up?** → [adaptive-warehouse-setup sub-skill](./skills/adaptive-warehouse-setup/SKILL.md)
- **Want to monitor existing?** → [adaptive-warehouse-monitor sub-skill](./skills/adaptive-warehouse-monitor/SKILL.md)
- **Comparing options?** → [adaptive-vs-standard.md reference](./references/adaptive-vs-standard.md)
- **Prerequisites not met?** → [PREREQUISITES.md](./PREREQUISITES.md)
- **Not on AWS?** → Use `ops-monitor` skill for standard warehouse optimization

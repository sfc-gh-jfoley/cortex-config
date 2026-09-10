# Adaptive Compute Prerequisites

Before invoking adaptive-warehouse-setup or adaptive-warehouse-monitor, ensure your Snowflake account and environment meet these requirements.

---

## Cloud and Region Requirements

### AWS (Required)
- **Required**: Snowflake account deployed on AWS
- **Supported regions** (as of Jun 16, 2024 GA):
  - `us-east-1` (N. Virginia)
  - `us-west-2` (N. Oregon)
  - `eu-west-1` (Ireland)
  - `ap-southeast-1` (Singapore)
  - `ap-southeast-2` (Sydney)

**How to check**:
```sql
SELECT CURRENT_CLOUD() AS cloud, CURRENT_REGION() AS region;
```

**If not on AWS or unsupported region**:
- Azure/GCP: Use `ops-monitor` skill for standard warehouse optimization (no Adaptive support yet)
- AWS but unsupported region: Contact Snowflake support for regional rollout timeline

### Azure / GCP (Not Supported Yet)
- Adaptive Warehouse is AWS-only as of Jun 16, 2024
- Support for Azure and GCP planned for future releases
- In the meantime: Use `ops-monitor` skill for warehouse cluster scaling and cost optimization

---

## Cortex Code Version

- **Required**: Cortex Code >= 2026-07 (Adaptive Warehouse GA release)
- **How to check**: 
  ```bash
  cortex version
  ```
- **If outdated**: Upgrade via `brew upgrade cortex-code` (macOS) or equivalent for your OS

---

## Snowflake Account Prerequisites

### Edition
- **No specific edition requirement** (Adaptive is available on all editions)
- Standard, Business, and Business Critical editions all support Adaptive Warehouses

**How to check**:
```sql
SELECT CURRENT_ACCOUNT_EDITION();
```

### Role Permissions

For **adaptive-warehouse-setup** (create or convert):
- `CREATE WAREHOUSE` privilege
- `ALTER WAREHOUSE` privilege (to convert existing warehouse)
- `USAGE` on database/schema where warehouse exists or will be created

For **adaptive-warehouse-monitor** (monitor existing):
- `MONITOR` privilege on warehouse (or read-only access via `ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY`)
- Read access to `SNOWFLAKE.ACCOUNT_USAGE` database (account-level view)

**How to verify**:
```sql
SHOW GRANTS TO ROLE <your_role>;
-- Look for: CREATE WAREHOUSE, ALTER WAREHOUSE, MONITOR, USAGE on databases
```

**If permissions are missing**, contact your Snowflake account admin:
```sql
-- Admin grants warehouse creation privilege
GRANT CREATE WAREHOUSE ON ACCOUNT TO ROLE <your_role>;

-- Admin grants monitoring privilege
GRANT USAGE ON DATABASE SNOWFLAKE TO ROLE <your_role>;
```

---

## Network and Connectivity

### Snowflake Connectivity
- **Outbound**: Connection to Snowflake's control plane (port 443, usually automatic)
- **If behind proxy**: Proxy must allow HTTPS to `*.snowflakecomputing.com`
- **If network policy**: Account network policy must not block warehouse operations

**Verify connectivity**:
```bash
curl -I https://your-snowflake-account.snowflakecomputing.com
# Should return HTTP 200 OK
```

---

## Existing Warehouse Prerequisites (If Converting)

### For Convert-to-Adaptive Workflow
If you're converting an existing standard warehouse to Adaptive type:

1. **Warehouse must exist**: Standard type, not already Adaptive
   ```sql
   SHOW WAREHOUSES LIKE 'your_warehouse_name';
   -- TYPE column should show: STANDARD
   ```

2. **Warehouse must be suspended or idle** (recommended before conversion)
   ```sql
   ALTER WAREHOUSE <warehouse_name> SUSPEND;
   ```

3. **No active queries**: Suspend warehouse or wait for all queries to complete
   ```sql
   -- Check active queries
   SELECT *
   FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
   WHERE WAREHOUSE_NAME = '<warehouse_name>'
     AND STATE IN ('QUEUED', 'RUNNING')
     AND START_TIME > DATEADD(hour, -1, CURRENT_TIMESTAMP);
   ```

4. **Warehouse size compatibility**: Current warehouse size becomes the starting compute level
   - If currently Small (1 credit/hour) → can scale up to your max
   - If currently Large (8 credits/hour) → can scale down only if workload allows

---

## Credit and Cost Considerations

### Estimate Your Savings

**Before conversion, estimate potential savings**:

1. **Current cost** (standard warehouse):
   ```sql
   SELECT
     WAREHOUSE_NAME,
     WAREHOUSE_SIZE,
     SUM(CREDITS_USED) as total_credits_used,
     DATEDIFF(day, MIN(START_TIME), MAX(START_TIME)) as days_active
   FROM SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY
   WHERE WAREHOUSE_NAME = '<your_warehouse>'
     AND START_TIME > DATEADD(day, -30, CURRENT_TIMESTAMP)
   GROUP BY WAREHOUSE_NAME, WAREHOUSE_SIZE;
   ```

2. **Estimate Adaptive cost** (30% average utilization assumption):
   ```
   Adaptive cost ≈ Standard cost × 0.30 (rough estimate for variable workloads)
   Savings ≈ Standard cost × 0.70 (if truly variable)
   ```

3. **Calculate ROI**:
   - If current monthly cost: $1,000
   - Estimated Adaptive cost: $300/month
   - **Savings: $700/month (~84% reduction)**

### Cost is Zero During Auto-Suspend
- When Adaptive warehouse suspends (due to idle timeout), it consumes **zero credits**
- Standard warehouse: still accrues credits even when idle (if not manually suspended)
- This is Adaptive's primary cost advantage for variable workloads

---

## Monitoring and Alerts Setup (Optional)

To get the most from adaptive-warehouse-monitor sub-skill:

1. **Existing ops-monitor dashboards** (optional):
   - If you've already set up `ops-monitor` / `self-healing-pipeline`, baseline metrics are available
   - Not required; adaptive-warehouse-monitor will establish its own baseline

2. **Alert integration** (optional):
   - If you use Slack, email, or webhook alerts, have your notification integration set up
   - adaptive-warehouse-monitor Phase 4 can route alerts via `alert` skill
   - Not required for basic monitoring

3. **Query history access** (required):
   - Must have read access to `SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY` and `WAREHOUSE_METERING_HISTORY`
   - Usually automatic with account admin role
   - Verify:
     ```sql
     SELECT * FROM SNOWFLAKE.ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY LIMIT 1;
     -- If error: contact account admin for read access
     ```

---

## Summary Checklist

Before invoking adaptive-warehouse-setup or adaptive-warehouse-monitor:

### Cloud & Region
- [ ] Snowflake account is deployed on AWS
- [ ] Your region is in the supported list (us-east-1, us-west-2, eu-west-1, ap-southeast-1, ap-southeast-2)

### Cortex Code
- [ ] Cortex Code version is >= 2026-07
- [ ] `cortex version` confirms correct version

### Snowflake Account
- [ ] Your role has CREATE WAREHOUSE and ALTER WAREHOUSE privileges
- [ ] Your role has read access to ACCOUNT_USAGE views (for monitoring)
- [ ] Account is not subject to restrictive network policies

### Existing Warehouse (If Converting)
- [ ] Warehouse exists and is type = STANDARD
- [ ] No active queries on the warehouse (safe to convert)
- [ ] Warehouse is suspended or idle

### Cost Baseline (Optional)
- [ ] You've estimated current monthly credit usage (for ROI calc)
- [ ] You understand potential savings for your workload pattern

---

## If Prerequisites Are Not Met

| Prerequisite | Status | Resolution |
|---------------|--------|-----------|
| Not on AWS | ❌ | Use standard warehouse + ops-monitor skill |
| AWS region unsupported | ❌ | Wait for regional rollout or contact support |
| Cortex Code outdated | ❌ | Upgrade: `brew upgrade cortex-code` |
| No CREATE WAREHOUSE privilege | ❌ | Contact account admin to grant privilege |
| Warehouse type not STANDARD | ❌ | Ensure warehouse is standard type (not already Adaptive) |
| Active queries on warehouse | ⚠️ | Suspend warehouse or wait for queries to complete |
| No ACCOUNT_USAGE access | ⚠️ | Contact account admin for read access |

---

## Next Steps

Once all prerequisites are met:
1. Proceed to [adaptive-warehouse-setup sub-skill](../skills/adaptive-warehouse-setup/SKILL.md) to create or convert warehouse
2. Or proceed to [adaptive-warehouse-monitor sub-skill](../skills/adaptive-warehouse-monitor/SKILL.md) to monitor existing Adaptive warehouse

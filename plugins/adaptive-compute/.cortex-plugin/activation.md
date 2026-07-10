# Adaptive Compute Plugin Activation

## Entry Conditions

The Adaptive Compute plugin is available to accounts that:
1. Operate on AWS (other clouds coming in future releases)
2. Are in a supported AWS region for Adaptive Warehouses (see below)
3. Have warehouse admin or equivalent role privileges
4. Are running Cortex Code version >= 2026-07 (Adaptive Warehouse GA date)

---

## Phase 0: AWS Region Check (Mandatory)

Before invoking any sub-skill, the plugin performs this check automatically. If your account is not on AWS, you will see:

```
❌ Adaptive Warehouses are available on AWS regions only.

Current deployment: <CLOUD> / <REGION>

Supported AWS regions (as of Jun 16, 2024 GA):
  • us-east-1 (N. Virginia)
  • us-west-2 (N. Oregon)
  • eu-west-1 (Ireland)
  • ap-southeast-1 (Singapore)
  • ap-southeast-2 (Sydney)

Next steps:
  1. If you're on Azure or GCP: Use the ops-monitor plugin for standard warehouse optimization.
  2. If you're on AWS but in an unsupported region: Contact Snowflake support for Adaptive Warehouse rollout timeline.
  3. If you're migrating to AWS: Plan migration to a supported region.
```

### Manual Check

To verify your region manually:

```sql
SELECT CURRENT_REGION() AS region, CURRENT_CLOUD() AS cloud;
```

**Expected output** (to proceed):
```
region: us-east-1 (or other supported AWS region)
cloud: AWS
```

---

## Supported AWS Regions

| Region | AWS Designation | Status |
|--------|-----------------|--------|
| N. Virginia | `us-east-1` | ✅ Supported |
| N. Oregon | `us-west-2` | ✅ Supported |
| Ireland | `eu-west-1` | ✅ Supported |
| Singapore | `ap-southeast-1` | ✅ Supported |
| Sydney | `ap-southeast-2` | ✅ Supported |

**All other AWS regions**: Support coming in future releases. Contact Snowflake support for timeline.

**Azure and GCP**: No Adaptive Warehouse support yet. Use `ops-monitor` skill for standard warehouse tuning.

---

## Lifecycle and Phase Gates

### Phase 0 (Entry Gate)
- **Check**: Cloud is AWS
- **Check**: Region is in supported list
- **Action**: If checks fail, block entry with clear error message and alternatives
- **Exit**: If checks pass, proceed to sub-skill selection

### Phase 1 (Sub-Skill Selection)
- **Options**: adaptive-warehouse-setup OR adaptive-warehouse-monitor
- **Gate**: No additional gating; both sub-skills are available on supported AWS regions

### Phase 2 (Sub-Skill Execution)
- **adaptive-warehouse-setup**: Creates or converts warehouse (no additional gates in Phase 1-4)
- **adaptive-warehouse-monitor**: Monitors existing Adaptive warehouse (no additional gates)

---

## Tethering Contract Verification

This plugin satisfies the expansion architecture's tethering contract:

- ✅ **Root SKILL.md** — Present at `plugins/adaptive-compute/SKILL.md` with router, positioning, cost examples, and region gating note
- ✅ **activation.md** — This file; documents entry conditions, phase gates, and AWS-only constraint
- ✅ **Sub-skill SKILL.md files** — Two sub-skills (`adaptive-warehouse-setup`, `adaptive-warehouse-monitor`) with full workflows
- ✅ **README.md** — Overview, use cases, quick start (AWS-only constraint upfront)
- ✅ **PREREQUISITES.md** — Account setup, region/edition requirements, cost examples
- ✅ **References** — `adaptive-vs-standard.md` (comparison and decision matrix)
- ✅ **Bidirectional cross-refs** — `plugins/ops-monitor/skills/self-healing-pipeline/SKILL.md` updated to mention adaptive-compute as alternative
- ✅ **skill-loader integration** — Will be added in batch Step 7

---

## Cortex Code Version Requirement

**Minimum version**: Cortex Code >= 2026-07

**Reason**: Adaptive Warehouse feature is GA as of Jun 16, 2024; Cortex Code support added in 2026-07 release.

**Check your version**:
```bash
cortex version
# Should output: cortex code 2026-07 or later
```

**If outdated**: Upgrade via `brew upgrade cortex-code` (macOS) or equivalent for your OS.

---

## Role and Permission Requirements

To use this plugin, your current Snowflake role must have:

### For adaptive-warehouse-setup:
- `CREATE WAREHOUSE` privilege (to create new Adaptive warehouse)
- `ALTER WAREHOUSE` privilege (to convert existing warehouse to Adaptive type)
- `USAGE` on database/schema where warehouse will be created/modified

**Verify**:
```sql
SHOW GRANTS TO ROLE <your_role>;
-- Look for: CREATE WAREHOUSE, ALTER WAREHOUSE, USAGE on DATABASE
```

### For adaptive-warehouse-monitor:
- `MONITOR` privilege on warehouse (or read access to `ACCOUNT_USAGE.WAREHOUSE_METERING_HISTORY`)
- Account-level role that can query `SNOWFLAKE.ACCOUNT_USAGE` views

**Verify**:
```sql
SHOW GRANTS TO ROLE <your_role>;
-- Look for: USAGE on SNOWFLAKE database, ability to query ACCOUNT_USAGE
```

### If permissions are missing:

Contact your account admin:
```sql
-- Admin can grant warehouse creation privilege
GRANT CREATE WAREHOUSE ON ACCOUNT TO ROLE <your_role>;
GRANT USAGE ON DATABASE SNOWFLAKE TO ROLE <your_role>;
```

---

## Activation Flags (Internal)

For Cortex Code's internal routing:

```yaml
plugin_name: adaptive-compute
version_required: cortex-code >= 2026-07
cloud_required: AWS
regions_supported:
  - us-east-1
  - us-west-2
  - eu-west-1
  - ap-southeast-1
  - ap-southeast-2
feature_gated: false
note: AWS-only as of GA Jun 16 2024; Azure/GCP support planned for future releases
```

---

## Troubleshooting Phase 0

**Problem**: "You are not on AWS" error.

**Solution**:
1. Verify your cloud: `SELECT CURRENT_CLOUD();`
2. If Azure or GCP: Use `ops-monitor` skill for warehouse tuning
3. If AWS but planning multi-cloud: Contact Snowflake sales for migration planning

**Problem**: "Your region is not supported" error.

**Solution**:
1. Verify region: `SELECT CURRENT_REGION();`
2. If unsupported AWS region: Check [Adaptive Warehouse documentation](https://docs.snowflake.com/en/user-guide/warehouses-adaptive) for rollout timeline
3. Alternatively: Migrate to supported region, or use standard warehouse with `ops-monitor`

**Problem**: Cortex Code version is outdated.

**Solution**:
1. Upgrade Cortex Code: `brew upgrade cortex-code` (macOS) or equivalent
2. Verify new version: `cortex version`
3. Retry sub-skill invocation

---

## Next Steps

Once Phase 0 checks pass:
- Proceed to [adaptive-warehouse-setup sub-skill](../skills/adaptive-warehouse-setup/SKILL.md) to create or convert warehouse
- Or proceed to [adaptive-warehouse-monitor sub-skill](../skills/adaptive-warehouse-monitor/SKILL.md) to monitor existing Adaptive warehouse

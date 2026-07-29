# Workload Identity Federation Plugin Activation

## Entry Conditions

The Workload Identity Federation plugin is available to accounts that:
1. Have WIF feature enabled (contact Snowflake support or check account preferences)
2. Operate on Business Critical edition or higher
3. Are in a supported region (see below)

---

## Phase 0: Prerequisite Checks

Before invoking any sub-skill, run these checks. If any fail, the plugin will not proceed.

### Check 1: Region Compatibility
```sql
SELECT CURRENT_REGION();
```

**Supported regions** (as of Jul 2026 GA):
- AWS: `us-east-1`, `us-west-2`, `eu-west-1`, `ap-southeast-1`, `ap-southeast-2`
- Azure: `eastus`, `westeurope`, `southeastasia`, `canadaeast`
- GCP: `us-central1`, `europe-west1`, `asia-southeast1`

**If your region is NOT listed above:**
```
❌ Workload Identity Federation is not available in your region (CURRENT_REGION = <region>).
   WIF is currently GA on AWS/Azure/GCP regions listed above.
   Please either:
   a) Migrate your Snowflake account to a supported region, or
   b) Use API keys or OAuth as a temporary authentication method (see key-and-secret-management).
```

### Check 2: Edition Requirement
```sql
SELECT CURRENT_ACCOUNT_EDITION();
```

**If edition is NOT `BUSINESS_CRITICAL` or higher:**
```
❌ Workflake Identity Federation requires Business Critical edition or higher.
   Current edition: <edition>.
   Contact Snowflake sales to upgrade or use API keys for now.
```

### Check 3: WIF Feature Enabled
```sql
SHOW PARAMETERS LIKE 'ENABLE_WORKLOAD_IDENTITY_FEDERATION' IN ACCOUNT;
```

**If parameter is `false` or not present:**
```
❌ Workload Identity Federation is not enabled in your account.
   Please contact Snowflake support to enable WIF for your account.
```

### Check 4: External Service Credentials Available
Before creating a WIF secret, you'll need credentials from your external service provider (AWS IAM role, GCP service account, Azure managed identity, or generic OIDC token endpoint).

- **AWS**: IAM role ARN and account ID
- **GCP**: Service account email and project ID
- **Azure**: Tenant ID, application (client) ID, and subscription ID
- **Generic OIDC**: Token endpoint URL and issuer URL

If you don't have these yet, halt and prepare them before invoking wif-setup.

---

## Entry Point: Arriving from key-and-secret-management?

If you searched for API keys or long-lived secret management and were routed to this plugin, **you're in the right place**. This is the recommended upgrade path:

| From | To | Why |
|------|----|----|
| API keys | WIF | Short-lived tokens, no shared secrets |
| OAuth (consuming external IdP) | Stay with `key-and-secret-management` | Different use case (Snowflake as consumer, not provider) |
| Static credentials in code | WIF | Eliminates hardcoded secrets |

---

## Activation Flags (Internal)

For Cortex Code's internal routing:

```yaml
plugin_name: workload-identity
version_required: snowflake-cli >= 1.2.0
edition_required: BUSINESS_CRITICAL
regions_supported:
  - aws: [us-east-1, us-west-2, eu-west-1, ap-southeast-1, ap-southeast-2]
  - azure: [eastus, westeurope, southeastasia, canadaeast]
  - gcp: [us-central1, europe-west1, asia-southeast1]
feature_gated: true
feature_name: WORKFLAKE_IDENTITY_FEDERATION
```

---

## Troubleshooting Phase 0

**Problem**: "Region not supported" error appears but you believe your region should be supported.

**Solution**: 
1. Contact Snowflake support to confirm WIF support for your region.
2. Alternatively, use API keys (`key-and-secret-management` skill) as a temporary workaround.

**Problem**: "Edition not supported" error.

**Solution**:
1. Verify your edition with `SELECT CURRENT_ACCOUNT_EDITION()`.
2. If you're on Standard or Business edition, contact sales to upgrade to Business Critical.
3. Alternatively, use OAuth or API keys for now.

**Problem**: "WIF feature not enabled" error.

**Solution**:
1. Contact Snowflake support to request WIF enablement for your account.
2. Provide your account ID and organization ID.
3. Support will enable the feature; this typically takes a few minutes.

---

## Next Steps

Once all Phase 0 checks pass:
- Proceed to [wif-setup sub-skill](../skills/wif-setup/SKILL.md) to configure your first WIF secret.

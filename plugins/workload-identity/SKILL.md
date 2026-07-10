---
name: workload-identity
description: Workload Identity Federation (WIF) plugin enabling service-to-service authentication using federated identity tokens instead of long-lived secrets.
---

# Workload Identity Federation Plugin

## Overview

Workload Identity Federation (WIF) enables **Snowflake as an OIDC provider**, allowing external services (AWS Lambda, GCP Cloud Functions, Azure Functions, etc.) to authenticate to Snowflake using short-lived federated identity tokens rather than long-lived API keys or secrets.

This is **fundamentally different from OAuth**, where Snowflake acts as a *consumer* of an external IdP. With WIF, Snowflake *issues* the tokens.

## When to Use This Plugin

| Scenario | Use WIF? | Alternative |
|----------|----------|-------------|
| External app needs to call Snowflake | ✅ Yes — issue federated token | API keys (less secure, long-lived) |
| Snowflake needs to call external service | ❌ No — use OAuth or specific connector | OAuth (`key-and-secret-management` skill) |
| Service account in AWS/GCP/Azure | ✅ Yes — native OIDC support | Managed identity + static API key |
| Lambda → Snowflake | ✅ Yes — perfect fit | Hard-coded credentials (anti-pattern) |
| Rotate credentials frequently | ✅ Yes — tokens auto-expire | Manual API key rotation |

**Not sure?** See `auth-patterns.md` for a comprehensive comparison table.

## Sub-Skills

### 🔧 [wif-setup](./skills/wif-setup/SKILL.md)
Set up Workload Identity Federation end-to-end:
1. Create WIF secret in Snowflake
2. Retrieve issuer URL
3. Configure external service (AWS IAM role, GCP service account, Azure managed identity, or generic OIDC)
4. Test token issuance and validation
5. Configure ongoing token refresh

**Supported providers:** AWS IAM, GCP Workload Identity, Azure Managed Identity, generic OIDC.

### 🔍 [wif-troubleshoot](./skills/wif-troubleshoot/SKILL.md)
Diagnose and fix WIF authentication failures:
- Token rejected by external service
- Secret not found or insufficient grants
- Issuer URL or audience mismatch
- Token expiry and refresh issues
- Audit failed authentication attempts

### ⏱️ [session-policy](./skills/session-policy/SKILL.md)
Create and manage Snowflake Session Policies (GA Apr 2026):
1. Choose policy strategy: max lifespan vs. UI-specific idle timeout
2. Create SESSION POLICY with constraints
3. Apply policy to role
4. Test and troubleshoot session expiration
5. Monitor active sessions and audit policy violations

**Use cases:** Enforce strict session expiration for compliance, protect against unattended UI sessions, enforce re-authentication policies.

---

## Quick Decision Tree

```
External service needs to authenticate to Snowflake?
│
├─ YES (Lambda, GCP Function, app in AWS/GCP/Azure)
│  └─ → Use WIF (this plugin)
│     └─ → Go to wif-setup sub-skill
│
└─ NO (Snowflake needs to authenticate to external service)
   └─ → Use OAuth or service-specific connector
      └─ → See key-and-secret-management skill
```

---

## Positioning vs. Related Patterns

| Pattern | Snowflake Role | Token Lifetime | Use This Plugin? |
|---------|-----------------|---|---|
| **Workload Identity Federation** | OIDC Provider | 5–60 min (default 5) | ✅ Yes → wif-setup |
| OAuth | OIDC Consumer | Varies (30 min–1 year) | ❌ No → key-and-secret-management |
| API Keys | Static | Indefinite (manual rotation) | ❌ No → security risk, use WIF instead |
| SAML | IdP Consumer | Session-based | ❌ No → setup-snowflake-sso |

---

## Architecture

### Snowflake Objects
- **`CREATE SECRET ... TYPE = WORKLOAD_IDENTITY_FEDERATION`** — registers a federated identity configuration with issuer URL and audience
- **`SYSTEM$ISSUE_WORKLOAD_IDENTITY_FEDERATION_TOKEN(<secret_name>)`** — SQL function to issue a short-lived token
- **`snow connection generate-workload-identity-token <connection>`** — CLI utility for programmatic token generation

### Token Flow
```
External Service (e.g., Lambda)
  │
  ├─ Reads local AWS credentials / service account key
  │
  ├─ Calls OIDC token endpoint on AWS / GCP / Azure
  │     (proves service identity to cloud provider)
  │
  ├─ Receives OIDC token (JWT with service account claims)
  │
  └─ Exchanges OIDC token → Snowflake WIF token
       (proves token issuer matches WIF secret configuration)
       │
       ├─ Snowflake verifies issuer & audience
       │
       └─ Returns short-lived Snowflake session token
            (service can now query Snowflake)
```

---

## Entry Points

### Arriving from `key-and-secret-management` skill?
You're in the right place! If you were setting up API keys or long-lived secrets and want a more secure alternative, **Workload Identity Federation is what you need**. OAuth is different (see auth-patterns.md comparison).

### Arriving from security/secrets training?
**Workload Identity Federation is the modern standard** for service-to-service authentication. API keys are legacy; long-lived credentials are high-risk. Start with wif-setup to configure your first WIF secret.

---

## Prerequisites Check

Before proceeding to wif-setup:
- ✅ Snowflake region supports WIF (see activation.md for list)
- ✅ Account edition ≥ Business Critical
- ✅ WIF feature enabled in your account (verified in Phase 0 of wif-setup)
- ✅ External service is AWS, GCP, Azure, or OIDC-compatible
- ✅ Service account credentials available locally (will not be shared with Snowflake)

---

## Next Steps

1. **Ready to set up WIF?** → [wif-setup sub-skill](./skills/wif-setup/SKILL.md)
2. **Troubleshooting an existing WIF secret?** → [wif-troubleshoot sub-skill](./skills/wif-troubleshoot/SKILL.md)
3. **Want to compare WIF to other auth patterns?** → [auth-patterns.md reference](./references/auth-patterns.md)
4. **First time? Check prerequisites** → [PREREQUISITES.md](./PREREQUISITES.md) + [README.md](./README.md)

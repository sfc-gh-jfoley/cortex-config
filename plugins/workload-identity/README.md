# Workload Identity Federation Plugin

## Overview

Workload Identity Federation (WIF) is Snowflake's solution for **service-to-service authentication without long-lived secrets**. Instead of provisioning API keys or passwords, external services (Lambda, Cloud Functions, containerized apps, etc.) authenticate to Snowflake using short-lived federated identity tokens issued by their cloud provider (AWS, GCP, Azure).

WIF launched **July 1, 2026 (GA)** and is the recommended authentication pattern for all new service-to-Snowflake integrations.

---

## The Problem WIF Solves

### ❌ Traditional Approach (Insecure)
```
API Key in Lambda Environment → hardcoded in code / secrets manager
                              → static, long-lived
                              → difficult to rotate
                              → high blast radius if exposed
```

### ✅ WIF Approach (Secure)
```
Lambda IAM Role (proof of identity) → AWS OIDC Token (dynamic, short-lived)
                                   → Snowflake WIF Secret (verifies AWS account)
                                   → Snowflake Session Token (5 min expiry, auto-refreshed)
```

**Benefits:**
- **No shared secrets** — Lambda proves identity to AWS, AWS issues token, Snowflake verifies token issuer
- **Auto-expiring tokens** — 5 minute default, no need for manual rotation
- **Cloud-native** — AWS IAM, GCP service account, Azure managed identity native support
- **Audit trail** — every token issuance logged, including failed attempts

---

## Use Cases

### 1. Lambda → Snowflake
```
AWS Lambda (role: lambda-exec)
  ├─ Assumes lambda-exec role at runtime (local to Lambda, no credentials exposed)
  ├─ Calls AWS OIDC endpoint (proves identity)
  ├─ Gets OIDC token with lambda-exec claims
  └─ Exchanges token → Snowflake WIF token
      ├─ Snowflake verifies AWS account in WIF secret matches
      └─ Lambda authenticated to Snowflake, inserts data
```

### 2. GCP Cloud Function → Snowflake
```
GCP Cloud Function (service account: my-function@project.iam.gserviceaccount.com)
  ├─ Calls GCP metadata server (proves identity)
  ├─ Gets OIDC token with service account claims
  └─ Exchanges token → Snowflake WIF token
      ├─ Snowflake verifies GCP project in WIF secret matches
      └─ Function authenticated to Snowflake
```

### 3. Kubernetes Pod (running on GCP GKE) → Snowflake
```
Pod with Workload Identity enabled (service account: my-sa@project.iam.gserviceaccount.com)
  ├─ Kubernetes admission webhook injects OIDC token
  ├─ Pod exchanges token → Snowflake WIF token
  └─ App authenticated to Snowflake
```

### 4. CI/CD Pipeline (GitHub Actions) → Snowflake
```
GitHub Actions Job (repo: my-org/my-repo)
  ├─ GitHub issues OIDC token with repo claims
  ├─ Job exchanges token → Snowflake WIF token
  └─ Deployment pipeline authenticated to Snowflake
```

---

## Authentication Pattern Comparison

| Pattern | Token Lifetime | Who Issues | Revocation | Secret Storage | Delegation | Audit Trail | Use WIF? |
|---------|---|---|---|---|---|---|---|
| **Workload Identity Federation** | 5–60 min | Cloud provider + Snowflake | Automatic (expiry) | Cloud native (IAM role) | Yes (scope to role/service account) | Full (per-token event) | ✅ **Yes** |
| API Keys | Indefinite | Snowflake user | Manual (revoke key) | Env var / secrets manager | Limited (static to key) | Per-query only | ❌ **No** — use WIF |
| OAuth | 30 min – 1 year | Third-party IdP | Provider-dependent | Refresh token stored | Yes (scope to user) | Per-session | ❌ **No** — for Snowflake-as-consumer |
| SAML | Session-based | IdP (Okta, Entra, etc.) | Session logout | None (browser only) | Yes (group-based) | Per-login | ❌ **No** — see setup-snowflake-sso |

---

## Supported Cloud Providers

- **AWS** — IAM roles (EC2, Lambda, ECS, any OIDC-compatible workload)
- **GCP** — Service accounts, Kubernetes pods (GKE), Cloud Functions
- **Azure** — Managed identities, Kubernetes (AKS), Container Instances
- **Generic OIDC** — GitHub Actions, GitLab CI, any OIDC token endpoint

---

## High-Level Flow

```
1. Set Up WIF Secret in Snowflake
   └─ CREATE SECRET ... TYPE = WORKLOAD_IDENTITY_FEDERATION
      ├─ Issuer URL (AWS, GCP, Azure STS endpoint, or custom OIDC issuer)
      ├─ Audience (Snowflake account identifier)
      └─ Provider-specific claims mapping (AWS account, GCP project, etc.)

2. Configure External Service
   ├─ AWS: Add Snowflake as trusted relying party in trust policy
   ├─ GCP: Link service account → Snowflake OIDC issuer
   ├─ Azure: Add federated credential with Snowflake issuer
   └─ Generic OIDC: Record issuer and audience with token provider

3. Test Token Issuance
   ├─ External service obtains cloud-native OIDC token
   └─ Calls Snowflake: SELECT SYSTEM$ISSUE_WORKLOAD_IDENTITY_FEDERATION_TOKEN('secret_name')
       └─ Returns Snowflake session token on success

4. Authenticate to Snowflake
   └─ Use session token in connection string
      └─ App is authenticated; queries proceed
      └─ Token auto-refreshes before expiry (configurable 5–60 min)
```

---

## Migration Path: API Keys → WIF

If you currently use static API keys:

| Step | Before (API Key) | After (WIF) | Effort |
|------|---|---|---|
| 1. Create credential | Generate key in Snowflake | Create WIF secret | **5 min** |
| 2. Configure external | Hardcode key in env var / config | Add issuer URL to cloud IAM | **10 min** |
| 3. Update app code | Use key in connection string | Call `SYSTEM$ISSUE_WORKLOAD_IDENTITY_FEDERATION_TOKEN()` or `snow connection gen-token` | **15 min** |
| 4. Test | Verify query succeeds | Verify token issued and query succeeds | **5 min** |
| 5. Deprecate | Remove API key from secrets manager | Revoke WIF secret (optional; can coexist) | **0 min** (optional) |

**Total effort: ~35 min for typical serverless app.**

---

## Risk Mitigation

### Risk: Confusion with OAuth
**Scenario**: User tries to use WIF to call third-party API (e.g., Salesforce) from Snowflake.  
**Mitigation**: WIF is for **Snowflake as OIDC provider**. To call external services, use OAuth (key-and-secret-management skill).

### Risk: Token Expiry
**Scenario**: Application caches token, doesn't refresh, token expires after 5 min, queries fail.  
**Mitigation**: wif-setup Phase 4 covers token refresh strategies; wif-troubleshoot covers diagnosis.

### Risk: Provider-Specific Config Errors
**Scenario**: WIF secret configured for AWS IAM but external service is GCP service account → token never validates.  
**Mitigation**: wif-setup Phase 1 has provider-specific branches; Phase 3 test catches mismatches.

---

## Next Steps

- **New to WIF?** Start with [wif-setup sub-skill](./skills/wif-setup/SKILL.md)
- **Troubleshooting?** Try [wif-troubleshoot sub-skill](./skills/wif-troubleshoot/SKILL.md)
- **Comparing authentication patterns?** See [auth-patterns.md](./references/auth-patterns.md)
- **Prerequisites not met?** Check [PREREQUISITES.md](./PREREQUISITES.md) and [activation.md](./.cortex-plugin/activation.md)

# Authentication Patterns: OAuth, API Keys, WIF, SAML

This reference guide compares authentication patterns to help you choose the right solution for your use case.

---

## Quick Comparison Table

| Pattern | Who Issues | Token Lifetime | Revocation | Secret Storage | Delegation | Audit Trail | Snowflake Role | When to Use |
|---------|---|---|---|---|---|---|---|---|
| **Workload Identity Federation** | Cloud provider + Snowflake | 5–60 min (auto-expiring) | Automatic (expiry) | Cloud-native IAM (no shared secret) | Yes (scope to service account) | Per-token (detailed) | OIDC Provider | Service-to-Snowflake (Lambda, GCP Functions, Kubernetes, CI/CD) |
| **API Keys** | Snowflake user | Indefinite (manual rotation) | Manual (revoke key) | Env var, secrets manager, code (❌ risky) | Limited (static) | Per-query only | None (legacy) | **Avoid** — use WIF instead |
| **OAuth 2.0** | Third-party IdP (Okta, Entra, Google, GitHub) | 30 min – 1 year | Provider-dependent | Refresh token | Yes (scope-based) | Per-session | OIDC Consumer | Snowflake calling external services (e.g., Salesforce API) |
| **SAML 2.0** | Identity Provider (Okta, Entra, Ping) | Session-based (browser) | Session logout | None (browser-managed) | Yes (group-based) | Per-login | IdP Consumer | User SSO into Snowflake (human users, not services) |

---

## Detailed Scenarios

### Scenario 1: Lambda → Snowflake (Insert Data)

```
Lambda needs to authenticate to Snowflake and insert data.
```

**What does Lambda have?**
- IAM role (assigned at runtime, not hardcoded)
- Local AWS credentials (temporary, auto-rotated by AWS)

**Best Pattern: Workload Identity Federation (WIF)**
```
Lambda (IAM role)
  └─ Calls AWS STS with local credentials
     └─ Gets AWS OIDC token with role claims
        └─ Exchanges with Snowflake WIF secret
           └─ Gets Snowflake session token
              └─ Inserts data into Snowflake
```

**Why WIF?**
- ✅ No API key hardcoded
- ✅ Token auto-expires after 5 min
- ✅ AWS rotates credentials automatically
- ✅ Full audit trail per token
- ✅ Easy to revoke: delete WIF secret

**NOT OAuth or SAML**: Those are for consuming external IdPs, not issuing tokens to Snowflake.

**NOT API keys**: Long-lived, high blast radius, manual rotation required.

---

### Scenario 2: Snowflake → Salesforce API

```
Stored procedure or Snowpark Python needs to call Salesforce API from Snowflake.
```

**What does Snowflake have?**
- Snowflake role and user
- Need to call external service (Salesforce) as a consumer

**Best Pattern: OAuth (key-and-secret-management skill)**
```
Snowflake procedure
  └─ Calls Salesforce OAuth endpoint with client_id + client_secret
     └─ Gets OAuth access token from Salesforce
        └─ Uses token to call Salesforce API
           └─ Gets data, inserts into Snowflake table
```

**Why OAuth?**
- ✅ Snowflake is the OIDC *consumer* (standard pattern)
- ✅ Salesforce issues access token
- ✅ Token expires; refresh token handles renewal
- ✅ Credentials stored in Snowflake secrets manager

**NOT WIF**: WIF is for Snowflake as provider, not consumer.

**NOT API keys**: Possible but requires storing Salesforce API key in Snowflake; OAuth is better (scoped, temporary access).

---

### Scenario 3: User Login to Snowflake (Human User)

```
Human user (in Okta or Entra AD) logs into Snowflake via SSO.
```

**What does user have?**
- Identity in corporate IdP (Okta, Entra, Ping)
- Browser

**Best Pattern: SAML 2.0 (setup-snowflake-sso skill)**
```
User browser
  └─ Redirects to Snowflake login
     └─ Snowflake redirects to Okta (via SAML redirect)
        └─ User authenticates to Okta
           └─ Okta posts SAML assertion to Snowflake
              └─ Snowflake creates session
                 └─ User logged in
```

**Why SAML?**
- ✅ Browser-native (no token management by user)
- ✅ Group-based access control (Okta groups → Snowflake roles)
- ✅ MFA enforcement via IdP
- ✅ Single logout: logout from Okta → logout from Snowflake

**NOT OAuth**: OAuth is for service-to-service or Snowflake as consumer, not user SSO.

**NOT WIF**: WIF is for service-to-Snowflake, not human users.

**NOT API keys**: Obviously not for browser-based user login.

---

### Scenario 4: GitLab CI → Snowflake (Deploy Pipeline)

```
GitLab CI job needs to authenticate to Snowflake and run migrations.
```

**What does job have?**
- GitLab service account (OIDC-enabled in newer GitLab versions)
- CI/CD environment

**Best Pattern: Workload Identity Federation (WIF) with generic OIDC**
```
GitLab CI job
  └─ Calls GitLab OIDC endpoint
     └─ Gets GitLab OIDC token with job claims (project, branch, etc.)
        └─ Exchanges with Snowflake WIF secret
           └─ Gets Snowflake session token
              └─ Runs dbt seed / deployment commands
```

**Why WIF?**
- ✅ No API key in GitLab CI variables (more secure)
- ✅ Token scoped to job and project
- ✅ Auto-expiring (5 min default)
- ✅ Revoke by deleting WIF secret

**Alternative: API Key in GitLab CI Variables**
- Possible but higher risk (long-lived, static)
- Use WIF if GitLab version supports OIDC

---

### Scenario 5: Microservice in Kubernetes (GKE) → Snowflake

```
Microservice pod in Google Kubernetes Engine needs to access Snowflake.
```

**What does pod have?**
- Kubernetes service account
- GKE Workload Identity (federated identity)

**Best Pattern: Workload Identity Federation (WIF) with GCP**
```
Pod (GKE service account)
  └─ GKE admission webhook injects OIDC token
     └─ Pod exchanges with Snowflake WIF secret
        └─ Gets Snowflake session token
           └─ Queries Snowflake from pod
```

**Why WIF?**
- ✅ Kubernetes-native (no secret injection needed)
- ✅ GCP Workload Identity handles OIDC federation
- ✅ Auto-expiring tokens
- ✅ Pod can be ephemeral (no persistent credentials)

**Not OAuth**: OAuth is for consuming external IdPs, not Kubernetes service accounts.

---

## Migration Paths

### Path 1: API Keys → WIF

**Timeline**: ~30 min for typical app.

```
Current State:
  └─ API key in env var or secrets manager
     └─ App connects to Snowflake with key

Target State:
  └─ WIF secret in Snowflake
     └─ App exchanges cloud-native token → Snowflake session token
        └─ App connects to Snowflake with session token
```

**Steps**:
1. Create WIF secret in Snowflake (wif-setup Phase 1)
2. Configure cloud provider (wif-setup Phase 2)
3. Update app to call `SYSTEM$ISSUE_WORKLOAD_IDENTITY_FEDERATION_TOKEN()` or `snow connection gen-token` (wif-setup Phase 3)
4. Remove API key (optional; can coexist during transition)

**Benefits**:
- No more hardcoded secrets in code or env vars
- Token auto-expires; no manual rotation
- Better audit trail
- Cloud-native credential management

---

### Path 2: OAuth (Snowflake Consumer) ← → WIF (Snowflake Provider)

**These are opposite patterns; do NOT mix.**

```
Scenario A: Snowflake calling external API (e.g., Salesforce)
  └─ Use OAuth (key-and-secret-management skill)
  └─ Snowflake is consumer of Salesforce's OIDC provider

Scenario B: External service calling Snowflake (e.g., Lambda)
  └─ Use WIF (this plugin)
  └─ Snowflake is provider of OIDC tokens
```

**If you're confused**, check:
- "Does Snowflake need to *call* an external service?" → OAuth
- "Does an external service need to *call* Snowflake?" → WIF

---

### Path 3: SAML (User SSO) ← → WIF (Service Auth)

**Different use cases; can coexist.**

```
User SSO:
  └─ Okta SAML → Snowflake (human user login)
  └─ Use setup-snowflake-sso skill

Service Auth:
  └─ Lambda WIF → Snowflake (service login)
  └─ Use workload-identity plugin (this skill)
```

**A single Snowflake account can have both:**
- Users log in via SAML (SSO)
- Services authenticate via WIF
- Both mechanisms work simultaneously

---

## Token Lifetime and Expiry Handling

| Pattern | Token Lifetime | Refresh Mechanism | Auto-Renew | Best For |
|---------|---|---|---|---|
| WIF | 5–60 min | Token endpoint | Yes (configurable) | Short-lived, frequent-refresh scenarios |
| API Keys | N/A (indefinite) | Manual revoke | No | Static credentials (legacy, not recommended) |
| OAuth | 30 min – 1 year (provider-dependent) | Refresh token | Yes (if refresh token provided) | External service integrations |
| SAML | Session-based (30 min – 8 hrs typical) | Browser session | No | User SSO (handled by browser) |

**WIF Token Refresh Example (in application code)**:
```python
# Get initial token
token = snowflake_api.issue_wif_token('wif-secret-name')
print(f"Token expires in: {token.expires_in} seconds")  # e.g., 300 (5 min)

# Use token for queries
while True:
    try:
        conn.query("SELECT 1")
    except TokenExpiredError:
        # Refresh token automatically
        token = snowflake_api.issue_wif_token('wif-secret-name')
```

---

## Compliance and Audit Considerations

| Compliance Requirement | API Keys | OAuth | WIF | SAML |
|---|---|---|---|---|
| **No shared secrets** | ❌ | ✅ | ✅ | ✅ |
| **Auto-expiring tokens** | ❌ | ✅ (if short-lived) | ✅ | ✅ (session-based) |
| **Detailed audit log** | ❌ (per-query only) | ⚠️ (per-refresh) | ✅ (per-token) | ✅ (per-login) |
| **Revocation possible** | ✅ (slow) | ✅ (fast, provider-dependent) | ✅ (delete secret) | ✅ (logout) |
| **MFA support** | ❌ | ⚠️ (provider-dependent) | ❌ (OAuth pattern, not WIF) | ✅ (IdP-enforced) |
| **GDPR/HIPAA compatible** | ⚠️ (shared secrets risky) | ✅ | ✅ | ✅ |

**Recommendation for compliance**: Use WIF for service-to-service, SAML for user SSO, OAuth for external integrations. Avoid API keys.

---

## Decision Tree: Which Pattern to Use?

```
Q1: Is this for a human user?
  ├─ YES → Use SAML (setup-snowflake-sso)
  └─ NO → Go to Q2

Q2: Is this for Snowflake calling an external service?
  ├─ YES → Use OAuth (key-and-secret-management)
  └─ NO → Go to Q3

Q3: Is this for an external service calling Snowflake?
  ├─ YES → Use WIF (workload-identity, THIS PLUGIN)
  └─ NO → You may need a custom pattern; contact support

Q4 (if using WIF): Which cloud provider?
  ├─ AWS (Lambda, EC2, ECS) → AWS IAM setup (Phase 1 of wif-setup)
  ├─ GCP (Cloud Functions, GKE) → GCP service account setup (Phase 1)
  ├─ Azure (Functions, AKS) → Azure managed identity setup (Phase 1)
  └─ Other (GitHub Actions, GitLab CI) → Generic OIDC setup (Phase 1)
```

---

## Troubleshooting: Which Pattern Am I Using?

**Symptom**: "I'm not sure if WIF, OAuth, or API keys is right for my use case."

**Quick questions**:
1. Is a *human* logging in? → SAML
2. Is *Snowflake* calling an external API? → OAuth
3. Is an *external service* calling *Snowflake*? → WIF
4. Am I currently using an API key? → Migrate to WIF

**Still unsure?** See [Root Cause Analysis section of wif-troubleshoot](../skills/wif-troubleshoot/SKILL.md) or contact your security team.

---

## Next Steps

- **Setting up WIF?** → [wif-setup sub-skill](../skills/wif-setup/SKILL.md)
- **Troubleshooting WIF?** → [wif-troubleshoot sub-skill](../skills/wif-troubleshoot/SKILL.md)
- **Setting up OAuth?** → `key-and-secret-management` skill
- **Setting up user SSO?** → `setup-snowflake-sso` skill

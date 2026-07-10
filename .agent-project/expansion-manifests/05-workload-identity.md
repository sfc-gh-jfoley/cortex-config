# Track 5: Workload Identity Federation Plugin Expansion

## Overview
New plugin `plugins/workload-identity/` supporting Workload Identity Federation (Jul 1 GA).

Workload Identity Federation (WIF) enables Snowflake to act as an OIDC provider, allowing external services to authenticate to Snowflake using federated identity tokens rather than long-lived API keys or secrets. This is fundamentally different from OAuth (where Snowflake is the consumer of an external IdP).

## Architecture

### New Snowflake Objects
- `CREATE SECRET ... TYPE = WORKLOAD_IDENTITY_FEDERATION` — register federated identity configuration
- `SYSTEM$ISSUE_WORKLOAD_IDENTITY_FEDERATION_TOKEN(<secret_name>)` — issue short-lived token for external service
- `snow connection generate-workload-identity-token <connection>` — CLI utility for token generation

### Sub-Skills
- `wif-setup`: Create WIF secret → retrieve issuer URL → configure external service → test token
- `wif-troubleshoot`: Diagnose expired tokens, issuer mismatches, missing grants

### Plugin Structure
```
plugins/workload-identity/
├── SKILL.md (router)
├── .cortex-plugin/
│   └── activation.md
├── README.md
├── PREREQUISITES.md
├── references/
│   └── auth-patterns.md (comparison: OAuth, API keys, WIF, SAML)
├── skills/
│   ├── wif-setup/
│   │   └── SKILL.md
│   └── wif-troubleshoot/
│       └── SKILL.md
```

**Total new files: 8**

## What to Build

### Root SKILL.md (Router)
- Positioning: Snowflake as OIDC provider (not OAuth consumer)
- Decision tree: when to use WIF vs. API keys vs. OAuth
- Links to both sub-skills
- Provider-specific routing (AWS, GCP, Azure, generic OIDC)

### activation.md
- Entry conditions: WIF feature enabled in account
- Phase 0 checks: verify Snowflake region supports WIF, Snowflake edition ≥ Business Critical

### README.md
- Overview of Workload Identity Federation
- Use case: service-to-service authentication without shared secrets
- Comparison table: OAuth vs. WIF vs. API keys (what each solves for)
- Supported providers: AWS IAM, GCP Workload Identity, Azure Managed Identity, generic OIDC

### PREREQUISITES.md
- Account activation and licensing
- CLI version requirement: `snow` ≥ 1.2.0 (example version; verify actual)
- External service prerequisites per provider (AWS IAM role, GCP service account, Azure managed identity, etc.)

### references/auth-patterns.md
- Comprehensive comparison table: OAuth, API keys, WIF, SAML
- Dimensions: token lifetime, revocation mechanism, secret storage, delegation model, audit trail
- When to pick each pattern
- Migration path from API keys → WIF

### wif-setup/SKILL.md
- Phase 0: Region and prerequisite checks
  - `SELECT CURRENT_REGION()` — confirm WIF-compatible region
  - Account edition check
  - External service access verification
- Phase 1: Create WIF secret (provider-specific branches: AWS / GCP / Azure / generic OIDC)
  - `CREATE SECRET ... TYPE = WORKLOAD_IDENTITY_FEDERATION`
  - Issuer URL retrieval
  - Provider-specific claims mapping
- Phase 2: Configure external service
  - Add issuer URL and audience to external service trust policy
  - Provider-specific: AWS trust policy, GCP service account binding, Azure federated credential
- Phase 3: Test token issuance
  - `SELECT SYSTEM$ISSUE_WORKLOAD_IDENTITY_FEDERATION_TOKEN('secret_name')`
  - Validate token format and expiry
  - Verify external service can consume token
- Phase 4: Set up ongoing token refresh
  - If calling from application: periodic token refresh loop
  - If CLI-based: `snow connection generate-workload-identity-token` caching strategy

### wif-troubleshoot/SKILL.md
- Phase 1: Symptom diagnosis
  - Token rejected by external service → issuer URL mismatch, audience mismatch, expired
  - `snow connection` returns auth error → secret not found, insufficient grants
  - External service cannot find issuer → issuer URL not propagated, network access issue
- Phase 2: Inspect WIF configuration
  - Query secret metadata
  - Verify issuer URL matches external service configuration
  - Check grants on role that owns secret
- Phase 3: Fix and retry
  - Update secret if issuer/audience wrong
  - Grant required role to service account
  - Refresh token and test
- Phase 4: Audit and monitoring
  - Query QUERY_HISTORY for WIF-related activity
  - AUTHENTICATION_LOG for failed token issuance
  - Alert on repeated token failures (potential credential misuse)

## Risks & Mitigations

### Risk: Confusion with OAuth
**Impact**: Users attempt to use WIF for "Snowflake as consumer" scenarios (e.g., Snowflake calling a third-party API), where OAuth is correct.  
**Mitigation**: 
- Root SKILL.md and README.md both have prominent positioning: "Snowflake as OIDC provider" vs. OAuth
- auth-patterns.md comparison table makes distinction explicit
- If user arrives from `key-and-secret-management` looking for OAuth: activation.md explicitly says "arrived from key-and-secret-management? You're in the right place. OAuth is different; see auth-patterns.md."

### Risk: Provider-Specific Configuration Drift
**Impact**: WIF secret is configured for AWS IAM, but external service is GCP service account → token never validates.  
**Mitigation**: wif-setup Phase 1 has provider-specific branches; Phase 2 explicitly documents provider-specific trust policy updates; Phase 3 test is provider-agnostic (any issuer/audience mismatch caught here)

### Risk: Token Expiry and Refresh Not Documented
**Impact**: Application uses initial token successfully, but fails when token expires and refresh is needed.  
**Mitigation**: wif-setup Phase 4 addresses ongoing refresh; wif-troubleshoot Phase 4 includes monitoring for repeated token failures

### Risk: Insufficient Grants
**Impact**: User creates WIF secret in one role, but service account doesn't have USAGE privilege → token cannot be issued.  
**Mitigation**: wif-troubleshoot Phase 2 includes grant inspection; wif-setup Phase 4 includes verification step

## Breaking Changes
**None for existing skills.** New plugin is standalone and does not modify existing code paths.

**Risk in bundled `key-and-secret-management`**: The bundled skill has no awareness of `TYPE = WORKLOAD_IDENTITY_FEDERATION` as a secret type → users creating WIF secrets may hit dead ends in that skill. Mitigation: activation.md positioning section explicitly addresses this carve-out.

## Cross-Manifest Dependencies
- **Outbound**: references `key-and-secret-management` (positions relative to OAuth, API keys)
- **Inbound**: None (standalone plugin)

## Verification Checklist (Tethering Contract)
- [ ] Plugin directory exists: `plugins/workload-identity/`
- [ ] Root SKILL.md present and routes to two sub-skills
- [ ] `activation.md` documents entry conditions and region/edition checks
- [ ] Both sub-skill SKILL.md files exist with provider-specific branches
- [ ] README.md explains WIF positioning and comparison to OAuth/API keys
- [ ] PREREQUISITES.md documents CLI version and external service requirements per provider
- [ ] auth-patterns.md reference file exists and includes OAuth vs. WIF distinction
- [ ] Bidirectional cross-reference in `key-and-secret-management/SKILL.md` created (optional; explicit positioning in wif activation.md sufficient)
- [ ] No modification to skill-loader yet (batch step 7)

## Files to Create
1. `plugins/workload-identity/SKILL.md` (router)
2. `plugins/workload-identity/.cortex-plugin/activation.md`
3. `plugins/workload-identity/README.md`
4. `plugins/workload-identity/PREREQUISITES.md`
5. `plugins/workload-identity/references/auth-patterns.md`
6. `plugins/workload-identity/skills/wif-setup/SKILL.md`
7. `plugins/workload-identity/skills/wif-troubleshoot/SKILL.md`

## Files to Modify
None (standalone plugin; no cross-references required from existing skills in phase 0-1).

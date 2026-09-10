---
name: wif-troubleshoot
description: Diagnose and fix Workload Identity Federation issues. Token rejected, insufficient grants, issuer mismatch, expiry, and audit logging.
---

# WIF Troubleshoot Sub-Skill

Diagnose and resolve Workload Identity Federation (WIF) authentication failures.

## Overview

This sub-skill guides you through:
1. **Phase 1**: Symptom diagnosis (identify what's failing)
2. **Phase 2**: Inspect WIF configuration (check secret and grants)
3. **Phase 3**: Fix and retry (apply corrective action)
4. **Phase 4**: Audit and monitoring (detect future issues early)

---

## Phase 1: Symptom Diagnosis

### Symptom 1: Token Rejected by External Service

**Error Message Examples:**
- AWS: `Invalid token signature` / `Token expired`
- GCP: `Invalid OIDC token` / `Audience mismatch`
- Azure: `Token not valid for audience` / `Issuer not recognized`
- Generic OIDC: `Token validation failed`

**Root Causes:**
- Issuer URL in WIF secret doesn't match external service configuration
- Audience claim in token doesn't match expected audience
- Token has expired (> 5 min old)
- External service trust policy not updated to accept Snowflake issuer

**Diagnosis:**

1. **Check token expiry time:**
   ```sql
   -- Decode token and check exp claim (should be within 5 min of issue time)
   SELECT SYSTEM$ISSUE_WORKLOAD_IDENTITY_FEDERATION_TOKEN('wif_secret_name') AS token;
   ```
   
   If token is > 5 min old, it's expired. → **Fix**: Issue fresh token.

2. **Check issuer URL in secret:**
   ```sql
   SELECT SYSTEM$GET_SECRET_ISSUER_URL('wif_secret_name') AS issuer_url;
   ```
   
   Compare this URL with what's configured in external service. → **Fix**: Match URLs exactly (see Phase 3).

3. **Check audience in token:**
   ```python
   import json
   import base64
   
   token = "<token-from-sql-above>"
   parts = token.split('.')
   payload = json.loads(base64.urlsafe_b64decode(parts[1] + '=='))
   print(f"Audience in token: {payload.get('aud')}")
   ```
   
   Compare with audience configured in external service. → **Fix**: Ensure audiences match.

4. **Verify external service trust policy:**
   - **AWS**: Check IAM role trust policy includes Snowflake OIDC issuer and audience condition
   - **GCP**: Verify Workload Identity Pool provider issuer and service account linkage
   - **Azure**: Confirm federated credential issuer and subject match Snowflake values
   - **Generic OIDC**: Validate trust policy at OIDC provider

---

### Symptom 2: "Secret Not Found" or "Insufficient Privileges"

**Error Message Examples:**
- `Secret 'wif_secret_name' does not exist or not authorized`
- `Insufficient privileges on secret`
- `USAGE privilege missing`

**Root Causes:**
- Secret doesn't exist in current schema
- Current role lacks `USAGE` privilege on secret
- Secret is in a different database/schema than where you're querying

**Diagnosis:**

1. **Verify secret exists:**
   ```sql
   SHOW SECRETS IN SCHEMA current_schema();
   ```
   
   Look for your secret name (e.g., `wif_aws_lambda`). → **Fix**: Create secret if missing (see wif-setup).

2. **Check current role and schema:**
   ```sql
   SELECT CURRENT_ROLE(), CURRENT_DATABASE(), CURRENT_SCHEMA();
   ```
   
   Verify you're in the correct database/schema where secret was created.

3. **Check grants on secret:**
   ```sql
   SHOW GRANTS ON SECRET <secret_name>;
   ```
   
   Verify `USAGE` is granted to your role. → **Fix**: Grant privilege (see Phase 3).

---

### Symptom 3: External Service Cannot Find Issuer

**Error Message Examples:**
- `Issuer URL not found` / `Issuer not accessible`
- `HTTP 404 on OIDC endpoint`
- `Cannot resolve hostname`

**Root Causes:**
- Issuer URL not propagated to external service configuration
- Network access blocked (firewall, proxy, security group)
- Issuer URL has typo or wrong URL format

**Diagnosis:**

1. **Verify issuer URL in Snowflake:**
   ```sql
   SELECT SYSTEM$GET_SECRET_ISSUER_URL('wif_secret_name') AS issuer_url;
   ```

2. **Check external service configuration:**
   - **AWS**: IAM trust policy should reference `arn:aws:iam::ACCOUNT:oidc-provider/oidc.snowflakecomputing.com`
   - **GCP**: Workload Identity Provider should list `https://oidc.snowflakecomputing.com` as issuer
   - **Azure**: Federated credential should show `https://oidc.snowflakecomputing.com` as issuer
   - **Generic OIDC**: Trust policy should reference issuer URL

3. **Test network access to issuer:**
   ```bash
   # From your workload (Lambda, Cloud Function, etc.)
   curl -I https://oidc.snowflakecomputing.com/.well-known/openid-configuration
   # Should return HTTP 200 OK
   ```

   If blocked, work with security/network team to allowlist endpoint.

---

### Symptom 4: Token Refresh Failing

**Error Message Examples:**
- `Token expired and refresh failed`
- `Cannot call SYSTEM$ISSUE_WORKLOAD_IDENTITY_FEDERATION_TOKEN() repeatedly`
- `Rate limit exceeded on token endpoint`

**Root Causes:**
- Application not calling `SYSTEM$ISSUE_WORKLOAD_IDENTITY_FEDERATION_TOKEN()` before token expires
- Snowflake token endpoint rate-limited (too many requests)
- Application logic doesn't handle token refresh

**Diagnosis:**

1. **Check token expiry handling in your app:**
   ```python
   # Look for refresh logic in your code
   if token_expiry_time < time.time():
       token = issue_new_token()  # Should refresh before expiry
   ```

2. **Check token issuance rate:**
   ```sql
   -- Query QUERY_HISTORY to see token issuance patterns
   SELECT
     USER_NAME,
     QUERY_TEXT,
     START_TIME,
     COUNT(*) as count
   FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
   WHERE QUERY_TEXT LIKE '%SYSTEM$ISSUE_WORKLOAD_IDENTITY_FEDERATION_TOKEN%'
   GROUP BY USER_NAME, QUERY_TEXT, START_TIME
   HAVING COUNT(*) > 10  -- More than 10 per minute might indicate rate limit
   ORDER BY START_TIME DESC;
   ```

   If seeing rapid repeated calls, → **Fix**: Implement token caching (see wif-setup Phase 4).

---

## Phase 2: Inspect WIF Configuration

### Inspection 1: Secret Metadata

```sql
-- View secret properties
DESCRIBE SECRET wif_secret_name;

-- Expected output includes:
-- - TYPE: WORKLOAD_IDENTITY_FEDERATION
-- - ENABLED: true
-- - ISSUER_URL: https://oidc.snowflakecomputing.com
-- - AUDIENCE: snowflake:account:YOUR_ACCOUNT_ID
-- - EXTERNAL_SERVICE_PRINCIPAL: (role/service account identifier)
-- - EXTERNAL_SERVICE_PRINCIPAL_TYPE: AWS_ROLE / GCP_SERVICE_ACCOUNT / AZURE_APPLICATION_ID / OIDC_SUBJECT_IDENTIFIER
```

### Inspection 2: Grants

```sql
-- Check who can use this secret
SHOW GRANTS ON SECRET wif_secret_name;

-- Expected: USAGE granted to service account role or user roles
```

If `USAGE` is not granted:
```sql
-- Grant privilege
GRANT USAGE ON SECRET wif_secret_name TO ROLE service_account_role;
```

### Inspection 3: Test Token Issuance

```sql
-- Issue a test token
SELECT SYSTEM$ISSUE_WORKLOAD_IDENTITY_FEDERATION_TOKEN('wif_secret_name') AS test_token;

-- Decode and inspect token:
-- - iss: should match ISSUER_URL
-- - aud: should match AUDIENCE
-- - sub: should match EXTERNAL_SERVICE_PRINCIPAL
-- - exp: should be ~5 min in future
-- - iat: should be current time
```

### Inspection 4: Compare Configurations

```sql
-- For AWS: Compare Snowflake secret with IAM trust policy
-- For GCP: Compare Snowflake secret with Workload Identity Pool settings
-- For Azure: Compare Snowflake secret with federated credential

-- Checklist:
-- [ ] Issuer URL matches?
-- [ ] Audience matches?
-- [ ] Service principal (role/account) matches?
-- [ ] Token not expired?
```

---

## Phase 3: Fix and Retry

### Fix 1: Issuer/Audience Mismatch

**Symptom**: Token validation fails with "issuer not recognized" or "audience mismatch".

**Corrective Action:**

1. Get the correct issuer URL from Snowflake:
   ```sql
   SELECT SYSTEM$GET_SECRET_ISSUER_URL('wif_secret_name') AS issuer_url;
   ```

2. Update external service configuration to use this exact URL:
   - **AWS**: Update IAM trust policy `oidc-provider/` entry
   - **GCP**: Update Workload Identity Pool provider issuer
   - **Azure**: Update federated credential issuer
   - **Generic OIDC**: Update OIDC provider configuration

3. Retry token exchange:
   ```sql
   SELECT SYSTEM$ISSUE_WORKLOAD_IDENTITY_FEDERATION_TOKEN('wif_secret_name') AS token;
   ```

### Fix 2: Insufficient Grants

**Symptom**: "Insufficient privileges" or "Secret not authorized".

**Corrective Action:**

1. Identify the role/user that needs access:
   ```sql
   SELECT CURRENT_USER(), CURRENT_ROLE();
   ```

2. Grant `USAGE` on secret:
   ```sql
   GRANT USAGE ON SECRET wif_secret_name TO ROLE <role_name>;
   ```

3. Retry token issuance:
   ```sql
   SELECT SYSTEM$ISSUE_WORKLOAD_IDENTITY_FEDERATION_TOKEN('wif_secret_name') AS token;
   ```

### Fix 3: External Service Not Configured

**Symptom**: External service cannot validate token.

**Corrective Action:**

1. Verify external service has Snowflake OIDC issuer in trust policy:
   - **AWS**: Add OIDC provider and trust relationship
   - **GCP**: Create Workload Identity Provider and link service account
   - **Azure**: Create federated credential on app registration
   - **Generic OIDC**: Configure issuer at OIDC token provider

2. Test from external service:
   ```bash
   # From Lambda, Cloud Function, etc.:
   curl -X POST https://your-snowflake-account.snowflakecomputing.com/api/v2/statements \
     -H "Authorization: Bearer <wif_token>" \
     -H "Content-Type: application/json" \
     -d '{"statement": "SELECT 1"}'
   ```

### Fix 4: Token Expiry

**Symptom**: "Token expired" or queries fail after 5 minutes.

**Corrective Action:**

1. Implement token refresh in application (see wif-setup Phase 4):
   ```python
   # Refresh token before expiry
   if time.time() > token_expiry - 30:  # 30 sec buffer
       token = issue_fresh_wif_token()
   ```

2. Set up automated refresh task:
   ```sql
   CREATE TASK refresh_wif_token
     WAREHOUSE = compute_wh
     SCHEDULE = 'USING CRON 0 */4 * * * UTC'
   AS
     INSERT INTO wif_token_cache
     SELECT
       SYSTEM$ISSUE_WORKLOAD_IDENTITY_FEDERATION_TOKEN('wif_secret_name'),
       CURRENT_TIMESTAMP,
       DATEADD(minute, 5, CURRENT_TIMESTAMP);
   
   ALTER TASK refresh_wif_token RESUME;
   ```

### Fix 5: Service Principal Mismatch

**Symptom**: Token rejected with "principal not recognized" or "role not authorized".

**Corrective Action:**

1. Verify service principal in secret:
   ```sql
   DESCRIBE SECRET wif_secret_name;
   ```

2. Ensure external service principal exactly matches:
   - **AWS**: Role ARN (e.g., `arn:aws:iam::123456789012:role/lambda-exec`)
   - **GCP**: Service account email (e.g., `sa@project.iam.gserviceaccount.com`)
   - **Azure**: Application client ID
   - **Generic OIDC**: Subject identifier

3. If incorrect, recreate secret:
   ```sql
   DROP SECRET wif_secret_name;
   CREATE SECRET wif_secret_name
     TYPE = WORKLOAD_IDENTITY_FEDERATION
     ENABLED = true
     ISSUER_URL = '...'
     AUDIENCE = '...'
     EXTERNAL_SERVICE_PRINCIPAL = '<correct-principal>'
     EXTERNAL_SERVICE_PRINCIPAL_TYPE = '<type>';
   ```

---

## Phase 4: Audit and Monitoring

### Audit 1: Token Issuance Events

```sql
-- Query QUERY_HISTORY for token issuance
SELECT
  USER_NAME,
  QUERY_TEXT,
  START_TIME,
  EXECUTION_TIME,
  BYTES_SCANNED,
  ERROR_MESSAGE
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE QUERY_TEXT LIKE '%SYSTEM$ISSUE_WORKLOAD_IDENTITY_FEDERATION_TOKEN%'
  AND START_TIME > DATEADD(hour, -24, CURRENT_TIMESTAMP)
ORDER BY START_TIME DESC;
```

**Look for:**
- Repeated failures (same error message)
- Unusual timing (tokens issued at non-refresh intervals)
- Error escalation (new error types appearing)

### Audit 2: Authentication Failures

```sql
-- Query AUTHENTICATION_LOG for WIF-related failures
SELECT
  TIMESTAMP,
  USER_NAME,
  CLIENT_IP,
  AUTHENTICATION_METHOD,
  ERROR_CODE,
  ERROR_MESSAGE
FROM SNOWFLAKE.ACCOUNT_USAGE.AUTHENTICATION_LOG
WHERE AUTHENTICATION_METHOD LIKE '%WORKLOAD_IDENTITY%'
  OR ERROR_MESSAGE LIKE '%WIF%'
  AND TIMESTAMP > DATEADD(hour, -24, CURRENT_TIMESTAMP)
ORDER BY TIMESTAMP DESC;
```

**Look for:**
- Repeated failed authentication from same IP (potential attacker)
- Geographic anomalies (authentication from unexpected region)
- Service principal changes (may indicate compromise)

### Monitoring 1: Set Up Alert on Token Failures

```sql
-- Create alert for repeated token issuance failures
CREATE ALERT wif_token_failure_alert
  WAREHOUSE = alert_warehouse
  CONDITION = (
    SELECT COUNT(*) AS failure_count
    FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
    WHERE QUERY_TEXT LIKE '%SYSTEM$ISSUE_WORKLOAD_IDENTITY_FEDERATION_TOKEN%'
      AND ERROR_MESSAGE IS NOT NULL
      AND START_TIME > DATEADD(minute, -10, CURRENT_TIMESTAMP)
    HAVING COUNT(*) > 5  -- Alert if > 5 failures in 10 min
  )
  THEN CALL SYSTEM$SEND_EMAIL(
    'security-team@company.com',
    'WIF Token Issuance Failures Detected',
    'Multiple WIF token issuance failures detected. Check QUERY_HISTORY.'
  );
```

### Monitoring 2: Token Refresh Rate

```sql
-- Monitor if refresh rate matches expected pattern
SELECT
  DATE_TRUNC(minute, START_TIME) AS minute,
  COUNT(*) AS token_issued_count
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE QUERY_TEXT LIKE '%SYSTEM$ISSUE_WORKLOAD_IDENTITY_FEDERATION_TOKEN%'
  AND START_TIME > DATEADD(hour, -24, CURRENT_TIMESTAMP)
GROUP BY DATE_TRUNC(minute, START_TIME)
ORDER BY minute DESC;
```

**Expected pattern:**
- ~1 token every 5 min per application (normal refresh)
- Spikes during app restart or deployment

**Alert on anomalies:**
- > 10 tokens per minute (potential attack or code bug)
- 0 tokens per hour (service may be down)

### Monitoring 3: Service Principal Activity

```sql
-- Monitor which service principals are issuing tokens
SELECT
  USER_NAME,
  COUNT(*) AS token_count,
  MAX(START_TIME) AS last_issued
FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE QUERY_TEXT LIKE '%SYSTEM$ISSUE_WORKLOAD_IDENTITY_FEDERATION_TOKEN%'
  AND START_TIME > DATEADD(day, -7, CURRENT_TIMESTAMP)
GROUP BY USER_NAME
ORDER BY token_count DESC;
```

**Look for:**
- Unexpected service principals (may indicate lateral movement)
- Dormant principals suddenly becoming active
- Privileges escalation patterns

---

## Root Cause Analysis Template

If you're stuck, use this decision tree:

```
Q1: Can external service obtain an OIDC token from cloud provider (AWS STS, GCP metadata, Azure login)?
  ├─ NO → Network issue or cloud credentials missing. Check Phase 1 Symptom 3.
  └─ YES → Go to Q2

Q2: Can external service exchange OIDC token for Snowflake WIF token?
  ├─ NO → Token validation failed. Check Phase 1 Symptom 1 (issuer/audience).
  └─ YES → Go to Q3

Q3: Can Snowflake issue WIF token?
  ├─ NO (error on `SYSTEM$ISSUE_WORKLOAD_IDENTITY_FEDERATION_TOKEN()`) → Check Phase 1 Symptom 2 (grants).
  └─ YES → Go to Q4

Q4: Does token expire after 5 minutes?
  ├─ YES → Implement token refresh (Phase 3 Fix 4).
  └─ NO → Token TTL misconfigured. Contact support.

Q5: Does external service recognize Snowflake as trusted issuer?
  ├─ NO → Trust policy not updated. Check Phase 1 Symptom 1 or Phase 3 Fix 3.
  └─ YES → WIF working correctly!
```

---

## Common Issues and Quick Fixes

| Issue | Quick Fix | Deep Dive |
|-------|-----------|-----------|
| Token rejected by external service | Verify issuer URL matches trust policy | Phase 1 Symptom 1, Phase 3 Fix 1 |
| Secret not found | Check schema and grants | Phase 1 Symptom 2, Phase 3 Fix 2 |
| Issuer URL not accessible | Check network, firewall, proxy | Phase 1 Symptom 3 |
| Token expires, queries fail | Implement token refresh | Phase 1 Symptom 4, Phase 3 Fix 4 |
| Service principal not recognized | Recreate secret with correct principal | Phase 3 Fix 5 |
| Repeated token failures | Check audit logs for attack pattern | Phase 4 Audit 1 & 2 |

---

## Contacting Support

If you cannot resolve the issue:
1. Gather diagnostic info:
   ```sql
   SELECT SYSTEM$GET_SECRET_ISSUER_URL('wif_secret_name') AS issuer;
   SELECT SYSTEM$ISSUE_WORKLOAD_IDENTITY_FEDERATION_TOKEN('wif_secret_name') AS token;
   DESCRIBE SECRET wif_secret_name;
   SHOW GRANTS ON SECRET wif_secret_name;
   ```

2. Collect error messages and logs from external service

3. Contact Snowflake support with:
   - Account ID and region
   - Snowflake secret name and configuration
   - External service type (AWS, GCP, Azure, etc.)
   - Error messages from both Snowflake and external service
   - Recent QUERY_HISTORY and AUTHENTICATION_LOG entries

---

## Next Steps

- **Still having issues?** Reread Phase 1 (Symptom Diagnosis) and follow the Root Cause Analysis template
- **Need to set up WIF?** → [wif-setup sub-skill](./wif-setup/SKILL.md)
- **Want to understand auth patterns better?** → [auth-patterns.md reference](../references/auth-patterns.md)

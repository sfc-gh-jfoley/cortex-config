---
name: wif-setup
description: Set up Workload Identity Federation end-to-end. Create WIF secret → retrieve issuer URL → configure external service → test token issuance → enable ongoing refresh.
---

# WIF Setup Sub-Skill

Set up Workload Identity Federation (WIF) to enable external services to authenticate to Snowflake using federated identity tokens.

## Overview

This sub-skill guides you through:
1. **Phase 0**: Prerequisites and prerequisites checks (region, edition, feature flag)
2. **Phase 1**: Create WIF secret in Snowflake (provider-specific branches: AWS, GCP, Azure, generic OIDC)
3. **Phase 2**: Configure external service trust policy
4. **Phase 3**: Test token issuance
5. **Phase 4**: Set up ongoing token refresh

---

## Phase 0: Prerequisites and Checks

Before starting, ensure:
- ✅ Snowflake account on Business Critical edition or higher
- ✅ Your region is in the supported list (see PREREQUISITES.md)
- ✅ `ENABLE_WORKLOAD_IDENTITY_FEDERATION` parameter is `true`
- ✅ `snow` CLI version >= 1.2.0
- ✅ Current role has `CREATE SECRET` privilege

**Check your setup:**

```sql
-- 1. Verify region
SELECT CURRENT_REGION();

-- 2. Verify edition
SELECT CURRENT_ACCOUNT_EDITION();

-- 3. Verify WIF feature enabled
SHOW PARAMETERS LIKE 'ENABLE_WORKLOAD_IDENTITY_FEDERATION' IN ACCOUNT;

-- 4. Verify CLI version (run in terminal)
-- snow version
```

**If any check fails**, see [activation.md](../.cortex-plugin/activation.md) or [PREREQUISITES.md](../PREREQUISITES.md).

---

## Phase 1: Create WIF Secret

Choose your cloud provider and follow the corresponding section.

### Option 1a: AWS IAM Role

**Prerequisites:**
- IAM role ARN (e.g., `arn:aws:iam::123456789012:role/lambda-exec`)
- AWS account ID (12-digit number)
- Role exists and is accessible from Snowflake's OIDC issuer

**Step 1: Create WIF secret in Snowflake**

```sql
-- In your target database/schema
CREATE SECRET wif_aws_lambda
  TYPE = WORKLOAD_IDENTITY_FEDERATION
  ENABLED = true
  ISSUER_URL = 'https://sts.amazonaws.com'
  TOKEN_USE_CASE = 'SNOWFLAKE_JWT_BEARER'
  AUDIENCE = 'snowflake:account:YOUR_ACCOUNT_IDENTIFIER'
  EXTERNAL_SERVICE_PRINCIPAL = 'arn:aws:iam::123456789012:role/lambda-exec'
  EXTERNAL_SERVICE_PRINCIPAL_TYPE = 'AWS_ROLE';
```

**Replace:**
- `wif_aws_lambda` — secret name (use descriptive name)
- `YOUR_ACCOUNT_IDENTIFIER` — your Snowflake account ID (e.g., `xy12345`)
- `123456789012` — your AWS account ID
- `lambda-exec` — your IAM role name

**Step 2: Retrieve issuer URL**

```sql
SELECT SYSTEM$GET_SECRET_ISSUER_URL('wif_aws_lambda') AS issuer_url;
```

**Copy the issuer URL** — you'll need this in Phase 2.

---

### Option 1b: GCP Service Account

**Prerequisites:**
- Service account email (e.g., `my-sa@my-project.iam.gserviceaccount.com`)
- GCP project ID (e.g., `my-project`)
- Service account has appropriate IAM roles

**Step 1: Create WIF secret in Snowflake**

```sql
-- In your target database/schema
CREATE SECRET wif_gcp_function
  TYPE = WORKLOAD_IDENTITY_FEDERATION
  ENABLED = true
  ISSUER_URL = 'https://accounts.google.com'
  TOKEN_USE_CASE = 'SNOWFLAKE_JWT_BEARER'
  AUDIENCE = 'snowflake:account:YOUR_ACCOUNT_IDENTIFIER'
  EXTERNAL_SERVICE_PRINCIPAL = 'my-sa@my-project.iam.gserviceaccount.com'
  EXTERNAL_SERVICE_PRINCIPAL_TYPE = 'GCP_SERVICE_ACCOUNT';
```

**Replace:**
- `wif_gcp_function` — secret name
- `YOUR_ACCOUNT_IDENTIFIER` — your Snowflake account ID
- `my-sa@my-project.iam.gserviceaccount.com` — your service account email
- `my-project` — your GCP project ID

**Step 2: Retrieve issuer URL**

```sql
SELECT SYSTEM$GET_SECRET_ISSUER_URL('wif_gcp_function') AS issuer_url;
```

---

### Option 1c: Azure Managed Identity

**Prerequisites:**
- Tenant ID (Azure AD tenant ID)
- Application (Client) ID
- Subscription ID
- Managed identity is assigned to VM, container, or app service

**Step 1: Create WIF secret in Snowflake**

```sql
-- In your target database/schema
CREATE SECRET wif_azure_mi
  TYPE = WORKLOAD_IDENTITY_FEDERATION
  ENABLED = true
  ISSUER_URL = 'https://login.microsoftonline.com/<TENANT_ID>/v2.0'
  TOKEN_USE_CASE = 'SNOWFLAKE_JWT_BEARER'
  AUDIENCE = 'snowflake:account:YOUR_ACCOUNT_IDENTIFIER'
  EXTERNAL_SERVICE_PRINCIPAL = '<APPLICATION_CLIENT_ID>'
  EXTERNAL_SERVICE_PRINCIPAL_TYPE = 'AZURE_APPLICATION_ID';
```

**Replace:**
- `wif_azure_mi` — secret name
- `<TENANT_ID>` — your Azure AD tenant ID
- `YOUR_ACCOUNT_IDENTIFIER` — your Snowflake account ID
- `<APPLICATION_CLIENT_ID>` — Azure application (client) ID

**Step 2: Retrieve issuer URL**

```sql
SELECT SYSTEM$GET_SECRET_ISSUER_URL('wif_azure_mi') AS issuer_url;
```

---

### Option 1d: Generic OIDC (GitHub Actions, GitLab CI, Custom)

**Prerequisites:**
- OIDC token endpoint (e.g., `https://token.actions.githubusercontent.com`)
- Issuer URL (usually same as endpoint base)
- Audience value

**Step 1: Create WIF secret in Snowflake**

```sql
-- In your target database/schema
CREATE SECRET wif_github_actions
  TYPE = WORKLOAD_IDENTITY_FEDERATION
  ENABLED = true
  ISSUER_URL = 'https://token.actions.githubusercontent.com'
  TOKEN_USE_CASE = 'SNOWFLAKE_JWT_BEARER'
  AUDIENCE = 'snowflake:account:YOUR_ACCOUNT_IDENTIFIER'
  EXTERNAL_SERVICE_PRINCIPAL = 'https://github.com/my-org/my-repo'
  EXTERNAL_SERVICE_PRINCIPAL_TYPE = 'OIDC_SUBJECT_IDENTIFIER';
```

**Replace:**
- `wif_github_actions` — secret name
- `https://token.actions.githubusercontent.com` — OIDC token endpoint
- `YOUR_ACCOUNT_IDENTIFIER` — your Snowflake account ID
- `https://github.com/my-org/my-repo` — subject identifier (varies by OIDC provider)

**Step 2: Retrieve issuer URL**

```sql
SELECT SYSTEM$GET_SECRET_ISSUER_URL('wif_github_actions') AS issuer_url;
```

---

## Phase 2: Configure External Service

### AWS: Update IAM Trust Policy

1. Go to **IAM → Roles** in AWS console
2. Select your IAM role (e.g., `lambda-exec`)
3. Click **Trust relationships** tab
4. Click **Edit trust policy**
5. Add this statement (replace `YOUR_ACCOUNT_ID` and issuer URL from Phase 1):

```json
{
  "Effect": "Allow",
  "Principal": {
    "Federated": "arn:aws:iam::YOUR_ACCOUNT_ID:oidc-provider/oidc.snowflakecomputing.com"
  },
  "Action": "sts:AssumeRoleWithWebIdentity",
  "Condition": {
    "StringEquals": {
      "oidc.snowflakecomputing.com:aud": "snowflake:account:YOUR_ACCOUNT_IDENTIFIER"
    }
  }
}
```

6. Click **Update policy**

**Verification**: Lambda or EC2 running under this role can now call Snowflake via WIF.

---

### GCP: Link Service Account to OIDC Provider

1. Go to **IAM & Admin → Workload Identity Federation** in GCP console
2. Create or select existing **Workload Identity Pool** (e.g., `snowflake-wif`)
3. Create or select existing **Provider** (OIDC type)
   - Set **Issuer**: `https://oidc.snowflakecomputing.com` (from Phase 1)
   - Set **Audience**: your Snowflake account identifier
4. Link service account:
   - **Service account**: `my-sa@my-project.iam.gserviceaccount.com`
   - **Attribute mapping**: `google.subject` = `assertion.sub`
5. Grant service account `iam.workloadIdentityUser` role on the pool

**Verification**: Cloud Function or GKE pod running as this service account can now call Snowflake via WIF.

---

### Azure: Create Federated Credential

1. Go to **Azure AD → App registrations** in Azure portal
2. Select your app registration
3. Go to **Certificates & secrets** → **Federated credentials**
4. Click **Add credential**
5. Select **Other issued by an identity provider**
   - **Issuer**: `https://oidc.snowflakecomputing.com` (from Phase 1)
   - **Subject**: `snowflake:account:YOUR_ACCOUNT_IDENTIFIER` (your Snowflake account ID)
6. Click **Add**

**Verification**: VM, App Service, or AKS pod running with this managed identity can now call Snowflake via WIF.

---

### Generic OIDC: Configure OIDC Provider

**For GitHub Actions:**
1. In your GitHub Actions workflow, add:

```yaml
permissions:
  id-token: write  # Required for OIDC token

jobs:
  snowflake-job:
    runs-on: ubuntu-latest
    steps:
      - name: Get OIDC token
        env:
          ACTIONS_ID_TOKEN_REQUEST_TOKEN: ${{ secrets.ACTIONS_ID_TOKEN_REQUEST_TOKEN }}
          ACTIONS_ID_TOKEN_REQUEST_URL: ${{ secrets.ACTIONS_ID_TOKEN_REQUEST_URL }}
        run: |
          TOKEN=$(curl -s -H "Authorization: bearer $ACTIONS_ID_TOKEN_REQUEST_TOKEN" \
            "$ACTIONS_ID_TOKEN_REQUEST_URL" | jq -r '.token')
          # Use TOKEN in next step
```

2. In Snowflake WIF secret, ensure `EXTERNAL_SERVICE_PRINCIPAL` matches your repo: `https://github.com/my-org/my-repo`

**For GitLab CI:**
1. In your GitLab CI configuration, enable **OIDC** in project settings
2. In your `.gitlab-ci.yml`:

```yaml
deploy-to-snowflake:
  id_tokens:
    SNOWFLAKE_TOKEN:
      aud: snowflake:account:YOUR_ACCOUNT_IDENTIFIER
  script:
    - |
      curl -X POST -H "Content-Type: application/json" \
        -d "{\"token\": \"$SNOWFLAKE_TOKEN\"}" \
        https://your-oidc-token-endpoint/token
```

**Verification**: Workflow run can now call Snowflake via WIF token.

---

## Phase 3: Test Token Issuance

### Test 1: Issue Token from Snowflake (Direct SQL)

```sql
-- Issue a token from Snowflake
SELECT SYSTEM$ISSUE_WORKLOAD_IDENTITY_FEDERATION_TOKEN('wif_aws_lambda') AS token;
```

**Expected output**: Base64-encoded JWT token, approximately 500-800 characters.

**If you get an error**:
- `Secret not found` → Verify secret name is correct and exists in current schema
- `Insufficient privileges` → Grant `USAGE` on secret to current role
- `Invalid issuer or audience` → See wif-troubleshoot Phase 2

### Test 2: Issue Token via CLI

```bash
# CLI method (requires snow CLI 1.2.0+)
snow connection generate-workload-identity-token --secret-name wif_aws_lambda
```

**Expected output**: Token and metadata (issuer, audience, expires).

### Test 3: Validate Token Format

```python
# Decode token to inspect claims (Python example)
import json
import base64

token = "<token-from-test-1>"
parts = token.split('.')
payload = json.loads(base64.urlsafe_b64decode(parts[1] + '=='))
print(json.dumps(payload, indent=2))
```

**Expected claims**:
```json
{
  "iss": "https://oidc.snowflakecomputing.com",
  "aud": "snowflake:account:YOUR_ACCOUNT_IDENTIFIER",
  "sub": "aws:arn:aws:iam::123456789012:role/lambda-exec",
  "exp": <timestamp>,
  "iat": <timestamp>
}
```

### Test 4: Validate Token Expiry

```sql
-- Check token expiry time (should be ~5 min from now)
WITH token AS (
  SELECT SYSTEM$ISSUE_WORKLOAD_IDENTITY_FEDERATION_TOKEN('wif_aws_lambda') AS jwt
)
SELECT
  CURRENT_TIMESTAMP AS issued_now,
  DATEADD(minute, 5, CURRENT_TIMESTAMP) AS expected_expiry;
```

---

## Phase 4: Set Up Ongoing Token Refresh

Tokens auto-expire after 5 minutes (configurable 1-60 min). Your application must refresh tokens before expiry.

### Option A: Application-Level Refresh (Recommended for Long-Running Services)

```python
# Python example: Snowpark with automatic token refresh
from snowflake.snowpark import Session
import time
from datetime import datetime

def get_wif_token(connection_name: str, secret_name: str) -> str:
    """Issue a fresh WIF token."""
    # Use Snowflake CLI or Snowpark API
    # snow connection generate-workload-identity-token --secret-name <secret>
    # Returns token and expiry
    pass

class SnowflakeWIFSession:
    def __init__(self, account: str, database: str, schema: str, secret_name: str):
        self.account = account
        self.database = database
        self.schema = schema
        self.secret_name = secret_name
        self.token = None
        self.token_expiry = None
        self.session = None
    
    def _connect(self):
        """Create session with fresh WIF token."""
        token = get_wif_token('default', self.secret_name)
        self.session = Session.builder.config(
            "account", self.account
        ).config(
            "authenticator", f"oauth://{token}"
        ).config(
            "database", self.database
        ).config(
            "schema", self.schema
        ).create()
        self.token_expiry = datetime.now().timestamp() + 300  # 5 min
    
    def query(self, sql: str):
        """Execute query, refreshing token if needed."""
        now = datetime.now().timestamp()
        if self.session is None or now > (self.token_expiry - 30):  # Refresh 30s before expiry
            self._connect()
        return self.session.sql(sql).collect()

# Usage
wif_session = SnowflakeWIFSession(
    account='xy12345',
    database='my_db',
    schema='my_schema',
    secret_name='wif_aws_lambda'
)
result = wif_session.query("SELECT COUNT(*) FROM my_table")
```

### Option B: Scheduled Token Refresh (Recommended for Batch Jobs)

```sql
-- Create a Snowflake task that refreshes token in a location your app can read
-- (e.g., S3, GCS, or a Snowflake internal stage)
CREATE OR REPLACE TASK refresh_wif_token
  WAREHOUSE = compute_wh
  SCHEDULE = 'USING CRON 0 */4 * * * UTC'
AS
  INSERT INTO wif_token_cache (token, issued_at, expires_at)
  SELECT
    SYSTEM$ISSUE_WORKLOAD_IDENTITY_FEDERATION_TOKEN('wif_aws_lambda'),
    CURRENT_TIMESTAMP,
    DATEADD(minute, 5, CURRENT_TIMESTAMP);

-- Resume task
ALTER TASK refresh_wif_token RESUME;
```

### Option C: External Service Refresh (AWS Lambda Example)

```python
# AWS Lambda handler: refresh token on every invocation
import boto3
import json
import os
from datetime import datetime, timedelta

def lambda_handler(event, context):
    """Lambda function that refreshes WIF token and executes Snowflake query."""
    
    # Get fresh WIF token from Snowflake
    token = issue_snowflake_wif_token(
        account_id=os.environ['SNOWFLAKE_ACCOUNT'],
        secret_name=os.environ['SNOWFLAKE_WIF_SECRET']
    )
    
    # Use token to query Snowflake (token auto-expires after 5 min)
    result = snowflake_query(token, "SELECT * FROM my_table")
    
    return {
        'statusCode': 200,
        'body': json.dumps(result)
    }

def issue_snowflake_wif_token(account_id: str, secret_name: str) -> str:
    """Issue fresh WIF token from Snowflake."""
    # Calls Snowflake REST API:
    # POST /api/v2/statements
    # with SQL: SELECT SYSTEM$ISSUE_WORKLOAD_IDENTITY_FEDERATION_TOKEN('<secret>')
    pass
```

---

## Verification Checklist

After completing all phases:

- [ ] WIF secret exists and is enabled in Snowflake
- [ ] `SYSTEM$ISSUE_WORKLOAD_IDENTITY_FEDERATION_TOKEN()` returns a valid JWT token
- [ ] Token claims include correct issuer, audience, and subject
- [ ] Token expires in ~5 minutes
- [ ] External service (Lambda, GCP Function, etc.) can assume the federated identity
- [ ] External service can call Snowflake using token
- [ ] Application handles token refresh correctly (before 5 min expiry)

---

## Troubleshooting

If you encounter issues during any phase:
1. Check your setup matches the prerequisites in PREREQUISITES.md
2. See [wif-troubleshoot sub-skill](./wif-troubleshoot/SKILL.md) for diagnosis
3. Verify issuer URL matches external service configuration (Phase 2)
4. Check grants: `SHOW GRANTS ON SECRET wif_aws_lambda`

---

## Next Steps

- **Done with setup?** Proceed to Phase 4 (token refresh) if not already done
- **Troubleshooting issues?** → [wif-troubleshoot sub-skill](./wif-troubleshoot/SKILL.md)
- **Need to compare auth patterns?** → [auth-patterns.md reference](../references/auth-patterns.md)
- **Learn more about WIF?** → [README.md](../README.md)

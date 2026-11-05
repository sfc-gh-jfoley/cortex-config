---
name: agent-ddl-phase8-cicd-deploy
description: CI/CD deployment patterns for Cortex Agents — service user OIDC, GitHub Actions with snow CLI, environment promotion, rollback, drift detection
---

# Phase 8: CI/CD Deployment

## Purpose
Provision disposable DEV agents from Git-tracked specs using guarded CI examples. Existing agent releases follow independently evaluated named-version promotion, with recorded alias/default pointers for authorized rollback. OIDC setup and drift detection remain optional; DDL recovery examples are not production release commands.

**Activation:** This phase is opt-in. It activates only when the user selects CI/CD deployment from the Phase 7 handoff menu.

**Release contract (applies before running any template below):** Separate initial DDL provisioning from release promotion. CREATE OR REPLACE/GET_DDL templates are provisioning or recovery examples, not proof that an evaluated version was released. For an existing agent, follow `../reference/agent-versioning.md` for the version-based lifecycle, after verifying supported syntax and account capabilities. Do not silently replace version promotion with recreation.

Capture the exact candidate version identity, resolved alias target, spec digest, environment-specific tool/SV dependencies, dataset snapshot and split, metric versions, evaluation run IDs/results, and previous release alias and default-version targets. Unknown identity stays unknown and blocks evaluated-release claims. Evaluate the exact immutable candidate in the target dependency context; changes after evaluation invalidate that evidence. Operator approval is separate from factual/evaluation validation. Require explicit approval before production mutation or grants, recheck the alias target immediately before promotion, and verify it afterwards. Roll back to the recorded prior target only with authorization; DDL recreation requires a separately reviewed recovery plan. Existing templates must not be executed as automatic production releases without these checks.

**Prerequisites from Phase 7:**
- `SPEC_EXPORT_PATH` — local path to the exported agent spec JSON file
- `AGENT_FQN` — fully-qualified agent name (e.g., `DB.SCHEMA.MY_AGENT`)
- `HANDOFF_PATH` — path to handoff.json

---

## Step 8.1: Prepare Git-tracked spec file

The spec JSON exported in Phase 7 (Step 7.4) becomes the source of truth. Structure it for environment parameterization:

```
repo/
├── agents/
│   └── my_agent/
│       ├── spec.json          # Agent spec (from Phase 7 export)
│       ├── profile.json       # Profile settings (display_name, avatar, color)
│       └── grants.sql         # Post-creation grants
├── .github/
│   └── workflows/
│       └── deploy-agent.yml   # GitHub Actions workflow
└── snowflake.yml              # Optional — snow CLI project config
```

The `spec.json` file should use the exact spec JSON from `SPEC_EXPORT_PATH`. No modifications needed — environment-specific values (database, schema, warehouse) are parameterized at deploy time via FQN construction.

Create `profile.json`:
```json
{
  "display_name": "<AGENT_PROFILE.display_name>",
  "avatar": "<AGENT_PROFILE.avatar>",
  "color": "<AGENT_PROFILE.color>"
}
```

Create `grants.sql`:
```sql
-- Post-creation grants (adjust roles per environment)
GRANT USAGE ON AGENT {{AGENT_FQN}} TO ROLE {{CONSUMER_ROLE}};
-- Reminder: consumer roles also need USAGE on underlying SVs and warehouse
```

Present this structure to the user and ask them to commit it to their repository.

---

## Step 8.2: Create service user for CI/CD (OIDC)

> **Security note:** Service users with `WORKLOAD_IDENTITY` authenticate via OIDC tokens from the CI provider. No passwords or key pairs are stored in CI secrets.

```sql
-- Run as ACCOUNTADMIN or SECURITYADMIN
-- NOTE: Prefer SECURITYADMIN or a custom security automation role.
-- ACCOUNTADMIN is shown for simplicity but is not required for these operations.
USE ROLE SECURITYADMIN;

-- Create a dedicated role for agent deployment
CREATE ROLE IF NOT EXISTS AGENT_DEPLOYER;

GRANT USAGE ON DATABASE <AGENT_DB> TO ROLE AGENT_DEPLOYER;
GRANT USAGE ON SCHEMA <AGENT_DB>.<AGENT_SCHEMA> TO ROLE AGENT_DEPLOYER;
GRANT CREATE AGENT ON SCHEMA <AGENT_DB>.<AGENT_SCHEMA> TO ROLE AGENT_DEPLOYER;
-- Agent needs access to its tool resources at deploy time
GRANT USAGE ON SEMANTIC VIEW <SV_FQN> TO ROLE AGENT_DEPLOYER;
GRANT USAGE ON WAREHOUSE <AGENT_WAREHOUSE> TO ROLE AGENT_DEPLOYER;

USE ROLE ACCOUNTADMIN;

-- Create service user with OIDC workload identity
CREATE USER IF NOT EXISTS AGENT_CI_DEPLOYER
  TYPE = SERVICE
  DEFAULT_ROLE = AGENT_DEPLOYER;

GRANT ROLE AGENT_DEPLOYER TO USER AGENT_CI_DEPLOYER;

-- Configure OIDC trust for GitHub Actions
-- Replace <github_org> and <repo> with actual values
ALTER USER AGENT_CI_DEPLOYER SET
  WORKLOAD_IDENTITY = '{
    "oidc_issuer": "https://token.actions.githubusercontent.com",
    "audience": ["https://<account_identifier>.snowflakecomputing.com"],
    "subject_claim": "repo:<github_org>/<repo>:ref:refs/heads/main"
  }';
```

> **subject_claim patterns:**
> - Restrict to main branch: `repo:org/repo:ref:refs/heads/main`
> - Allow any branch: `repo:org/repo:*`
> - Restrict to environment: `repo:org/repo:environment:production`

Present the SQL to the user. They must run it with ACCOUNTADMIN/SECURITYADMIN privileges.

---

## Step 8.3: GitHub Actions workflow

Generate the workflow file. This uses `snowflakedb/snowflake-cli-action@v2.0.2` with OIDC authentication — no secrets stored in GitHub.

```yaml
# .github/workflows/deploy-agent.yml
name: Deploy Cortex Agent

on:
  push:
    branches: [main]
    paths:
      - 'agents/**'
  workflow_dispatch:
    inputs:
      environment:
        description: 'Target environment'
        required: true
        default: 'DEV'
        type: choice
        options: [DEV, TEST, PROD]

permissions:
  id-token: write   # Required for OIDC
  contents: read

env:
  SNOWFLAKE_ACCOUNT: ${{ vars.SNOWFLAKE_ACCOUNT }}
  SNOWFLAKE_USER: AGENT_CI_DEPLOYER
  SNOWFLAKE_AUTHENTICATOR: OAUTH_AUTHORIZATION_CODE_FLOW
  SNOWFLAKE_ROLE: AGENT_DEPLOYER
  AGENT_NAME: <AGENT_NAME>

jobs:
  deploy:
    runs-on: ubuntu-latest
    environment: ${{ github.event.inputs.environment || 'DEV' }}
    steps:
      - uses: actions/checkout@v4

      - name: Install Snowflake CLI
        uses: snowflakedb/snowflake-cli-action@v2.0.2

      - name: Set environment-specific variables
        run: |
          ENV="${{ github.event.inputs.environment || 'DEV' }}"
          case "$ENV" in
            DEV)  DB="AGENTS_DEV";  SCHEMA="AGENTS";  WH="DEV_WH"  ;;
            TEST) DB="AGENTS_TEST"; SCHEMA="AGENTS";  WH="TEST_WH" ;;
            PROD) DB="AGENTS_PROD"; SCHEMA="AGENTS";  WH="PROD_WH" ;;
          esac
          echo "AGENT_DB=$DB" >> "$GITHUB_ENV"
          echo "AGENT_SCHEMA=$SCHEMA" >> "$GITHUB_ENV"
          echo "AGENT_WH=$WH" >> "$GITHUB_ENV"
          echo "AGENT_FQN=$DB.$SCHEMA.${{ env.AGENT_NAME }}" >> "$GITHUB_ENV"

      - name: Capture existing DDL for rollback
        id: rollback
        continue-on-error: true
        run: |
          snow sql -q "SELECT GET_DDL('AGENT', '${{ env.AGENT_FQN }}')" \
            --database "${{ env.AGENT_DB }}" \
            --schema "${{ env.AGENT_SCHEMA }}" \
            -o json > rollback_ddl.json 2>/dev/null || true

      - name: Deploy agent
        run: |
          [ "${{ github.event.inputs.environment || 'DEV' }}" = DEV ] && [ -n "${APPROVED_DISPOSABLE_AGENT_FQN:-}" ] && [ "${{ env.AGENT_FQN }}" = "$APPROVED_DISPOSABLE_AGENT_FQN" ] || exit 1
          SPEC=$(cat agents/${{ env.AGENT_NAME }}/spec.json)
          snow sql -q "CREATE OR REPLACE AGENT ${{ env.AGENT_FQN }}
            FROM SPECIFICATION \$\$${SPEC}\$\$;" \
            --database "${{ env.AGENT_DB }}" \
            --schema "${{ env.AGENT_SCHEMA }}" \
            --warehouse "${{ env.AGENT_WH }}"

      - name: Restore profile
        run: |
          PROFILE=$(cat agents/${{ env.AGENT_NAME }}/profile.json)
          snow sql -q "ALTER AGENT ${{ env.AGENT_FQN }} SET PROFILE = '${PROFILE}';" \
            --database "${{ env.AGENT_DB }}" \
            --schema "${{ env.AGENT_SCHEMA }}"

      - name: Apply grants
        run: |
          snow sql -f agents/${{ env.AGENT_NAME }}/grants.sql \
            --database "${{ env.AGENT_DB }}" \
            --schema "${{ env.AGENT_SCHEMA }}" \
            --warehouse "${{ env.AGENT_WH }}" || true

      - name: Verify deployment
        run: |
          snow sql -q "DESCRIBE AGENT ${{ env.AGENT_FQN }}" \
            --database "${{ env.AGENT_DB }}" \
            --schema "${{ env.AGENT_SCHEMA }}" \
            -o json > describe_output.json
          echo "Agent deployed and verified: ${{ env.AGENT_FQN }}"

      - name: Upload rollback artifact
        if: steps.rollback.outcome == 'success'
        uses: actions/upload-artifact@v4
        with:
          name: rollback-ddl-${{ github.run_number }}
          path: rollback_ddl.json
          retention-days: 30
```

Present the workflow to the user for review. They should:
1. Set `SNOWFLAKE_ACCOUNT` as a GitHub repository variable (not secret — it's not sensitive)
2. Replace `<AGENT_NAME>` with their actual agent name
3. Adjust the environment-to-database mapping in "Set environment-specific variables"

---

## Step 8.4: Environment promotion

Environment promotion follows the evaluated named-version lifecycle in `../reference/agent-versioning.md`. Resolve and record the immutable candidate, evaluate it against the target dependencies, obtain approval, then verify every changed alias and default-version pointer. DDL captured with `GET_DDL` is a recovery artifact, not an evaluated promotion command; do not copy, rename, and execute it in TEST or PROD as a substitute.

**Release flow (separate from DEV-only provisioning templates):**

```
Approved disposable DEV target → guarded provisioning only
Exact immutable candidate + target dependencies → independent evaluation
Matching release evidence → explicit operator approval → version-target promotion
Recorded previous target → separately approved version-target rollback
```

GitHub required reviewers supply approval, not factual validation. TEST/PROD recreation through the legacy provisioning templates is blocked; use the reviewed version lifecycle and verify current account syntax.

---

## Step 8.5: Rollback

If a disposable DEV provisioning deployment causes issues, recover only the explicitly approved disposable target. Existing production rollback uses the recorded version target, not these recreation examples.

**Method 1: From CI artifact (DEV only)**
```bash
[ "${ENV:-}" = DEV ] && [ -n "${APPROVED_DISPOSABLE_AGENT_FQN:-}" ] && [ "$AGENT_FQN" = "$APPROVED_DISPOSABLE_AGENT_FQN" ] || exit 1
# Review the captured DDL and verify its target equals the approved FQN before execution.
exit 1 # Fail closed until the reviewed recovery command is supplied.
```

**Method 2: Non-executable recovery illustration**
```sql
-- If the previous version's DDL was logged
-- Re-execute the CREATE OR REPLACE with the old spec
CREATE OR REPLACE AGENT <AGENT_FQN>
FROM SPECIFICATION $$
<previous_spec_json>
$$;

-- Restore profile after OR REPLACE
ALTER AGENT <AGENT_FQN> SET PROFILE = '<profile_json>';
```

**Method 3: Source correction (not production rollback)**

A reviewed Git revert changes the source for a future candidate; it does not restore production alias or default-version targets. Do not push or redeploy automatically. Production rollback requires explicit authorization to restore every recorded prior pointer, followed by verification. Any disposable DEV recreation remains subject to the target-bound provisioning guard.

---

## Step 8.6: Drift detection

Detect when the live agent spec diverges from the Git-tracked spec (e.g., someone edited via Snowsight or ALTER AGENT directly):

```yaml
# Add to .github/workflows/deploy-agent.yml or create a separate scheduled workflow
  drift-check:
    runs-on: ubuntu-latest
    # Run daily or on schedule
    steps:
      - uses: actions/checkout@v4

      - uses: snowflakedb/snowflake-cli-action@v2.0.2

      - name: Check for drift
        run: |
          # Get live spec
          snow sql -q "DESCRIBE AGENT ${{ env.AGENT_FQN }}" \
            --database "${{ env.AGENT_DB }}" \
            --schema "${{ env.AGENT_SCHEMA }}" \
            -o json > live_spec.json

          # Extract spec from DESCRIBE output and compare
          LIVE_SPEC=$(cat live_spec.json | jq -r '.[0].spec // .[0].agent_spec')
          GIT_SPEC=$(cat agents/${{ env.AGENT_NAME }}/spec.json)

          if [ "$(echo "$LIVE_SPEC" | jq -S .)" != "$(echo "$GIT_SPEC" | jq -S .)" ]; then
            echo "::warning::Agent spec drift detected for ${{ env.AGENT_FQN }}"
            echo "Live spec differs from Git. Someone may have edited the agent outside CI/CD."
            diff <(echo "$LIVE_SPEC" | jq -S .) <(echo "$GIT_SPEC" | jq -S .) || true
            exit 1
          else
            echo "No drift detected — live spec matches Git."
          fi
```

Schedule drift checks with a cron trigger:
```yaml
on:
  schedule:
    - cron: '0 8 * * 1-5'  # Weekdays at 8 AM UTC
```

---

## Step 8.7: Present CI/CD summary

```
CI/CD deployment configured for <AGENT_NAME>:

  Spec file:    agents/<AGENT_NAME>/spec.json
  Workflow:     .github/workflows/deploy-agent.yml
  Service user: AGENT_CI_DEPLOYER (OIDC — no stored credentials)
  Deploy role:  AGENT_DEPLOYER

  Environments:
    DEV  → auto-deploy on push to main (agents/** path filter)
    TEST → manual dispatch with approval gate
    PROD → manual dispatch with approval gate

  Rollback: Previous DDL captured as CI artifact (30-day retention)
  Drift:    Scheduled weekday check comparing live DESCRIBE vs Git spec

Next steps:
  1. Commit the repo structure (spec.json, profile.json, grants.sql, workflow)
  2. Run the service user SQL in Snowflake (requires ACCOUNTADMIN)
  3. Set SNOWFLAKE_ACCOUNT as a GitHub repository variable
  4. Push to main — first deployment will trigger automatically
```

---

## Output variables (terminal)

| Variable | Contents |
|----------|----------|
| `CICD_WORKFLOW_PATH` | Path to the generated GitHub Actions workflow file |
| `SERVICE_USER` | Name of the service user created for CI/CD |
| `DEPLOY_ROLE` | Name of the deployment role |

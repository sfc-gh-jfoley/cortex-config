---
name: cortex-agent-ddl-cicd-patterns-reference
description: Reusable CI/CD workflow templates for Cortex Agent deployment — GitHub Actions, GitLab CI, Azure Pipelines
---

# CI/CD Workflow Templates for Cortex Agents

Reusable templates for deploying Cortex Agents from Git-tracked spec files. Each template covers:
- OIDC authentication (no stored passwords/keys)
- Environment promotion (DEV / TEST / PROD)
- Rollback via `GET_DDL` capture
- Post-deploy profile restoration and grants

> **Prerequisite:** Service user with `WORKLOAD_IDENTITY` configured for your CI provider. See Phase 8 Step 8.2 for setup.

---

## GitHub Actions

```yaml
# .github/workflows/deploy-agent.yml
name: Deploy Cortex Agent

on:
  push:
    branches: [main]
    paths: ['agents/**']
  workflow_dispatch:
    inputs:
      environment:
        description: 'Target environment'
        required: true
        default: 'DEV'
        type: choice
        options: [DEV, TEST, PROD]

permissions:
  id-token: write
  contents: read

env:
  SNOWFLAKE_ACCOUNT: ${{ vars.SNOWFLAKE_ACCOUNT }}
  SNOWFLAKE_USER: AGENT_CI_DEPLOYER
  SNOWFLAKE_AUTHENTICATOR: OAUTH_AUTHORIZATION_CODE_FLOW
  SNOWFLAKE_ROLE: AGENT_DEPLOYER

jobs:
  deploy:
    runs-on: ubuntu-latest
    environment: ${{ github.event.inputs.environment || 'DEV' }}
    steps:
      - uses: actions/checkout@v4
      - uses: snowflakedb/snowflake-cli-action@v2.0.2

      - name: Set env vars
        run: |
          ENV="${{ github.event.inputs.environment || 'DEV' }}"
          echo "TARGET_ENV=$ENV" >> "$GITHUB_ENV"
          # Source environment config
          source agents/env_config.sh "$ENV"

      - name: Capture rollback DDL
        continue-on-error: true
        run: |
          snow sql -q "SELECT GET_DDL('AGENT', '${AGENT_FQN}')" \
            -o json > rollback_ddl.json 2>/dev/null || true

      - name: Deploy
        run: |
          SPEC=$(cat agents/${AGENT_NAME}/spec.json)
          snow sql -q "CREATE OR REPLACE AGENT ${AGENT_FQN}
            FROM SPECIFICATION \$\$${SPEC}\$\$;" \
            --warehouse "${AGENT_WH}"

      - name: Post-deploy (profile + grants)
        run: |
          PROFILE=$(cat agents/${AGENT_NAME}/profile.json)
          snow sql -q "ALTER AGENT ${AGENT_FQN} SET PROFILE = '${PROFILE}';"
          snow sql -f agents/${AGENT_NAME}/grants.sql || true

      - name: Verify
        run: snow sql -q "DESCRIBE AGENT ${AGENT_FQN}" -o json

      - uses: actions/upload-artifact@v4
        with:
          name: rollback-${{ github.run_number }}
          path: rollback_ddl.json
          retention-days: 30
```

**Setup required:**
1. Repository variable: `SNOWFLAKE_ACCOUNT` (Settings → Variables)
2. GitHub Environments: `DEV`, `TEST`, `PROD` with required reviewers on TEST/PROD
3. Service user `AGENT_CI_DEPLOYER` with OIDC trust for GitHub Actions (see Phase 8 Step 8.2)

---

## GitLab CI

```yaml
# .gitlab-ci.yml
stages:
  - deploy
  - verify

variables:
  SNOWFLAKE_ACCOUNT: ${CI_SNOWFLAKE_ACCOUNT}
  SNOWFLAKE_USER: AGENT_CI_DEPLOYER
  SNOWFLAKE_AUTHENTICATOR: OAUTH_AUTHORIZATION_CODE_FLOW
  SNOWFLAKE_ROLE: AGENT_DEPLOYER

.deploy_template: &deploy_template
  image: python:3.11-slim
  before_script:
    - pip install snowflake-cli-labs
  script:
    - |
      # Capture rollback DDL
      snow sql -q "SELECT GET_DDL('AGENT', '${AGENT_FQN}')" \
        -o json > rollback_ddl.json 2>/dev/null || true
    - |
      # Deploy agent
      SPEC=$(cat agents/${AGENT_NAME}/spec.json)
      snow sql -q "CREATE OR REPLACE AGENT ${AGENT_FQN}
        FROM SPECIFICATION \$\$${SPEC}\$\$;" \
        --warehouse "${AGENT_WH}"
    - |
      # Restore profile
      PROFILE=$(cat agents/${AGENT_NAME}/profile.json)
      snow sql -q "ALTER AGENT ${AGENT_FQN} SET PROFILE = '${PROFILE}';"
    - |
      # Apply grants
      snow sql -f agents/${AGENT_NAME}/grants.sql || true
    - |
      # Verify
      snow sql -q "DESCRIBE AGENT ${AGENT_FQN}" -o json
  artifacts:
    paths:
      - rollback_ddl.json
    expire_in: 30 days

deploy_dev:
  <<: *deploy_template
  stage: deploy
  variables:
    AGENT_FQN: AGENTS_DEV.AGENTS.${AGENT_NAME}
    AGENT_WH: DEV_WH
  rules:
    - if: $CI_COMMIT_BRANCH == "main"
      changes:
        - agents/**

deploy_test:
  <<: *deploy_template
  stage: deploy
  variables:
    AGENT_FQN: AGENTS_TEST.AGENTS.${AGENT_NAME}
    AGENT_WH: TEST_WH
  rules:
    - if: $CI_COMMIT_BRANCH == "main"
      when: manual

deploy_prod:
  <<: *deploy_template
  stage: deploy
  variables:
    AGENT_FQN: AGENTS_PROD.AGENTS.${AGENT_NAME}
    AGENT_WH: PROD_WH
  environment:
    name: production
  rules:
    - if: $CI_COMMIT_BRANCH == "main"
      when: manual
```

**OIDC for GitLab:** Configure the service user's `WORKLOAD_IDENTITY` with:
```json
{
  "oidc_issuer": "https://gitlab.com",
  "audience": ["https://<account_identifier>.snowflakecomputing.com"],
  "subject_claim": "project_path:<group>/<project>:ref_type:branch:ref:main"
}
```

**Setup required:**
1. CI/CD variable: `CI_SNOWFLAKE_ACCOUNT` (Settings → CI/CD → Variables)
2. CI/CD variable: `AGENT_NAME`
3. Protected environments for TEST/PROD with required approvals

---

## Azure Pipelines

```yaml
# azure-pipelines.yml
trigger:
  branches:
    include: [main]
  paths:
    include: ['agents/**']

parameters:
  - name: environment
    displayName: Target Environment
    type: string
    default: DEV
    values: [DEV, TEST, PROD]

variables:
  snowflakeAccount: $(SNOWFLAKE_ACCOUNT)
  snowflakeUser: AGENT_CI_DEPLOYER
  snowflakeRole: AGENT_DEPLOYER

stages:
  - stage: Deploy
    jobs:
      - deployment: DeployAgent
        environment: ${{ parameters.environment }}
        strategy:
          runOnce:
            deploy:
              steps:
                - checkout: self

                - task: UsePythonVersion@0
                  inputs:
                    versionSpec: '3.11'

                - script: pip install snowflake-cli-labs
                  displayName: Install Snow CLI

                - script: |
                    case "${{ parameters.environment }}" in
                      DEV)  export AGENT_FQN="AGENTS_DEV.AGENTS.$(AGENT_NAME)" WH="DEV_WH" ;;
                      TEST) export AGENT_FQN="AGENTS_TEST.AGENTS.$(AGENT_NAME)" WH="TEST_WH" ;;
                      PROD) export AGENT_FQN="AGENTS_PROD.AGENTS.$(AGENT_NAME)" WH="PROD_WH" ;;
                    esac

                    # Capture rollback
                    snow sql -q "SELECT GET_DDL('AGENT', '$AGENT_FQN')" \
                      -o json > $(Build.ArtifactStagingDirectory)/rollback_ddl.json || true

                    # Deploy
                    SPEC=$(cat agents/$(AGENT_NAME)/spec.json)
                    snow sql -q "CREATE OR REPLACE AGENT $AGENT_FQN
                      FROM SPECIFICATION \$\$${SPEC}\$\$;" --warehouse "$WH"

                    # Profile + grants
                    PROFILE=$(cat agents/$(AGENT_NAME)/profile.json)
                    snow sql -q "ALTER AGENT $AGENT_FQN SET PROFILE = '$PROFILE';"
                    snow sql -f agents/$(AGENT_NAME)/grants.sql || true

                    # Verify
                    snow sql -q "DESCRIBE AGENT $AGENT_FQN" -o json
                  displayName: Deploy Agent
                  env:
                    SNOWFLAKE_ACCOUNT: $(snowflakeAccount)
                    SNOWFLAKE_USER: $(snowflakeUser)
                    SNOWFLAKE_ROLE: $(snowflakeRole)
                    SNOWFLAKE_AUTHENTICATOR: OAUTH_AUTHORIZATION_CODE_FLOW

                - publish: $(Build.ArtifactStagingDirectory)/rollback_ddl.json
                  artifact: rollback-$(Build.BuildNumber)
                  condition: succeededOrFailed()
```

**OIDC for Azure DevOps:** Configure the service user's `WORKLOAD_IDENTITY` with:
```json
{
  "oidc_issuer": "https://vstoken.dev.azure.com/<azure_tenant_id>",
  "audience": ["https://<account_identifier>.snowflakecomputing.com"],
  "subject_claim": "sc://<org>/<project>/<service_connection>"
}
```

**Setup required:**
1. Pipeline variable: `SNOWFLAKE_ACCOUNT`, `AGENT_NAME`
2. Azure DevOps Environments: `DEV`, `TEST`, `PROD` with approval gates on TEST/PROD
3. Service connection for Snowflake OIDC

---

## Environment config helper

Create `agents/env_config.sh` (sourced by all templates):

```bash
#!/bin/bash
# agents/env_config.sh — environment-specific configuration
# Usage: source agents/env_config.sh <ENV>

ENV="${1:-DEV}"
AGENT_NAME="${AGENT_NAME:-MY_AGENT}"

case "$ENV" in
  DEV)
    export AGENT_DB="AGENTS_DEV"
    export AGENT_SCHEMA="AGENTS"
    export AGENT_WH="DEV_WH"
    ;;
  TEST)
    export AGENT_DB="AGENTS_TEST"
    export AGENT_SCHEMA="AGENTS"
    export AGENT_WH="TEST_WH"
    ;;
  PROD)
    export AGENT_DB="AGENTS_PROD"
    export AGENT_SCHEMA="AGENTS"
    export AGENT_WH="PROD_WH"
    ;;
  *)
    echo "Unknown environment: $ENV" >&2
    exit 1
    ;;
esac

export AGENT_FQN="${AGENT_DB}.${AGENT_SCHEMA}.${AGENT_NAME}"
```

---

## Drift detection (reusable script)

```bash
#!/bin/bash
# agents/drift_check.sh — compare live agent spec vs Git
# Usage: ./agents/drift_check.sh <AGENT_FQN> <SPEC_PATH>

AGENT_FQN="$1"
SPEC_PATH="$2"

LIVE=$(snow sql -q "DESCRIBE AGENT ${AGENT_FQN}" -o json | jq -r '.[0].spec // .[0].agent_spec')
GIT=$(cat "$SPEC_PATH")

LIVE_SORTED=$(echo "$LIVE" | jq -S .)
GIT_SORTED=$(echo "$GIT" | jq -S .)

if [ "$LIVE_SORTED" = "$GIT_SORTED" ]; then
  echo "OK: No drift detected for ${AGENT_FQN}"
  exit 0
else
  echo "DRIFT DETECTED for ${AGENT_FQN}"
  echo "--- Live vs Git diff ---"
  diff <(echo "$LIVE_SORTED") <(echo "$GIT_SORTED") || true
  exit 1
fi
```

---

## Repo structure summary

```
repo/
├── agents/
│   ├── env_config.sh              # Shared environment config
│   ├── drift_check.sh             # Drift detection script
│   └── <agent_name>/
│       ├── spec.json              # Agent spec (source of truth)
│       ├── profile.json           # Display settings
│       └── grants.sql             # Post-creation grants
├── .github/workflows/
│   └── deploy-agent.yml           # GitHub Actions
├── .gitlab-ci.yml                 # GitLab CI (alternative)
└── azure-pipelines.yml            # Azure Pipelines (alternative)
```

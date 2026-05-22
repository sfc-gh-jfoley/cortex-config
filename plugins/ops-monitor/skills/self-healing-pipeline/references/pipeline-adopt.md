---
name: self-healing-pipeline-adopt
description: Add self-healing capabilities to existing Snowflake tasks and dynamic tables.
---

# Adopt Self-Healing on Existing Pipelines

Add a self-healing agent to an environment that already has tasks and/or dynamic tables running. This is a streamlined version of the full build — it skips pipeline creation and focuses on the agent infrastructure.

## When to Use

- User has existing tasks/DTs that are already running
- User wants to add auto-detection, diagnosis, and repair
- User does NOT need to create the underlying pipeline objects

## Workflow

### Step 1: Discover Existing Infrastructure

Run the discovery scan from `references/core-session.md` Step 2. Gather:

1. **Target database.schema** for agent deployment
2. **Monitored database.schema(s)** where existing tasks/DTs live

**Scan what's there:**
```sql
-- Count tasks
SELECT COUNT(*) AS task_count FROM TABLE(INFORMATION_SCHEMA.TASK_HISTORY(
    SCHEDULED_TIME_RANGE_START => DATEADD('day', -7, CURRENT_TIMESTAMP())
)) WHERE DATABASE_NAME = '{MONITORED_DB}' AND SCHEMA_NAME = '{MONITORED_SCHEMA}';

-- Count DTs
SELECT COUNT(*) AS dt_count FROM TABLE(INFORMATION_SCHEMA.DYNAMIC_TABLES())
WHERE DATABASE_NAME = '{MONITORED_DB}' AND SCHEMA_NAME = '{MONITORED_SCHEMA}';

-- Recent failures (are things already broken?)
SELECT NAME, STATE, ERROR_MESSAGE, SCHEDULED_TIME
FROM TABLE(INFORMATION_SCHEMA.TASK_HISTORY(
    SCHEDULED_TIME_RANGE_START => DATEADD('day', -1, CURRENT_TIMESTAMP()),
    RESULT_LIMIT => 20
))
WHERE STATE = 'FAILED'
  AND DATABASE_NAME = '{MONITORED_DB}'
ORDER BY SCHEDULED_TIME DESC;
```

**Present** the scan:

> "I found [N] tasks and [M] dynamic tables in {MONITORED_DB}.{MONITORED_SCHEMA}. [X] task failures in the last 24 hours. I'll set up a self-healing agent to monitor these."

**STOP**: Confirm scope with user.

### Step 2: Check for Partial Setup

Before creating anything, check if some agent infrastructure already exists:

```sql
SHOW TABLES LIKE 'PIPELINE_FAILURES' IN {DB}.{SCHEMA};
SHOW TABLES LIKE 'ERROR_RUNBOOK' IN {DB}.{SCHEMA};
SHOW PROCEDURES LIKE 'SP_DETECT%' IN {DB}.{SCHEMA};
SHOW TASKS LIKE 'SELF_HEALING%' IN {DB}.{SCHEMA};
```

| Result | Action |
|--------|--------|
| Nothing exists | Full build — route to `references/pipeline-build.md` |
| Tables exist, no procedures | Create procedures only (Step 4 of build) |
| Tables + procedures, no task | Create orchestrator task only (Step 5 of build) |
| Everything exists | Health check — route to `references/core-session.md` Step 3 |

### Step 3: Deploy Missing Components

Follow `references/pipeline-build.md` but **skip** steps for components that already exist. The typical adopt flow:

1. **Create tables** (if missing) — Step 2 of build
2. **Seed runbook** (if missing) — Step 3 of build
3. **Create procedures** (if missing) — Step 4 of build
4. **Create orchestrator task** (if missing) — Step 5 of build
5. **Activate** — Step 6 of build

### Step 4: Calibrate for Existing Failures

If existing failures were found in Step 1, backfill them:

```sql
-- Backfill recent task failures into PIPELINE_FAILURES
INSERT INTO {DB}.{SCHEMA}.PIPELINE_FAILURES
    (OBJECT_NAME, OBJECT_DATABASE, OBJECT_SCHEMA, OBJECT_TYPE, ERROR_CODE, ERROR_MESSAGE, SCHEDULED_TIME)
SELECT NAME, DATABASE_NAME, SCHEMA_NAME, 'TASK', ERROR_CODE, ERROR_MESSAGE, SCHEDULED_TIME
FROM TABLE({MONITORED_DB}.INFORMATION_SCHEMA.TASK_HISTORY(
    SCHEDULED_TIME_RANGE_START => DATEADD('day', -1, CURRENT_TIMESTAMP()),
    RESULT_LIMIT => 50
))
WHERE STATE = 'FAILED';
```

Then run the agent once manually to process backfilled failures:

```sql
CALL {DB}.{SCHEMA}.SP_DETECT_FAILURES();
```

**STOP**: Show results. Are there patterns that should be added to the runbook?

### Step 5: Trigger Compound Follow-ups

Same as build — present Monitor, DQM, Optimize, Fix-readiness as follow-up tasks.

## Stopping Points

- Step 1: Scope confirmed
- Step 4: Backfill results reviewed

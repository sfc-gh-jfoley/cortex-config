---
name: self-healing-pipeline-build
description: Build a net-new self-healing pipeline agent from scratch. This is a compound operation that triggers Monitor, DQM, Optimize, and Fix-readiness as follow-up steps.
---

# Build Self-Healing Pipeline

Net-new deployment of a self-healing pipeline agent. This is a **compound operation** — after the core build, the skill should present Monitor, DQM, Optimize, and Fix-readiness as follow-up tasks (see Compound Requests in SKILL.md).

## Workflow

### Step 1: Gather Configuration

**Ask** user for:

1. **Target database.schema** where the agent will be deployed
2. **Monitored database.schema(s)** where failing tasks/DTs live (can be same)
3. **Object types to monitor**: Tasks only, Dynamic Tables only, or Both (default: Both)
4. **Warehouse** for agent execution
5. **Guardrail preferences**:
   - Confidence threshold for auto-execute vs human review (default: 0.7)
   - Max fixes per run (default: 5)
   - **Default policy: conservative** — see `references/core-guidelines.md` for guardrail tiers
6. **Schedule** (default: every 5 minutes)

**STOP**: Confirm config before proceeding.

### Step 2: Create Tables

**Execute** 4 tables using `snowflake_sql_execute`. **Load** `references/sql-templates.md` is NOT needed — table DDL is here:

**Table 1: PIPELINE_FAILURES** — tracks detected failures
```sql
CREATE TABLE IF NOT EXISTS {DB}.{SCHEMA}.PIPELINE_FAILURES (
    FAILURE_ID VARCHAR DEFAULT UUID_STRING(),
    OBJECT_NAME VARCHAR NOT NULL,
    OBJECT_DATABASE VARCHAR,
    OBJECT_SCHEMA VARCHAR,
    OBJECT_TYPE VARCHAR NOT NULL,  -- 'TASK' or 'DYNAMIC_TABLE'
    ERROR_CODE VARCHAR,
    ERROR_MESSAGE VARCHAR,
    SCHEDULED_TIME TIMESTAMP_TZ,
    DETECTED_AT TIMESTAMP_TZ DEFAULT CURRENT_TIMESTAMP(),
    STATUS VARCHAR DEFAULT 'NEW',
    FIX_ATTEMPTS NUMBER DEFAULT 0,
    RESOLVED_AT TIMESTAMP_TZ,
    CONSTRAINT PK_FAILURES PRIMARY KEY (FAILURE_ID)
);
```

**Table 2: ERROR_RUNBOOK** — deterministic fixes for known errors
```sql
CREATE TABLE IF NOT EXISTS {DB}.{SCHEMA}.ERROR_RUNBOOK (
    RUNBOOK_ID VARCHAR DEFAULT UUID_STRING(),
    ERROR_PATTERN VARCHAR NOT NULL,
    ERROR_CATEGORY VARCHAR,
    OBJECT_TYPE VARCHAR DEFAULT 'ALL',  -- 'TASK', 'DYNAMIC_TABLE', or 'ALL'
    FIX_TEMPLATE VARCHAR NOT NULL,
    DESCRIPTION VARCHAR,
    CONFIDENCE NUMBER(3,2) DEFAULT 1.0,
    TIMES_USED NUMBER DEFAULT 0,
    LAST_USED TIMESTAMP_TZ,
    CREATED_AT TIMESTAMP_TZ DEFAULT CURRENT_TIMESTAMP()
);
```

**Table 3: HEALING_AUDIT_LOG** — full observability
```sql
CREATE TABLE IF NOT EXISTS {DB}.{SCHEMA}.HEALING_AUDIT_LOG (
    LOG_ID VARCHAR DEFAULT UUID_STRING(),
    FAILURE_ID VARCHAR,
    ACTION_TYPE VARCHAR NOT NULL,
    TASK_NAME VARCHAR,
    LLM_MODEL_USED VARCHAR,
    PROMPT_SENT VARCHAR,
    LLM_RESPONSE VARCHAR,
    GENERATED_SQL VARCHAR,
    GUARDRAIL_RESULT VARCHAR,
    EXECUTION_RESULT VARCHAR,
    CONFIDENCE_SCORE NUMBER(3,2),
    CREATED_AT TIMESTAMP_TZ DEFAULT CURRENT_TIMESTAMP()
);
```

**Table 4: PENDING_REVIEWS** — items held for human review (HITL)
```sql
CREATE TABLE IF NOT EXISTS {DB}.{SCHEMA}.PENDING_REVIEWS (
    REVIEW_ID VARCHAR DEFAULT UUID_STRING(),
    FAILURE_ID VARCHAR NOT NULL,
    OBJECT_NAME VARCHAR NOT NULL,
    OBJECT_TYPE VARCHAR NOT NULL,
    ERROR_MESSAGE VARCHAR,
    PROPOSED_SQL VARCHAR,
    CONFIDENCE_SCORE NUMBER(3,2),
    GUARDRAIL_REASON VARCHAR,
    LLM_MODEL_USED VARCHAR,
    LLM_REASONING VARCHAR,
    REMEDIATION_STEPS VARCHAR,
    REVIEW_STATUS VARCHAR DEFAULT 'PENDING',
    REVIEWED_BY VARCHAR,
    REVIEW_NOTES VARCHAR,
    CREATED_AT TIMESTAMP_TZ DEFAULT CURRENT_TIMESTAMP(),
    EXPIRES_AT TIMESTAMP_TZ DEFAULT DATEADD('hour', 24, CURRENT_TIMESTAMP()),
    REVIEWED_AT TIMESTAMP_TZ,
    CONSTRAINT PK_REVIEWS PRIMARY KEY (REVIEW_ID)
);
```

### Step 3: Seed the Runbook

**Load** `references/default-runbook.md` for the seed INSERT statements (task + DT patterns).

**STOP**: Show user the runbook entries. Ask if they want to add custom patterns.

### Step 4: Create Core Stored Procedures

Create procedures in order. **Load** the appropriate reference file for full SQL.

**Detection & Safety:**
1. **SP_CHECK_CIRCUIT_BREAKER** — **Load** `references/monitoring-templates.md`
2. **SP_DETECT_FAILURES** (unified task + DT) — **Load** `references/task-dag-templates.md`

**Guardrails & Execution:**
3. **SP_CHECK_GUARDRAILS** — **Load** `references/sql-templates.md`
4. **SP_EXECUTE_FIX** — **Load** `references/sql-templates.md`

**Task-specific:**
5. **SP_DIAGNOSE_FAILURE** — **Load** `references/sql-templates.md`
6. **SP_VERIFY_TASK_DAG** — **Load** `references/task-dag-templates.md`

**Dynamic Table-specific:**
7. **SP_DIAGNOSE_DT_FAILURE** — **Load** `references/dt-templates.md`
8. **SP_VERIFY_DT_FIX** — **Load** `references/dt-templates.md`

**STOP**: Present each procedure's logic summary for approval before creating.

### Step 5: Create the Orchestrator Task

```sql
CREATE OR REPLACE TASK {DB}.{SCHEMA}.SELF_HEALING_AGENT
  WAREHOUSE = {WAREHOUSE}
  SCHEDULE = '{SCHEDULE}'
AS
  CALL {DB}.{SCHEMA}.SP_DETECT_FAILURES();
```

### Step 6: Activate

```sql
ALTER TASK {DB}.{SCHEMA}.SELF_HEALING_AGENT RESUME;
```

**STOP**: Confirm agent is running. Check:
```sql
SELECT * FROM TABLE(INFORMATION_SCHEMA.TASK_HISTORY(
    TASK_NAME => 'SELF_HEALING_AGENT',
    SCHEDULED_TIME_RANGE_START => DATEADD('minute', -10, CURRENT_TIMESTAMP())
));
```

## Build Complete — Trigger Compound Follow-ups

After the core build succeeds, present the remaining compound tasks:

> "Core agent is deployed and running. Next steps:
> 1. **Monitor** — wire up alerting and HITL review queue
> 2. **DQM** — add data quality checks
> 3. **Optimize** — tune thresholds and model selection
> 4. **Fix-readiness** — test with a simulated failure
>
> Shall I proceed with monitoring setup?"

Route to each follow-up reference in order:
1. `references/pipeline-monitor.md`
2. `references/pipeline-dqm.md`
3. `references/pipeline-optimize.md`
4. `references/pipeline-fix.md` (fix-readiness test section)

## Stopping Points

- Step 1: Config confirmed
- Step 3: Runbook reviewed
- Step 4: Procedures approved
- Step 6: Agent running confirmed

## Output

Core self-healing agent:
- **4 tables**: PIPELINE_FAILURES, ERROR_RUNBOOK, HEALING_AUDIT_LOG, PENDING_REVIEWS
- **8 procedures**: detect, circuit breaker, diagnose (task + DT), guardrails, execute, verify (task + DT)
- **1 task**: SELF_HEALING_AGENT (scheduled)

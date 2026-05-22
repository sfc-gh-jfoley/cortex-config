---
name: self-healing-pipeline-core-session
description: Session initialization and discovery for self-healing pipeline. Always load this reference and follow the discovery workflow at session start.
---

# Session Management

This reference handles session initialization. Load this at the start of every self-healing pipeline session and follow the workflow below.

## Session Start Workflow

### Step 1: Gather Target Environment

**Ask** the user for:

1. **Target database.schema** where the agent will be deployed (or already lives)
2. **Monitored database.schema(s)** where tasks/DTs live (can be same as target)

If the user says "I already have one set up", skip to Step 3 (Health Check).

### Step 2: Scan Existing Infrastructure

Run these queries to understand what exists:

**Check for existing agent:**
```sql
SHOW TASKS LIKE 'SELF_HEALING%' IN {DB}.{SCHEMA};
```

**Check for existing healing tables:**
```sql
SHOW TABLES LIKE 'PIPELINE_FAILURES' IN {DB}.{SCHEMA};
SHOW TABLES LIKE 'ERROR_RUNBOOK' IN {DB}.{SCHEMA};
SHOW TABLES LIKE 'HEALING_AUDIT_LOG' IN {DB}.{SCHEMA};
SHOW TABLES LIKE 'PENDING_REVIEWS' IN {DB}.{SCHEMA};
```

**Check for existing alerts:**
```sql
SHOW ALERTS LIKE 'ALERT_%' IN {DB}.{SCHEMA};
```

**Scan monitored pipelines:**
```sql
-- Tasks in monitored schema
SHOW TASKS IN {MONITORED_DB}.{MONITORED_SCHEMA};

-- Dynamic tables in monitored schema
SHOW DYNAMIC TABLES IN {MONITORED_DB}.{MONITORED_SCHEMA};
```

| Discovery Result | Scenario | Route |
|-----------------|----------|-------|
| No agent, no tables | Net-new | `references/pipeline-build.md` |
| No agent, tasks/DTs exist | Adopt existing | `references/pipeline-adopt.md` |
| Agent exists, user says "broken" or "not working" | Fix | `references/pipeline-fix.md` |
| Agent exists, user says "add monitoring" or "set up alerts" | Monitor | `references/pipeline-monitor.md` |
| Agent exists, user says "add quality checks" | DQM | `references/pipeline-dqm.md` |
| Agent exists, user says "tune" or "improve" | Optimize | `references/pipeline-optimize.md` |
| Agent exists, no specific complaint | Health Check (continue below) | — |

### Step 3: Health Check (If Agent Exists)

Run diagnostics to assess current state:

**Agent status:**
```sql
SELECT NAME, STATE, SCHEDULE, LAST_COMMITTED_ON
FROM TABLE(INFORMATION_SCHEMA.TASK_HISTORY(
    TASK_NAME => 'SELF_HEALING_AGENT',
    SCHEDULED_TIME_RANGE_START => DATEADD('hour', -24, CURRENT_TIMESTAMP()),
    RESULT_LIMIT => 5
))
ORDER BY SCHEDULED_TIME DESC;
```

**Failure summary (last 7 days):**
```sql
SELECT
    OBJECT_TYPE,
    STATUS,
    COUNT(*) AS cnt
FROM {DB}.{SCHEMA}.PIPELINE_FAILURES
WHERE DETECTED_AT > DATEADD('day', -7, CURRENT_TIMESTAMP())
GROUP BY 1, 2
ORDER BY 1, 2;
```

**Success rate:**
```sql
SELECT
    COUNT(*) AS total,
    SUM(IFF(STATUS = 'RESOLVED', 1, 0)) AS auto_resolved,
    SUM(IFF(STATUS = 'ESCALATED', 1, 0)) AS escalated,
    SUM(IFF(STATUS = 'PENDING_REVIEW', 1, 0)) AS pending,
    ROUND(auto_resolved / NULLIF(total, 0) * 100, 1) AS success_rate_pct
FROM {DB}.{SCHEMA}.PIPELINE_FAILURES
WHERE DETECTED_AT > DATEADD('day', -7, CURRENT_TIMESTAMP());
```

**Recent audit activity:**
```sql
SELECT ACTION_TYPE, COUNT(*) AS cnt
FROM {DB}.{SCHEMA}.HEALING_AUDIT_LOG
WHERE CREATED_AT > DATEADD('day', -7, CURRENT_TIMESTAMP())
GROUP BY 1
ORDER BY 2 DESC;
```

**Present** the health summary:

> **Agent Health Report:**
> - Agent status: [RUNNING/SUSPENDED/FAILED]
> - Failures detected (7d): [N]
> - Auto-resolved: [N] ([X]%)
> - Escalated: [N]
> - Pending review: [N]
> - [Any notable patterns]

### Step 4: Confirm Intent

Based on discovery and health check, confirm what the user wants:

> "Based on what I see, [summary]. It sounds like you want to [detected intent]. Is that right, or were you looking for something else?"

Then route to the appropriate reference per the SKILL.md routing tables.

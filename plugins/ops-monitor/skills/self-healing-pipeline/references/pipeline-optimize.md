---
name: self-healing-pipeline-optimize
description: Optimize guardrails, model selection, runbook, and performance of a self-healing pipeline agent.
---

# Optimize Pipeline

Tune the self-healing agent for better success rates, lower costs, and faster resolution. Can be used standalone or as part of a Build compound.

## Workflow

### Step 1: Understand Current State

**Ask** user what they want to optimize, then query:

**Fix success rate:**
```sql
SELECT
    DATE_TRUNC('day', DETECTED_AT) AS day,
    COUNT(*) AS total_failures,
    SUM(IFF(STATUS = 'RESOLVED', 1, 0)) AS auto_resolved,
    SUM(IFF(STATUS = 'ESCALATED', 1, 0)) AS escalated,
    ROUND(auto_resolved / NULLIF(total_failures, 0) * 100, 1) AS success_rate_pct
FROM {DB}.{SCHEMA}.PIPELINE_FAILURES
WHERE DETECTED_AT > DATEADD('day', -30, CURRENT_TIMESTAMP())
GROUP BY 1 ORDER BY 1 DESC;
```

**Model usage + cost:**
```sql
SELECT LLM_MODEL_USED, COUNT(*) AS calls, AVG(CONFIDENCE_SCORE) AS avg_confidence
FROM {DB}.{SCHEMA}.HEALING_AUDIT_LOG
WHERE LLM_MODEL_USED IS NOT NULL
GROUP BY LLM_MODEL_USED ORDER BY calls DESC;
```

**Guardrail stats:**
```sql
SELECT GUARDRAIL_RESULT, COUNT(*) AS cnt
FROM {DB}.{SCHEMA}.HEALING_AUDIT_LOG
WHERE GUARDRAIL_RESULT IS NOT NULL
GROUP BY GUARDRAIL_RESULT ORDER BY cnt DESC;
```

**Runbook hit rate:**
```sql
SELECT ERROR_PATTERN, TIMES_USED, CONFIDENCE, DESCRIPTION
FROM {DB}.{SCHEMA}.ERROR_RUNBOOK
ORDER BY TIMES_USED DESC;
```

**Escalation patterns:**
```sql
SELECT OBJECT_NAME, OBJECT_TYPE, ERROR_MESSAGE, FIX_ATTEMPTS
FROM {DB}.{SCHEMA}.PIPELINE_FAILURES
WHERE STATUS = 'ESCALATED'
ORDER BY DETECTED_AT DESC LIMIT 20;
```

**Present** optimization report.

**STOP**: Confirm optimization direction with user.

### Step 2: Route to Optimization Type

#### Guardrail Tuning
- Review BLOCK'd entries in audit log — are they false positives?
- Expand allowlist or adjust confidence threshold
- Add operation-specific rules (e.g., allow ALTER TABLE ADD COLUMN but not ALTER TABLE DROP COLUMN)
- To promote REVIEW → AUTO: add a runbook entry with `CONFIDENCE >= 0.8`

#### Runbook Expansion
- Analyze ESCALATED failures for repeating patterns
- For each pattern, propose a deterministic runbook entry with fix template
- Insert approved entries into ERROR_RUNBOOK:

```sql
INSERT INTO {DB}.{SCHEMA}.ERROR_RUNBOOK
    (ERROR_PATTERN, ERROR_CATEGORY, OBJECT_TYPE, FIX_TEMPLATE, DESCRIPTION, CONFIDENCE)
VALUES
    ('{PATTERN}', '{CATEGORY}', '{TYPE}', '{FIX_SQL}', '{DESC}', {CONF});
```

- Run `SP_LEARN_FROM_MANUAL_FIXES()` to auto-generate entries from manual fixes

#### Model Selection Tuning
- Review cases where small model produced wrong fixes (upgrade model for that error category)
- Review cases where large model was used for simple fixes (downgrade to save cost)
- Adjust the complexity classification logic in SP_DIAGNOSE_FAILURE:

| Error Pattern | Current Model | Recommended |
|--------------|--------------|-------------|
| Simple object-not-found | llama3.1-8b | Keep |
| Schema mismatch | llama3.1-70b | Keep |
| Complex multi-table | llama3.1-70b | Upgrade to 405b if success rate < 50% |
| Recurring pattern | Any LLM | Add to runbook (no LLM needed) |

#### Prompt Engineering
- Review LLM prompts in audit log where fix was wrong
- Improve system prompt with more schema context, examples, constraints
- Add few-shot examples from successful fixes
- Include relevant runbook patterns as examples in the prompt

#### Performance Tuning
- **Schedule frequency**: Adjust based on failure rate. High failure rate → more frequent. Low rate → less frequent.
- **Dedup window**: Tune the NOT EXISTS check in SP_DETECT_FAILURES to avoid reprocessing.
- **Batch limits**: Adjust `MAX_FIXES_PER_RUN` (default: 5).
- **Circuit breaker**: Tune escalation threshold and fix-loop detection window.
- **DT target lag**: If DTs are refreshing too slowly, consider relaxing target lag.

### Step 3: Apply Changes

**STOP**: Present all proposed changes for approval.

After approval, apply changes via `snowflake_sql_execute`.

### Step 4: Monitor Improvement

Create a monitoring query the user can run to track improvement:

```sql
SELECT
    DATE_TRUNC('day', DETECTED_AT) AS day,
    COUNT(*) AS total_failures,
    SUM(IFF(STATUS = 'RESOLVED', 1, 0)) AS auto_resolved,
    SUM(IFF(STATUS = 'ESCALATED', 1, 0)) AS escalated,
    ROUND(auto_resolved / NULLIF(total_failures, 0) * 100, 1) AS success_rate_pct
FROM {DB}.{SCHEMA}.PIPELINE_FAILURES
GROUP BY 1 ORDER BY 1 DESC;
```

Compare before/after the optimization changes.

## Stopping Points

- Step 1: After optimization report
- Step 3: Before applying changes

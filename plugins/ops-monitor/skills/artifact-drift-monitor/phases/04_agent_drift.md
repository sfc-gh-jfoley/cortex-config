---
name: artifact-drift-monitor-phase4
description: Cortex Agent intent and tool-routing drift via AI_OBSERVABILITY_EVENTS
---

# Phase 4: Cortex Agent Drift Analysis

Inputs: `ARTIFACT_NAME`, `LOOKBACK_DAYS`

---

## Step 4.1: Check AI_OBSERVABILITY_EVENTS availability

```sql
SELECT COUNT(*) FROM SNOWFLAKE.ACCOUNT_USAGE.AI_OBSERVABILITY_EVENTS
WHERE start_time >= DATEADD('days', -1, CURRENT_TIMESTAMP());
```

If empty: "AI observability events not available — contact Snowflake support to enable."

---

## Step 4.2: Error rate over time

```sql
SELECT
    DATE_TRUNC('day', start_time)   AS day,
    COUNT(*)                         AS total_requests,
    COUNT_IF(status = 'ERROR')       AS error_count,
    ROUND(error_count / total_requests * 100, 1) AS error_pct
FROM SNOWFLAKE.ACCOUNT_USAGE.AI_OBSERVABILITY_EVENTS
WHERE agent_name = '<AGENT_SHORT_NAME>'
  AND start_time >= DATEADD('days', -:LOOKBACK_DAYS, CURRENT_TIMESTAMP())
GROUP BY 1
ORDER BY 1 DESC;
```

---

## Step 4.3: Unanswered intent patterns

```sql
SELECT
    LEFT(user_message, 200)   AS sample_question,
    response_status,
    error_message,
    COUNT(*)                   AS occurrence_count
FROM SNOWFLAKE.ACCOUNT_USAGE.AI_OBSERVABILITY_EVENTS
WHERE agent_name = '<AGENT_SHORT_NAME>'
  AND start_time >= DATEADD('days', -:LOOKBACK_DAYS, CURRENT_TIMESTAMP())
  AND (response_status = 'ERROR' OR error_message IS NOT NULL)
GROUP BY 1, 2, 3
ORDER BY occurrence_count DESC
LIMIT 20;
```

Cluster by topic. Score by occurrence_count (>= 10: HIGH, 3–9: MED, 1–2: LOW).
Store as `INTENT_GAPS` with ADD/SKIP recommendation and tool coverage suggestion.

---

## Step 4.4: Tool routing failures

```sql
SELECT
    tool_name,
    COUNT(*)                        AS call_count,
    COUNT_IF(tool_status = 'ERROR') AS error_count,
    ROUND(error_count / call_count * 100, 1) AS error_pct,
    ANY_VALUE(tool_error_message)   AS sample_error
FROM SNOWFLAKE.ACCOUNT_USAGE.AI_OBSERVABILITY_EVENTS
WHERE agent_name = '<AGENT_SHORT_NAME>'
  AND start_time >= DATEADD('days', -:LOOKBACK_DAYS, CURRENT_TIMESTAMP())
GROUP BY tool_name
ORDER BY error_count DESC;
```

Tool failures > 20% error_pct → ADD recommendation.
Store as `TOOL_ROUTING_FAILURES`. Pass to Phase 6.

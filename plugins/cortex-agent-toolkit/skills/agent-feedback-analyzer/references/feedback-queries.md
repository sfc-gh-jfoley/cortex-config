# Feedback Queries Reference

> SQL templates for pulling and joining CoWork feedback events.
> Used by `agent-feedback-analyzer` Phase 1 and Phase 2.

---

## Workflow A: Full Negative Feedback with Request Context

Joins feedback events to request events to get the original question and agent response
for every thumbs-down.

```sql
WITH feedback AS (
    SELECT
        VALUE:orig_request_id::STRING AS request_id,
        VALUE:positive::BOOLEAN AS is_positive,
        VALUE:feedback_message::STRING AS feedback_message,
        VALUE:categories::ARRAY AS categories,
        RECORD_ATTRIBUTES:"snow.ai.observability.user.name"::STRING AS feedback_user,
        TIMESTAMP AS feedback_time
    FROM TABLE(SNOWFLAKE.LOCAL.GET_AI_OBSERVABILITY_EVENTS(
        '<DATABASE>', '<SCHEMA>', '<AGENT_NAME>', 'CORTEX AGENT'
    ))
    WHERE RECORD:name = 'CORTEX_AGENT_FEEDBACK'
      AND VALUE:positive::BOOLEAN = FALSE
),
requests AS (
    SELECT
        RECORD_ATTRIBUTES:"ai.observability.record_id"::STRING AS record_id,
        VALUE:"snow.ai.observability.request_body":messages[0]:content[0]:text::STRING AS input_query,
        VALUE:"snow.ai.observability.response"::STRING AS agent_response,
        RECORD_ATTRIBUTES:"snow.ai.observability.user.name"::STRING AS request_user,
        TIMESTAMP AS request_time
    FROM TABLE(SNOWFLAKE.LOCAL.GET_AI_OBSERVABILITY_EVENTS(
        '<DATABASE>', '<SCHEMA>', '<AGENT_NAME>', 'CORTEX AGENT'
    ))
    WHERE RECORD:name = 'CORTEX_AGENT_REQUEST'
)
SELECT
    f.request_id,
    f.feedback_message,
    f.categories,
    f.feedback_user,
    f.feedback_time,
    r.input_query,
    LEFT(r.agent_response, 1000) AS response_preview,
    r.request_user,
    r.request_time
FROM feedback f
JOIN requests r ON f.request_id = r.record_id
ORDER BY f.feedback_time DESC;
```

**Notes:**
- `orig_request_id` may be NULL for agent-level feedback (not tied to a specific response).
  These rows won't join and are excluded. Report the count of agent-level-only feedback separately.
- `agent_response` can be very large. Truncate to 1000 chars for the triage view.
- If `READ UNREDACTED AI OBSERVABILITY EVENTS TABLE` is not granted, text fields will be redacted.
  The skill should detect this (NULL input_query on rows that have a valid request_id) and STOP
  with guidance on requesting the privilege.

---

## Workflow B: Feedback Summary by Day

Useful for velocity trending.

```sql
SELECT
    DATE_TRUNC('day', TIMESTAMP) AS feedback_date,
    COUNT_IF(VALUE:positive::BOOLEAN = TRUE) AS thumbs_up,
    COUNT_IF(VALUE:positive::BOOLEAN = FALSE) AS thumbs_down,
    thumbs_up + thumbs_down AS total,
    ROUND(thumbs_down::FLOAT / NULLIF(total, 0) * 100, 1) AS neg_pct
FROM TABLE(SNOWFLAKE.LOCAL.GET_AI_OBSERVABILITY_EVENTS(
    '<DATABASE>', '<SCHEMA>', '<AGENT_NAME>', 'CORTEX AGENT'
))
WHERE RECORD:name = 'CORTEX_AGENT_FEEDBACK'
GROUP BY feedback_date
ORDER BY feedback_date;
```

---

## Workflow C: Top Feedback Users

Identifies power users whose feedback carries more weight (frequent users understand
the tool better — their complaints are higher signal).

```sql
SELECT
    RECORD_ATTRIBUTES:"snow.ai.observability.user.name"::STRING AS user_name,
    COUNT(*) AS total_feedback,
    COUNT_IF(VALUE:positive::BOOLEAN = TRUE) AS thumbs_up,
    COUNT_IF(VALUE:positive::BOOLEAN = FALSE) AS thumbs_down,
    ROUND(thumbs_down::FLOAT / NULLIF(total_feedback, 0) * 100, 1) AS neg_pct
FROM TABLE(SNOWFLAKE.LOCAL.GET_AI_OBSERVABILITY_EVENTS(
    '<DATABASE>', '<SCHEMA>', '<AGENT_NAME>', 'CORTEX AGENT'
))
WHERE RECORD:name = 'CORTEX_AGENT_FEEDBACK'
GROUP BY user_name
ORDER BY total_feedback DESC;
```

---

## Workflow D: Agent-Level Feedback (No Request ID)

Captures feedback not tied to a specific response. Lower signal but still useful
for general sentiment.

```sql
SELECT
    VALUE:feedback_message::STRING AS feedback_message,
    VALUE:categories::ARRAY AS categories,
    RECORD_ATTRIBUTES:"snow.ai.observability.user.name"::STRING AS user_name,
    TIMESTAMP AS feedback_time
FROM TABLE(SNOWFLAKE.LOCAL.GET_AI_OBSERVABILITY_EVENTS(
    '<DATABASE>', '<SCHEMA>', '<AGENT_NAME>', 'CORTEX AGENT'
))
WHERE RECORD:name = 'CORTEX_AGENT_FEEDBACK'
  AND VALUE:orig_request_id IS NULL
ORDER BY feedback_time DESC;
```

---

## Redaction Detection

If `READ UNREDACTED AI OBSERVABILITY EVENTS TABLE` is not granted, query text will be
redacted. Detect this early:

```sql
SELECT
    COUNT(*) AS total_feedback,
    COUNT_IF(VALUE:orig_request_id IS NOT NULL) AS with_request_id,
    COUNT_IF(VALUE:feedback_message IS NOT NULL) AS with_message
FROM TABLE(SNOWFLAKE.LOCAL.GET_AI_OBSERVABILITY_EVENTS(
    '<DATABASE>', '<SCHEMA>', '<AGENT_NAME>', 'CORTEX AGENT'
))
WHERE RECORD:name = 'CORTEX_AGENT_FEEDBACK';
```

If `with_request_id = 0` but `total_feedback > 0`, the data may be redacted.
Inform the user:

> "Feedback events exist but request IDs and messages appear redacted. An account
> admin needs to grant `READ UNREDACTED AI OBSERVABILITY EVENTS TABLE` to your role
> for full diagnostic capability. Without it, I can report feedback volume and trends
> but cannot diagnose specific failures."

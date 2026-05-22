---
name: cortex-agent-optimization-feedback-pipeline
description: "Curate user feedback into eval dataset rows for the optimization loop."
parent_skill: cortex-agent-optimization
---

This sub-skill converts production user feedback (thumbs up/down from Snowflake Intelligence or the Feedback REST API) into eval dataset rows. It applies include/exclude filters to ensure only high-quality, actionable feedback enters the eval dataset.

Read `metadata.yaml` for parameters if not already loaded (`<DATABASE>`, `<SCHEMA>`, `<AGENT_NAME>`, `<EVAL_TABLE>`, `<CONNECTION>`).

**Prerequisites:**
- Agent must be deployed and receiving user traffic (feedback events exist)
- Role must have MONITOR on the agent + CORTEX_USER database role
- Account must have READ UNREDACTED AI OBSERVABILITY EVENTS TABLE granted (for full text access)

---

## Workflow A: Discover Feedback

### Step 1: Query Feedback Summary

```sql
SELECT 
    VALUE:positive::BOOLEAN AS is_positive,
    COUNT(*) AS feedback_count,
    MIN(TIMESTAMP) AS earliest,
    MAX(TIMESTAMP) AS latest,
    COUNT(DISTINCT RECORD_ATTRIBUTES:"snow.ai.observability.user.name"::STRING) AS distinct_users
FROM TABLE(SNOWFLAKE.LOCAL.GET_AI_OBSERVABILITY_EVENTS(
    '<DATABASE>', '<SCHEMA>', '<AGENT_NAME>', 'CORTEX AGENT'
))
WHERE RECORD:name = 'CORTEX_AGENT_FEEDBACK'
GROUP BY is_positive
ORDER BY is_positive;
```

### Step 2: Present Summary

Report:
- Total feedback events (positive / negative)
- Date range covered
- Number of distinct users providing feedback
- Breakdown by feedback category (if available)

If zero feedback events exist: **STOP** — no feedback to curate. The agent needs real user traffic first.

### Step 3: Check for Request-Level Feedback

```sql
SELECT COUNT(*) AS request_level_count
FROM TABLE(SNOWFLAKE.LOCAL.GET_AI_OBSERVABILITY_EVENTS(
    '<DATABASE>', '<SCHEMA>', '<AGENT_NAME>', 'CORTEX AGENT'
))
WHERE RECORD:name = 'CORTEX_AGENT_FEEDBACK'
  AND VALUE:orig_request_id IS NOT NULL;
```

Report how many feedback events have `orig_request_id` (joinable to specific responses) vs agent-level only.

---

## Workflow B: Curate Candidates

### Step 1: Extract Feedback with Request Context

Join feedback events to request events to get full input/output:

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
      AND VALUE:orig_request_id IS NOT NULL
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
    f.is_positive,
    f.feedback_message,
    f.categories,
    f.feedback_user,
    f.feedback_time,
    r.input_query,
    LEFT(r.agent_response, 500) AS response_preview,
    r.request_user
FROM feedback f
JOIN requests r ON f.request_id = r.record_id
ORDER BY f.feedback_time DESC;
```

### Step 2: Apply Exclude Filters

Remove candidates that match ANY of these criteria:

| # | Exclude Rule | Detection Method |
|---|---|---|
| 1 | No `orig_request_id` | Already filtered in Step 1 JOIN |
| 2 | Test/system users | `request_user = 'SYSTEM'` OR `request_user` in known test user list |
| 3 | Time-relative queries | `input_query ILIKE ANY ('%last week%', '%yesterday%', '%this month%', '%last month%', '%recently%', '%today%')` |
| 4 | Already in eval table | `input_query IN (SELECT INPUT_QUERY FROM <EVAL_TABLE>)` — deduplicate |
| 5 | Vague negative (no message) | `is_positive = FALSE AND feedback_message IS NULL AND categories IS NULL` |
| 6 | Multi-turn context-dependent | `input_query ILIKE ANY ('%what about%', '%and for%', '%same but%', '%also show%')` — relies on prior turn |
| 7 | Feedback during eval runs | `feedback_time` overlaps with known eval run timeframes (check `optimization_log.md`) |

### Step 3: Apply Include Prioritization

Score remaining candidates for promotion priority:

| Signal | Points |
|---|---|
| Negative feedback with message | +3 (highest value — tells you what's wrong) |
| Negative feedback with categories | +2 |
| Positive feedback with message | +1 (ground truth candidate) |
| Feedback from domain expert user | +2 (if user list available) |
| Query covers a category underrepresented in eval | +2 |

Sort by priority score descending.

### Step 4: Present Candidates

**⚠️ STOP (supervised mode):** Present the filtered, prioritized candidate list:

| # | Input Query | Positive? | Message | Priority | Proposed Action |
|---|---|---|---|---|---|
| 1 | "..." | No | "Wrong numbers" | 5 | Write correct GT |
| 2 | "..." | Yes | "Perfect" | 3 | Promote response as GT |
| ... | ... | ... | ... | ... | ... |

For negative feedback: proposed action is "Write correct GT" (needs human/agent to determine correct answer).
For positive feedback: proposed action is "Promote response as GT" (use the agent's actual output as ground truth).

Ask user: Which candidates to promote? (Select by number, "all", or "none")

---

## Workflow C: Write Ground Truth and Insert

### Step 1: Generate Ground Truth

For each approved candidate:

**Positive feedback (promote agent response as GT):**
- Extract the key factual assertions from the agent's response
- Write as natural language ground truth (not the full formatted response — just the facts)
- Format: `{"ground_truth_output": "<factual assertions>"}`

**Negative feedback (write correct answer):**
- If `feedback_message` explains what's wrong: use it as context to query the data directly
- Run the query against the underlying tables to determine the correct answer
- If unclear: **ASK the user** what the correct answer should be
- Format: `{"ground_truth_output": "<correct answer>"}`

### Step 2: Assign Metadata

For each row:
- `TEST_ID`: `(SELECT COALESCE(MAX(TEST_ID), 0) + 1 FROM <EVAL_TABLE>)` — auto-increment from next available
- `TEST_CATEGORY`: Detect from tool used in the agent trace, or ask user
- `SPLIT`: `NULL` — unassigned. User runs `eval-data` Workflow A to assign to DEV or TEST later.

### Step 3: Generate INSERT SQL

```sql
INSERT INTO <EVAL_TABLE> (TEST_ID, TEST_CATEGORY, INPUT_QUERY, GROUND_TRUTH, SPLIT)
SELECT 
    <NEXT_ID>,
    '<CATEGORY>',
    '<INPUT_QUERY>',
    PARSE_JSON('{"ground_truth_output": "<GT_TEXT>"}'),
    NULL;
-- Repeat for each promoted candidate
```

### Step 4: Present and Execute

**⚠️ STOP:** Present the full INSERT block with all rows. Show:
- Number of new rows to add
- Category distribution of new rows
- Current eval table size vs new size after insert

Wait for user approval before executing.

### Step 5: Post-Insert Guidance

After execution:
> "Added {N} rows to {EVAL_TABLE} with SPLIT=NULL. Next steps:
> 1. Run `eval-data` Workflow B (Validate Split) to check current balance
> 2. Run `eval-data` Workflow A (Create Split) or C (Re-balance) to assign new rows to DEV/TEST
> 3. Optionally run Workflow D below to validate the new ground truth quality"

---

## Workflow D: Validate Promoted Rows

Validates that newly promoted rows have sound ground truth before they influence optimization decisions.

### Step 1: Identify Unvalidated Rows

```sql
SELECT TEST_ID, INPUT_QUERY, GROUND_TRUTH:ground_truth_output::STRING AS gt_text
FROM <EVAL_TABLE>
WHERE SPLIT IS NULL
ORDER BY TEST_ID DESC;
```

These are rows added by the feedback pipeline that haven't been split-assigned yet.

### Step 2: Spot-Check via Agent

For each unvalidated row, run the question against the agent and apply `factual_correctness_verdict` logic manually:

1. Call the agent with the `INPUT_QUERY`
2. Compare agent output to the `ground_truth_output` you wrote
3. Ask: Is the ground truth actually correct? Is it complete? Is it specific enough?

### Step 3: Quality Gate

| Check | Condition | Action |
|---|---|---|
| GT is correct and complete | Agent output matches GT, or GT is clearly right and agent is wrong | PASS — ready for split assignment |
| GT is ambiguous | Multiple valid interpretations | REWRITE — make GT more specific |
| GT is wrong | Agent is actually correct, GT was written from bad feedback | DELETE — remove the row |
| GT is stale | Underlying data changed since feedback was given | UPDATE — refresh GT with current data |

### Step 4: Report

Present validation results:
- Rows PASSED: ready for split assignment
- Rows needing REWRITE: list with specific issues
- Rows to DELETE: list with reason
- Rows needing UPDATE: list with staleness indicator

After fixes, re-run Workflow D to confirm all rows pass.

---

## Include/Exclude Reference

### INCLUDE signals (what makes good eval candidates)

1. `orig_request_id` present — joinable to specific response
2. `feedback_message` text — explains what's wrong/right
3. `categories` array — structured signal for failure type
4. Negative feedback — highest value for finding gaps
5. Query covers underrepresented category in eval
6. Feedback from identified domain expert users
7. Query is self-contained (no multi-turn context dependency)

### EXCLUDE signals (what to filter out)

1. Agent-level feedback only (no `orig_request_id`) — not actionable for specific questions
2. Test/system users (`SYSTEM`, `ACCOUNTADMIN` during smoke tests)
3. Time-relative queries ("last week", "yesterday") — ground truth expires
4. Duplicate input queries already in eval table
5. Vague negative feedback with no message and no categories
6. Multi-turn context-dependent queries ("what about X?" — needs prior turn)
7. Feedback during eval run timeframes (synthetic, not real user intent)
8. Positive feedback on potentially wrong answers (validate before promoting)

### When to use positive vs negative feedback

| Feedback Type | Eval Role | Validation Required |
|---|---|---|
| Negative + message | New eval row: write correct GT from message context | Medium — verify the correct answer |
| Negative + categories only | New eval row: must determine correct answer independently | High — no guidance on what's right |
| Positive + message | New eval row: promote agent response as GT | Low — user confirmed it's correct |
| Positive (no message) | Candidate only: user may not have validated numbers | High — run secondary correctness check before promoting |

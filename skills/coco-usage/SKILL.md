---
name: coco-usage
description: "Query Cortex Code CLI credit and token usage from Snowflake ACCOUNT_USAGE views. Use when: coco credits, coco usage, coco spend, how much have I used, cortex code usage, how many credits today, usage this week, top users, session spend, token breakdown."
---

# CoCo CLI Usage

Data lives in `SNOWFLAKE.ACCOUNT_USAGE.CORTEX_CODE_CLI_USAGE_HISTORY`.

**Key schema facts:**
- `USER_ID` — numeric, not username. Join `SNOWFLAKE.ACCOUNT_USAGE.USERS` to resolve names.
- `USAGE_TIME` — timestamp of usage event
- `TOKEN_CREDITS` — total credits consumed
- `TOKENS` — total token count
- `TOKENS_GRANULAR` / `CREDITS_GRANULAR` — OBJECT with per-model breakdown (e.g. `claude-sonnet-4-6` → `{cache_read_input, cache_write_input, input, output}`)
- `PARENT_REQUEST_ID` — groups all requests within a single session/conversation
- `REQUEST_ID` — individual turn

**Note:** Up to 45-minute latency. Very recent turns may not appear yet.

---

## Step 0: Detect Connection

**Always do this before running any queries.**

1. Read `~/.snowflake/cortex/settings.json` and extract `cortexAgentConnectionName`.
   - This is where CoCo is configured to run inference — it's the correct account.

2. **If `cortexAgentConnectionName` is set** → look up that connection's `account` from `~/.snowflake/config.toml`, then confirm:
   > "CoCo is configured to run inference on **`<account>`** (connection: `<name>`). Run the query there?"

   **⚠️ STOP**: Wait for Y/N.
   - If **N** → ask the user which connection to use instead, then confirm again.

3. **If `cortexAgentConnectionName` is not set** → fall back to the `active_connection` from `cortex connections list`, and confirm the same way.

4. **If user-specified or active connection is unreachable** → tell the user and ask them to pick an alternative from `cortex connections list`.

---

## Intent Routing

| User asks | Query to use |
|-----------|-------------|
| "my spend", "how much have I used", "my credits" | My Spend query |
| "all users", "top users", "leaderboard" | Top Users query |
| "this session", "current session", "session spend" | Session Spend query |
| "by model", "model breakdown", "token breakdown" | includes CREDITS_GRANULAR |

---

## Step 1: Resolve Current User ID

Always run this first if filtering by current user:

```sql
SELECT user_id FROM SNOWFLAKE.ACCOUNT_USAGE.USERS
WHERE name = CURRENT_USER();
```

Store the returned `user_id` for use in subsequent queries.

---

## Queries

### My Spend — Time Period

Replace `<user_id>` with resolved ID. Default period: today (`CURRENT_DATE()`).

```sql
SELECT
    ROUND(SUM(token_credits), 4)          AS total_credits,
    SUM(tokens)                            AS total_tokens,
    COUNT(*)                               AS requests,
    ANY_VALUE(credits_granular)            AS credits_by_model,
    ANY_VALUE(tokens_granular)             AS tokens_by_model
FROM SNOWFLAKE.ACCOUNT_USAGE.CORTEX_CODE_CLI_USAGE_HISTORY
WHERE user_id = <user_id>
  AND usage_time >= <start>   -- e.g. CURRENT_DATE(), DATEADD('day',-7,CURRENT_DATE())
  AND usage_time <  <end>;    -- e.g. DATEADD('day',1,CURRENT_DATE()) or CURRENT_TIMESTAMP()
```

**Period shortcuts:**
- Today: `usage_time >= CURRENT_DATE() AND usage_time < DATEADD('day',1,CURRENT_DATE())`
- This week: `usage_time >= DATE_TRUNC('week', CURRENT_DATE())`
- This month: `usage_time >= DATE_TRUNC('month', CURRENT_DATE())`
- Last N days: `usage_time >= DATEADD('day', -N, CURRENT_DATE())`

---

### Top Users — Time Period

```sql
SELECT
    u.name                                   AS username,
    h.user_id,
    ROUND(SUM(h.token_credits), 4)           AS total_credits,
    SUM(h.tokens)                            AS total_tokens,
    COUNT(*)                                 AS requests
FROM SNOWFLAKE.ACCOUNT_USAGE.CORTEX_CODE_CLI_USAGE_HISTORY h
JOIN SNOWFLAKE.ACCOUNT_USAGE.USERS u ON h.user_id = u.user_id
WHERE h.usage_time >= <start>
GROUP BY u.name, h.user_id
ORDER BY total_credits DESC
LIMIT 20;
```

---

### Session Spend

A "session" = all rows sharing the same `parent_request_id`. To find sessions for the current user:

```sql
SELECT
    parent_request_id                        AS session_id,
    MIN(usage_time)                          AS session_start,
    MAX(usage_time)                          AS session_end,
    ROUND(SUM(token_credits), 4)             AS session_credits,
    SUM(tokens)                              AS session_tokens,
    COUNT(*)                                 AS turns
FROM SNOWFLAKE.ACCOUNT_USAGE.CORTEX_CODE_CLI_USAGE_HISTORY
WHERE user_id = <user_id>
  AND usage_time >= <start>
GROUP BY parent_request_id
ORDER BY session_start DESC
LIMIT 20;
```

To find spend for the **current active session**, the user can provide their session ID, or look up the most recent `parent_request_id` from today's results.

---

### Model Breakdown (Granular)

To extract per-model token/credit detail, parse the OBJECT columns. Example for `claude-sonnet-4-6`:

```sql
SELECT
    usage_time,
    token_credits,
    credits_granular:"claude-sonnet-4-6":"cache_read_input"::FLOAT  AS cache_read_credits,
    credits_granular:"claude-sonnet-4-6":"cache_write_input"::FLOAT AS cache_write_credits,
    credits_granular:"claude-sonnet-4-6":"input"::FLOAT             AS input_credits,
    credits_granular:"claude-sonnet-4-6":"output"::FLOAT            AS output_credits
FROM SNOWFLAKE.ACCOUNT_USAGE.CORTEX_CODE_CLI_USAGE_HISTORY
WHERE user_id = <user_id>
  AND usage_time >= CURRENT_DATE()
ORDER BY usage_time DESC;
```

---

## Output Format

Present results as a markdown table. Always include:
- Total credits (rounded to 4 decimal places)
- Total tokens (formatted with commas)
- Request count
- Model breakdown if `credits_granular` was fetched

Note data latency if the user asks about very recent activity.

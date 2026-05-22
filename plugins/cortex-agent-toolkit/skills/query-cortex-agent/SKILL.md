---
name: query-cortex-agent
description: "Query a Cortex Agent in a Snowflake account using SQL. Use when: user wants to ask a question to a Cortex Agent, invoke an agent, run an agent, chat with an agent, query an agent. Triggers: query agent, ask agent, invoke agent, run agent, chat with agent, DATA_AGENT_RUN, AGENT_RUN."
---

# Query a Cortex Agent

Invoke a Cortex Agent in the user's Snowflake account and return the response, using SQL functions.

## When to Use

- User wants to send a question to an existing Cortex Agent object
- User wants to query an agent without creating an agent object (ad-hoc)

## Workflow

### Step 1: Discover Available Agents

If the user hasn't specified an agent, discover what's available:

```sql
SHOW AGENTS IN ACCOUNT;
```

To see details about a specific agent:

```sql
DESCRIBE AGENT <DATABASE>.<SCHEMA>.<AGENT_NAME>;
```

**STOP**: Ask the user which agent to query and what question to ask.

### Step 2: Determine the Right SQL Function

There are two SQL functions for invoking agents:

| Function | Use Case |
|----------|----------|
| `SNOWFLAKE.CORTEX.DATA_AGENT_RUN` | Invoke an **existing agent object** (created via `CREATE AGENT`) |
| `SNOWFLAKE.CORTEX.AGENT_RUN` | Run an agent **ad-hoc** without a pre-created agent object (provide tools/config inline) |

**Default to `DATA_AGENT_RUN`** when the user wants to query an existing agent.

### Step 3: Execute the Query

#### Option A: Query an existing agent (`DATA_AGENT_RUN`)

```sql
SELECT TRY_PARSE_JSON(
  SNOWFLAKE.CORTEX.DATA_AGENT_RUN(
    '<DATABASE>.<SCHEMA>.<AGENT_NAME>',
    $${
      "messages": [
        {
          "role": "user",
          "content": [{"type": "text", "text": "<USER_QUESTION>"}]
        }
      ],
      "stream": false
    }$$
  )
) AS resp;
```

#### Option B: Ad-hoc agent run (`AGENT_RUN`)

```sql
SELECT TRY_PARSE_JSON(
  SNOWFLAKE.CORTEX.AGENT_RUN(
    $${
      "messages": [
        {
          "role": "user",
          "content": [{"type": "text", "text": "<USER_QUESTION>"}]
        }
      ],
      "models": {"orchestration": "claude-4-sonnet"},
      "stream": false
    }$$
  )
) AS resp;
```

For `AGENT_RUN`, you can also provide `tools`, `tool_resources`, `instructions`, and `orchestration` fields inline. See the Cortex Agents Run API docs for the full schema.

### Step 4: Parse and Present the Response

The response JSON has this structure:

```json
{
  "role": "assistant",
  "content": [
    {"type": "thinking", "thinking": {"text": "..."}},
    {"type": "tool_use", "tool_use": {"name": "...", "input": {}}},
    {"type": "tool_result", "tool_result": {"content": []}},
    {"type": "text", "text": "The actual answer..."}
  ],
  "metadata": {"run_id": "..."}
}
```

Extract the `text` entries from the `content` array to present the agent's answer to the user.

### Step 5 (Optional): Multi-Turn Conversation

To continue a conversation with the agent, use `thread_id` and `parent_message_id`:

```sql
SELECT TRY_PARSE_JSON(
  SNOWFLAKE.CORTEX.DATA_AGENT_RUN(
    '<DATABASE>.<SCHEMA>.<AGENT_NAME>',
    $${
      "thread_id": <THREAD_ID>,
      "parent_message_id": <PARENT_MESSAGE_ID>,
      "messages": [
        {
          "role": "user",
          "content": [{"type": "text", "text": "<FOLLOW_UP_QUESTION>"}]
        }
      ],
      "stream": false
    }$$
  )
) AS resp;
```

## Stopping Points

- Step 1: After discovering agents, confirm which agent and question
- Step 4: After presenting response, ask if user wants a follow-up

## Notes

- `DATA_AGENT_RUN` and `AGENT_RUN` always return non-streaming responses (the `stream` field is ignored in SQL; include `"stream": false` for clarity)
- Use `TRY_PARSE_JSON` to convert the JSON string response to a VARIANT for easier reading
- The user's role must have access to the agent object and the `SNOWFLAKE.CORTEX` functions
- Set `timeout_seconds` to 120 when executing, as agent responses can take time

## Output

The agent's text response, extracted and presented to the user in a readable format.

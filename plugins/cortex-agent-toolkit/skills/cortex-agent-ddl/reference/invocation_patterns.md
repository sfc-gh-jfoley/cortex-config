---
name: cortex-agent-ddl-invocation-patterns
description: DATA_AGENT_RUN payload options — variables, role headers, multi-turn threading, and tenant isolation invocation patterns
last_verified: 2026-07-21
---

# DATA_AGENT_RUN — Invocation Patterns

This reference covers **how to call** a Cortex Agent at runtime. For spec creation (what goes inside `CREATE AGENT FROM SPECIFICATION`), see [agent_spec_syntax.md](agent_spec_syntax.md).

---

> **Note on `stream` parameter**: The `stream` key is only meaningful for REST API invocations. In SQL-based invocations via `DATA_AGENT_RUN`, it is ignored — responses are always returned as a complete JSON object.

## Basic invocation

Single-turn, no special options:

```sql
SELECT SNOWFLAKE.CORTEX.DATA_AGENT_RUN(
  'DB.SCHEMA.AGENT_NAME',
  $${
    "messages": [
      {
        "role": "user",
        "content": [{"type": "text", "text": "What is total revenue this quarter?"}]
      }
    ]
  }$$
);
```

---

## Multi-turn conversations

Use `thread_id` and `parent_message_id` to maintain conversation context across calls. The agent remembers prior messages within the same thread.

### First message (start a thread)

```sql
SELECT SNOWFLAKE.CORTEX.DATA_AGENT_RUN(
  'DB.SCHEMA.AGENT_NAME',
  $${
    "messages": [
      {
        "role": "user",
        "content": [{"type": "text", "text": "Show me top 10 customers by revenue."}]
      }
    ]
  }$$
);
```

Parse the response to extract `thread_id` and `message_id` from the returned JSON.

### Follow-up message (continue the thread)

```sql
SELECT SNOWFLAKE.CORTEX.DATA_AGENT_RUN(
  'DB.SCHEMA.AGENT_NAME',
  $${
    "messages": [
      {
        "role": "user",
        "content": [{"type": "text", "text": "Now filter that to just EMEA region."}]
      }
    ],
    "thread_id": "<thread_id from previous response>",
    "parent_message_id": "<message_id from previous response>"
  }$$
);
```

> **Tip**: In application code, store `thread_id` in the user's session and pass `parent_message_id` from the most recent response to chain messages.

---

## Variables block

The `variables` block passes key-value pairs into the agent's execution context. These can be referenced by the agent's instructions or used as session attributes for security scoping.

### Basic variables

```sql
SELECT SNOWFLAKE.CORTEX.DATA_AGENT_RUN(
  'DB.SCHEMA.AGENT_NAME',
  $${
    "messages": [
      {
        "role": "user",
        "content": [{"type": "text", "text": "Show my orders."}]
      }
    ],
    "variables": {
      "region": "EMEA",
      "fiscal_year": "FY2026"
    }
  }$$
);
```

Variables are available to the agent's orchestration instructions and can influence tool behavior.

### Immutable session attributes (tenant isolation)

When `is_immutable_session_attribute` is set to `true`, the variable is injected as a Snowflake session attribute that **cannot be overridden by the agent's generated SQL**. This is the foundation for tenant isolation via session-attribute-based Row Access Policies.

```sql
SELECT SNOWFLAKE.CORTEX.DATA_AGENT_RUN(
  'DB.SCHEMA.AGENT_NAME',
  $${
    "messages": [
      {
        "role": "user",
        "content": [{"type": "text", "text": "Show my orders."}]
      }
    ],
    "variables": {
      "tenant_id": {
        "value": "ACME_CORP",
        "is_immutable_session_attribute": true
      }
    }
  }$$
);
```

The session attribute is then readable inside a RAP via:

```sql
GET_SYS_CONTEXT('SNOWFLAKE$SESSION_ATTRIBUTES', 'tenant_id')
```

> **Security caveat**: This pattern is only secure when the calling application controls the `DATA_AGENT_RUN` payload. If end users can craft arbitrary payloads, they can set any `tenant_id` value. The immutability guarantee means the **agent's LLM-generated SQL** cannot override it — but the **caller** sets the initial value. Trusted middleware (Snowflake's auth flow, a controlled API gateway, or a Streamlit app with server-side session management) must be responsible for setting the correct tenant identity.

> **Source note**: The `is_immutable_session_attribute` pattern is documented in Brian Hess's Medium article (May 2026). Verify behavior against live API before customer-facing use.

---

## Role-based invocation

### X-Snowflake-Role header

When calling `DATA_AGENT_RUN` through the Snowflake REST API (not SQL), the `X-Snowflake-Role` header controls which role executes the agent's queries:

```
POST /api/v2/cortex/agent:run
X-Snowflake-Role: TENANT_ACME_ROLE
Content-Type: application/json

{
  "agent_name": "DB.SCHEMA.AGENT_NAME",
  "messages": [...],
}
```

This enables **role-per-tenant** isolation: each tenant's role has access only to its own data via RBAC grants, and the agent executes under that role.

> **Note**: When calling via SQL (`SELECT SNOWFLAKE.CORTEX.DATA_AGENT_RUN(...)`), the agent executes as the calling user's current role. Use `USE ROLE <tenant_role>` before the call, or use a stored procedure that calls `DATA_AGENT_RUN` under a specific role via caller's rights.

---

## Tenant isolation patterns — invocation side

These patterns pair with the spec-side configuration in Phase 4b. The table below summarizes which invocation mechanism to use for each isolation strategy:

| Isolation pattern | Invocation mechanism | How tenant identity flows |
|---|---|---|
| **User-per-tenant** | No special invocation needed | RAP uses `CURRENT_USER()` — identity comes from authentication |
| **Role-per-tenant** | `X-Snowflake-Role` header (REST) or `USE ROLE` (SQL) | RAP uses `CURRENT_ROLE()` — identity comes from role assumption |
| **Session-attribute** | `variables` block with `is_immutable_session_attribute: true` | RAP uses `GET_SYS_CONTEXT('SNOWFLAKE$SESSION_ATTRIBUTES', '<key>')` |

### Decision guide

- **User-per-tenant**: Simplest. Each user maps to one tenant. Works when users authenticate directly to Snowflake.
- **Role-per-tenant**: Good when users may belong to multiple tenants and switch context. Requires a role hierarchy that maps to tenants.
- **Session-attribute**: Most flexible. Works with shared service accounts where multiple tenants flow through the same Snowflake user. Requires trusted middleware to set the attribute.

---

## Connection pool / hybrid pattern

In applications using connection pools with a shared service account, combine mutable and immutable attributes:

```sql
-- Application middleware sets tenant context before each request:
SELECT SNOWFLAKE.CORTEX.DATA_AGENT_RUN(
  'DB.SCHEMA.AGENT_NAME',
  $${
    "messages": [...],
    "variables": {
      "tenant_id": {
        "value": "<tenant_from_app_auth>",
        "is_immutable_session_attribute": true
      }
    }
  }$$
);
```

The RAP on the base tables uses a `COALESCE` pattern to check both attribute sources:

```sql
-- Inside the RAP body:
COALESCE(
  GET_SYS_CONTEXT('SNOWFLAKE$SESSION_ATTRIBUTES', 'tenant_id'),
  -- fallback: check if the user itself maps to a tenant
  (SELECT tenant_id FROM TENANT_MAP WHERE username = CURRENT_USER())
)
```

This supports both direct-user and service-account access paths.

---

## Extracting responses

### Full response parsing

```sql
SELECT SNOWFLAKE.CORTEX.DATA_AGENT_RUN(
  'DB.SCHEMA.AGENT_NAME',
  $${"messages":[{"role":"user","content":[{"type":"text","text":"<question>"}]}]}$$
) AS raw_response;
```

### Extract text answer

Use FLATTEN with a type filter — `content[N]` indexing is model-specific and will silently return NULL when the response structure changes:

```sql
WITH response AS (
  SELECT TRY_PARSE_JSON(
    SNOWFLAKE.CORTEX.DATA_AGENT_RUN(
      'DB.SCHEMA.AGENT_NAME',
      $${"messages":[{"role":"user","content":[{"type":"text","text":"<question>"}]}]}$$
    )
  ) AS r
)
SELECT f.value:text::STRING AS answer
FROM response, LATERAL FLATTEN(input => r:content) f
WHERE f.value:type::STRING = 'text'
  AND f.value:text::STRING IS NOT NULL
ORDER BY f.index DESC
LIMIT 1;
```

> **Legacy/Debug only — do not use in production**: `content[7]:text::STRING` is index-specific
> for claude-sonnet models only. Returns NULL silently if response structure changes (different
> model, more tool cycles). For reference only:
>
> ```sql
> SELECT TRY_PARSE_JSON(
>   SNOWFLAKE.CORTEX.DATA_AGENT_RUN(
>     'DB.SCHEMA.AGENT_NAME',
>     $${"messages":[{"role":"user","content":[{"type":"text","text":"<question>"}]}]}$$
>   )
> ):content[7]:text::STRING;
> ```

---

## Response block types — tool use events

> ⚠️ **Breaking change (Apr 13, 2026)**: Tool use and tool result blocks previously used type `cortex_analyst_text_to_sql`. They now use type `system_execute_sql`. Any application parsing responses for `cortex_analyst_text_to_sql` blocks must be updated — the old type is no longer emitted.

When a `cortex_analyst_text_to_sql` tool fires, two entries appear in the response `content` array:

**Tool use block** (agent requesting SQL execution):
```json
{
  "type": "system_execute_sql",
  "id": "<tool_use_id>",
  "sql": "<SQL generated by the agent>"
}
```

**Tool result block** (SQL execution result):
```json
{
  "type": "tool_result",
  "tool_use_id": "<tool_use_id>",
  "content": {
    "query_id": "<Snowflake query ID>",
    "result_set": [ { "<col>": "<val>", ... } ],
    "final_sql": "<actual SQL executed>"
  }
}
```

To inspect all block types in a response:
```sql
WITH response AS (
  SELECT TRY_PARSE_JSON(
    SNOWFLAKE.CORTEX.DATA_AGENT_RUN(
      'DB.SCHEMA.AGENT_NAME',
      $${"messages":[{"role":"user","content":[{"type":"text","text":"<question>"}]}]}$$
    )
  ) AS r
),
blocks AS (
  SELECT f.value AS block, f.index AS idx
  FROM response, LATERAL FLATTEN(input => r:content) f
)
SELECT
  idx,
  block:type::STRING                        AS block_type,
  block:sql::STRING                         AS generated_sql,
  block:content:query_id::STRING            AS query_id,
  block:text::STRING                        AS text_answer
FROM blocks
ORDER BY idx;
```

**Observability**: In `CORTEX_AGENT_USAGE_HISTORY`, `TOKENS_GRANULAR` and `CREDITS_GRANULAR` no longer include entries with service type `cortex_analyst`. All usage is now reported under `cortex_agents`.

---

## Payload reference (complete)

```json
{
  "messages": [
    {
      "role": "user",
      "content": [
        {"type": "text", "text": "<user question>"}
      ]
    }
  ],
  "thread_id": "<optional: continue existing thread>",
  "parent_message_id": "<optional: chain to specific message>",
  "variables": {
    "<key>": "<simple string value>",
    "<key>": {
      "value": "<string value>",
      "is_immutable_session_attribute": true
    }
  }
}
```

| Field | Required | Description |
|---|---|---|
| `messages` | Yes | Array of message objects. Each has `role` ("user") and `content` (array of `{type, text}`) |
| `thread_id` | No | UUID from a previous response to continue the conversation |
| `parent_message_id` | No | UUID of the specific message to reply to within a thread |
| `variables` | No | Key-value pairs for context injection. Values can be strings or objects with `is_immutable_session_attribute` |

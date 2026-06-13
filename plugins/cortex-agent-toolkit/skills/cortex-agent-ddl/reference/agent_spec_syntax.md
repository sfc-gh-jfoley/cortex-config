---
name: cortex-agent-ddl-spec-reference
description: Complete Cortex Agent spec JSON syntax — all fields, valid model names, tool types, experimental flags, execution_environment, profile, error cheat sheet
last_verified: 2026-05-21
---

# Cortex Agent Spec — Full Reference

## Top-level spec template

```json
{
  "models": {
    "orchestration": "<model_name>"
  },
  "experimental": {
    "EnableVQRFastPath": true
  },
  "orchestration": {
    "budget": {
      "seconds": 120,
      "tokens": 200000
    }
  },
  "instructions": {
    "orchestration": "<system prompt>",
    "response": "<response style instructions>",
    "sample_questions": [
      { "question": "<example question 1>" },
      { "question": "<example question 2>" }
    ]
  },
  "tools": [
    {
      "tool_spec": {
        "type": "<tool_type>",
        "name": "<tool_name>",
        "description": "<rich tool description>"
      }
    }
  ],
  "tool_resources": {
    "<tool_name>": {
      "semantic_view": "<DB>.<SCHEMA>.<SV_NAME>",
      "execution_environment": {
        "type": "warehouse",
        "warehouse": "<WAREHOUSE_NAME>"
      }
    }
  }
}
```

> ⚠️ **There is no top-level `execution_environment` field.** Warehouse configuration goes inside each `tool_resources` entry as `execution_environment: {type: "warehouse", warehouse: "..."}`. A top-level `execution_environment` block is rejected as an unrecognized field.

---

## Valid model names (orchestration)

Only Claude and OpenAI models are supported for agent orchestration. Open-weight models (Llama, Mistral) work with COMPLETE() but do NOT reliably complete the agent tool-use loop.

### Claude Models

| Model | Tier | Notes |
|-------|------|-------|
| `claude-opus-4-7` | Heavy | Most capable, slowest, highest cost |
| `claude-opus-4-6` | Heavy | Previous Opus generation |
| `claude-opus-4-5` | Heavy | Older Opus |
| `claude-sonnet-4-6` | Balanced | **Recommended default** — quality + speed |
| `claude-sonnet-4-5` | Balanced | Previous Sonnet generation |
| `claude-haiku-4-5` | Fast | Best latency with full tool-use support (~30% faster than Sonnet) |
| `claude-4-sonnet` | Legacy | Deprecated alias for older Sonnet |
| `claude-4-5-sonnet` | Legacy | Deprecated alias |

### OpenAI Models

| Model | Tier | Notes |
|-------|------|-------|
| `openai-gpt-5.2` | Heavy | Latest, most capable |
| `openai-gpt-5.1` | Heavy | Previous GPT-5 |
| `openai-gpt-5` | Balanced | Base GPT-5 |
| `openai-gpt-5-mini` | Fast | Smaller, faster |
| `openai-gpt-4.1` | Legacy | Previous generation |

> ⚠️ `openai-gpt-5-nano` is available for COMPLETE() but is **NOT allowed** in agent orchestration.

### Speed Recommendations

> Resolve alias values from `~/.snowflake/cortex/vault/LLMs.md` before using in specs.

- **Demo / latency-sensitive**: `fast_agent` alias (e.g. claude-haiku class) or `openai_fast` alias
- **Production default**: `default_agent` alias (e.g. current Sonnet class)
- **Maximum accuracy**: `heavy_agent` alias (e.g. current Opus class) or `openai_heavy` alias

> **Note**: `auto` resolves to a Sonnet-class model. For explicit speed control, set the model directly.

---

## Tool types

### `cortex_analyst_text_to_sql`

Translates natural language questions into SQL against a Semantic View.

```json
{
  "tool_spec": {
    "type": "cortex_analyst_text_to_sql",
    "name": "MyAnalyticsTool",
    "description": "..."
  }
}
```

`tool_resources` entry:
```json
"MyAnalyticsTool": {
  "semantic_view": "DB.SCHEMA.SEMANTIC_VIEW_NAME",
  "execution_environment": {
    "type": "warehouse",
    "warehouse": "MY_WH"
  }
}
```

**Requirements**:
- `semantic_view` must be a fully-qualified 3-part name pointing to a **Semantic View** object — NOT a regular SQL view, table, or materialized view.
- Run `SHOW SEMANTIC VIEWS LIKE '<name>'` to confirm the object exists and is of type SEMANTIC_VIEW.
- `execution_environment.type` must be `"warehouse"` and `execution_environment.warehouse` must be set. Omitting `execution_environment` from a tool's tool_resources entry causes `DATA_AGENT_RUN` error 399504 ("missing execution environment").

---

### `cortex_search`

Semantic/keyword search over a Cortex Search Service (CSS).

```json
{
  "tool_spec": {
    "type": "cortex_search",
    "name": "MySearchTool",
    "description": "..."
  }
}
```

`tool_resources` entry:
```json
"MySearchTool": {
  "name": "DB.SCHEMA.CSS_SERVICE_NAME",
  "max_results": 5
}
```

**Requirements**:
- `name` must be a fully-qualified 3-part name pointing to a **Cortex Search Service**.
- Run `SHOW CORTEX SEARCH SERVICES LIKE '<name>'` to confirm.
- `max_results` optional, defaults to 5.

---

### `generic`

Calls a custom Snowflake UDF or stored procedure.

```json
{
  "tool_spec": {
    "type": "generic",
    "name": "MyCustomTool",
    "description": "..."
  }
}
```

`tool_resources` entry — function:
```json
"MyCustomTool": {
  "function": "DB.SCHEMA.FUNCTION_NAME"
}
```

`tool_resources` entry — procedure:
```json
"MyCustomTool": {
  "procedure": "DB.SCHEMA.PROC_NAME"
}
```

---

### `sql`

Executes a parameterized SQL statement.

```json
{
  "tool_spec": {
    "type": "sql",
    "name": "MySqlTool",
    "description": "..."
  }
}
```

`tool_resources` entry:
```json
"MySqlTool": {
  "statement": "SELECT * FROM MY_DB.MY_SCHEMA.MY_TABLE WHERE id = ?",
  "warehouse": "MY_WH"
}
```

---

### `code_interpreter`

Executes code in a sandboxed container (requires SPCS + account-level parameter).

```json
{
  "tool_spec": {
    "type": "code_interpreter",
    "name": "code_interpreter"
  }
}
```

`tool_resources` entry:
```json
"code_interpreter": {
  "enabled": "true"
}
```

---

## Experimental flags

These go inside `"experimental": {}`.

| Flag | Type | Effect |
|------|------|--------|
| `EnableAgenticAnalyst` | ~~obsolete~~ | **Default behavior as of April 2026** — this flag is now the standard. Setting it has no documented effect. Remove from new agent specs. |
| `EnableVQRFastPath` | `true`/`false` | Skips full orchestration for simple single-tool questions — faster but less nuanced. Default `true` |
| `EnableUnrestrictedChartTool` | `true`/`false` | Allows chart generation without account-level policy restrictions. Use with care. |

```json
"experimental": {
  "EnableVQRFastPath": true
  // Add flags here only if recommended by Snowflake — see cortex-agent-flags/EXPERIMENTAL_FLAGS.md
}
```

---

## execution_environment

Warehouse configuration is specified **per tool** inside `tool_resources`, not at the spec root.

For each `cortex_analyst_text_to_sql` tool, include inside its `tool_resources` entry:

```json
"<tool_name>": {
  "semantic_view": "<DB>.<SCHEMA>.<SV_NAME>",
  "execution_environment": {
    "type": "warehouse",
    "warehouse": "MY_WAREHOUSE"
  }
}
```

> ⚠️ Do **not** put `execution_environment` at the spec root — it will be rejected as an unrecognized field and cause CREATE to fail.  
> Do **not** use a flat `"warehouse"` key directly in the tool_resources entry — this causes `DATA_AGENT_RUN` error 399504 (missing execution environment) at query time even if CREATE succeeds.

---

## orchestration.budget

Controls max execution time and token spend per request.

```json
"orchestration": {
  "budget": {
    "seconds": 120,
    "tokens": 200000
  }
}
```

| Field | Default | Notes |
|-------|---------|-------|
| `seconds` | 60 | Wall-clock timeout per request. 120 recommended for multi-tool agents. |
| `tokens` | 100000 | Max LLM tokens per request (input + output combined). 200000 for complex queries. |

---

## instructions structure

```json
"instructions": {
  "orchestration": "You are a ...",
  "response": "Always include ...",
  "sample_questions": [
    { "question": "What is the total revenue this quarter?" },
    { "question": "Show me the top 10 customers by spend." }
  ]
}
```

- `orchestration` — main system prompt. Agent identity, scope, tool routing rules. Required.
- `response` — output format instructions. Optional but improves consistency.
- `sample_questions` — shown in Snowflake Intelligence UI as quick-start prompts. Use 4-6 business-relevant questions.

> ⚠️ `sample_questions` must be **inside** `instructions` — NOT at the spec root level.

---

## profile (display settings for Snowflake Intelligence)

Set via `ALTER AGENT ... SET PROFILE` after creation (not in the spec JSON):

```sql
ALTER AGENT DB.SCHEMA.MY_AGENT SET PROFILE = '{
  "display_name": "My Business Agent",
  "avatar": "robot",
  "color": "#0057B8"
}';
```

Valid `avatar` values: `robot`, `assistant`, `analyst`, `chart`, `search`  
`color`: any hex color string

> Without a profile, the agent appears as a UUID in Snowflake Intelligence — always set display_name.

---

## DDL syntax — CREATE and ALTER

### CREATE

```sql
CREATE [ OR REPLACE ] AGENT <db>.<schema>.<name>
FROM SPECIFICATION $$
<spec JSON>
$$;
```

### ALTER (spec replace — only way to change spec fields)

```sql
ALTER AGENT <db>.<schema>.<name>
  MODIFY LIVE VERSION SET SPECIFICATION = $$
<full new spec JSON>
$$;
```

> ⚠️ There is **no targeted field update** syntax for agents. Every spec change (instructions, tools, model, flags, budget) requires replacing the entire spec. Only `COMMENT` and `PROFILE` can be set independently.

### ALTER (comment and profile — independent from spec)

```sql
-- Set comment only:
ALTER AGENT <db>.<schema>.<name> SET COMMENT = '<description>';

-- Set profile only:
ALTER AGENT <db>.<schema>.<name> SET PROFILE = '{"display_name": "My Agent", "avatar": "robot", "color": "#0057B8"}';

-- Both at once:
ALTER AGENT <db>.<schema>.<name>
  SET COMMENT = '...',
      PROFILE = '{"display_name": "..."}';
```

### DESCRIBE (inspect current spec)

```sql
DESCRIBE AGENT <db>.<schema>.<name>;
```

Returns columns: `name`, `database_name`, `schema_name`, `spec`, `created_on`, `last_altered_on`, `owner`, `comment`

### GET_DDL (reconstruct CREATE statement)

```sql
SELECT GET_DDL('AGENT', '<db>.<schema>.<name>');
```

### SHOW AGENTS

```sql
SHOW AGENTS IN ACCOUNT;
SHOW AGENTS IN DATABASE <db>;
SHOW AGENTS IN SCHEMA <db>.<schema>;
```

---

## Error cheat sheet

| Error message | Root cause | Fix |
|--------------|-----------|-----|
| `Object '<name>' does not exist` on tool_resources | Semantic view or CSS FQN is wrong | Run `SHOW SEMANTIC VIEWS` / `SHOW CORTEX SEARCH SERVICES` to confirm FQN |
| `Invalid specification: unrecognized field 'execution_environment'` | `execution_environment` placed at spec root level | Move it into each `tool_resources[name]` entry as `execution_environment: {type: "warehouse", warehouse: "..."}` |
| `DATA_AGENT_RUN error 399504: missing execution environment` | Flat `"warehouse"` key in tool_resources instead of nested `execution_environment` | Change to `execution_environment: {type: "warehouse", warehouse: "..."}` inside the tool_resources entry |
| `Tool '<name>' defined in tools but not in tool_resources` | tool_resources key missing or misspelled | Ensure tool_resources has a key matching exactly `tool_spec.name` |
| `Invalid model name` | Unsupported string in `models.orchestration` | Use a model from the valid model names list above |
| `Agent not found` | Wrong FQN or missing privilege | Check SHOW AGENTS; verify role has USAGE on schema |
| `Timeout exceeded` | `budget.seconds` too low for complex multi-tool question | Increase to 120-180 |
| Blank response / no tools called | Instructions too vague, tool descriptions too short | Improve tool descriptions (>100 chars, add "When NOT to use") |
| Profile not visible in SI | `ALTER AGENT SET PROFILE` not run | Run ALTER AGENT SET PROFILE with display_name/avatar/color |

---

## Tool description best-practices template

Follow this structure for every tool description:

```
[1-sentence summary of what this tool queries]

Data coverage: [what tables/domain it covers, date range if relevant]

When to use:
- [specific question type 1]
- [specific question type 2]

When NOT to use:
- Do NOT use for [out-of-scope question type 1]
- Do NOT use for [out-of-scope question type 2]
```

**Minimum quality bar**: >100 characters, contains "When NOT to use" or equivalent boundary language.  
**Why**: Tool descriptions are the #1 factor in agent quality. Vague descriptions cause tool misselection, leading to hallucinations.

---

## DATA_AGENT_RUN — invoke agent in SQL

> **Full invocation reference**: See [invocation_patterns.md](invocation_patterns.md) for multi-turn threading, `variables` block, tenant isolation invocation, role headers, and response parsing patterns.

Basic invocation:

```sql
SELECT SNOWFLAKE.CORTEX.DATA_AGENT_RUN(
  'DB.SCHEMA.AGENT_NAME',
  $${"messages":[{"role":"user","content":[{"type":"text","text":"<question>"}]}]}$$
);
```

Extract text answer (use FLATTEN — portable across all accounts):
```sql
SELECT TRY_PARSE_JSON(
  SNOWFLAKE.CORTEX.DATA_AGENT_RUN(
    'DB.SCHEMA.AGENT_NAME',
    $${{"messages":[{{"role":"user","content":[{{"type":"text","text":"<question>"}}]}}]}}$$
  )
):content[7]:text::STRING;
```

> ⚠️ **Debug/legacy only** — `content[N]` indexing is model-specific and will silently return NULL when
> the response structure changes. Use the FLATTEN pattern from `invocation_patterns.md` for all
> non-debug purposes: filter `content` array by `type = 'text'` instead of hardcoding an index.

---
name: cortex-agent-ddl-spec-reference
description: Complete Cortex Agent spec JSON syntax — all fields, valid model names, tool types, experimental flags, execution_environment, profile, error cheat sheet
last_verified: 2026-07-21
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

Translates natural language questions into SQL against a Semantic View or YAML semantic model.

```json
{
  "tool_spec": {
    "type": "cortex_analyst_text_to_sql",
    "name": "MyAnalyticsTool",
    "description": "..."
  }
}
```

`tool_resources` entry — exactly one of `semantic_view` or `semantic_model_file` is required:
```json
"MyAnalyticsTool": {
  "semantic_view": "DB.SCHEMA.SEMANTIC_VIEW_NAME",
  "execution_environment": {
    "type": "warehouse",
    "warehouse": "MY_WH",
    "query_timeout": 60
  }
}
```

Or using a YAML file on a Snowflake Stage:
```json
"MyAnalyticsTool": {
  "semantic_model_file": "@DB.SCHEMA.MY_STAGE/semantic_model.yaml",
  "execution_environment": {
    "type": "warehouse",
    "warehouse": "MY_WH"
  }
}
```

**Requirements**:
- `semantic_view` must be a fully-qualified 3-part name pointing to a **Semantic View** object.
- `semantic_model_file` is the alternative for stage-based YAML semantic models.
- Exactly one of the two must be provided — not both.
- Run `SHOW SEMANTIC VIEWS LIKE '<name>'` to confirm a Semantic View object exists.
- Omitting `execution_environment` from the tool_resources entry causes `DATA_AGENT_RUN` error 399504.

> ⚠️ **Breaking change (Apr 13, 2026)**: Tool use and tool result blocks emitted by this tool type changed from `cortex_analyst_text_to_sql` to `system_execute_sql`. If your application parses agent responses for `cortex_analyst_text_to_sql` blocks, update it to look for `system_execute_sql` instead. See [invocation_patterns.md](invocation_patterns.md) for the full block schema and migration notes.

---

### `cortex_search`

Semantic/keyword search over a Cortex Search Service.

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
  "max_results": 5,
  "title_column": "document_title",
  "id_column": "document_id",
  "filter": {
    "@eq": { "region": "North America" }
  }
}
```

> ⚠️ **Field naming discrepancy**: The YAML/DDL spec uses `name` for the service FQN; the REST API
> JSON schema uses `search_service`. Both appear in official docs. Use `name` for DDL/YAML specs;
> use `search_service` when constructing the spec via the REST API directly.

| Field | Required | Notes |
|---|---|---|
| `name` / `search_service` | Yes | FQN of the Cortex Search Service |
| `max_results` | No | Defaults to 5 |
| `title_column` | No | Column to use as document title in results |
| `id_column` | No | Column to use as document ID |
| `filter` | No | Filter object; use `@eq`, `@contains`, etc. operators |

**Requirements**:
- Run `SHOW CORTEX SEARCH SERVICES LIKE '<name>'` to confirm the service exists.

---

### `generic`

Calls a Snowflake UDF or stored procedure server-side.

```json
{
  "tool_spec": {
    "type": "generic",
    "name": "MyCustomTool",
    "description": "...",
    "input_schema": {
      "type": "object",
      "properties": {
        "param1": { "type": "string", "description": "..." }
      },
      "required": ["param1"]
    }
  }
}
```

`tool_resources` entry:
```json
"MyCustomTool": {
  "type": "function",
  "identifier": "DB.SCHEMA.MY_UDF_OR_PROC",
  "execution_environment": {
    "type": "warehouse",
    "warehouse": "MY_WH",
    "query_timeout": 60
  }
}
```

| Field | Required | Notes |
|---|---|---|
| `type` | Yes | `"function"` (UDF) or `"stored_procedure"` |
| `identifier` | Yes | Fully qualified name of the UDF or stored procedure |
| `execution_environment` | Yes | Warehouse to execute on |

> ⚠️ **Correct `tool_resources` schema uses `type` + `identifier`**, not `"function": "..."` or
> `"procedure": "..."` key names. The latter will be silently ignored or error at runtime.

---

### `web_search`

Performs a web search and returns results. No `tool_spec.input_schema` required.

```json
{
  "tool_spec": {
    "type": "web_search",
    "name": "MyWebSearch",
    "description": "..."
  }
}
```

`tool_resources` entry:
```json
"MyWebSearch": {
  "max_results": 10
}
```

| Field | Required | Notes |
|---|---|---|
| `max_results` | No | Maximum web results to return |

---

### `sql` *(unconfirmed — not in official API schema)*

Executes a parameterized SQL statement. This type appears in third-party references but is **not
listed in the official Snowflake API ToolSpec schema**. Use `generic` with a stored procedure as
the confirmed alternative.

```json
{
  "tool_spec": {
    "type": "sql",
    "name": "MySqlTool",
    "description": "..."
  }
}
```

`tool_resources` entry (if supported):
```json
"MySqlTool": {
  "statement": "SELECT * FROM MY_DB.MY_SCHEMA.MY_TABLE WHERE id = ?",
  "warehouse": "MY_WH"
}
```

---

### `code_execution` *(Private Preview)*

Built-in tool that executes Python in a secure, isolated sandbox. The agent decides at runtime whether to invoke it based on the user's query. Also used when executing Python scripts as part of an agent skill.

```json
{
  "tool_spec": {
    "type": "code_execution",
    "name": "code_execution"
  }
}
```

`tool_resources` entry — bare minimum:
```json
"code_execution": {}
```

With PyPI package access:
```json
"code_execution": {
  "artifact_repositories": [
    "SNOWFLAKE.SNOWPARK.PYPI_SHARED_REPOSITORY"
  ]
}
```

With external internet access:
```json
"code_execution": {
  "external_access_integrations": [
    "my_integration"
  ]
}
```

**Default environment**: Python 3.12, `numpy` and `pandas` pre-installed. The sandbox persists within a session — imports, variables, and intermediate results survive across multiple tool invocations in the same session.

**PyPI access**: Requires the database role `SNOWFLAKE.PYPI_REPOSITORY_USER` granted to the agent owner role. Check current grants:

```sql
SHOW GRANTS OF DATABASE ROLE SNOWFLAKE.PYPI_REPOSITORY_USER;
```

If the owner role is not listed (directly or via `PUBLIC`), grant it:

```sql
GRANT DATABASE ROLE SNOWFLAKE.PYPI_REPOSITORY_USER TO ROLE <agent_owner_role>;
```

> **Note**: Many accounts grant this to `PUBLIC` by default — check before granting redundantly.

**External access**: Create a network rule and external access integration, then reference the integration name in `external_access_integrations`. See [Snowflake docs](https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-agents-code-execution-tool) for the full setup.

**Limitations**:
- Sandbox is session-scoped — state does not persist across separate `DATA_AGENT_RUN` invocations.
- Code execution operates under the agent owner role's privileges.

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

For each `cortex_analyst_text_to_sql` or `generic` tool, include inside its `tool_resources` entry:

```json
"<tool_name>": {
  "semantic_view": "<DB>.<SCHEMA>.<SV_NAME>",
  "execution_environment": {
    "type": "warehouse",
    "warehouse": "MY_WAREHOUSE",
    "query_timeout": 60
  }
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `type` | string | Yes | Always `"warehouse"` (only supported value) |
| `warehouse` | string | Yes | Case-sensitive — use ALL_CAPS for unquoted identifiers |
| `query_timeout` | integer | No | Per-query timeout in seconds; overrides warehouse default |

> ⚠️ Do **not** put `execution_environment` at the spec root — rejected as an unrecognized field.  
> Do **not** use a flat `"warehouse"` key directly in the tool_resources entry — causes error 399504 at query time even if CREATE succeeds.

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

Can be set in `CREATE AGENT` directly or updated later via `ALTER AGENT SET PROFILE`:

```sql
-- In CREATE AGENT (optional, alongside COMMENT):
CREATE OR REPLACE AGENT DB.SCHEMA.MY_AGENT
  COMMENT = 'My agent'
  PROFILE = '{"display_name": "My Business Agent", "avatar": "robot", "color": "#0057B8"}'
  FROM SPECIFICATION $$ ... $$;

-- Or update after creation:
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
| `generic` tool returns no results / wrong data | Using `"function": "..."` or `"procedure": "..."` keys in tool_resources (old incorrect schema) | Use `"type": "function"` + `"identifier": "DB.SCHEMA.NAME"` + `"execution_environment"` |
| `Invalid model name` | Unsupported string in `models.orchestration` | Use a model from the valid model names list above |
| `Agent not found` | Wrong FQN or missing privilege | Check SHOW AGENTS; verify role has USAGE on schema |
| `Timeout exceeded` | `budget.seconds` too low for complex multi-tool question | Increase to 120-180 |
| Blank response / no tools called | Instructions too vague, tool descriptions too short | Improve tool descriptions (>100 chars, add "When NOT to use") |
| Profile not visible in SI | `ALTER AGENT SET PROFILE` not run | Run ALTER AGENT SET PROFILE with display_name/avatar/color |
| `DATA_AGENT_RUN` returns "agent not found" with `!VERSION$N` suffix | Version was dropped or wrong identifier | Run `SHOW VERSIONS IN AGENT <fqn>` to confirm the version exists |
| `ALTER AGENT ... COMMIT` fails with "no live version" | No live version exists (already committed or never created) | Run `ALTER AGENT ... ADD LIVE VERSION FROM LAST` first |
| `ALTER AGENT ... ADD LIVE VERSION` fails | A live version already exists | Each agent can have at most one live version — commit the existing one first |

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

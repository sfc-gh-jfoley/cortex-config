---
name: cortex-agent-ddl-phase4-assemble-spec
description: Assemble the complete agent spec JSON from all prior phase outputs — model, experimental flags, execution_environment, budget, tools, instructions, and profile notes
---

# Phase 4: Assemble Spec JSON

## Purpose
Combine all outputs from Phases 1-3 into a single, complete spec JSON ready for self-check and execution.

This phase produces one artifact: `AGENT_SPEC` — the full spec JSON. No user interaction required unless a field is ambiguous. Proceed directly to Phase 5.

---

## Step 4.1: Select model

If not already specified by the user, recommend `claude-sonnet-4-5`:

```
Recommended model: claude-sonnet-4-5
(Best balance of instruction-following and speed for multi-tool agents)

Other options: claude-opus-4 (highest quality), claude-haiku-3-5 (fastest)
Confirm model or override:
```

Store as `AGENT_MODEL`.

---

## Step 4.2: Set experimental flags

Default flags for all new agents:

```json
"experimental": {
  "EnableAgenticAnalyst": true,
  "EnableVQRFastPath": true
}
```

> **Router agents**: If `AGENT_TYPE == "router"`, default `EnableVQRFastPath` to `false`. The fast path skips full orchestration, which defeats routing logic.

Ask if the user wants to adjust any flags. Reference `../reference/agent_spec_syntax.md` for flag descriptions.

Store as `EXPERIMENTAL_FLAGS`.

---

## Step 4.3: Set budget

Default values:

```json
"orchestration": {
  "budget": {
    "seconds": 120,
    "tokens": 200000
  }
}
```

If `AGENT_PURPOSE` mentions real-time, operational, or simple lookup use cases → suggest `seconds: 60, tokens: 100000`.  
If it mentions complex multi-step analytics → suggest `seconds: 180, tokens: 300000`.

Ask user to confirm or override. Store as `AGENT_BUDGET`.

---

## Step 4.4: Build tools array

For each tool (SVs + CSS + custom in order from Phase 2):

```json
{
  "tool_spec": {
    "type": "<tool_type>",
    "name": "<TOOL_NAME>",
    "description": "<TOOL_DESCRIPTIONS[TOOL_NAME]>"
  }
}
```

**For `cortex_analyst_text_to_sql`**: type = `"cortex_analyst_text_to_sql"`  
**For `cortex_search`**: type = `"cortex_search"`  
**For generic/UDF**: type = `"generic"`  
**For parameterized SQL**: type = `"sql"`

---

## Step 4.5: Build tool_resources

> ⚠️ **CRITICAL — #1 deployment failure**: Every `cortex_analyst_text_to_sql` tool MUST have `execution_environment` nested inside its `tool_resources` entry. Without it, `CREATE AGENT` succeeds but `DATA_AGENT_RUN` fails with error 399504 ("missing execution environment"). This is NOT optional. Do NOT use a flat `"warehouse"` key — it must be the nested structure shown below.

For each SV tool:
```json
"<TOOL_NAME>": {
  "semantic_view": "<SV_FQN>",
  "execution_environment": {
    "type": "warehouse",
    "warehouse": "<AGENT_WAREHOUSE>"
  }
}
```

For each CSS tool:
```json
"<TOOL_NAME>": {
  "name": "<CSS_FQN>",
  "max_results": 5
}
```

For each generic tool:
```json
"<TOOL_NAME>": {
  "function": "<DB>.<SCHEMA>.<FUNCTION_NAME>"
}
```

---

## Step 4.6: Assemble the full spec

Combine all sections into the complete JSON:

```json
{
  "models": {
    "orchestration": "<AGENT_MODEL>"
  },
  "experimental": <EXPERIMENTAL_FLAGS>,
  "orchestration": {
    "budget": <AGENT_BUDGET>
  },
  "instructions": {
    "orchestration": "<INSTRUCTIONS_ORCHESTRATION>",
    "response": "<INSTRUCTIONS_RESPONSE>",
    "sample_questions": <SAMPLE_QUESTIONS>
  },
  "tools": [
    <tool entries from Step 4.4>
  ],
  "tool_resources": {
    "<TOOL_NAME>": {
      "semantic_view": "<SV_FQN>",
      "execution_environment": {
        "type": "warehouse",
        "warehouse": "<AGENT_WAREHOUSE>"
      }
    }
  }
}
```

> ⚠️ Do **not** include a top-level `execution_environment` field — it is rejected as an unrecognized field. Warehouse configuration belongs inside each `tool_resources` entry as shown above.

Store as `AGENT_SPEC`.

---

## Step 4.7: Profile note

The agent profile (display_name, avatar, color) is set via `ALTER AGENT SET PROFILE` **after** creation — it cannot be included in the spec JSON. Record the desired profile values now for use in Phase 6:

Ask:
```
Profile settings for Snowflake Intelligence UI:
  display_name: [e.g., "Sales Pipeline Agent"]
  avatar: [robot | assistant | analyst | chart | search] — default: robot
  color: [hex color, e.g., #0057B8] — default: Snowflake blue
```

Store as `AGENT_PROFILE`. Proceed to Phase 5 immediately — no user stop needed here.

---

## Output variables passed to next phases

| Variable | Contents |
|----------|----------|
| `AGENT_SPEC` | Complete spec JSON string |
| `AGENT_MODEL` | Selected model name |
| `EXPERIMENTAL_FLAGS` | Experimental flags JSON block |
| `AGENT_BUDGET` | Budget JSON block |
| `AGENT_PROFILE` | Dict with display_name, avatar, color |

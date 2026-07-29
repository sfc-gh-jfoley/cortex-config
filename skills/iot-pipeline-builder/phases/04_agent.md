---
name: iot-pipeline-builder-phase4
description: Create Cortex Agent over the Semantic View — spec assembly, self-check, execute, smoke test
---

# Phase 4: Cortex Agent

## Step 4.1: Write the tool description

From the `DESCRIBE SEMANTIC VIEW` output in Phase 3, write a tool description:
- Must be **>100 characters**
- Must include **boundary language** — what the tool covers AND what it does not
- Format: "Use this tool to query [domain] data including [key topics]. Covers [table 1], [table 2], [table 3]. Do not use for [out-of-scope topics]."

Store as `TOOL_DESCRIPTION`.

---

## Step 4.2: Write the orchestration instructions

Based on what you know about the domain from Phases 1-3, write instructions that:
- State the agent's role and audience (who will use it)
- Reference key thresholds or domain rules discovered in the data (e.g., numeric ranges, status codes)
- Tell the agent to cite specific IDs and timestamps in answers
- Tell the agent to use the tool for ALL data questions

Store as `ORCHESTRATION_INSTRUCTIONS`.

---

## Step 4.3: Assemble the spec JSON

```json
{
  "models": {
    "orchestration": "claude-sonnet-4-6"
  },
  "experimental": {
    "EnableAgenticAnalyst": true,
    "EnableVQRFastPath": true
  },
  "orchestration": {
    "budget": {
      "seconds": 120,
      "tokens": 200000
    }
  },
  "instructions": {
    "orchestration": "<ORCHESTRATION_INSTRUCTIONS>",
    "response": "Be concise and specific. Always include device IDs, timestamps, and numeric values when available. Format tabular results as markdown tables.",
    "sample_questions": [
      { "question": "<question 1 from Phase 5 preview>" },
      { "question": "<question 2 from Phase 5 preview>" },
      { "question": "<question 3 from Phase 5 preview>" }
    ]
  },
  "tools": [
    {
      "tool_spec": {
        "type": "cortex_analyst_text_to_sql",
        "name": "query_data",
        "description": "<TOOL_DESCRIPTION>"
      }
    }
  ],
  "tool_resources": {
    "query_data": {
      "semantic_view": "<MY_SV_FQN>",
      "execution_environment": {
        "type": "warehouse",
        "warehouse": "<CURRENT_WAREHOUSE>"
      }
    }
  }
}
```

> ⚠️ `execution_environment` goes **inside `tool_resources.query_data`** — NOT at the top level.  
> A top-level `execution_environment` block is rejected with an unrecognized field error.

---

## Step 4.4: Self-check before executing

Verify all 5 before running the CREATE:

1. `models.orchestration` is set (not empty, not "auto")
2. `instructions.orchestration` is non-empty
3. `execution_environment` is nested inside `tool_resources.query_data` — not top-level
4. `tool_resources` key `"query_data"` exactly matches `tools[0].tool_spec.name`
5. `semantic_view` value is a valid FQN (3 parts: `DB.SCHEMA.NAME`) matching what was created in Phase 3

Fix any issue before proceeding.

---

## Step 4.5: Execute

Get the current warehouse:
```sql
SELECT CURRENT_WAREHOUSE();
```

Substitute into the spec, then run:

```sql
CREATE SCHEMA IF NOT EXISTS <MY_DB>.<MY_AGENTS_SCHEMA>;

CREATE OR REPLACE AGENT <MY_DB>.<MY_AGENTS_SCHEMA>.<AGENT_NAME>
FROM SPECIFICATION $$
<SPEC_JSON>
$$;

-- Set display profile for Snowflake Intelligence UI
ALTER AGENT <MY_DB>.<MY_AGENTS_SCHEMA>.<AGENT_NAME>
  SET PROFILE = '{"display_name": "<friendly name>", "color": "#0057B8"}';
```

---

## Step 4.6: Verify structure

```sql
DESCRIBE AGENT <MY_DB>.<MY_AGENTS_SCHEMA>.<AGENT_NAME>;
```

Confirm: tools listed, orchestration model shown. If CREATE failed, read the error, fix the spec, retry.

---

## Step 4.7: Smoke test

Use a question that requires the agent to **join across two tables**. A single-table question passes even if the SV relationships are broken.

```sql
SELECT SNOWFLAKE.CORTEX.DATA_AGENT_RUN(
    '<MY_DB>.<MY_AGENTS_SCHEMA>.<AGENT_NAME>',
    '{"messages": [{"role": "user", "content": [{"type": "text", "text": "Which devices have the weakest signal and do any of them have open incidents?"}]}]}'
) AS response;
```

**Evaluate the response — do not treat any response as a pass:**

| Response pattern | Diagnosis |
|-----------------|-----------|
| Returns device IMEIs with RSRP values AND incident IDs | ✅ PASS — relationships working |
| Returns device IMEIs with RSRP only, no incident data | ⚠️ WARN — SV relationship may be broken; cross-table join failed silently |
| Response contains `"error"` or `"does not exist"` | ❌ FAIL — SV FQN wrong or `execution_environment` missing in spec |
| Response returns in < 2 seconds | ❌ FAIL — agent fast-failed, SV likely not found (CREATE AGENT does not validate SV existence at DDL time) |

If PASS → proceed to **Phase 5**.  
If WARN → go back to Phase 3 and verify the RELATIONSHIPS clause used DT_DEVICES as anchor.  
If FAIL (error) → check `execution_environment` is nested inside `tool_resources`, not top-level.  
If FAIL (fast) → run `DESCRIBE SEMANTIC VIEW <MY_SV_FQN>` to confirm the SV exists before retrying.

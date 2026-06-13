---
name: cortex-agent-ddl-phase6-execute-verify
description: Execute CREATE AGENT DDL, handle post-creation grants (including ownership + profile reset gotchas), DESCRIBE the agent for structural verification, and present results
---

# Phase 6: Execute & Verify

## Purpose
Execute the `CREATE AGENT FROM SPECIFICATION` DDL, handle all post-creation grants, restore profile settings, and structurally verify the agent matches the intended spec. Failures loop back to Phase 5 for spec fixes.

This phase has **one mandatory stopping point** after the grant workflow completes.

---

## Step 6.1: Execute CREATE AGENT

> **Rollback gate:** Ask the user: "Want me to create a rollback clone first so we can undo this?" then execute on confirmation.

```sql
CREATE OR REPLACE AGENT <AGENT_FQN>
FROM SPECIFICATION $$
<AGENT_SPEC>
$$;
```

**Expected result**: `Agent <AGENT_NAME> successfully created.`

If `CREATE OR REPLACE` is used on an existing agent:
> ⚠️ **Known gotchas (memory 7395efae)**:
> - Ownership resets to the current role after OR REPLACE → must re-grant
> - Profile (display_name/avatar/color) is wiped → must restore in Step 6.3
>
> Always save the current profile with `DESCRIBE AGENT` before OR REPLACE if editing an existing agent.

If creation fails: go to Step 6.2 (error handling).

---

## Step 6.2: Error handling map

| Error message | Root cause | Fix (return to Phase 5) |
|--------------|-----------|------------------------|
| `Object '<FQN>' does not exist or not authorized` in tool_resources | SV or CSS FQN is wrong or inaccessible | Run `SHOW SEMANTIC VIEWS` / `SHOW CORTEX SEARCH SERVICES`; confirm 3-part FQN |
| `Invalid specification: missing field 'execution_environment'` | Block absent | Add `"execution_environment": {"warehouse": "..."}` — Rule 3 |
| `Tool '<name>' defined in tools but not in tool_resources` | tool_resources key mismatch | Fix key name to match `tool_spec.name` exactly — Rule 5 |
| `Duplicate tool name '<name>'` | Two tools share the same name | Rename one — Rule 6 |
| `Invalid model name '<name>'` | Model string not recognized | Use a valid model from reference/agent_spec_syntax.md |
| `Insufficient privileges` / `CREATE AGENT on schema` | Role lacks CREATE AGENT | `GRANT CREATE AGENT ON SCHEMA <db>.<schema> TO ROLE <role>` |
| `JSON parse error` in spec | Malformed JSON in `$$...$$` | Check for unescaped single quotes, trailing commas, mismatched braces |

After identifying the error:
1. Fix `AGENT_SPEC` targeting the specific rule
2. Re-run Phase 5 self-check (`retry`)
3. Return to Step 6.1

---

## Step 6.3: Post-creation grants

### 6.3.1 Restore ownership (if CREATE OR REPLACE was used on an existing agent)

```sql
-- Check current owner
SHOW GRANTS ON AGENT <AGENT_FQN>;
```

If ownership changed from original owner:
```sql
GRANT OWNERSHIP ON AGENT <AGENT_FQN> TO ROLE <original_owner_role> COPY CURRENT GRANTS;
```

### 6.3.2 Grant USAGE to consumer roles

Ask:
```
Which roles should be able to use this agent?
(e.g., ANALYST_ROLE, SNOWFLAKE_INTELLIGENCE_USER, PUBLIC)

Type role names (comma-separated), or press Enter to skip for now.
```

For each role:
```sql
GRANT USAGE ON AGENT <AGENT_FQN> TO ROLE <role_name>;
```

### 6.3.3 Verify tool resource access for consumer roles

Remind the user:
```
The agent executes tools as the calling user's role.
Verify those roles have access to the underlying semantic views and warehouses:

  GRANT USAGE ON SEMANTIC VIEW <SV_FQN> TO ROLE <consumer_role>;
  GRANT USAGE ON WAREHOUSE <AGENT_WAREHOUSE> TO ROLE <consumer_role>;

Skip if users already have access via a parent role.
```

### 6.3.4 Restore profile (always required after CREATE OR REPLACE)

```sql
ALTER AGENT <AGENT_FQN> SET PROFILE = '{
  "display_name": "<AGENT_PROFILE.display_name>",
  "avatar": "<AGENT_PROFILE.avatar>",
  "color": "<AGENT_PROFILE.color>"
}';
```

Without this, the agent appears as a UUID in Snowflake Intelligence.

### 6.3.5 Set comment (optional but recommended)

```sql
ALTER AGENT <AGENT_FQN> SET COMMENT = '<one-line description of agent purpose>';
```

---

## Step 6.4: Structural verification with DESCRIBE

```sql
DESCRIBE AGENT <AGENT_FQN>;
```

Parse the `agent_spec` column from the returned row and verify against `AGENT_SPEC`:

| Check | Expected | Actual |
|-------|----------|--------|
| Model | `<AGENT_MODEL>` | `agent_spec.models.orchestration` |
| Tool count | `<N>` | `agent_spec.tools.length` |
| Tool names | `<list>` | each `agent_spec.tools[i].tool_spec.name` |
| Warehouse (per tool) | `<AGENT_WAREHOUSE>` | `agent_spec.tool_resources.<tool_name>.execution_environment.warehouse` |

Report:
```
DESCRIBE verification:
  ✓ Model: <value of default_agent alias from LLMs.md>
  ✓ Tools: 2 — [SubscriberAnalytics, CustomerSupportSearch]
  ✓ Warehouse: COMPUTE_WH
  ✓ Profile: "Customer Analytics 360" / robot / #0057B8
```

If any check fails: fix `AGENT_SPEC` → re-run Phase 5 → re-execute.

---

## ⚠️ MANDATORY STOP

Present the full execution summary:

```
✅ Agent created and verified

  Agent:    <AGENT_FQN>
  Model:    <AGENT_MODEL>
  Tools:    <N> — <tool names>
  Profile:  "<display_name>" (<avatar> / <color>)

Post-creation grants applied:
  ✓ Profile restored
  ✓ USAGE granted to: <roles or "none yet">
  ⚠️  Remember: consumer roles need USAGE on underlying SVs and warehouse

Test in Snowflake Intelligence:
  Search for "<display_name>" in the SI agent picker.

Type 'go' to proceed to Phase 7 (smoke test + eval handoff).
```

Wait for user confirmation.

---

## Output variables passed to next phases

| Variable | Contents |
|----------|----------|
| `AGENT_FQN` | Confirmed fully-qualified agent name (unchanged) |
| `AGENT_SPEC_LIVE` | Spec JSON as returned by DESCRIBE AGENT (may differ from draft) |
| `GRANTS_APPLIED` | List of roles granted USAGE |

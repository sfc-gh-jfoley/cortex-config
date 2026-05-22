---
name: cortex-agent-ddl-edit-flow
description: Edit an existing Cortex Agent — load current spec, show diff, offer production clone, apply patch, run Phase 5 self-check, execute, verify, and restore profile
---

# Edit Flow: Modify an Existing Agent

## Purpose
A focused 5-step path for editing an existing agent. Loads the current spec, shows a precise diff of proposed changes, offers a production safety clone, runs the full Phase 5 self-check on the patched spec, and executes via ALTER. Handles the CREATE OR REPLACE ownership + profile wipe gotchas automatically.

---

## Step E.1: Identify the agent

Ask:

```
Which agent would you like to edit?
  Fully qualified name: [e.g., MYDB.PUBLIC.MY_AGENT]
  Connection: [or press Enter for default]
```

If only a name is provided (not FQN), search:
```sql
SHOW AGENTS LIKE '%<name>%' IN ACCOUNT;
```
Present matches and ask the user to confirm the FQN.

Store as `EDIT_AGENT_FQN`, `EDIT_AGENT_CONNECTION`.

---

## Step E.2: Load current spec and save baseline

**Fetch current spec:**
```sql
DESCRIBE AGENT <EDIT_AGENT_FQN>;
```

Parse the `spec` column JSON. Store as `CURRENT_SPEC`.

**Save baseline to local file** (crash insurance):
```bash
cat > ./<agent_name>_baseline_<timestamp>.json << 'EOF'
<CURRENT_SPEC>
EOF
```

**Also capture current profile** (will be wiped by any CREATE OR REPLACE):
```sql
SHOW AGENTS LIKE '<agent_name>' IN SCHEMA <db>.<schema>;
```
Look for `profile` column. Store as `CURRENT_PROFILE`.

**Capture current ownership:**
```sql
SHOW GRANTS ON AGENT <EDIT_AGENT_FQN>;
```
Find the OWNERSHIP row. Store owner role as `ORIGINAL_OWNER_ROLE`.

Report:
```
Loaded: <EDIT_AGENT_FQN>
  Model:    <model>
  Tools:    <N> — <tool names>
  Profile:  "<display_name>" (avatar: <avatar>, color: <color>)
  Owner:    <ORIGINAL_OWNER_ROLE>
  Baseline: saved to ./<agent_name>_baseline_<timestamp>.json
```

---

## Step E.3: Production safety check

Ask:

```
Is <EDIT_AGENT_FQN> a production agent?
  - Used by real users or in a live demo
  - Linked from Snowflake Intelligence or a Streamlit app

  yes → I'll offer to create a clone first
  no  → proceed directly
```

**If yes:**

```
Create a safety clone before editing?

  Clone name: [e.g., MYDB.PUBLIC.MY_AGENT_BACKUP]

This is a zero-cost DDL clone — just copies the spec. To rollback:
  DROP AGENT <EDIT_AGENT_FQN>;
  ALTER AGENT <clone_name> RENAME TO <EDIT_AGENT_FQN>;
```

If user confirms clone:
```sql
CREATE AGENT <clone_fqn>
FROM SPECIFICATION $$
<CURRENT_SPEC>
$$;

ALTER AGENT <clone_fqn> SET PROFILE = '<CURRENT_PROFILE>';
ALTER AGENT <clone_fqn> SET COMMENT = 'Backup of <EDIT_AGENT_FQN> before edit on <timestamp>';
```

---

## Step E.4: Gather changes

Ask what the user wants to change. Accept any of:

```
Examples:
  - Update the orchestration instructions
  - Add a new semantic view tool
  - Remove a tool
  - Change the model to claude-opus-4
  - Update sample questions
  - Change budget to 180 seconds
  - Add EnableVQRFastPath flag
  - Rename the agent display name
```

For each requested change, show the **before → after diff**:

```
Proposed changes:

  instructions.orchestration:
    BEFORE: "You are a subscriber analytics agent..."
    AFTER:  "You are a customer analytics agent covering all product lines
             and regional segments..."

  orchestration.budget.seconds:
    BEFORE: 120
    AFTER:  180

  tools:
    ADD: { "tool_spec": { "type": "cortex_search", "name": "SupportDocsSearch", ... } }

Type 'go' to apply, or adjust any field.
```

Apply changes to `CURRENT_SPEC` → store as `PATCHED_SPEC`.

**Special cases:**

- **Adding a new SV/CSS tool**: run Steps 2.4-2.6 (access check + CORTEX.COMPLETE description generation) before adding to spec
- **Changing tool descriptions**: offer CORTEX.COMPLETE regeneration or manual edit
- **Renaming display_name**: this goes in `ALTER AGENT SET PROFILE`, not in spec JSON — note for Step E.6

---

## Step E.4.5: Multitenancy check (conditional)

After gathering changes, check if multitenancy is relevant for this edit:

```
Does this agent need to serve multiple tenants from shared base tables?
(e.g., adding tenant isolation to an existing agent, or the agent already has RAPs
but you want to verify the invocation pattern)

  A) Yes — walk me through tenant isolation (loads Phase 4b)
  B) No  — proceed to self-check
```

### If A (Yes):

Set `IS_MULTITENANT = true` and load [../phases/04b_tenant_isolation.md](../phases/04b_tenant_isolation.md).

Populate the Phase 4b context variables from the current spec:
- `AGENT_DB`, `AGENT_SCHEMA` from `EDIT_AGENT_FQN`
- `AGENT_FQN` = `EDIT_AGENT_FQN`
- `AGENT_WAREHOUSE` from the first tool_resources entry's `execution_environment.warehouse`

Run Phase 4b Steps 4b.1 through 4b.5, then return here to continue with Step E.5.

### If B (No):

Set `IS_MULTITENANT = false`. Continue to Step E.5.

---

## Step E.5: Run Phase 5 self-check on patched spec

Set `AGENT_SPEC = PATCHED_SPEC` and run all 17 rules from `../phases/05_self_check.md`.

The self-check output will indicate:
```
Self-check on patched spec: 10/10 PASS, <N> warnings
```

If any FAIL: fix and re-check before proceeding.

**Important**: There is no targeted field update for agents. Any spec change (instructions, tools, model, budget, flags) requires a full replace via `MODIFY LIVE VERSION SET SPECIFICATION`. Only `COMMENT` and `PROFILE` can be set independently without touching the spec. Always load the current spec first (Step E.2) so the full replace preserves fields you're not changing.

---

## Step E.6: Execute the change

> ⚠️ **Snowflake ALTER AGENT has no targeted field update path.**
> Every spec change requires a full spec replace via `MODIFY LIVE VERSION SET SPECIFICATION`.
> Profile and comment are the only fields settable independently via `SET`.

### Option A — Profile or comment only (no spec change needed):

```sql
-- Profile only:
ALTER AGENT <EDIT_AGENT_FQN> SET PROFILE = '{"display_name": "...", "avatar": "...", "color": "..."}';

-- Comment only:
ALTER AGENT <EDIT_AGENT_FQN> SET COMMENT = '<updated description>';

-- Both at once:
ALTER AGENT <EDIT_AGENT_FQN>
  SET COMMENT = '...',
      PROFILE = '{"display_name": "..."}';
```

No ownership or profile reset needed. Go directly to Step E.7.

### Option B — Full spec replace (required for ANY spec field change):

```sql
ALTER AGENT <EDIT_AGENT_FQN>
  MODIFY LIVE VERSION SET SPECIFICATION = $$
<PATCHED_SPEC>
$$;
```

Immediately after:

**Restore ownership** (full spec replace resets owner):
```sql
GRANT OWNERSHIP ON AGENT <EDIT_AGENT_FQN> TO ROLE <ORIGINAL_OWNER_ROLE> COPY CURRENT GRANTS;
```

**Restore profile** (full spec replace wipes display_name/avatar/color):
```sql
ALTER AGENT <EDIT_AGENT_FQN> SET PROFILE = '<CURRENT_PROFILE>';
```

**Or set new profile** if display_name was one of the requested changes:
```sql
ALTER AGENT <EDIT_AGENT_FQN> SET PROFILE = '{
  "display_name": "<new display_name>",
  "avatar": "<avatar>",
  "color": "<color>"
}';
```

---

## Step E.7: Verify the change

```sql
DESCRIBE AGENT <EDIT_AGENT_FQN>;
```

Compare `spec` column against `PATCHED_SPEC`:
- Confirm each requested change is reflected
- Confirm model, tools, warehouse are intact
- Confirm profile is correct

Report:
```
Verification:
  ✓ instructions.orchestration updated
  ✓ budget.seconds: 180 ✓
  ✓ tools: 3 (SupportDocsSearch added) ✓
  ✓ Profile: "Customer Analytics 360" ✓
  ✓ Owner: SYSADMIN ✓
```

---

## Step E.8: Optional — quick smoke test

Ask:

```
Run a quick smoke test to confirm the changes work as expected?
  yes → test 1 sample question via DATA_AGENT_RUN (see Phase 7 Step 7.1)
  no  → done
```

If the smoke test fails: use the baseline file saved in Step E.2 to restore:
```sql
-- Rollback using baseline file
ALTER AGENT <EDIT_AGENT_FQN> SET SPECIFICATION $$
<paste contents of baseline file>
$$;
-- Then restore profile and ownership as above
```

---

## Edit flow output summary

```
Edit complete: <EDIT_AGENT_FQN>

Changes applied:
  <list of field paths changed>

Baseline:  ./<agent_name>_baseline_<timestamp>.json
Clone:     <clone_fqn or "none">

To undo: use the baseline file or clone (if created).
```

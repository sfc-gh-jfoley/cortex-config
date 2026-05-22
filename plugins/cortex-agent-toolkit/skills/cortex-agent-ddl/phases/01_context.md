---
name: cortex-agent-ddl-phase1-context
description: Context gathering for agent creation — new vs edit gate, name/placement, purpose, and privilege pre-check
---

# Phase 1: Context & Privilege Pre-Check

## Purpose
Determine whether we're creating a new agent or editing an existing one, collect placement and purpose, and verify the necessary privileges exist before doing any discovery work.

This phase has **one mandatory stopping point** — present the context summary and wait for confirmation before loading Phase 2.

---

## Step 1.0: New or existing agent?

Before anything else, ask:

```
Are you creating a new agent or editing an existing one?

  A) New — build from scratch through all phases
  B) Edit — modify an existing agent's spec (instructions, tools, settings)
```

### If B (Edit):
Set `MODE = "edit"` and **load [../edit/01_edit_flow.md](../edit/01_edit_flow.md)** immediately. Do not continue with Steps 1.1+ below.

### If A (New):
Set `MODE = "new"`. Continue to Step 1.0.5.

---

## Step 1.0.5: Agent type — domain or router?

Ask:

```
What type of agent is this?

  A) Domain agent — answers questions using its own tools (semantic views, search services, UDFs)
  B) Router agent — dispatches questions to other existing Cortex Agents based on intent
     (multi-agent orchestration pattern)
```

### If A (Domain):
Set `AGENT_TYPE = "domain"`. Continue to Step 1.1 as normal.

### If B (Router):
Set `AGENT_TYPE = "router"`. Continue to Step 1.1 as normal, but note:
- Phase 2 will use the multi-agent branch (Step 2.0) instead of SV/CSS discovery
- Phase 3 will use the strict-router instruction template
- Reference: [../reference/multi_agent_orchestration.md](../reference/multi_agent_orchestration.md)

Continue to Step 1.1.

---

## Step 1.1: Agent identity

Ask for all three in a single message:

```
Where will this agent live, and what should it be called?

  Database:    [e.g., MY_DB]
  Schema:      [e.g., AGENTS]
  Agent name:  [e.g., SALES_PIPELINE_AGENT]
  Connection:  [which Snowflake connection to use, or "default"]
```

Store as:
- `AGENT_DB`, `AGENT_SCHEMA`, `AGENT_NAME`
- `AGENT_FQN` = `<AGENT_DB>.<AGENT_SCHEMA>.<AGENT_NAME>`
- `AGENT_CONNECTION`

---

## Step 1.2: Purpose and scope

Ask:

```
Describe the agent's purpose in 2-4 sentences:
  - What business questions should it answer?
  - What data domains does it cover?
  - Who are the primary users (analysts, executives, ops teams)?
  - Any questions it should explicitly NOT answer?
```

Store as `AGENT_PURPOSE`. This feeds into:
- Tool description generation in Phase 2
- Orchestration instruction drafting in Phase 3
- Sample question generation in Phase 4

---

## Step 1.2.5: Multitenancy check

Ask:

```
Will this agent serve multiple tenants from shared base tables?
(e.g., different customers/orgs querying the same tables, scoped by a tenant ID column)

  A) Yes — I need tenant isolation (row access policies + scoped invocation)
  B) No  — single-tenant or no row-level isolation needed
```

### If A (Yes):
Set `IS_MULTITENANT = true`. Phase 4b (Tenant Isolation) will activate after Phase 4.

### If B (No):
Set `IS_MULTITENANT = false`. Phase 4b will be skipped.

---

## Step 1.3: Privilege pre-check

Before any discovery work, verify the current role can create an agent at the target location.

**Check CREATE AGENT privilege:**
```sql
SHOW GRANTS ON SCHEMA <AGENT_DB>.<AGENT_SCHEMA>;
```

Scan the output for `CREATE AGENT` privilege on the current role (or a role it inherits).

If the privilege is not found:
```
⚠️  Missing privilege: CREATE AGENT on <AGENT_DB>.<AGENT_SCHEMA>

To grant it:
  GRANT CREATE AGENT ON SCHEMA <AGENT_DB>.<AGENT_SCHEMA> TO ROLE <current_role>;

Ask your Snowflake admin to run this, then restart Phase 1.
```
**Stop here** until the privilege is confirmed. Do not proceed to Phase 2 without it.

If confirmed: proceed.

**Check target schema exists:**
```sql
SHOW SCHEMAS LIKE '<AGENT_SCHEMA>' IN DATABASE <AGENT_DB>;
```
If not found, prompt the user to create it:
```sql
CREATE SCHEMA IF NOT EXISTS <AGENT_DB>.<AGENT_SCHEMA>;
```

---

## Step 1.4: Warehouse selection

Ask:

```
Which warehouse should the agent use for tool execution?
  [e.g., COMPUTE_WH, ANALYST_WH, or press Enter to pick one from the list]
```

If blank, run:
```sql
SHOW WAREHOUSES;
```
Present the list and let the user pick. Store as `AGENT_WAREHOUSE`.

> ℹ️ This warehouse will be embedded as `execution_environment: {type: "warehouse", warehouse: "<AGENT_WAREHOUSE>"}` inside every semantic view tool's `tool_resources` entry in Phase 4. Without it, the agent's CREATE succeeds but queries fail at runtime with error 399504.

Verify access:
```sql
SHOW GRANTS TO ROLE CURRENT_ROLE() ON WAREHOUSE <AGENT_WAREHOUSE>;
```
If USAGE is missing:
```
⚠️  USAGE not granted on warehouse <AGENT_WAREHOUSE>.
Grant: GRANT USAGE ON WAREHOUSE <AGENT_WAREHOUSE> TO ROLE <current_role>;
```

---

## ⚠️ MANDATORY STOP

Present this summary before proceeding to Phase 2:

```
Agent context collected:
  FQN:        <AGENT_FQN>
  Connection: <AGENT_CONNECTION>
  Warehouse:  <AGENT_WAREHOUSE>
  Purpose:    <first sentence of AGENT_PURPOSE>
  Multitenant: <IS_MULTITENANT> (Phase 4b will <activate/be skipped>)

Privilege checks:
  ✓ CREATE AGENT on <AGENT_DB>.<AGENT_SCHEMA>
  ✓ USAGE on warehouse <AGENT_WAREHOUSE>

Next: Phase 2 — discover available tools (semantic views + search services).
Type 'go' to continue, or update any values above.
```

Wait for confirmation before loading Phase 2.

---

## Output variables passed to next phases

| Variable | Contents |
|----------|----------|
| `MODE` | `"new"` |
| `AGENT_DB`, `AGENT_SCHEMA`, `AGENT_NAME` | Target placement |
| `AGENT_FQN` | Fully-qualified agent name |
| `AGENT_CONNECTION` | Active Snowflake connection name |
| `AGENT_WAREHOUSE` | Default execution warehouse |
| `AGENT_PURPOSE` | Free-form business description |
| `AGENT_TYPE` | `"domain"` or `"router"` |
| `IS_MULTITENANT` | `true` or `false` — gates Phase 4b activation |

---
name: cortex-agent-ddl-phase2-discover-tools
description: Discover available semantic views and Cortex Search Services, check tool resource access, and auto-generate rich tool descriptions using CORTEX.COMPLETE
---

# Phase 2: Discover Tools & Auto-Generate Descriptions

## Purpose
Find what semantic views and Cortex Search Services are available, verify the current role can access them, and use CORTEX.COMPLETE to generate tool descriptions that meet the best-practices quality bar. **Tool descriptions are the #1 factor in agent quality** — this phase earns its time.

This phase has **one mandatory stopping point** — present the tool catalog and generated descriptions for user approval.

---

## Step 2.0: Multi-Agent Router Branch

> **Skip this step entirely if `AGENT_TYPE == "domain"`.** Jump to Step 2.1.

If `AGENT_TYPE == "router"`, this agent routes to other Cortex Agents via UDF custom tools. Follow this branch instead of Steps 2.1-2.4.

### Step 2.0.1: Discover sub-agents

Ask: "Which agents should this router dispatch to? List their FQNs, or press Enter to search."

If the user presses Enter:
```sql
SHOW AGENTS IN ACCOUNT;
```

Present the list and ask the user to select which agents to route to. Store as `SUB_AGENTS` — list of FQNs.

For each selected sub-agent, extract its purpose:
```sql
DESCRIBE AGENT <sub_agent_fqn>;
```

Parse the `spec` column → extract `instructions.orchestration` first 200 chars and `tools[].tool_spec.name` list. Store as `SUB_AGENT_METADATA[fqn]`.

### Step 2.0.2: Deploy infrastructure

Reference: [../reference/multi_agent_orchestration.md](../reference/multi_agent_orchestration.md)

Ask:
```
I need to create the multi-agent infrastructure in <AGENT_DB>.<AGENT_SCHEMA>:
  - Network rule (egress to your Snowflake account API)
  - Secret (stores your PAT token)
  - External Access Integration

Do you already have these set up, or should I create them?
  A) Create all infrastructure now
  B) I already have them — provide the integration and secret names
```

**If A**: Present the infrastructure DDL from the reference doc (Steps 1-4), with `<DB>.<SCHEMA>` = `AGENT_DB.AGENT_SCHEMA`, and `<YOUR_ACCOUNT>` filled from the connection.

> ⚠️ **Secret handling**: Do NOT ask the user to paste their PAT token into this conversation. Token values in CoCo history may appear in Snowflake query history.
>
> Instead:
> 1. Present the `CREATE SECRET` template with a placeholder: `SECRET_STRING = '<paste_your_token_here>'`
> 2. Instruct the user to run this statement directly in Snowsight or their SQL client
> 3. Ask the user to confirm when done, then provide the secret FQN (e.g., `DB.SCHEMA.cortex_agent_token_secret`)
>
> If the user already has a secret, ask for its FQN and skip creation.

Execute the remaining statements (network rule, integration, grants) normally.

**If B**: Ask for the integration name and secret FQN. Store as `EAI_NAME` and `SECRET_FQN`.

### Step 2.0.3: Create agent-caller UDFs

For each sub-agent in `SUB_AGENTS`, generate a UDF using the template from the reference doc:
- Function name: `ASK_<agent_name_uppercase>` (e.g., `ASK_SALES_PIPELINE_AGENT`)
- URL: constructed from account + sub-agent FQN parts

Present all UDF DDL statements and ask for confirmation before executing.

Store created UDF FQNs as `CUSTOM_TOOLS` — list of `{name: "Ask<AgentName>", type: "generic", function_fqn: "<DB>.<SCHEMA>.ASK_<NAME>"}`.

### Step 2.0.4: Generate tool descriptions for sub-agent UDFs

First, resolve `COMPLETE_MODEL` by reading `~/.snowflake/cortex/vault/LLMs.md`. Try models in this order: `current_haiku` alias first, then `default_agent` alias. Use the first model from the Available Models table that succeeds.

For each sub-agent UDF, generate a tool description using `SUB_AGENT_METADATA`:

```sql
SELECT SNOWFLAKE.CORTEX.COMPLETE(
  '<COMPLETE_MODEL>',
  CONCAT(
    'You are writing a tool description for a routing agent. ',
    'This tool dispatches questions to a specialized sub-agent. ',
    'Write a concise description following this template:\n\n',
    '[1 sentence: what domain this sub-agent covers]\n\n',
    'When to use:\n- [question type 1]\n- [question type 2]\n- [question type 3]\n\n',
    'When NOT to use:\n- Do NOT use for [out-of-scope 1]\n- Do NOT use for [out-of-scope 2]\n\n',
    'Keep total length between 150-300 characters.\n\n',
    'Sub-agent purpose: ', :sub_agent_instructions_excerpt, '\n',
    'Sub-agent tools: ', :sub_agent_tool_names
  )
) AS generated_description;
```

Store as `TOOL_DESCRIPTIONS`. Then **continue to Step 2.7** (tool naming) — skip Steps 2.1-2.6.

---

## Step 2.1: Discover available Semantic Views

Ask: "Which database(s) and schema(s) contain your semantic views and search services? (Press Enter to search the current database, or list specific schemas)"

For each named schema, run:

```sql
SHOW SEMANTIC VIEWS IN SCHEMA <db>.<schema>;
```

If the user presses Enter / is unsure, run:
```sql
SHOW SEMANTIC VIEWS IN ACCOUNT;
```

Store results as `AVAILABLE_SVS` — list of rows with `name`, `database_name`, `schema_name`, `comment`.

If zero SVs found:
```
No semantic views found in <scope>.

Options:
  1. Search a different schema → provide DB.SCHEMA
  2. Build a semantic view first → invoke the semantic-view-ddl skill (if installed) or use the bundled semantic-view skill
  3. Skip semantic view tools and use cortex_search or generic tools only
```

---

## Step 2.2: Discover available Cortex Search Services

```sql
SHOW CORTEX SEARCH SERVICES IN ACCOUNT;
```

Store as `AVAILABLE_CSS` — list of rows with `name`, `database_name`, `schema_name`, `definition`.

---

## Step 2.3: Tool selection

Present the discovered objects:

```
Available tools:

Semantic Views (cortex_analyst_text_to_sql):
  [1] DB.SCHEMA.SV_NAME_1  — "<comment if any>"
  [2] DB.SCHEMA.SV_NAME_2  — "<comment if any>"

Cortex Search Services (cortex_search):
  [3] DB.SCHEMA.CSS_NAME_1
  [4] DB.SCHEMA.CSS_NAME_2

Select which ones to include as tools (e.g. "1,3" or "all"):
Also list any custom UDFs/procedures you want as generic tools.
```

Additional tool types (configure manually if needed):

```
  web_search      — Real-time web search. No setup required beyond account param.
                    Requires: ENABLE_CORTEX_WEBSEARCH enabled by account admin.
                    Ask: "Does this agent need to search the internet for current information?"

  data_to_chart   — Generates Vega-Lite charts from query results.
                    No setup required. Pair with EnableUnrestrictedChartTool flag for
                    extended chart types (area, dual-axis, boxplots, etc.).
                    Ask: "Should this agent produce charts/visualizations?"

  code_execution  — Python sandbox for calculations and data processing.
                    No setup required. Required if Agent Skills include code files.
                    Ask: "Does this agent need to run Python code or use Skills with scripts?"

  MCP connector   — Connect to an external MCP server (e.g., GitHub, Jira, Salesforce).
                    Requires an EXTERNAL MCP SERVER object in Snowflake.
                    Configured in spec under mcp_servers[], not in tools[].
                    Ask: "Does this agent need to connect to external tools via MCP?"
```

For each new tool type selected:
- `web_search` / `data_to_chart` / `code_execution`: add to `CUSTOM_TOOLS` list with `{type: "<tool_type>", name: "<name>", tool_resources: null}`. These go in the `tools` array with no `tool_resources` entry.
- MCP: store separately as `MCP_SERVERS` list — handled in Phase 4 spec assembly, not in `tool_resources`.

Store selected SVs as `SELECTED_SVS`, selected CSS as `SELECTED_CSS`, custom functions as `CUSTOM_TOOLS`.

**Tool count check**: if total selected > 10, warn:
```
⚠️  Best practice: 5-10 tools per agent. You've selected <N>.
More tools = harder routing decisions for the agent.
Consider splitting into multiple specialized agents.
Continue anyway? (yes/no)
```
Note: `web_search`, `data_to_chart`, and `code_execution` each count as 1 tool toward this limit even though they need no tool_resources.

---

## Step 2.4: Tool resource access check

For each selected SV, verify the current role can access it using DESCRIBE (not SELECT):

```sql
DESCRIBE SEMANTIC VIEW <sv_db>.<sv_schema>.<sv_name>;
```

> ⚠️ Do **not** use `SELECT * FROM <sv> LIMIT 0` — semantic views with granularity constraints will reject this query even when the role has valid access. `DESCRIBE SEMANTIC VIEW` is the reliable access check.

For each selected CSS:
```sql
DESCRIBE CORTEX SEARCH SERVICE <css_db>.<css_schema>.<css_name>;
```

If any access check fails:
```
⚠️  Access denied: <object_fqn>
The current role does not have USAGE on this object.

Fix:
  GRANT USAGE ON <object_type> <fqn> TO ROLE <current_role>;

Skip this tool for now? (yes/no)
```

Remove inaccessible tools from the selection unless the user explicitly keeps them.

---

## Step 2.4a: New tool type prerequisite checks

For each new tool type selected, run the relevant check:

**`web_search`:**
```sql
-- Check if web search is enabled at account level
SHOW PARAMETERS LIKE 'ENABLE_CORTEX_WEBSEARCH' IN ACCOUNT;
```
If not enabled: warn the user that they need an account admin to run `ALTER ACCOUNT SET ENABLE_CORTEX_WEBSEARCH = TRUE` before this tool will function. Do not block — user can enable it after deployment.

**`code_execution`:** No prerequisite check needed — available by default.

**`data_to_chart`:** No prerequisite check needed — available by default.

**MCP:**
```sql
SHOW EXTERNAL MCP SERVERS IN SCHEMA <AGENT_SCHEMA>;
```
If none found: warn that an `EXTERNAL MCP SERVER` object is required before the agent can use MCP tools. Provide the DDL skeleton:
```sql
CREATE EXTERNAL MCP SERVER <DATABASE>.<SCHEMA>.<MCP_SERVER_NAME>
  URL = '<mcp_server_url>'
  ...;
-- Full syntax: see Snowflake docs on Cortex Agent MCP Connectors
```

---

## Step 2.5: Describe each selected Semantic View

For each SV in `SELECTED_SVS`:

```sql
DESCRIBE SEMANTIC VIEW <sv_db>.<sv_schema>.<sv_name>;
```

From the DESCRIBE output, extract:
- `OBJECT_KIND = 'TABLE'` rows → table names (store as `sv_tables`)
- `OBJECT_KIND = 'FACT'` rows → fact names + descriptions (store as `sv_facts`)
- `OBJECT_KIND = 'DIMENSION'` rows → dimension names + descriptions (store as `sv_dimensions`)
- `OBJECT_KIND = 'METRIC'` rows → metric names + expressions (store as `sv_metrics`)

Build a compact summary string for the CORTEX.COMPLETE prompt:
```
Tables: <comma-list of table names>
Facts: <comma-list of top 10 fact names>
Key metrics: <comma-list of metric names + expressions>
Key dimensions: <comma-list of top 10 dimension names>
SV comment: <comment if present>
```

---

## Step 2.6: CORTEX.COMPLETE — auto-generate tool descriptions

For each selected SV, generate a tool description.

**Step 2.6a: Probe for the best available model first**

Before running CORTEX.COMPLETE, find the fastest available Claude model with this probe sequence. Run each until one succeeds:

```sql
-- Read LLMs.md: try current_haiku (currently claude-haiku-4-5) first, then default_agent (currently claude-sonnet-4-6)
SELECT SNOWFLAKE.CORTEX.COMPLETE('claude-haiku-4-5', 'OK') AS r;   -- current_haiku
SELECT SNOWFLAKE.CORTEX.COMPLETE('claude-sonnet-4-6', 'OK') AS r;  -- default_agent (fallback)
```

Use the first model that returns without a "model unavailable" error. Store it as `COMPLETE_MODEL`. Read LLMs.md for current alias values — do not hardcode version strings.

**Step 2.6b: Generate the description**

```sql
SELECT SNOWFLAKE.CORTEX.COMPLETE(
  '<COMPLETE_MODEL>',
  CONCAT(
    'You are writing a tool description for a Cortex Agent. ',
    'The tool is a Snowflake Semantic View that answers business questions via SQL. ',
    'Write a concise but complete description following this exact template:\n\n',
    '[1 sentence: what business domain this covers and what questions it answers]\n\n',
    'Data coverage: [key facts and metrics available, date ranges if inferable]\n\n',
    'When to use:\n- [specific question type 1]\n- [specific question type 2]\n- [specific question type 3]\n\n',
    'When NOT to use:\n- Do NOT use for [out-of-scope 1]\n- Do NOT use for [out-of-scope 2]\n\n',
    'Keep the total length between 150-400 characters.\n\n',
    'Semantic view context:\n',
    'Agent purpose: ', :agent_purpose, '\n',
    'SV name: ', :sv_name, '\n',
    'Tables: ', :sv_tables, '\n',
    'Key metrics: ', :sv_metrics, '\n',
    'Key dimensions: ', :sv_dimensions, '\n',
    'SV comment: ', :sv_comment
  )
) AS generated_description;
```

Replace `:agent_purpose`, `:sv_name`, etc. with the actual values collected above.

For each selected CSS, generate a description similarly using the same `<COMPLETE_MODEL>` resolved in Step 2.6a:

```sql
SELECT SNOWFLAKE.CORTEX.COMPLETE(
  '<COMPLETE_MODEL>',
  CONCAT(
    'You are writing a tool description for a Cortex Agent. ',
    'The tool is a Cortex Search Service that does semantic/keyword search over text. ',
    'Write a concise but complete description following this exact template:\n\n',
    '[1 sentence: what documents or text content this searches]\n\n',
    'When to use:\n- [specific question type 1]\n- [specific question type 2]\n\n',
    'When NOT to use:\n- Do NOT use for [out-of-scope 1]\n\n',
    'Keep the total length between 100-300 characters.\n\n',
    'Search service name: ', :css_name, '\n',
    'Agent purpose: ', :agent_purpose
  )
) AS generated_description;
```

For custom `generic` tools: ask the user for a brief description and auto-format it using the template.

Store all generated descriptions as `TOOL_DESCRIPTIONS` dict keyed by tool name.

---

## Step 2.7: Generate tool names

Tool names appear in the agent's routing decisions — they must be specific and meaningful.

Apply these naming rules:
- Include the data domain: `Sales`, `Customer`, `IoT`, `Subscriber`
- Include the function: `Analytics`, `Search`, `Query`, `Lookup`
- Avoid generic names: not `DataTool`, `Tool1`, `Query`
- Max 40 characters, no spaces (use CamelCase)

Auto-suggest names from the SV names:
- `CUSTOMER_360` → `CustomerAnalytics`
- `MARKETING_CAMPAIGNS_SV` → `MarketingCampaignQuery`
- `IOT_FLEET_360` → `IoTFleetAnalytics`

Present suggestions and ask user to confirm or rename.

Store as `TOOL_NAMES` dict mapping SV/CSS FQN → tool name.

---

## Step 2.8: Quality check on descriptions

Before presenting, verify each generated description:

| Check | Minimum bar |
|-------|-------------|
| Length | > 100 characters |
| Contains "When NOT to use" or "Do NOT use" | Required |
| Contains at least 2 "When to use" examples | Required |
| Mentions the data domain (matches AGENT_PURPOSE) | Preferred |

If any description fails: regenerate with more specific context or present it for manual editing.

---

## ⚠️ MANDATORY STOP

Present the full tool catalog with generated descriptions:

```
Tool catalog — <N> tools selected:

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Tool 1: <TOOL_NAME> (cortex_analyst_text_to_sql)
  Source: <SV_FQN>
  Description:
    <generated description — full text>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Tool 2: <TOOL_NAME> (cortex_search)
  Source: <CSS_FQN>
  Description:
    <generated description — full text>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Access checks: all ✓
Description quality: N/N passed

Type 'go' to proceed, edit any description inline, or ask me to regenerate one.
```

Wait for user approval before loading Phase 3.

---

## Output variables passed to next phases

| Variable | Contents |
|----------|----------|
| `SELECTED_SVS` | List of approved SV FQNs |
| `SELECTED_CSS` | List of approved CSS FQNs |
| `CUSTOM_TOOLS` | List of generic tool specs (includes web_search/data_to_chart/code_execution entries) |
| `MCP_SERVERS` | List of MCP connector specs (handled separately in Phase 4 spec assembly) |
| `TOOL_NAMES` | Dict: FQN → tool name |
| `TOOL_DESCRIPTIONS` | Dict: tool name → approved description |
| `SV_METADATA` | Dict: SV FQN → {tables, facts, dimensions, metrics} from DESCRIBE |

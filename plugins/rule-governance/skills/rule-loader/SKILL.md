---
name: rule-loader
description: "Load contextual coding rules for your current task. Use when: user explicitly asks for rules, or when you identify a task that has relevant rules available. Always ASK before loading rules - never auto-load."
---

# Rule Loader

Load relevant coding rules from the global rules library. **Always prompt user before loading.**

## Rules Location

- Rules: `~/.snowflake/cortex/rules/`
- Index: `~/.snowflake/cortex/rules/RULES_INDEX.md`

## Workflow

### Step 1: Identify Available Rules

When you recognize a task domain, check if rules exist:

| Domain | Rule Available |
|--------|----------------|
| **Foundation** | `000-global-core.md` |
| **Snowflake Core** | `100-snowflake-core.md` |
| Streamlit | `101-snowflake-streamlit-core.md` |
| SQL Files | `102-snowflake-sql-core.md` |
| Performance | `103-snowflake-performance-tuning.md` |
| Streams & Tasks | `104-snowflake-streams-tasks.md` |
| Cost Governance | `105-snowflake-cost-governance.md` |
| Semantic Views | `106-snowflake-semantic-views-core.md` |
| Security | `107-snowflake-security-governance.md` |
| Data Loading | `108-snowflake-data-loading.md` |
| Notebooks | `109-snowflake-notebooks.md` |
| Model Registry | `110-snowflake-model-registry.md` |
| Observability | `111-snowflake-observability-core.md` |
| Snow CLI | `112-snowflake-snowcli.md` |
| Feature Store | `113-snowflake-feature-store.md` |
| Cortex AISQL | `114-snowflake-cortex-aisql.md` |
| Cortex Agents | `115-snowflake-cortex-agents-core.md` |
| Cortex Search | `116-snowflake-cortex-search.md` |
| MCP Server | `117-snowflake-mcp-server.md` |
| Dynamic Tables | `122-snowflake-dynamic-tables.md` |
| Data Quality | `124-snowflake-data-quality-core.md` |
| Demo SQL | `130-snowflake-demo-sql.md` |
| **Python Core** | `200-python-core.md` |
| Lint/Format | `201-python-lint-format.md` |
| Project Setup | `203-python-project-setup.md` |
| pytest | `206-python-pytest.md` |
| FastAPI | `210-python-fastapi-core.md` |
| HTMX | `221-python-htmx-core.md` |
| Pydantic | `230-python-pydantic.md` |
| Flask | `250-python-flask.md` |
| Pandas | `252-python-pandas.md` |
| **Bash** | `300-bash-scripting-core.md` |
| Zsh | `310-zsh-scripting-core.md` |
| **Docker** | `350-docker-best-practices.md` |
| **JavaScript** | `420-javascript-core.md` |
| Alpine.js | `421-javascript-alpinejs-core.md` |
| **TypeScript** | `430-typescript-core.md` |
| **React** | `440-react-core.md` |
| **Golang** | `600-golang-core.md` |
| Taskfile | `820-taskfile-automation.md` |

### Step 2: Prompt User

**Before loading any rules, ask:**

```
I found rules that may help with this task:
- 101-snowflake-streamlit-core.md (Streamlit patterns)
- 100-snowflake-core.md (Snowflake basics)

Want me to load these rules for guidance?
```

**Wait for user confirmation before proceeding.**

### Step 3: Load Only If Approved

If user approves:
1. Read the specific rule file(s)
2. Confirm what was loaded
3. Apply guidance during the task

If user declines:
- Proceed without rules
- Do not mention rules again for this task

## Hard Requirements

- **NEVER auto-load rules** - always ask first
- **Keep prompts brief** - list rule names, not full descriptions
- **Respect "no"** - if user declines, don't push
- **One prompt per task** - don't repeatedly ask about rules

## Example Interaction

**User:** Help me build a Streamlit app

**Assistant:** 
```
I have Streamlit rules available that cover patterns, performance, and security. 
Want me to load them for guidance?
```

**User:** yes

**Assistant:** *loads rules, confirms, proceeds with task*

---

**User:** Help me write a Python script

**Assistant:**
```
I have Python rules (core patterns, testing, linting). Load them?
```

**User:** no, just do it

**Assistant:** *proceeds without rules, doesn't mention them again*

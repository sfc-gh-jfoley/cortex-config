# Prerequisites

## Snowflake Roles and Permissions

Your Snowflake role needs the following grants. If you use SYSADMIN, most of these are already available. For a custom role, grant each explicitly:

```sql
-- Core agent permissions
GRANT CREATE AGENT ON SCHEMA <database>.<schema> TO ROLE <your_role>;
GRANT USAGE ON DATABASE <database> TO ROLE <your_role>;
GRANT USAGE ON SCHEMA <database>.<schema> TO ROLE <your_role>;
GRANT USAGE ON WAREHOUSE <warehouse> TO ROLE <your_role>;

-- Access to Cortex functions
GRANT DATABASE ROLE SNOWFLAKE.CORTEX_USER TO ROLE <your_role>;

-- For agent evaluations (agent-evaluation / agent-flag-tester skills)
GRANT EXECUTE TASK ON ACCOUNT TO ROLE <your_role>;
GRANT CREATE FILE FORMAT ON SCHEMA <database>.<schema> TO ROLE <your_role>;
GRANT CREATE DATASET ON SCHEMA <database>.<schema> TO ROLE <your_role>;
GRANT CREATE TASK ON SCHEMA <database>.<schema> TO ROLE <your_role>;
GRANT CREATE STAGE ON SCHEMA <database>.<schema> TO ROLE <your_role>;
GRANT IMPERSONATE ON USER <your_user> TO ROLE <your_role>;
GRANT MONITOR ON AGENT <database>.<schema>.<agent_name> TO ROLE <your_role>;

-- For semantic view access (if your agent uses Cortex Analyst tools)
GRANT SELECT ON SEMANTIC VIEW <database>.<schema>.<sv_name> TO ROLE <your_role>;
```

Replace `<database>`, `<schema>`, `<your_role>`, `<your_user>`, and object names with your actual values.

## Warehouse Requirements

- A running warehouse is required for all operations (agent creation, evaluation runs, queries).
- **Size**: X-Small is sufficient for agent creation and querying. Small or Medium recommended for evaluation runs with large datasets (50+ questions).
- The warehouse must be specified in the agent spec's `execution_environment.warehouse` field.

## Tooling

### Cortex Code CLI

Required. This plugin runs inside Cortex Code.

```bash
# Check your version
cortex --version

# v1.0.70+ recommended
```

### snow CLI

Required by `agent-evaluation` and `agent-flag-tester` for agent operations (DESCRIBE, CREATE, ALTER).

```bash
# Check installation
snow --version

# Configure a connection (if not already done)
snow connection add
```

Your `snow` connection must point to the same Snowflake account and have the role/warehouse grants listed above.

### uv (Python package manager)

Required only if you use the Python helper scripts bundled with `agent-evaluation` (e.g., `invoke_agent.py`, `convert_eval_dataset.py`). Not needed for the core SQL workflows.

```bash
# Install uv (macOS/Linux)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Verify
uv --version
```

## Environment Variables

| Variable | Used By | Purpose |
|---|---|---|
| `SNOWFLAKE_CONNECTION_NAME` | agent-evaluation scripts | Tells Python scripts which `snow` connection to use for REST API calls. Defaults to `default` if not set. |

## Quick Checklist

Before starting, verify:

- [ ] Snowflake role has CREATE AGENT privilege on your target schema
- [ ] Snowflake role has CORTEX_USER database role granted
- [ ] A warehouse is available and accessible to your role
- [ ] `snow` CLI is installed and a connection is configured
- [ ] (If running evals) EXECUTE TASK and CREATE DATASET grants are in place
- [ ] (If using Python scripts) `uv` is installed

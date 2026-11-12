# Prerequisites

## Required for All Skills

- Snowflake account with at least one database containing queryable objects
- Role with `USAGE` on target database and schemas
- `CORTEX_USER` database role (granted by default)

## Per-Skill Requirements

### sv-discovery

| Requirement | Why | Fallback if Missing |
|---|---|---|
| `IMPORTED PRIVILEGES` on `SNOWFLAKE` database | Access ACCOUNT_USAGE (QUERY_HISTORY, ACCESS_HISTORY) | Runs with INFORMATION_SCHEMA only (reduced accuracy) |
| 30+ days of query history | Meaningful co-occurrence data | Works with less, lower confidence scores |
| Enterprise Edition or higher | ACCESS_HISTORY for column-level usage | Skips column usage analysis |

### sv-ddl

| Requirement | Why | Fallback if Missing |
|---|---|---|
| `CREATE SEMANTIC VIEW` privilege on target schema | Create the new SV and candidate copies | Cannot proceed |
| `SELECT` on source tables/views/DTs | Validate relationships and sample data | Cannot proceed |
| `USE AI FUNCTIONS` (granted to PUBLIC by default) and a warehouse | AI-generated descriptions | Manual descriptions only |
| `OWNERSHIP` on an existing SV | Promotion by `CREATE OR ALTER` at gate `SV-PROMOTE` | Retarget consumers instead, or ask the owner |

### sv-audit

| Requirement | Why | Fallback if Missing |
|---|---|---|
| `SELECT` on the semantic view | DESCRIBE SEMANTIC VIEW | Cannot proceed |
| `IMPORTED PRIVILEGES` on `SNOWFLAKE` database | QUERY_HISTORY + ACCESS_HISTORY analysis | Structural analysis only (no usage data) |

### sv-evaluation

| Requirement | Why | Fallback if Missing |
|---|---|---|
| `CORTEX_USER` database role | Required to call EXECUTE_AI_EVALUATION | Cannot run eval |
| `USE AI FUNCTIONS` on account | EXECUTE_AI_EVALUATION entitlement | Cannot run eval |
| `EXECUTE TASK ON ACCOUNT` | Eval runs use Snowflake tasks | Cannot run eval |
| `CREATE TASK` on SV schema | Task creation for eval | Cannot run eval |
| `CREATE DATASET ON SCHEMA` on SV schema | Dataset registration | Cannot run eval |
| `SELECT` on SV and underlying tables | Execute eval queries | Cannot run eval |
| `MONITOR` on semantic view | Eval API requirement | Cannot run eval |
| At least 1 VQR on the SV | Ground truth for eval | Route to vqr-generator first |

**⚠️ Single primary role:** all evaluation privileges must be held by the session's **primary role** (directly or through roles it inherits). Evaluation runs as Snowflake tasks, which ignore secondary-role privileges.

### sv-iterative-optimizer / sv-gepa-optimizer

| Requirement | Why | Fallback if Missing |
|---|---|---|
| All sv-evaluation prerequisites | Runs evals in a loop | Cannot proceed |
| `CREATE SEMANTIC VIEW` on the SV schema | Deploy candidate copies | Cannot proceed |
| `OWNERSHIP` on the production SV | Replace production at gate `SV-PROMOTE` (`CREATE OR ALTER`) | Retarget consumers instead, or ask the owner |
| `CREATE SCHEMA` (first run only) | Create `_SV_TOOLKIT_META` | Ask user to create manually |
| `CREATE TABLE` on `_SV_TOOLKIT_META` | Persist optimization state | Cannot proceed |

### sv-watch

| Requirement | Why | Fallback if Missing |
|---|---|---|
| `IMPORTED PRIVILEGES` on `SNOWFLAKE` database | Detect schema changes via ACCOUNT_USAGE | Cannot detect drift |
| `SELECT` on semantic views to monitor | DESCRIBE to compare | Cannot proceed |
| `CREATE TABLE` on `_SV_TOOLKIT_META` | Persist watch history | Cannot proceed |
| Enterprise Edition | ACCESS_HISTORY for Check 2 (coverage decay) | Skips Check 2 |

### sv-materialize

| Requirement | Why | Fallback if Missing |
|---|---|---|
| `SELECT` on the SV | `SHOW MATERIALIZATIONS` | Cannot proceed |
| `CREATE SEMANTIC VIEW` on the SV schema | `mat` trial candidates | Assess and design only |
| `OWNERSHIP` on the SV, `ADD SEMANTIC VIEW MATERIALIZATION` on the schema, `USAGE` on the refresh warehouse | Materialization changes at gate `SV-PROMOTE` | Produce statements for the owner |

### sv-rearchitect

| Requirement | Why | Fallback if Missing |
|---|---|---|
| `CREATE SEMANTIC VIEW` on target schema | Create nested/composed SVs | Cannot proceed |
| `SELECT` on source SVs | Read existing SV definitions | Cannot proceed |

### vqr-generator

| Requirement | Why | Fallback if Missing |
|---|---|---|
| `IMPORTED PRIVILEGES` on `SNOWFLAKE` database | QUERY_HISTORY for question mining | Cannot auto-generate (manual only) |
| `CREATE SEMANTIC VIEW` on the SV schema | Candidate copy carrying the new VQRs | Generate only, user applies manually |
| `OWNERSHIP` on the target SV | Promote the VQRs (`CREATE OR ALTER`; `ALTER SEMANTIC VIEW` cannot change VQRs) at `SV-PROMOTE` | Generate only, user applies manually |

## Edition Requirements

| Feature | Edition |
|---|---|
| ACCESS_HISTORY (column-level usage) | Enterprise or higher |
| Cortex Analyst evaluations (`EXECUTE_AI_EVALUATION`) | No edition or Preview label on the current evaluation page; Snowflake now recommends transitioning to Cortex Agents. Verify before relying on this |
| Semantic view materializations | Preview (Open, all accounts) |
| Dynamic Tables as SV sources | Standard |
| External Tables (Iceberg) as SV sources | Standard |

## Quick Validation

Run this to check your current role has the essentials:

```sql
-- Check ACCOUNT_USAGE access
SELECT COUNT(*) FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE START_TIME >= DATEADD('day', -1, CURRENT_TIMESTAMP()) LIMIT 1;

-- Check role grants (look for CORTEX_USER, USE AI FUNCTIONS, EXECUTE TASK, CREATE SEMANTIC VIEW)
SELECT CURRENT_ROLE();
SHOW GRANTS TO ROLE <your_role>;
```

## Install and Verify

1. Install `uv` (required for the optimization, GEPA, candidate and validator scripts):

   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

   Make sure `uv` is on your shell PATH. On macOS with zsh, put the `PATH` export in `~/.zshenv`
   (not `.zshrc`) so non-interactive shells can find it:

   ```bash
   # ~/.zshenv
   export PATH="$HOME/.local/bin:$PATH"
   ```

2. Grant the privileges listed under each skill above to the role you will use.
3. Reload your Cortex Code session. The toolkit banner confirms it is active; a "Setup Incomplete"
   warning means a prerequisite above is missing.


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
| `CREATE SEMANTIC VIEW` privilege on target schema | Create the SV | Cannot proceed |
| `SELECT` on source tables/views/DTs | Validate relationships and sample data | Cannot proceed |
| Warehouse with `CORTEX.COMPLETE` access | AI-generated descriptions | Manual descriptions only |

### sv-audit

| Requirement | Why | Fallback if Missing |
|---|---|---|
| `SELECT` on the semantic view | DESCRIBE SEMANTIC VIEW | Cannot proceed |
| `IMPORTED PRIVILEGES` on `SNOWFLAKE` database | QUERY_HISTORY + ACCESS_HISTORY analysis | Structural analysis only (no usage data) |

### sv-evaluation

| Requirement | Why | Fallback if Missing |
|---|---|---|
| `EXECUTE TASK ON ACCOUNT` | Eval runs use Snowflake tasks | Cannot run eval |
| `CREATE TASK` on SV schema | Task creation for eval | Cannot run eval |
| `CREATE DATASET ON SCHEMA` on SV schema | Dataset registration | Cannot run eval |
| `SELECT` on SV and underlying tables | Execute eval queries | Cannot run eval |
| `MONITOR` on semantic view | Eval API requirement | Cannot run eval |
| At least 1 VQR on the SV | Ground truth for eval | Route to vqr-generator first |

### sv-optimization / sv-gepa-optimizer

| Requirement | Why | Fallback if Missing |
|---|---|---|
| All sv-evaluation prerequisites | Runs evals in a loop | Cannot proceed |
| `CREATE OR REPLACE SEMANTIC VIEW` | Deploy SV variants | Cannot proceed |
| `CREATE SCHEMA` (first run only) | Create `_SV_TOOLKIT_META` | Ask user to create manually |
| `CREATE TABLE` on `_SV_TOOLKIT_META` | Persist optimization state | Cannot proceed |

### sv-watch

| Requirement | Why | Fallback if Missing |
|---|---|---|
| `IMPORTED PRIVILEGES` on `SNOWFLAKE` database | Detect schema changes via ACCOUNT_USAGE | Cannot detect drift |
| `SELECT` on semantic views to monitor | DESCRIBE to compare | Cannot proceed |
| `CREATE TABLE` on `_SV_TOOLKIT_META` | Persist watch history | Cannot proceed |

### sv-composer

| Requirement | Why | Fallback if Missing |
|---|---|---|
| `CREATE SEMANTIC VIEW` on target schema | Create nested/composed SVs | Cannot proceed |
| `SELECT` on source SVs | Read existing SV definitions | Cannot proceed |

### vqr-generator

| Requirement | Why | Fallback if Missing |
|---|---|---|
| `IMPORTED PRIVILEGES` on `SNOWFLAKE` database | QUERY_HISTORY for question mining | Cannot auto-generate (manual only) |
| `ALTER SEMANTIC VIEW` on target SV | Add generated VQRs | Generate only, user applies manually |

## Edition Requirements

| Feature | Edition |
|---|---|
| ACCESS_HISTORY (column-level usage) | Enterprise or higher |
| EXECUTE_AI_EVALUATION | Standard (Preview, all accounts) |
| Cortex Analyst evaluations | Standard (Preview, all accounts) |
| Dynamic Tables as SV sources | Standard |
| External Tables (Iceberg) as SV sources | Standard |

## Quick Validation

Run this to check your current role has the essentials:

```sql
-- Check ACCOUNT_USAGE access
SELECT COUNT(*) FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY
WHERE START_TIME >= DATEADD('day', -1, CURRENT_TIMESTAMP()) LIMIT 1;

-- Check CORTEX_USER role
SELECT CURRENT_ROLE();
SHOW GRANTS TO ROLE <your_role>;

-- Check eval prerequisites
SELECT SYSTEM$ALLOWLIST('CORTEX');
```

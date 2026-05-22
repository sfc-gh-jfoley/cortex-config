# agent-flag-tester

Standalone Cortex Code skill for A/B/C testing Cortex Agent feature flags.

Creates 3 agent variants (BASE, AGENTIC, FASTPATH_OFF), builds and validates an eval dataset with ground truth verification, runs DEV/TEST evaluations using the `EXECUTE_AI_EVALUATION` API, and compares results across variants.

## What It Does

| Phase | Description |
|---|---|
| 1. Discover | Extract agent spec, identify semantic views |
| 2. Create Variants | Deploy 3 agent clones with different flag configs |
| 3. Build/Validate Dataset | Create or validate eval table + DEV/TEST splits + GT completeness gate |
| 4. Verify Ground Truth | Run queries against semantic views to confirm data actually exists |
| 5. Generate Configs | Create YAML eval configs + upload to internal stage |
| 6. Fire Evals | Launch all runs via `EXECUTE_AI_EVALUATION` + poll to completion |
| 7. Compare Results | Extract scores, build comparison table, recommend winner |

## Metrics

- **answer_correctness** (built-in) — factual accuracy vs ground truth
- **logical_consistency** (built-in, reference-free) — reasoning coherence
- **tool_selection_accuracy** (custom LLM judge) — did the agent pick the right semantic view tool?

## Prerequisites

- Snowflake Cortex Agent with at least one `cortex_analyst_text_to_sql` tool
- `snow` CLI installed with a named connection
- Cortex Code CLI installed
- Role with: `SNOWFLAKE.CORTEX_USER`, `EXECUTE TASK ON ACCOUNT`, `USAGE`/`CREATE DATASET ON SCHEMA`

## Install

```bash
cortex plugin install sfc-gh-jfoley/cortex-agent-toolkit
```

Then open Cortex Code and say:

> "Run a flag comparison test on MYDB.MYSCHEMA.MY_AGENT"

The skill will walk you through all 7 phases with confirmation gates at each step.

## File Structure

```
agent-flag-tester/
├── SKILL.md                              # 7-phase workflow
├── README.md                             # This file
└── references/
    ├── eval-config-template.yaml         # YAML template with 3 metrics
    ├── eval-table-schema.md              # Eval table DDL + VARIANT ground truth format
    ├── variant-matrix.md                 # Default 3-variant matrix (extensible)
    └── gt-verification.md                # How GT verification works via semantic view SQL
```

## Key Constraints

- **Schema co-location:** Agent variants and eval dataset table MUST be in the same schema. The eval task DAG resolves agent names relative to the task's schema.
- **VARIANT ground truth:** The `GROUND_TRUTH` column must be VARIANT type (use `PARSE_JSON`), not VARCHAR.
- **Unique dataset names per run slot:** Each run gets its own `dataset_name` to avoid version lock conflicts during parallel execution.

## API

Uses the current `EXECUTE_AI_EVALUATION` API (not the deprecated `SYSTEM$EXECUTE_AI_OBSERVABILITY_RUN`).

- Start: `CALL EXECUTE_AI_EVALUATION('START', OBJECT_CONSTRUCT('run_name', '...'), '@stage/config.yaml')`
- Status: `CALL EXECUTE_AI_EVALUATION('STATUS', ...)`
- Results: `SELECT * FROM TABLE(SNOWFLAKE.LOCAL.GET_AI_EVALUATION_DATA(db, schema, agent, 'CORTEX AGENT', run_name))`

## Typical Results

From an example flag sweep (34 questions, 3 runs per split):

| Variant | answer_correctness (TEST) | logical_consistency (TEST) |
|---|---|---|
| BASE | 65.2% | 97.1% |
| AGENTIC | 71.8% | 89.3% |
| FASTPATH_OFF | 77.5% | 85.6% |

FASTPATH_OFF wins correctness; BASE wins consistency. The right choice depends on your use case.

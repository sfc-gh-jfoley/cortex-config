# cortex-agent-toolkit

A Cortex Code plugin for the full Snowflake Cortex Agent lifecycle — from creation through evaluation, optimization, and production flag-tuning. All workflows use pure SQL DDL and native Snowflake evaluation APIs.

## Install

```bash
# Install from your local copy of the toolkit:
cortex plugin install /path/to/cortex-agent-toolkit
```

## Skills

| Skill | Purpose | When to Use |
|---|---|---|
| `cortex-agent-ddl` | Create or edit Cortex Agents using SQL DDL with auto-generated tool descriptions, 17-rule spec validation, tenant isolation (Phase 4b), and CI/CD deployment (Phase 8) | Building a new agent from a semantic view, editing an existing agent's spec, or deploying agents via CI/CD pipelines |
| `agent-evaluation` | Run native Snowflake agent evaluations with ground-truth datasets | Measuring agent quality: answer correctness, tool selection accuracy, logical consistency |
| `agent-flag-tester` | Compare model variants (_MODEL_A/B/C: claude-sonnet vs openai-gpt-5 vs haiku) and conditional flag variants (_VQR, _CHART) side-by-side with statistical rigor | Finding the best model/config combination before committing to a final agent configuration |
| `cortex-agent-optimization` | Iterative improvement loop with dev/test eval splits and accept/reject gates | Systematically improving an existing agent's accuracy over multiple iterations |
| `cortex-agent-flags` | Reference for experimental flags and chart customization options | Looking up available flags, understanding what each flag does, adding flags to a spec |
| `query-cortex-agent` | Invoke agents programmatically via SQL (DATA_AGENT_RUN / AGENT_RUN) | Quick agent testing, scripted invocations, multi-turn conversations |

## Key: execution_environment

The #1 deployment failure for new agents is missing `execution_environment` in `tool_resources`. Every `cortex_analyst_text_to_sql` tool **must** have:

```json
"tool_resources": {
  "MyTool": {
    "semantic_view": "DB.SCHEMA.SV_NAME",
    "execution_environment": {
      "type": "warehouse",
      "warehouse": "MY_WH"
    }
  }
}
```

Without it, `CREATE AGENT` succeeds silently but `DATA_AGENT_RUN` fails with error 399504. The `cortex-agent-ddl` skill enforces this via self-check Rule 3.

## Recommended Workflow

```
semantic-view-ddl (create semantic view — separate plugin)
  └── cortex-agent-ddl (create agent from SV)
       ├── Phase 4b: Tenant Isolation (if multitenant)
       │   └── RAP generation + invocation pattern docs
       └── writes handoff.json
            ├── agent-evaluation (baseline quality measurement)
            ├── agent-flag-tester (compare flag variants)
            │   └── writes flag_sweep_baseline.json
            ├── cortex-agent-optimization (iterative improvement)
            │   └── uses flag_sweep_baseline.json as starting point
            └── Phase 8: CI/CD Deploy (GitHub Actions / GitLab / Azure)
                 └── OIDC service user + env promotion + rollback
```

## Bundled Skill Dependencies

These skills ship with Cortex Code and are referenced by some workflows. They require no separate installation:

- `dataset-curation` — help building evaluation datasets
- `debug-single-query-for-cortex-agent` — debug a specific failing query
- `adhoc-testing-for-cortex-agent` — quick manual testing
- `evaluate-cortex-agent` — bundled evaluation entry point

## Prerequisites

See [PREREQUISITES.md](./PREREQUISITES.md) for roles, permissions, and tooling requirements.

See [CUSTOMER_GUIDE.md](./CUSTOMER_GUIDE.md) for a step-by-step walkthrough of the full workflow.

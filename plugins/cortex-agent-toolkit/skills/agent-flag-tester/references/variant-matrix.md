# Variant Matrix

## Default Sweep: Model Comparison

Always applicable — run for any agent regardless of features configured.

| Variant Suffix | Spec change | Description |
|---|---|---|
| `_MODEL_A` | `models.orchestration: claude-sonnet-4-6` | Baseline — current recommended default |
| `_MODEL_B` | `models.orchestration: openai-gpt-5` | Cross-family comparison (OpenAI vs Claude) |
| `_MODEL_C` | `models.orchestration: claude-haiku-4-5` | Latency-optimized option |

## Conditional Sweep: Flags

Add these variants only if the agent uses the relevant feature.

| Variant Suffix | When to use | Flags |
|---|---|---|
| `_VQR` | Agent has VQRs defined in semantic views | `EnableVQRFastPath: true` vs baseline |
| `_CHART` | Agent has `data_to_chart` tool | `EnableUnrestrictedChartTool: true` vs baseline |
| `_BUDGET_HIGH` | Latency is a concern | `orchestration.budget.seconds` increased |

## How to Select Variants

For a first sweep, always run the model comparison (3 variants). Add conditional flag variants only if the agent uses the relevant features. Skip flag variants if the feature isn't configured on the agent.

## Agent Naming Convention

Given a source agent `{DATABASE}.{SCHEMA}.{AGENT}`, variants are named:

- `{DATABASE}.{SCHEMA}.{AGENT}_MODEL_A`
- `{DATABASE}.{SCHEMA}.{AGENT}_MODEL_B`
- `{DATABASE}.{SCHEMA}.{AGENT}_MODEL_C`
- `{DATABASE}.{SCHEMA}.{AGENT}_{SUFFIX}` (for conditional flag variants)

All variants **must** be in the same schema as the eval dataset (co-location constraint).

## Variant Creation SQL

For model comparison variants, clone the original agent spec and change `models.orchestration`:

```sql
-- MODEL_A: current recommended default
CREATE AGENT {DATABASE}.{SCHEMA}.{AGENT}_MODEL_A
FROM SPECIFICATION $$
{
  ... original spec ...,
  "models": {"orchestration": "claude-sonnet-4-6"}
}
$$;

-- MODEL_B: cross-family comparison
CREATE AGENT {DATABASE}.{SCHEMA}.{AGENT}_MODEL_B
FROM SPECIFICATION $$
{
  ... original spec ...,
  "models": {"orchestration": "openai-gpt-5"}
}
$$;

-- MODEL_C: latency-optimized
CREATE AGENT {DATABASE}.{SCHEMA}.{AGENT}_MODEL_C
FROM SPECIFICATION $$
{
  ... original spec ...,
  "models": {"orchestration": "claude-haiku-4-5"}
}
$$;
```

For conditional flag variants, modify the `experimental` section instead:

```sql
-- _VQR: VQR fast path enabled
CREATE AGENT {DATABASE}.{SCHEMA}.{AGENT}_VQR
FROM SPECIFICATION $$
{
  ... original spec ...,
  "experimental": {
    "EnableVQRFastPath": true
  }
}
$$;
```

## Custom Variants

The matrix is extensible. To add a custom variant:

1. Add a row to the matrix with a suffix, flags, and description
2. The skill will generate the additional agent + YAML configs automatically
3. Keep suffix short (used in run names: `{prefix}_{suffix}_{split}_r{N}`)

Examples of custom variants:
- `_BUDGET_HIGH`: `orchestration.budget` increased to 50000
- `_MODEL_SWAP`: Switch orchestration model (e.g., `claude-sonnet-4-5` → `llama3.1-70b`)
- `_INSTRUCTIONS_V2`: Modified instructions for A/B testing prompt changes

## Cleanup

After the sweep is complete and a variant is promoted:

```sql
-- Drop whichever variant suffixes were created for the sweep
-- e.g., for model comparison:
DROP AGENT IF EXISTS {DATABASE}.{SCHEMA}.{AGENT}_MODEL_A;
DROP AGENT IF EXISTS {DATABASE}.{SCHEMA}.{AGENT}_MODEL_B;
DROP AGENT IF EXISTS {DATABASE}.{SCHEMA}.{AGENT}_MODEL_C;

-- Apply winning model/config to the original agent via ALTER or CREATE OR REPLACE
```

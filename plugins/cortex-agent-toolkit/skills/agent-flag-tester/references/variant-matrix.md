# Variant Matrix

## Default 3-Variant Flag Sweep

| Variant Suffix | `EnableAgenticAnalyst` | `DisableFastPath` | Description |
|---|---|---|---|
| `_BASE` | `false` | _(default)_ | Baseline — no agentic features. Simplest reasoning path. Often highest logical consistency. |
| `_AGENTIC` | `true` | _(default)_ | Agentic analyst enabled with fast-path optimization. Typically improves correctness for complex queries. |
| `_FASTPATH_OFF` | `true` | `true` | Agentic analyst with fast-path disabled — forces full reasoning chain on every query. Usually highest correctness but may reduce consistency or increase latency. |

## Agent Naming Convention

Given a source agent `{DATABASE}.{SCHEMA}.{AGENT}`, variants are named:

- `{DATABASE}.{SCHEMA}.{AGENT}_BASE`
- `{DATABASE}.{SCHEMA}.{AGENT}_AGENTIC`
- `{DATABASE}.{SCHEMA}.{AGENT}_FASTPATH_OFF`

All variants **must** be in the same schema as the eval dataset (co-location constraint).

## Variant Creation SQL

For each variant, clone the original agent spec and modify the `experimental` section:

```sql
-- BASE: disable agentic analyst
CREATE AGENT {DATABASE}.{SCHEMA}.{AGENT}_BASE
FROM SPECIFICATION $$
{
  ... original spec ...,
  "experimental": {
    "EnableAgenticAnalyst": false
  }
}
$$;

-- AGENTIC: enable agentic analyst (default fast-path)
CREATE AGENT {DATABASE}.{SCHEMA}.{AGENT}_AGENTIC
FROM SPECIFICATION $$
{
  ... original spec ...,
  "experimental": {
    "EnableAgenticAnalyst": true
  }
}
$$;

-- FASTPATH_OFF: enable agentic, disable fast-path
CREATE AGENT {DATABASE}.{SCHEMA}.{AGENT}_FASTPATH_OFF
FROM SPECIFICATION $$
{
  ... original spec ...,
  "experimental": {
    "EnableAgenticAnalyst": true,
    "DisableFastPath": true
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
-- Drop non-promoted variants
DROP AGENT IF EXISTS {DATABASE}.{SCHEMA}.{AGENT}_BASE;
DROP AGENT IF EXISTS {DATABASE}.{SCHEMA}.{AGENT}_AGENTIC;
DROP AGENT IF EXISTS {DATABASE}.{SCHEMA}.{AGENT}_FASTPATH_OFF;

-- Apply winning flags to the original agent via ALTER or CREATE OR REPLACE
```

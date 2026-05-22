# cortex-agent-toolkit Test Suite

## What's tested

| Test | File | Validates |
|------|------|-----------|
| Agent spec | `fixtures/sample_agent_spec.yaml` | Required keys (models, instructions, tools, tool_resources) |
| Eval config | `fixtures/sample_eval_config.yaml` | Structure: questions array with input_query + expected fields |
| Flag matrix | `fixtures/sample_flag_matrix.yaml` | 3 variants with suffix + experimental fields |
| Skill structure | — | All 6 SKILL.md files exist and are non-empty |
| Phase files | — | All 7 cortex-agent-ddl phase .md files (01-07) exist |
| Contamination | — | No customer/internal data (snowhouse, DISH, etc.) in skills/ |

## How to run

```bash
cd ~/.snowflake/cortex/plugins/cortex-agent-toolkit
bash tests/run_tests.sh
```

Or make executable and run directly:

```bash
chmod +x tests/run_tests.sh
./tests/run_tests.sh
```

## Expected output

All tests should pass with green checkmarks. The contamination check scans
`skills/` for known internal references (Snowhouse, customer names) that
must not be shipped to customers.

## Requirements

- Python 3.8+ (stdlib-only; uses PyYAML if available, otherwise a minimal fallback parser)
- No Snowflake connection required

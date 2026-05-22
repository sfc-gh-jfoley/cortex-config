# Cortex Semantic Layer Bundle — Manifest

## Version

Bundle version: **1.2.0**
Build date: 2026-05-15

## Components

| Component | Version | Self-checks | Location |
|-----------|---------|-------------|----------|
| semantic-view-discovery | 1.0.0 | N/A (discovery) | `semantic-view-discovery/` |
| semantic-view-ddl | 1.1.0 | 23 checks (18 syntax + 5 semantic) | `semantic-view-ddl/` |
| cortex-agent-toolkit | 1.2.0 | 17 rules | `cortex-agent-toolkit/` |

## Test Suites

| Suite | Expected | Location |
|-------|----------|----------|
| Agent toolkit unit tests | 3 pass | `cortex-agent-toolkit/tests/run_tests.sh` |
| Agent toolkit phase tests | 21 pass | `cortex-agent-toolkit/tests/test_new_phases.sh` |
| SV-DDL multitenant tests | 11 pass | `semantic-view-ddl/tests/test_multitenant_integration.sh` |

## Changelog (1.2.0)

- Fixed SQL injection in eval scripts (convert_eval_dataset.py, invoke_agent.py)
- Separated production vs test tenant isolation templates (Pattern C)
- Fixed PAT token handling to avoid secret exposure in query history
- Updated all check counts (SV-DDL 18→23, Agent 16→17)
- Fixed broken relative link in CUSTOMER_GUIDE.md
- Added stream parameter documentation
- Added ACCOUNTADMIN least-privilege guidance in CI/CD phase
- Created this manifest

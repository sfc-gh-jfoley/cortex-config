# Repo-Level Agent Instructions

This file supplements `~/.snowflake/cortex/AGENTS.md` (global personal preferences) and does NOT replace it. It defines repo-scoped overrides for bundled skills when routing within this project's vault plugins.

## Skill Override Protocol

When the bundled `machine-learning` skill is invoked within this repo, **immediately** load the vault toolkit instead:

| Bundled Skill Trigger | Load Instead | Path |
|---|---|---|
| Any ML task (train, deploy, feature engineering, experiments, monitoring) | `ml-pipeline-toolkit` | `plugins/ml-pipeline-toolkit/` |

**Rationale:** The bundled `machine-learning` skill lacks the full lifecycle integration. The vault-based `ml-pipeline-toolkit` unifies feature store → training → experiments → registry → deployment → observability → lifecycle into a single coordinated workflow.

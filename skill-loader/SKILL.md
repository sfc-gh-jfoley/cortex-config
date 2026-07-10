---
name: skill-loader
description: "On-demand skill/plugin/rule loader. Keeps context minimal — loads only what's needed for the current task."
---

# Skill Loader

Load skills, plugins, and rules on-demand from `~/.snowflake/cortex/vault/`. 

## Workflow

1. Identify which skill the user needs from the registry below
2. Read the SKILL.md: `~/.snowflake/cortex/vault/{path}/SKILL.md`
3. Follow the loaded skill's instructions for the remainder of the task

If unsure which skill matches, ask the user.

---

## Registry

### Semantic Views & Analyst

| Skill | When to use | Path |
|-------|-------------|------|
| semantic-view-toolkit | Full SV lifecycle router (discovery, DDL, audit, eval, optimization, GEPA, watch, compose, VQR) | `plugins/semantic-view-toolkit/` |
| sv-discovery | Find SV candidates from schema analysis | `plugins/semantic-view-toolkit/skills/sv-discovery/` |
| sv-ddl | Build/edit semantic views (DDL path); supports SQL queries as logical tables, VARIABLES clause, SAMPLE_VALUES + ENUM_INDICATOR (all GA Jun 2026) | `plugins/semantic-view-toolkit/skills/sv-ddl/` |
| sv-audit | Audit existing SV against usage patterns | `plugins/semantic-view-toolkit/skills/sv-audit/` |
| sv-evaluation | Run Cortex Analyst evaluations on SVs | `plugins/semantic-view-toolkit/skills/sv-evaluation/` |
| sv-optimization | Iterative SV improvement loop | `plugins/semantic-view-toolkit/skills/sv-optimization/` |
| sv-gepa-optimizer | Population-based evolutionary SV optimization | `plugins/semantic-view-toolkit/skills/sv-gepa-optimizer/` |
| sv-watch | Drift detection + SV maintenance monitoring | `plugins/semantic-view-toolkit/skills/sv-watch/` |
| sv-composer | Nested SVs + multi-SV agent composition | `plugins/semantic-view-toolkit/skills/sv-composer/` |
| vqr-generator | Auto-generate verified queries from query history | `plugins/semantic-view-toolkit/skills/vqr-generator/` |
| semantic-view-ddl | (LEGACY) Build/edit semantic views — use sv-ddl instead | `skills/semantic-view-ddl/` |
| semantic-view-discovery | (LEGACY) Find SV candidates — use sv-discovery instead | `skills/semantic-view-discovery/` |

### Cortex Agents

| Skill | When to use | Path |
|-------|-------------|------|
| cortex-agent-toolkit | Full agent lifecycle router (create, eval, flags, optimize, GEPA, query) | `plugins/cortex-agent-toolkit/` |
| cortex-agent-ddl | Create/deploy Cortex Agents | `plugins/cortex-agent-toolkit/skills/cortex-agent-ddl/` |
| cortex-agent-flags | Agent experimental flags reference | `plugins/cortex-agent-toolkit/skills/cortex-agent-flags/` |
| cortex-agent-optimization | Iterative agent prompt optimization + full lifecycle | `plugins/cortex-agent-toolkit/skills/cortex-agent-optimization/` |
| agent-evaluation | Run EXECUTE_AI_EVALUATION | `plugins/cortex-agent-toolkit/skills/agent-evaluation/` |
| agent-flag-tester | Compare agent flag variants (3-way) | `plugins/cortex-agent-toolkit/skills/agent-flag-tester/` |
| query-cortex-agent | Query an existing agent via SQL | `plugins/cortex-agent-toolkit/skills/query-cortex-agent/` |
| agent-gepa-optimizer | Evolutionary population-based agent optimization | `plugins/cortex-agent-toolkit/skills/agent-gepa-optimizer/` |
| analytical-search | Semantic + ranked search over large document collections as an agent tool type (GA Jul 2026) | `plugins/cortex-agent-toolkit/skills/analytical-search/` |

> **Bundled Skill Override**: If the bundled `cortex-agent`, `semantic-view`, or `machine-learning` skill was
> just invoked, load the vault toolkit instead (see paths above). The bundled skills lack
> the full lifecycle (eval → flag-test → optimize → GEPA; or ML feature store → train → experiments → registry → deploy → observe). Exceptions: YAML/FastGen
> and Tableau/PBI import stay on bundled semantic-view.

### Knowledge Graph & Ontology

| Skill | When to use | Path |
|-------|-------------|------|

### Ops & Monitoring

| Skill | When to use | Path |
|-------|-------------|------|
| ops-monitor | Full observability router (drift, release monitoring, self-healing) | `plugins/ops-monitor/` |
| artifact-drift-monitor | Check SV/DT/Agent drift | `plugins/ops-monitor/skills/artifact-drift-monitor/` |
| release-change-monitor | Monitor Snowflake release changes | `plugins/ops-monitor/skills/release-change-monitor/` |
| self-healing-pipeline | Auto-fix pipeline failures | `plugins/ops-monitor/skills/self-healing-pipeline/` |

### ML & MLOps

| Skill | When to use | Path |
|-------|-------------|------|
| ml-pipeline-toolkit | Full ML lifecycle router (feature store → train → experiments → registry → deploy → observe → lifecycle) | `plugins/ml-pipeline-toolkit/` |
| ml-feature-store | Define entities, feature views (Dynamic Table-backed), point-in-time retrieval | `plugins/ml-pipeline-toolkit/skills/ml-feature-store/` |
| ml-pipeline-build | Scaffold training pipelines (Snowpark ML, Container Runtime, stored procs) | `plugins/ml-pipeline-toolkit/skills/ml-pipeline-build/` |
| ml-experiments | Track experiments, log runs, compare metrics (Snowflake-native, NOT MLflow) | `plugins/ml-pipeline-toolkit/skills/ml-experiments/` |
| ml-registry | Register models, manage versions, metadata, RBAC | `plugins/ml-pipeline-toolkit/skills/ml-registry/` |
| ml-deploy | Deploy to warehouse inference, SPCS service, or REST endpoint | `plugins/ml-pipeline-toolkit/skills/ml-deploy/` |
| ml-observability | Create model monitors, query drift/performance/stat metrics | `plugins/ml-pipeline-toolkit/skills/ml-observability/` |
| ml-log-inspector | Diagnose ML pipeline and model monitor failures (5-surface triage) | `plugins/ml-pipeline-toolkit/skills/ml-log-inspector/` |
| ml-lifecycle | Promote via aliases, rollback, deprecate, govern model versions | `plugins/ml-pipeline-toolkit/skills/ml-lifecycle/` |
| ml-functions | AutoML in SQL: FORECAST, ANOMALY_DETECTION, CLASSIFICATION, TOP_INSIGHTS | `plugins/ml-pipeline-toolkit/skills/ml-functions/` |
| ml-watch | Scheduled retraining, data freshness SLAs, drift alert tasks | `plugins/ml-pipeline-toolkit/skills/ml-watch/` |

### Rules & Governance

| Skill | When to use | Path |
|-------|-------------|------|
| rule-governance | Full rules & governance router (create → review → load workflow for coding standards) | `plugins/rule-governance/` |
| rule-loader | Load coding rules for current task | `plugins/rule-governance/skills/rule-loader/` |
| rule-creator | Create new rules | `plugins/rule-governance/skills/rule-creator/` |
| rule-reviewer | Review a single rule quality | `plugins/rule-governance/skills/rule-reviewer/` |
| bulk-rule-reviewer | Batch review rules | `plugins/rule-governance/skills/bulk-rule-reviewer/` |
| memory-organizer | Clean/consolidate memories | `plugins/rule-governance/skills/memory-organizer/` |

### Meta & Quality

| Skill | When to use | Path |
|-------|-------------|------|
| coco-meta | Full quality & meta router (skill testing, documentation review, plan scoring, timing analysis) | `plugins/coco-meta/` |
| doc-reviewer | Review documents for quality | `plugins/coco-meta/skills/doc-reviewer/` |
| plan-reviewer | Score implementation plans | `plugins/coco-meta/skills/plan-reviewer/` |
| prompt-determinism-tester | Test prompt consistency (3-agent) | `plugins/coco-meta/skills/prompt-determinism-tester/` |
| skill-tester | Test skills with fixtures | `plugins/coco-meta/skills/skill-tester/` |
| skill-timing | Measure skill execution time | `plugins/coco-meta/skills/skill-timing/` |

### Compute & Warehouses

| Skill | When to use | Path |
|-------|-------------|------|
| adaptive-compute | Full Adaptive Warehouse router (create, convert, monitor) — AWS only (GA Jun 2026) | `plugins/adaptive-compute/` |
| adaptive-warehouse-setup | Create a new Adaptive Warehouse or convert an existing standard warehouse | `plugins/adaptive-compute/skills/adaptive-warehouse-setup/` |
| adaptive-warehouse-monitor | Track credit usage, performance, and revert criteria for Adaptive Warehouses | `plugins/adaptive-compute/skills/adaptive-warehouse-monitor/` |

> **Region gate**: Adaptive Warehouses are AWS-only. Phase 0 of adaptive-warehouse-setup verifies `CURRENT_REGION()` before proceeding.

### Security & Auth

| Skill | When to use | Path |
|-------|-------------|------|
| workload-identity | Full Workload Identity Federation router — Snowflake as OIDC provider for external services (GA Jul 2026) | `plugins/workload-identity/` |
| wif-setup | Create `WORKLOAD_IDENTITY_FEDERATION` secret, obtain issuer URL/subject, configure external service, test token issuance | `plugins/workload-identity/skills/wif-setup/` |
| wif-troubleshoot | Diagnose WIF failures: expired tokens, wrong issuer URL, missing grants | `plugins/workload-identity/skills/wif-troubleshoot/` |
| session-policy | Create and manage Session Policies (GA Apr 2026) — enforce max lifespan, UI idle timeouts, and session expiration | `plugins/workload-identity/skills/session-policy/` |

### Cortex Search Service

| Skill | When to use | Path |
|-------|-------------|------|
| cortex-search-lifecycle | Full Cortex Search Service lifecycle router (create, manage budgets, monitor) — semantic search over unstructured data (GA Jul 2, 2026) | `plugins/cortex-search-lifecycle/` |
| css-setup | Create a Cortex Search Service, configure warehouses, source tables, and index freshness settings | `plugins/cortex-search-lifecycle/skills/css-setup/` |
| css-budgets | Set monthly credit limits for search services and enforce automated budget actions | `plugins/cortex-search-lifecycle/skills/css-budgets/` |
| css-monitor | Monitor search service health via ACCOUNT_USAGE, track guardrails violations, analyze performance | `plugins/cortex-search-lifecycle/skills/css-monitor/` |

### Collaboration

| Skill | When to use | Path |
|-------|-------------|------|
| cowork | Full Snowflake CoWork router (Artifacts + Deep Research) — AI investigation and persistent result sharing (GA Jun–Jul 2026) | `plugins/cowork/` |
| cowork-artifacts | Create, refresh, and share persistent chart/table references from agent responses | `plugins/cowork/skills/cowork-artifacts/` |
| cowork-deep-research | Run multi-step AI investigations across structured + unstructured data with source tracing | `plugins/cowork/skills/cowork-deep-research/` |

### Workshops & Demos

| Skill | When to use | Path |
|-------|-------------|------|
| lab-builder | Build HOL/workshop labs | `skills/lab-builder/` |

### Project Architecture

| Skill | When to use | Path |
|-------|-------------|------|
| agent-architect | Multi-agent project builds (full framework, v3.0) | `skills/agent-architect/` |

### Diagrams & Visuals

| Skill | When to use | Path |
|-------|-------------|------|
| architecture-diagram | Generate architecture/system/flow diagrams (Mermaid→Excalidraw→PNG) | `skills/architecture-diagram/` |
| snowflake-gslides | Create Google Slides decks | `skills/snowflake-gslides/` |

### Utilities

| Skill | When to use | Path |
|-------|-------------|------|
| coco-usage | CoCo token/credit consumption analysis | `skills/coco-usage/` |
| google-doc-formatter | Format markdown as Google Doc | `skills/google-doc-formatter/` |
| snowflake-workspaces | Write Python in Snowflake Workspaces UI (GA Jun 18, 2026). Schedule Python jobs, create NPOs (Native Python Objects), integrate with Tasks. Understand when to use Workspaces vs. Notebooks | `skills/snowflake-workspaces/` |

---

## Loading Rules (coding standards)

For coding rules, first load rule-loader:
```
Read: ~/.snowflake/cortex/vault/plugins/rule-governance/skills/rule-loader/SKILL.md
```
Then follow its workflow to load specific rule files from `~/.snowflake/cortex/rules/`.

---

## Bundled Skills: Coverage Gaps & Entry Points

Some bundled Snowflake skills have documentation limitations or incomplete feature coverage. These notes guide users to appropriate workarounds or reference information:

### data-quality (DMF FILTER clause gap)

**Gap:** The bundled `data-quality` skill does not document the `FILTER` clause for Data Metric Functions (DMFs), which allows dynamic filtering of metrics (GA Jul 2026).

**Workaround:** 
- Refer to [Snowflake DMF documentation](https://docs.snowflake.com/data-quality/data-quality-setup#filter-clause)
- Use `FILTER (WHERE condition)` in DMF definitions to scope metrics to subsets of data
- Example: `METRIC temperature UNIT 'C' FILTER (WHERE region = 'EU')`

### snowflake-tasks (ACCOUNT_USAGE.TASKS view gap)

**Gap:** The bundled `snowflake-tasks` skill does not document the `ACCOUNT_USAGE.TASKS` view, which provides account-level task history and execution metrics across multiple databases/schemas.

**Workaround:**
- Use `INFORMATION_SCHEMA.TASK_HISTORY()` for schema-level task diagnostics (scoped, real-time)
- Use `ACCOUNT_USAGE.TASKS` for account-wide analytics and historical trends (delayed ~30 min)
- Query example:
  ```sql
  SELECT
    TASK_NAME,
    OWNER_NAME,
    DATABASE_NAME,
    DEFINITION,
    CREATED_ON
  FROM SNOWFLAKE.ACCOUNT_USAGE.TASKS
  ORDER BY CREATED_ON DESC;
  ```

---

## Constraints

- **Load one skill at a time** — don't bulk-load
- **After loading**: follow that skill's instructions completely as if natively invoked
- **If the skill references sub-files** (phases/, references/, etc.): those are relative to the skill's vault directory
- **All vault paths are relative to** `~/.snowflake/cortex/vault/`

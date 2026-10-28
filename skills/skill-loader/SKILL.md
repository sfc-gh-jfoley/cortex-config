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
| semantic-view-toolkit | Full SV lifecycle router (discovery, DDL, audit, eval, optimization, GEPA, watch, rearchitect, VQR) | `plugins/semantic-view-toolkit/` |
| sv-discovery | Find SV candidates from schema analysis | `plugins/semantic-view-toolkit/skills/sv-discovery/` |
| sv-ddl | Build/edit semantic views (DDL path) | `plugins/semantic-view-toolkit/skills/sv-ddl/` |
| sv-audit | Audit existing SV against usage patterns | `plugins/semantic-view-toolkit/skills/sv-audit/` |
| sv-evaluation | Run Cortex Analyst evaluations on SVs | `plugins/semantic-view-toolkit/skills/sv-evaluation/` |
| sv-iterative-optimizer | Sequential iterative SV improvement (descriptions, metrics, VQRs, filters); escalate to sv-gepa-optimizer if stuck | `plugins/semantic-view-toolkit/skills/sv-iterative-optimizer/` |
| sv-gepa-optimizer | Population-based evolutionary SV optimization | `plugins/semantic-view-toolkit/skills/sv-gepa-optimizer/` |
| sv-watch | Drift detection + SV maintenance monitoring | `plugins/semantic-view-toolkit/skills/sv-watch/` |
| sv-rearchitect | Rearchitect SV domain structure: split domains, nested SVs, multi-SV agent composition | `plugins/semantic-view-toolkit/skills/sv-rearchitect/` |
| vqr-generator | Auto-generate verified queries from query history | `plugins/semantic-view-toolkit/skills/vqr-generator/` |
| sv-coverage-checker | Check GT SQL coverage against an SV — gap report + per-question ANSWERABLE/NOT_ANSWERABLE verdicts | `plugins/semantic-view-toolkit/skills/sv-coverage-checker/` |
| sv-materialize | Manage SV materializations to accelerate repeated Semantic SQL queries (eligibility, grain/staleness, refresh history, auto-suspend) | `plugins/semantic-view-toolkit/skills/sv-materialize/` |
| sv-snippet-suggester | Pattern recognition across 25 canonical SV patterns from schema/question/partial DDL | `plugins/semantic-view-toolkit/skills/sv-snippet-suggester/` |
| vqr-curator | Audit/curate VQRs on an existing SV — KEEP/FIX_SQL/DEDUPLICATE/SIMPLIFY/REMOVE verdicts | `plugins/semantic-view-toolkit/skills/vqr-curator/` |
| vqr-semantic-view-generator | Multi-domain SV from query history (ontology-demo) | `plugins/ontology-demo/skills/vqr-semantic-view-generator/` |

### Cortex Agents

| Skill | When to use | Path |
|-------|-------------|------|
| cortex-agent-toolkit | Full agent lifecycle router (create, eval, flags, optimize, GEPA, query) | `plugins/cortex-agent-toolkit/` |
| agent-ddl | Create/deploy Cortex Agents | `plugins/cortex-agent-toolkit/skills/agent-ddl/` |
| agent-flags-reference | Agent experimental flags reference | `plugins/cortex-agent-toolkit/skills/agent-flags-reference/` |
| agent-optimizer | Full optimization lifecycle hub: setup, iterate, flag sweep, feedback pipeline, diagnose, RESUME_AFTER_SV_CHANGE, escalate to DSPy/GEPA | `plugins/cortex-agent-toolkit/skills/agent-optimizer/` |
| agent-instruction-optimizer | DSPy MIPROv2 optimizer — compile instructions + bootstrapped demonstrations via TPE | `plugins/cortex-agent-toolkit/skills/agent-instruction-optimizer/` |
| agent-feedback-analyzer | Analyze production thumbs-down from AI_OBSERVABILITY_EVENTS, cluster failures, produce remediation report | `plugins/cortex-agent-toolkit/skills/agent-feedback-analyzer/` |
| agent-analytical-search | Configure cortex_search tool for analytical search orchestration (GA Jul 2026) | `plugins/cortex-agent-toolkit/skills/agent-analytical-search/` |
| agent-evaluation | Run EXECUTE_AI_EVALUATION | `plugins/cortex-agent-toolkit/skills/agent-evaluation/` |
| agent-model-tester | Compare model variants (A/B/C) before optimization; also tests flags | `plugins/cortex-agent-toolkit/skills/agent-model-tester/` |
| agent-query | Query an existing agent via SQL | `plugins/cortex-agent-toolkit/skills/agent-query/` |
| agent-gepa-optimizer | Evolutionary population-based agent optimization | `plugins/cortex-agent-toolkit/skills/agent-gepa-optimizer/` |

> **Bundled Skill Override**: If the bundled `cortex-agent` or `semantic-view` skill was
> just invoked, load the vault toolkit instead (see paths above). The bundled skills lack
> the full lifecycle (eval → flag-test → optimize → GEPA). Exceptions: YAML/FastGen
> and Tableau/PBI import stay on bundled semantic-view.

### Knowledge Graph & Ontology

| Skill | When to use | Path |
|-------|-------------|------|
| cortex-accelerator | Guided discovery → agent build | `plugins/ontology-demo/skills/cortex-accelerator/` |
| kg-data-discovery | KG crawl/enrich/relationship detection | `plugins/ontology-demo/skills/kg-data-discovery/` |
| ontology-stack-builder | Build ontology-on-Snowflake | `plugins/ontology-demo/skills/ontology-stack-builder/` |
| schema-discovery-scaffold | Scaffold demo from Snowhouse telemetry | `plugins/ontology-demo/skills/schema-discovery-scaffold/` |
| sql-table-extractor | Extract table definitions from SQL | `plugins/ontology-demo/skills/sql-table-extractor/` |

### Ops & Monitoring

| Skill | When to use | Path |
|-------|-------------|------|
| artifact-drift-monitor | Check SV/DT/Agent drift | `plugins/ops-monitor/skills/artifact-drift-monitor/` |
| release-change-monitor | Monitor Snowflake release changes | `plugins/ops-monitor/skills/release-change-monitor/` |
| self-healing-pipeline | Auto-fix pipeline failures | `plugins/ops-monitor/skills/self-healing-pipeline/` |

### Platform Features (standalone plugins)

| Skill | When to use | Path |
|-------|-------------|------|
| adaptive-compute | Adaptive Warehouse provisioning/monitoring — auto-scaling, credit optimization (AWS only) | `plugins/adaptive-compute/` |
| adaptive-warehouse-setup | Create/convert warehouses to Adaptive type — region check, scaling config, validation | `plugins/adaptive-compute/skills/adaptive-warehouse-setup/` |
| adaptive-warehouse-monitor | Monitor Adaptive Warehouse perf/credits/scaling events, ROI vs. standard warehouse | `plugins/adaptive-compute/skills/adaptive-warehouse-monitor/` |
| cortex-search-lifecycle | Cortex Search Service lifecycle — create/configure services, budgets, guardrails monitoring | `plugins/cortex-search-lifecycle/` |
| css-setup | Create/configure Cortex Search Services | `plugins/cortex-search-lifecycle/skills/css-setup/` |
| css-budgets | Configure Cortex Search resource budgets/credit limits | `plugins/cortex-search-lifecycle/skills/css-budgets/` |
| css-monitor | Monitor Cortex Search usage and guardrails violations | `plugins/cortex-search-lifecycle/skills/css-monitor/` |
| cowork | Snowflake CoWork — multi-step agent investigation, persistent artifacts, source tracing | `plugins/cowork/` |
| cowork-artifacts | Create/manage persistent artifact references from Cortex Agent responses | `plugins/cowork/skills/cowork-artifacts/` |
| cowork-deep-research | Multi-step investigations across structured/unstructured data with source tracing | `plugins/cowork/skills/cowork-deep-research/` |
| ml-pipeline-toolkit | Full ML lifecycle router — feature engineering, training, registry, deployment, observability | `plugins/ml-pipeline-toolkit/` |
| ml-feature-store | Feature Store entities, feature views, point-in-time retrieval | `plugins/ml-pipeline-toolkit/skills/ml-feature-store/` |
| ml-pipeline-build | Scaffold ML training pipelines (Notebooks/Container Runtime, Snowpark ML, SPCS) | `plugins/ml-pipeline-toolkit/skills/ml-pipeline-build/` |
| ml-experiments | Track experiments, log hyperparameters/metrics, compare runs (native ExperimentTracking API) | `plugins/ml-pipeline-toolkit/skills/ml-experiments/` |
| ml-functions | AutoML in SQL via Cortex ML Functions — forecast, anomaly detection, classification | `plugins/ml-pipeline-toolkit/skills/ml-functions/` |
| ml-registry | Register models in Model Registry, manage versions/metadata/RBAC | `plugins/ml-pipeline-toolkit/skills/ml-registry/` |
| ml-deploy | Deploy Model Registry models — batch/online inference, REST endpoint, SPCS serving | `plugins/ml-pipeline-toolkit/skills/ml-deploy/` |
| ml-lifecycle | Model version lifecycle — promote, rollback, copy across environments, deprecate | `plugins/ml-pipeline-toolkit/skills/ml-lifecycle/` |
| ml-observability | Monitor deployed models for drift, performance, data quality | `plugins/ml-pipeline-toolkit/skills/ml-observability/` |
| ml-watch | Scheduled retraining triggers + freshness SLAs for models/feature pipelines | `plugins/ml-pipeline-toolkit/skills/ml-watch/` |
| ml-log-inspector | Diagnose ML pipeline/model monitor failures anywhere in the lifecycle | `plugins/ml-pipeline-toolkit/skills/ml-log-inspector/` |
| workload-identity | Workload Identity Federation (WIF) — service-to-service auth via federated tokens instead of secrets | `plugins/workload-identity/` |
| wif-setup | Set up WIF end-to-end — secret, issuer URL, external service config, token test | `plugins/workload-identity/skills/wif-setup/` |
| wif-troubleshoot | Diagnose WIF issues — token rejected, insufficient grants, issuer mismatch, expiry | `plugins/workload-identity/skills/wif-troubleshoot/` |

### Rules & Governance

| Skill | When to use | Path |
|-------|-------------|------|
| rule-loader | Load coding rules for current task | `plugins/rule-governance/skills/rule-loader/` |
| rule-creator | Create new rules | `plugins/rule-governance/skills/rule-creator/` |
| rule-reviewer | Review a single rule quality | `plugins/rule-governance/skills/rule-reviewer/` |
| bulk-rule-reviewer | Batch review rules | `plugins/rule-governance/skills/bulk-rule-reviewer/` |
| memory-organizer | Clean/consolidate memories | `plugins/rule-governance/skills/memory-organizer/` |

### Meta & Quality

| Skill | When to use | Path |
|-------|-------------|------|
| doc-reviewer | Review documents for quality | `plugins/coco-meta/skills/doc-reviewer/` |
| plan-reviewer | Score implementation plans | `plugins/coco-meta/skills/plan-reviewer/` |
| prompt-determinism-tester | Test prompt consistency (3-agent) | `plugins/coco-meta/skills/prompt-determinism-tester/` |
| skill-tester | Test skills with fixtures | `plugins/coco-meta/skills/skill-tester/` |
| skill-timing | Measure skill execution time | `plugins/coco-meta/skills/skill-timing/` |

### Workshops & Demos

| Skill | When to use | Path |
|-------|-------------|------|
| iot-pipeline-builder | Raw VARIANT tables → DTs → SV → Agent, pure SQL Snowsight-native | `skills/iot-pipeline-builder/` |
| lab-builder | Build HOL/workshop labs | `skills/lab-builder/` |
| telemetry-to-lab | Snowhouse telemetry (read-only) → infer customer ETL/query/ML/GenAI intent + failures → de-identified lab intake + lookalike data spec for lab-builder | `skills/telemetry-to-lab/` |
| se-lab-intake | SE lab intake questionnaire | `plugins/se-workshop/skills/se-lab-intake/` |
| executive-account-planning-markdown | Executive account plans | `plugins/se-workshop/skills/executive-account-planning-markdown/` |
| snowflake-ml-container-runtime | ML Container Runtime workshop | `plugins/se-workshop/skills/snowflake-ml-container-runtime/` |

### Project Architecture

| Skill | When to use | Path |
|-------|-------------|------|
| agent-architect | Multi-agent project builds (full framework, v3.1) | `skills/agent-architect/` |
| specbuilder | Spec-driven development alongside agent-architect — formal ACs, sign-off, drift detection | `skills/specbuilder/` |

> **agent-architect + specbuilder**: Use `specbuilder` to formalize what to build (spec modules, AC tables, sign-off), then `agent-architect` to build it robustly (multi-team, security-gated, independently verified). agent-architect Phase 2 can hand off to specbuilder when `SPECBUILDER_PRESENT=true`.

### Spec-Driven Development

| Skill | When to use | Path |
|-------|-------------|------|
| specbuilder | Router: scaffold, generate, propose, implement, verify, audit | `skills/specbuilder/` |
| generate-spec | Intake clarification + generate spec modules + AC tables | `skills/specbuilder/skills/generate-spec/` |
| propose-spec | Author EXT-NNN architecture proposals with impact analysis | `skills/specbuilder/skills/propose-spec/` |
| implement-spec | Stub generation + batched multi-agent implementation | `skills/specbuilder/skills/implement-spec/` |
| verify-spec | Drift detection + acceptance tests + sign-off workflow | `skills/specbuilder/skills/verify-spec/` |
| audit-spec | Project health checks + upgrade proposals | `skills/specbuilder/skills/audit-spec/` |
| scaffold-spec | Initialize spec project structure (PoC or Production mode) | `skills/specbuilder/skills/scaffold-spec/` |
| checkpoint-spec | Execution checkpoint protocol — track/resume multi-proposal batch implementations | `skills/specbuilder/skills/checkpoint-spec/` |
| handover-consumer | Scaffold a new POC project from a demo handover artifact | `skills/specbuilder/skills/handover-consumer/` |

### Diagrams & Visuals

| Skill | When to use | Path |
|-------|-------------|------|
| architecture-diagram | Generate architecture/system/flow diagrams (Mermaid→Excalidraw→PNG) | `skills/architecture-diagram/` |
| snowflake-gslides | Create Google Slides decks | `skills/snowflake-gslides/` |

### Utilities

| Skill | When to use | Path |
|-------|-------------|------|
| coco-usage | CoCo token/credit consumption analysis | `skills/coco-usage/` |
| coco-patch-usage | Paired CoCo usage reports for an SE leader's patch (accounts + SEs, MoM) | `skills/coco-patch-usage/` |
| google-doc-formatter | Format markdown as Google Doc | `skills/google-doc-formatter/` |
| llm-registry | Check current model aliases before picking a model name | `LLMs.md` at vault root |
| demo-deployment-verify | Audit a demo/lab dir against an account, deploy missing objects, loop build-test-fix | `skills/demo-deployment-verify/` |
| docs-to-toolkit-gap-plan | Review a Snowflake docs/blog URL against a toolkit, prove gaps with executable tests, patch only proven gaps | `skills/docs-to-toolkit-gap-plan/` |
| plugin-dev | Build or audit Cortex plugins against the RC checklist | `skills/plugin-dev/` |
| session-policy | Create/manage Snowflake Session Policies (lifespan constraints, troubleshooting) | `skills/session-policy/` |
| sf-app-deploy-package | Deploy a SiS monitoring app with least-privilege roles, verify SQL, package installer zip | `skills/sf-app-deploy-package/` |
| snowflake-deck-from-source | Build a Snowflake-branded deck from a doc/URL/session findings with speaker notes | `skills/snowflake-deck-from-source/` |
| snowflake-workspaces | Snowflake Workspaces (Python files, NPO+Tasks scheduling, vs. Notebooks) | `skills/snowflake-workspaces/` |
| sv-agent-findings-handoff | Turn SV/agent failure analysis into a grounded, customer-ready remediation doc | `skills/sv-agent-findings-handoff/` |
| vault-skill-publish | Load a personal skill from vault, audit for bloat, publish to catalog, back up to git | `skills/vault-skill-publish/` |

---

## Loading Rules (coding standards)

For coding rules, first load rule-loader:
```
Read: ~/.snowflake/cortex/vault/plugins/rule-governance/skills/rule-loader/SKILL.md
```
Then follow its workflow to load specific rule files from `~/.snowflake/cortex/rules/`.

---

## Constraints

- **Load one skill at a time** — don't bulk-load
- **After loading**: follow that skill's instructions completely as if natively invoked
- **If the skill references sub-files** (phases/, references/, etc.): those are relative to the skill's vault directory
- **All vault paths are relative to** `~/.snowflake/cortex/vault/`

---
name: ml-pipeline-toolkit
description: >
  Full lifecycle toolkit for Snowflake ML — from feature engineering through training,
  experiment tracking, model registration, deployment, observability, and governance.
  Single entry point — tell me where you are in your ML journey and I'll route you.
triggers:
  - ml pipeline toolkit
  - ml toolkit
  - help with ml
  - machine learning lifecycle
  - I need to train a model
  - I have a model
  - feature store
  - feature view
  - ml feature
  - model registry
  - register model
  - log model
  - deploy model
  - model inference
  - model drift
  - model monitor
  - model monitor suspended
  - something broke in my ml pipeline
  - promote model
  - rollback model
  - forecast snowflake
  - anomaly detection snowflake
  - classification snowflake
  - retrain model
  - ml observability
---

# ML Pipeline Toolkit

Full Snowflake ML lifecycle — feature store through deployment, observability, and governance.

---

## How to Use

Tell me where you are in your ML journey, or pick from the menu:

```
1. I have no features — build a feature store           → ml-feature-store
2. I need to train a model                               → ml-pipeline-build
3. I want to track experiments / compare runs            → ml-experiments
4. I need to register a trained model                    → ml-registry
5. I need to deploy for inference (warehouse/SPCS/REST)  → ml-deploy
6. I want to monitor model performance / drift           → ml-observability
7. Something broke — help me diagnose                    → ml-log-inspector
8. I need to promote/rollback/deprecate a model          → ml-lifecycle
9. I want AutoML in SQL (no Python training)             → ml-functions
10. I need ongoing monitoring + auto-retrain triggers    → ml-watch

Or just describe what you need — I'll figure out where to route you.
```

---

## Execution Modes

Ask once per session, then remember:

- **AUTOPILOT** — minimal interaction, chains skills automatically.
  Trigger: "just run it", "end to end", "autopilot"
- **GUIDED** — step-by-step, stops at gates. Default for new users.
  Trigger: "walk me through it"

---

## Phase 0: State Detection

Before routing, probe the current account to detect existing ML state:

```sql
SHOW MODELS IN DATABASE <DB>;
SHOW EXPERIMENTS IN SCHEMA <DB>.<SCHEMA>;
SHOW FEATURE VIEWS IN SCHEMA <DB>.<SCHEMA>;
SHOW MODEL MONITORS IN DATABASE <DB>;
```

| State | Recommendation |
|---|---|
| No models, no feature views | → ml-feature-store or ml-pipeline-build ("Let's start building") |
| Feature views exist, no models | → ml-pipeline-build |
| Models exist, no monitors | → ml-observability ("Get monitoring set up") |
| Monitor exists but SUSPENDED | → ml-log-inspector ("Something needs fixing") |
| Models + monitors + experiments | "Your ML stack looks healthy! What would you like to do?" |

---

## Intent Detection

| User Language | Route To | Skill Path |
|---|---|---|
| "feature store", "feature view", "entities", "point-in-time" | **ml-feature-store** | `skills/ml-feature-store/SKILL.md` |
| "train", "training pipeline", "notebook", "container runtime", "snowpark ml" | **ml-pipeline-build** | `skills/ml-pipeline-build/SKILL.md` |
| "experiment", "track runs", "hyperparameter", "compare runs", "log metrics" | **ml-experiments** | `skills/ml-experiments/SKILL.md` |
| "register model", "log model", "model registry", "model version" | **ml-registry** | `skills/ml-registry/SKILL.md` |
| "deploy", "inference", "SPCS", "REST endpoint", "warehouse scoring", "batch predict" | **ml-deploy** | `skills/ml-deploy/SKILL.md` |
| "drift", "performance degradation", "model monitor", "PSI", "observability" | **ml-observability** | `skills/ml-observability/SKILL.md` |
| "broke", "suspended", "failed", "error", "debug", "diagnose", "pipeline failure" | **ml-log-inspector** | `skills/ml-log-inspector/SKILL.md` |
| "promote", "rollback", "production", "alias", "deprecate", "governance" | **ml-lifecycle** | `skills/ml-lifecycle/SKILL.md` |
| "forecast", "anomaly detection", "classification SQL", "AutoML", "ML functions" | **ml-functions** | `skills/ml-functions/SKILL.md` |
| "watch", "retrain", "schedule", "freshness", "auto-refresh", "trigger" | **ml-watch** | `skills/ml-watch/SKILL.md` |

---

## Lifecycle Flow

```
ml-feature-store ──────────────────────────────────────────────┐
  │ entities + feature views                                    │
  ▼                                                            │
ml-pipeline-build ◄── ml-functions (SQL AutoML shortcut)       │
  │ Snowpark ML / Container Runtime                            │
  ▼                                                            │
ml-experiments                                                  │
  │ track runs, compare metrics                                │
  ▼                                                            │
ml-registry                                                     │
  │ log model, version metadata                               │
  ▼                                                            │
ml-deploy                                                       │
  │ warehouse / SPCS / REST                                   │
  ▼                                                            │
ml-observability ◄── ml-log-inspector                          │
  │ drift + perf monitoring     │ diagnose failures            │
  ▼                             │                             │
ml-lifecycle ──────────────────────────                        │
  │ promote/rollback/deprecate                                │
  ▼                                                            │
ml-watch ◄─────────────────────────────────────────────────────┘
  │ ongoing drift alerts + auto-retrain triggers
```

---

## Stateful Persistence

No custom schema is created. The toolkit reads from existing Snowflake infrastructure:

| Need | Source |
|---|---|
| Model drift / perf | `MODEL_MONITOR_DRIFT_METRIC`, `MODEL_MONITOR_PERFORMANCE_METRIC` table functions |
| Experiment runs | `SHOW EXPERIMENTS` + ExperimentTracking API |
| Pipeline failures | `ACCOUNT_USAGE.TASK_HISTORY` |
| Python logs | Account event table (`SHOW PARAMETERS LIKE 'EVENT_TABLE' IN ACCOUNT`) |
| Feature freshness | `INFORMATION_SCHEMA.DYNAMIC_TABLES` |
| Data quality | `SNOWFLAKE.LOCAL.DATA_QUALITY_MONITORING_LOGS` |

---

## Relationship to Other Plugins

| Plugin | Relationship |
|---|---|
| `semantic-view-toolkit` | Upstream: SVs can expose feature tables consumed by ml-feature-store |
| `cortex-agent-toolkit` | Downstream: deployed model endpoints can be tools in Cortex Agents |
| `ops-monitor/self-healing-pipeline` | Complementary: general pipeline healing; ml-log-inspector is ML-specific |

---

## Quick Start

```
$ml-pipeline-toolkit
"I need to predict customer churn — I have a training table ANALYTICS.PUBLIC.CUSTOMER_EVENTS"
```
→ Routes to ml-feature-store then ml-pipeline-build.

```
$ml-pipeline-toolkit
"My model monitor is suspended and I don't know why"
```
→ Routes to ml-log-inspector with immediate DESC MODEL MONITOR.

```
$ml-pipeline-toolkit
"Promote model version v3 to production"
```
→ Routes to ml-lifecycle, shows alias reassignment pattern.

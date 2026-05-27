# ml-pipeline-toolkit

Full lifecycle toolkit for Snowflake ML — from feature engineering through training, experiment tracking, model registration, deployment, observability, and governance.

## What it does

A single entry-point plugin that routes to 10 specialized sub-skills covering every phase of the ML lifecycle on Snowflake. Tell it where you are in your ML journey and it routes to the right skill.

## Lifecycle flow

```
ml-feature-store → ml-pipeline-build → ml-experiments → ml-registry
                                                              ↓
ml-functions (SQL AutoML shortcut)              ml-deploy
                                                              ↓
                                               ml-observability ← ml-log-inspector
                                                              ↓
                                               ml-lifecycle
                                                              ↓
                                               ml-watch
```

## Skills

| Skill | Phase | Description |
|-------|-------|-------------|
| ml-feature-store | Build | Define entities, feature views (Dynamic Table-backed), point-in-time retrieval |
| ml-pipeline-build | Build | Scaffold training pipelines (Snowpark ML, Container Runtime, stored procs) |
| ml-experiments | Build | Track experiments, log runs, compare metrics (Snowflake-native, NOT MLflow) |
| ml-registry | Build | Register models, manage versions, metadata, RBAC |
| ml-deploy | Ops | Deploy to warehouse inference, SPCS service, or REST endpoint |
| ml-observability | Ops | Create model monitors, query drift/performance/stat metrics |
| ml-log-inspector | Ops | Diagnose ML pipeline and monitor failures (5-surface triage) |
| ml-lifecycle | Ops | Promote via aliases, rollback, deprecate, govern model versions |
| ml-functions | Build | AutoML in SQL: FORECAST, ANOMALY_DETECTION, CLASSIFICATION, TOP_INSIGHTS |
| ml-watch | Ops | Scheduled retraining, data freshness SLAs, drift alert tasks |

## Prerequisites

See [PREREQUISITES.md](PREREQUISITES.md) for full RBAC grants and package requirements.

**Minimum:** `snowflake-ml-python >= 1.25.0`, `snowflake-snowpark-python`

## Quick start

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

```
$ml-pipeline-toolkit
"Set up daily anomaly detection on my revenue stream — no Python"
```
→ Routes to ml-functions, scaffolds SNOWFLAKE.ML.ANOMALY_DETECTION in SQL.

## Relationship to other plugins

| Plugin | Relationship |
|--------|-------------|
| `semantic-view-toolkit` | Upstream: semantic views can expose feature tables consumed by ml-feature-store |
| `cortex-agent-toolkit` | Downstream: deployed model endpoints can be tools in Cortex Agents |
| `ops-monitor/self-healing-pipeline` | Complementary: general pipeline healing; ml-log-inspector is ML-specific |

## References

- [snowflake-ml-api.md](references/snowflake-ml-api.md) — FeatureStore, ExperimentTracking, Registry, ModelMonitor API signatures
- [feature-store-patterns.md](references/feature-store-patterns.md) — Entity/FeatureView patterns, immutability gotchas, PIT retrieval
- [drift-detection.md](references/drift-detection.md) — MODEL_MONITOR_*_METRIC function SQL patterns
- [model-lifecycle.md](references/model-lifecycle.md) — Alias-based promotion, cross-env copy, version limits
- [log-triage.md](references/log-triage.md) — 5-step ML pipeline failure triage

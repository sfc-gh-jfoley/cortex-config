This plugin provides the full Snowflake ML pipeline lifecycle toolkit with 10 skills:

- **ml-feature-store** — Define entities, feature views (Dynamic Table-backed), and point-in-time retrieval
- **ml-pipeline-build** — Scaffold training pipelines (Snowpark ML, Container Runtime notebooks, stored procs)
- **ml-experiments** — Track experiments, log runs, compare metrics (Snowflake-native ExperimentTracking)
- **ml-registry** — Register models, manage versions, metadata, and RBAC
- **ml-deploy** — Deploy to warehouse inference, SPCS service, or REST endpoint
- **ml-observability** — Create model monitors, query drift/performance/stat metrics
- **ml-log-inspector** — Diagnose pipeline and model monitor failures across 5 system surfaces
- **ml-lifecycle** — Promote versions via aliases, rollback, deprecate, govern models
- **ml-functions** — AutoML in SQL: FORECAST, ANOMALY_DETECTION, CLASSIFICATION, TOP_INSIGHTS
- **ml-watch** — Scheduled retraining triggers, data freshness SLAs, drift alert tasks

To enable: `cortex plugin enable ml-pipeline-toolkit`

Start with: `$ml-pipeline-toolkit` and describe where you are in your ML journey.

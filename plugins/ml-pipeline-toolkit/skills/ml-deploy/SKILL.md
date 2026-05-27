---
name: ml-deploy
description: "Deploy Snowflake Model Registry models for inference. Use when: running batch or online inference from warehouse, deploying a model as a REST API endpoint, deploying to Snowpark Container Services (SPCS) for low-latency serving."
---

## ml-deploy

Deploy registered Snowflake models for batch warehouse inference, SPCS online serving, or external REST API access.

---

### Deployment Target Selection

| Target | Latency | Cost | Best For |
|---|---|---|---|
| Warehouse inference | Seconds–minutes | Credits | Batch scoring, analytics |
| SPCS service | Milliseconds | Compute pool | Online / real-time inference |
| REST endpoint | Milliseconds | Compute pool | External app integration |

> **NOTE:** SPCS and REST endpoint use the **same `create_service()` call** — `ingress_enabled=True` exposes the REST endpoint.

---

### Phase 1: Warehouse Inference (Simplest Path)

```python
from snowflake.ml.registry import Registry
from snowflake.snowpark.context import get_active_session

session = get_active_session()
reg = Registry(session, database_name="<DB>", schema_name="<SCHEMA>")

# Get by version or alias:
mv = reg.get_model("<MODEL_NAME>").version("<VERSION>")
# mv = reg.get_model("<MODEL_NAME>").alias("PROD")  # preferred for production

scored_df = mv.run(test_df, function_name="predict")

# Detect output column dynamically (avoids hardcoding generated column names)
output_col = [c for c in scored_df.columns if c not in test_df.columns][0]
scored_df = scored_df.with_column_renamed(output_col, "PREDICTION")
```

---

### Phase 2: SPCS Deployment (Online Inference)

**Prerequisites:**
- Compute pool available (can use system pools: `SYSTEM_COMPUTE_POOL_CPU` / `SYSTEM_COMPUTE_POOL_GPU`)
- Role has `USAGE` or `OWNERSHIP` on compute pool
- `snowflake-ml-python >= 1.25.0`
- GA feature (not available in government regions)

```python
# SPCS-only (no external access):
mv.create_service(
    service_name="<SERVICE_NAME>",
    service_compute_pool="<COMPUTE_POOL>",       # or SYSTEM_COMPUTE_POOL_CPU
    image_build_compute_pool="<BUILD_POOL>",     # optional: cheaper pool for image build step only
    gpu_requests="1",                            # omit for CPU deployment
    num_workers=1,
)
```

---

### Phase 3: REST Endpoint Deployment

**Additional prerequisite:** Role has `BIND SERVICE ENDPOINT ON ACCOUNT`

```python
# REST endpoint (external access enabled):
mv.create_service(
    service_name="<SERVICE_NAME>",
    service_compute_pool="SYSTEM_COMPUTE_POOL_CPU",
    ingress_enabled=True,  # exposes public REST endpoint
)
# Endpoint URL pattern: <unique-id>-<account-id>.snowflakecomputing.app/<method-name>
# NOTE: underscores in method names become dashes (predict_prob → /predict-prob)
# Port: 5000, endpoint name: 'inference' — hardcoded
```

**Run inference via SPCS service:**
```python
scored_df = mv.run(df, function_name="predict", service_name="<SERVICE_NAME>")
```

---

### Phase 4: Verify Deployment

```python
# Check service status
print(mv.list_services())

# Run a test inference row
test_sample = test_df.limit(1)
result = mv.run(test_sample, function_name="predict", service_name="<SERVICE_NAME>")
print(result.to_pandas())
```

```sql
-- Check service status via SQL
SHOW SERVICES LIKE '<SERVICE_NAME>' IN SCHEMA <DB>.<SCHEMA>;
DESCRIBE SERVICE <DB>.<SCHEMA>.<SERVICE_NAME>;
```

---

### Critical Warnings

| Warning | Detail |
|---|---|
| Cold start time | ~10 min (CPU), ~20 min (GPU) — set user expectations |
| SPCS package source | Uses conda-forge (NOT Snowflake conda channel — different versions) |
| Snowpark ML Pipeline / modeling classes | Cannot deploy to GPU SPCS — extract native model first |
| Table functions | Not supported in SPCS serving |
| Image management | No Dockerfile required — Snowflake builds container automatically |
| Traffic splitting | Canary/shadow deployments available via Snowsight UI |

---

### Success Criteria

- [ ] `mv.run()` returns predictions (warehouse path)
- [ ] `mv.list_services()` shows RUNNING status (SPCS path)
- [ ] Test inference via service returns valid output
- [ ] REST endpoint URL verified (if `ingress_enabled=True`)

---
name: ml-experiments
description: "Track ML experiments, log hyperparameters and metrics, compare runs. Use when: running hyperparameter search, comparing model variants, logging training runs for reproducibility. NOTE: This uses Snowflake's native ExperimentTracking API — NOT MLflow."
---

## ml-experiments

Track ML training runs, log metrics and hyperparameters, and compare experiments using Snowflake's native `ExperimentTracking` API.

---

> **⚠️ CRITICAL WARNING:**
> **This is NOT MLflow.** `mlflow.*` imports will fail. Use `snowflake.ml.experiment.ExperimentTracking`.
> Requires `snowflake-ml-python >= 1.19.0`.
> `ExperimentTracking` is a **singleton** — not thread-safe; only one active run at a time.

---

### Phase 1: Prerequisites Check

```sql
-- Verify privilege exists
SHOW GRANTS TO ROLE <role>;
-- Must see: CREATE EXPERIMENT ON SCHEMA <db>.<schema>
```

```bash
# Verify package version (requires >= 1.19)
pip show snowflake-ml-python | grep Version
```

---

### Phase 2: Create/Resume Experiment

```python
from snowflake.ml.experiment import ExperimentTracking
from snowflake.snowpark.context import get_active_session

session = get_active_session()
exp = ExperimentTracking(session=session)
exp.set_experiment("<EXPERIMENT_NAME>")  # creates if not exists
# Requires: CREATE EXPERIMENT ON SCHEMA privilege
```

---

### Phase 3: Log a Training Run

```python
with exp.start_run("<RUN_NAME>"):
    # Log hyperparameters (must be strings)
    exp.log_param("learning_rate", "0.01")
    exp.log_params({"n_estimators": "100", "max_depth": "5"})

    # --- train your model here ---
    model.fit(X_train, y_train)
    y_pred = model.predict(X_test)

    # Log metrics (must be floats)
    exp.log_metric("accuracy", float(accuracy_score(y_test, y_pred)))
    exp.log_metric("f1_score", float(f1_score(y_test, y_pred, average="weighted")))
    exp.log_metric("loss", 0.234, step=100)  # step= for per-epoch logging

    # Log the model artifact
    exp.log_model(model, model_name="<MODEL_NAME>", sample_input_data=X_train[:10])

    # Log file artifacts (charts, configs, etc.)
    exp.log_artifact("/tmp/feature_importance.png", artifact_path="plots")
# Completed runs are IMMUTABLE — cannot be edited after context manager exits
```

---

### Phase 4: Compare Runs

```python
# Returns a Snowpark DataFrame — call .to_pandas() for local use
runs_df = exp.list_metrics().to_pandas()
params_df = exp.list_params().to_pandas()
print(runs_df.sort_values("accuracy", ascending=False))
```

```sql
-- Via SQL
SHOW EXPERIMENTS IN SCHEMA <DATABASE>.<SCHEMA>;
```

> **NOTE:** Snowsight UI run comparison is capped at **5 runs** per comparison view.

---

### Phase 5: Autologging (XGBoost / LightGBM / Keras only)

```python
import xgboost as xgb

# XGBoost autologging via callback — no explicit log_metric calls needed
callbacks = [exp.get_xgboost_callback()]
model = xgb.XGBClassifier(n_estimators=100)
model.fit(X_train, y_train, callbacks=callbacks)
```

> **Autologging is supported for:** XGBoost, LightGBM, Keras
> **NOT supported:** sklearn, PyTorch (log manually)

---

### Limitations Reference

| Limitation | Detail |
|---|---|
| Not MLflow | `mlflow.*` will not work |
| Singleton | Not thread-safe; one active run at a time |
| Completed runs | Immutable — cannot be edited after context manager exits |
| UI comparison | Capped at 5 runs in Snowsight |
| Autologging | XGBoost, LightGBM, Keras only |
| Live stdout | Only in Snowflake Notebooks / SPCS ML Jobs |
| DDL | `CREATE/SHOW/ALTER/DROP EXPERIMENT` — experiments are first-class Snowflake objects |

---

### Success Criteria

- [ ] Experiment created (visible in `SHOW EXPERIMENTS IN SCHEMA`)
- [ ] At least one run logged with params and metrics
- [ ] `exp.list_metrics()` returns run data
- [ ] Model artifact logged (visible in Model Registry if `log_model` was called)

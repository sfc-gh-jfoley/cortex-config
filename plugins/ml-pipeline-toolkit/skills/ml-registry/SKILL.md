---
name: ml-registry
description: "Register trained models in Snowflake Model Registry, manage versions, metadata, and access control. Use when: logging a trained model, managing model versions, tagging and documenting models, setting up RBAC on models."
---

## ml-registry

Register, version, and govern trained ML models using the Snowflake Model Registry.

---

### Phase 1: Register a Model

```python
from snowflake.ml.registry import Registry
from snowflake.snowpark.context import get_active_session

session = get_active_session()
reg = Registry(
    session=session,
    database_name="<DATABASE>",
    schema_name="<SCHEMA>",
)

model_version = reg.log_model(
    model,                              # trained model object (XGBoost, sklearn, PyTorch, etc.)
    model_name="<MODEL_NAME>",
    # version_name intentionally omitted — Snowflake auto-generates, avoids conflicts on re-run
    sample_input_data=X_train[:10],     # used for signature inference (feature names + types)
    target_platforms=["WAREHOUSE"],     # WAREHOUSE | SNOWPARK_CONTAINER_SERVICES
    metrics={
        "accuracy": float(accuracy),
        "f1_score": float(f1),
    },
    comment="<description of training run>",
)
print(f"Registered: {model_version.model_name} version {model_version.version_name}")
```

> ⚠️ **WARN:** Model version **implementations are IMMUTABLE** once logged. Only `comment` and aliases can be changed post-registration.
> ⚠️ **WARN:** Explicit `version_name` causes failures on re-run. Omit it and let Snowflake auto-generate.

---

### Phase 2: Inspect Registered Model

```sql
-- List all models in schema
SHOW MODELS IN SCHEMA <database>.<schema>;

-- List all versions of a model
SHOW VERSIONS IN MODEL <database>.<schema>.<model_name>;

-- Full metadata including methods and signatures
DESCRIBE MODEL <database>.<schema>.<model_name>;
```

---

### Phase 3: Run Inference (Warehouse)

```python
# By version name:
mv = reg.get_model("<MODEL_NAME>").version("<VERSION>")

# Or by alias (preferred for production code — alias can be reassigned for zero-downtime rollback):
mv = reg.get_model("<MODEL_NAME>").default
# mv = reg.get_model("<MODEL_NAME>").alias("PROD")

scored_df = mv.run(test_df, function_name="predict")
# Detect output column dynamically:
output_col = [c for c in scored_df.columns if c not in test_df.columns][0]
scored_df = scored_df.with_column_renamed(output_col, "PREDICTION")
```

---

### Phase 4: Set Model Metadata + Aliases

```python
# Set a custom metric after registration
mv.set_metric("auc", 0.91)

# Assign a named alias (for rollback-safe promotion)
mv.set_alias("STAGING")

# Update description
mv.comment = "Trained on 2026-05 data; features v3"
```

```sql
-- Reassign PROD alias (zero-downtime promotion)
ALTER MODEL <database>.<schema>.<model_name> VERSION '<v2>' SET ALIAS = 'PROD';
```

> **NOTE:** System aliases `DEFAULT`, `FIRST`, and `LAST` are non-removable built-ins.

---

### Phase 5: RBAC Grants

```sql
-- Grant consumer role read access
GRANT USAGE ON MODEL <database>.<schema>.<model_name> TO ROLE <consumer_role>;
GRANT READ ON MODEL <database>.<schema>.<model_name> TO ROLE <consumer_role>;
-- READ grants: view metadata + run inference
-- WRITE grants: add metrics, aliases, comments
```

---

### Registry Limits

| Limit | Value |
|---|---|
| Versions per model | 1,000 |
| Methods per version | 10 |
| Arguments per method | 500 |
| Metadata size | 100 KB |
| Storage (warehouse) | 15 GB |

---

### Success Criteria

- [ ] `SHOW VERSIONS IN MODEL` shows new version
- [ ] `DESCRIBE MODEL` shows correct function signatures
- [ ] `mv.run()` returns predictions without error
- [ ] Aliases set for production access pattern
- [ ] Consumer roles granted appropriate access

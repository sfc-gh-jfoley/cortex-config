# Snowflake ML API Reference

Quick constructor and method signatures for `snowflake-ml-python`.

---

## FeatureStore

```python
from snowflake.ml.feature_store import FeatureStore, Entity, CreationMode, FeatureView

FeatureStore(
    session,
    database,
    name,                        # schema name — will be created
    default_warehouse,
    *,
    creation_mode=CreationMode.FAIL_IF_NOT_EXIST,
    default_iceberg_external_volume=None,
)

Entity(
    name,
    join_keys,                   # list[str] — IMMUTABLE after creation
    desc="",
)

fs.register_entity(entity)
fs.list_entities()               # returns Snowpark DataFrame

fs.register_feature_view(
    feature_view,
    version,                     # str e.g. "v1"
    refresh_freq=None,           # str e.g. "1 hour"; None = view-backed
    warehouse=None,
)
fs.list_feature_views()          # returns Snowpark DataFrame

dataset = fs.generate_dataset(
    name,
    spine_df,
    features,                    # list[FeatureView]
    spine_timestamp_col=None,    # required for PIT ASOF JOIN
    spine_label_cols=None,
)
# dataset.to_pandas() or dataset.to_snowpark_dataframe()
```

---

## ExperimentTracking (NOT MLflow)

```python
from snowflake.ml.experiment import ExperimentTracking

exp = ExperimentTracking(session=session)  # singleton
exp.set_experiment("name")                 # creates if not exists; needs CREATE EXPERIMENT

with exp.start_run("run_name"):
    exp.log_param("key", "value")          # value must be str
    exp.log_params({"k": "v"})
    exp.log_metric("key", 0.95)            # value must be float
    exp.log_metric("key", 0.95, step=10)
    exp.log_model(model, model_name="m", sample_input_data=X[:10])
    exp.log_artifact("/tmp/file.txt", artifact_path="subdir")

exp.list_metrics()   # Snowpark DataFrame
exp.list_params()    # Snowpark DataFrame

# XGBoost autologging:
model.fit(X, y, callbacks=[exp.get_xgboost_callback()])
```

---

## Registry

```python
from snowflake.ml.registry import Registry

reg = Registry(session, database_name, schema_name)

mv = reg.log_model(
    model,
    model_name,
    version_name=None,           # OMIT — auto-generate to avoid conflicts
    sample_input_data=None,      # for signature inference
    target_platforms=["WAREHOUSE"],  # WAREHOUSE | SNOWPARK_CONTAINER_SERVICES
    metrics=None,                # dict[str, float]
    comment=None,
)

mv = reg.get_model("name").version("v1")
mv = reg.get_model("name").default
mv = reg.get_model("name").alias("PROD")

scored = mv.run(df, function_name="predict")

mv.set_metric("key", value)
mv.set_alias("STAGING")
mv.comment = "description"

mv.create_service(
    service_name,
    service_compute_pool,
    image_build_compute_pool=None,
    gpu_requests=None,
    num_workers=1,
    ingress_enabled=False,       # True = REST endpoint
)
mv.list_services()
```

---

## ModelMonitor (SQL DDL)

```sql
CREATE MODEL MONITOR <name> WITH
    MODEL              = <db>.<schema>.<model_name>
    VERSION            = '<version>'
    FUNCTION           = 'predict'
    SOURCE             = <db>.<schema>.<inference_log_table>
    WAREHOUSE          = <warehouse>
    REFRESH_INTERVAL   = '1 hour'    -- min 60 seconds
    AGGREGATION_WINDOW = '1 day'     -- days only
    TIMESTAMP_COLUMN   = <ts_col>
    [BASELINE          = <db>.<schema>.<snapshot>]
    [ID_COLUMNS                  = ('<col>')]
    [PREDICTION_CLASS_COLUMNS    = ('<col>')]
    [PREDICTION_SCORE_COLUMNS    = ('<col>')]
    [ACTUAL_CLASS_COLUMNS        = ('<col>')]
    [SEGMENT_COLUMNS             = ('<col1>', '<col2>')];  -- max 5, STRING, <25 unique vals

SHOW MODEL MONITORS IN DATABASE <db>;
DESC MODEL MONITOR <name>;      -- has aggregation_status, aggregation_last_error
ALTER MODEL MONITOR <name> RESUME;
DROP MODEL MONITOR <name>;
```

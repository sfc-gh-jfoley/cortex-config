---
name: ml-feature-store
description: "Define and manage Snowflake Feature Store entities, feature views, and point-in-time retrieval. Use when: creating feature tables, defining entities for ML training, setting up Dynamic Table-backed feature views, generating training datasets with point-in-time correctness."
---

## ml-feature-store

Create and manage a Snowflake Feature Store: entities, feature views, and point-in-time training datasets.

---

### Phase 1: Scope

Confirm with the user:
- Target **database + schema** for the feature store (FeatureStore will create the schema)
- **Entity name** and **join key(s)** (e.g., `customer_id`)
- **Source table** for computing features

---

### Phase 2: Create FeatureStore + Entity

```python
from snowflake.ml.feature_store import FeatureStore, Entity, CreationMode
from snowflake.snowpark.context import get_active_session

session = get_active_session()
fs = FeatureStore(
    session=session,
    database="<DATABASE>",
    name="<FEATURE_STORE_SCHEMA>",  # creates this schema if it doesn't exist
    default_warehouse="<WAREHOUSE>",
    creation_mode=CreationMode.CREATE_IF_NOT_EXIST,
)
entity = Entity(name="<ENTITY_NAME>", join_keys=["<ID_COL>"], desc="<description>")
fs.register_entity(entity)
```

> ⚠️ **WARN:** Entity `join_keys` are **IMMUTABLE** after creation. Entities referenced by FeatureViews cannot be deleted.
> ⚠️ **WARN:** Entities are backed by Snowflake tags — account limit: 10,000 tags, 50 tags per object.

---

### Phase 3: Define FeatureView

**Variant A — Dynamic Table-backed (auto-refreshes):**

```python
from snowflake.ml.feature_store import FeatureView
from snowflake.snowpark import functions as F

feature_df = session.table("<DATABASE>.<SCHEMA>.<SOURCE_TABLE>").select(
    F.col("<ID_COL>"),
    F.col("<EVENT_TS_COL>"),
    # ... feature columns ...
)
fv = FeatureView(
    name="<FV_NAME>",
    entities=[entity],
    feature_df=feature_df,
    timestamp_col="<EVENT_TS_COL>",  # required for point-in-time retrieval
    refresh_freq="1 hour",            # min: 1 minute; set for DT-backed
    desc="<description>",
)
fv = fs.register_feature_view(feature_view=fv, version="v1", warehouse="<WAREHOUSE>")
```

**Variant B — View-backed (user manages source):**

Same as Variant A, but omit `refresh_freq`.

> ⚠️ **WARN:** The pipeline (`feature_df` definition) is **IMMUTABLE** after `register_feature_view()`. Only `refresh_freq`, `warehouse`, and `desc` can be updated. To change features: register a new version.
> ⚠️ **WARN:** Incremental DT refresh requires OWNERSHIP on source table. If permission error occurs, add `refresh_mode="FULL"` to the `FeatureView` constructor.

---

### Phase 4: Generate Training Dataset (Point-in-Time)

```python
spine_df = session.table("<DATABASE>.<SCHEMA>.<LABELS_TABLE>")
dataset = fs.generate_dataset(
    name="<DATASET_NAME>",
    spine_df=spine_df,
    features=[fv],
    spine_timestamp_col="<EVENT_TS_COL>",  # enables PIT-correct ASOF JOIN
    spine_label_cols=["<LABEL_COL>"],
)
pandas_df = dataset.to_pandas()
```

> ⚠️ **WARN:** PIT retrieval requires `timestamp_col` on **BOTH** the spine **AND** the feature view. Omitting either disables the ASOF JOIN and you will get non-PIT-correct data.
> **NOTE:** Online (low-latency) reads require `fs.create_online_service()` — a separate provisioning step not covered here.

---

### Phase 5: Verify

```python
# List all registered feature views
print(fs.list_feature_views().to_pandas())

# List all registered entities
print(fs.list_entities().to_pandas())
```

```sql
-- Confirm backing DT/view exists
SHOW DYNAMIC TABLES IN SCHEMA <DATABASE>.<FEATURE_STORE_SCHEMA>;
SHOW VIEWS IN SCHEMA <DATABASE>.<FEATURE_STORE_SCHEMA>;
```

---

### Optional: Iceberg-backed Feature Views

Pass `default_iceberg_external_volume="<VOLUME_NAME>"` to the `FeatureStore` constructor to store feature view data on external Iceberg tables.

---

### Success Criteria

- [ ] FeatureStore schema created in target database
- [ ] Entity registered (`fs.list_entities()` shows it; `SHOW TAGS` confirms backing tag)
- [ ] FeatureView registered (`SHOW DYNAMIC TABLES` or `SHOW VIEWS` confirms backing object)
- [ ] `generate_dataset()` returns a training-ready DataFrame with correct row count

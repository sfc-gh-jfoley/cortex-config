# Feature Store Patterns

Key patterns, limits, and gotchas for the Snowflake Feature Store.

---

## Entity Tag Limits

Entities are backed by Snowflake **tag objects**. Tag limits apply:
- **10,000 tags per account** (shared with all other tag usage)
- **50 tags per object** (applies to the join key columns)

> ⚠️ Warn users in large accounts with heavy tag usage that entity registration may fail with `TAG_LIMIT_EXCEEDED`.

---

## FeatureView Variants

| Variant | `refresh_freq` | Backing Object | Use Case |
|---------|---------------|----------------|----------|
| Dynamic Table-backed | Set (e.g. `"1 hour"`) | `DYNAMIC TABLE` | Auto-refreshing features from live source |
| View-backed | `None` (omit) | `VIEW` | User-managed source; no automatic refresh |

---

## Immutability Warning

The **pipeline** (`feature_df` definition) is **IMMUTABLE** after `register_feature_view()`. You cannot change which columns are computed or how.

Only these can be updated post-registration:
- `refresh_freq`
- `warehouse`
- `desc`

To change the feature computation logic: register a **new version** (`version="v2"`).

---

## Point-in-Time (PIT) Retrieval via ASOF JOIN

PIT retrieval requires `timestamp_col` on **both** the spine **and** the feature view:

```python
# Feature view MUST have timestamp_col set:
fv = FeatureView(
    name="my_fv",
    entities=[entity],
    feature_df=feature_df,
    timestamp_col="event_ts",   # REQUIRED for PIT
    refresh_freq="1 hour",
)

# generate_dataset MUST specify spine_timestamp_col:
dataset = fs.generate_dataset(
    name="training_ds",
    spine_df=spine_df,
    features=[fv],
    spine_timestamp_col="event_ts",  # REQUIRED for ASOF JOIN
    spine_label_cols=["label"],
)
```

Omitting either disables the ASOF JOIN and produces **non-PIT-correct** (leaky) data.

---

## Incremental DT Refresh — Permission Issue

Incremental DT refresh requires **OWNERSHIP** on the source table.

If you see a refresh permission error:
```python
# Add refresh_mode="FULL" to the FeatureView constructor:
fv = FeatureView(
    name="my_fv",
    entities=[entity],
    feature_df=feature_df,
    timestamp_col="event_ts",
    refresh_freq="1 hour",
    refresh_mode="FULL",   # full refresh when incremental permission not available
)
```

---

## Online Serving

The Feature Store SDK's `generate_dataset()` is for **offline** (batch) training data retrieval.

For **online (low-latency)** feature reads, a separate provisioning step is required:
```python
# Not covered in ml-feature-store skill by default — raise to user:
fs.create_online_service(...)  # separate online store provisioning
```

---

## Iceberg-Backed Feature Views

```python
fs = FeatureStore(
    session=session,
    database="<DB>",
    name="<SCHEMA>",
    default_warehouse="<WH>",
    default_iceberg_external_volume="<VOLUME_NAME>",  # enables Iceberg storage
    creation_mode=CreationMode.CREATE_IF_NOT_EXIST,
)
```

---

## FeatureViewSlice (Subset of Features)

```python
# Use a subset of features from a FeatureView:
fv_slice = fv.slice(["feature_col_1", "feature_col_2"])
dataset = fs.generate_dataset(name="ds", spine_df=spine_df, features=[fv_slice], ...)
```

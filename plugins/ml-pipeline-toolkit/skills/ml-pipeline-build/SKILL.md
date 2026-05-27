---
name: ml-pipeline-build
description: "Scaffold ML training pipelines on Snowflake. Use when: training models in Snowflake Notebooks with Container Runtime, building Snowpark ML Pipelines, wrapping training in stored procedures, choosing between warehouse and SPCS compute."
---

## ml-pipeline-build

Scaffold and execute ML training pipelines on Snowflake — from data loading to model training and evaluation.

---

### Compute Decision Table

| Model/Task | Data Size | Recommendation |
|---|---|---|
| XGBoost, LightGBM | < 1M rows | CPU |
| XGBoost, LightGBM | > 10M rows | GPU |
| sklearn, Logistic Regression | Any | CPU |
| Neural Networks (PyTorch, TF) | Any | GPU |
| Feature engineering | Any | CPU |

---

### Phase 1: Gather Requirements

Confirm with the user:
- Database, schema, source table
- Target column (what to predict)
- Model type: classification or regression
- Compute preference: CPU or GPU

---

## Path A: Container Runtime Notebook (Recommended for XGBoost/sklearn/PyTorch)

### Phase 2: Generate Notebook Cells

**Cell 1 — Imports:**
```python
from snowflake.snowpark.context import get_active_session
from snowflake.ml.utils.connection_params import SnowflakeLoginOptions
from snowflake.ml.registry import Registry
from snowflake.connector.pandas_tools import pd_writer
import xgboost as xgb
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score
```

**Cell 2 — Set context:**
```python
session = get_active_session()
session.use_database("<DATABASE>")
session.use_schema("<SCHEMA>")
session.use_warehouse("<WAREHOUSE>")
```

**Cell 3 — Load data:**
```python
# DataConnector is the preferred way to move data from Snowpark to Pandas
from snowflake.ml.data import DataConnector

df = session.table("<DATABASE>.<SCHEMA>.<SOURCE_TABLE>")
# Use DataConnector for optimized conversion to pandas (avoids memory spills)
pandas_df = DataConnector.from_dataframe(df).to_pandas()
print(f"Loaded {len(pandas_df)} rows")
```

**Cell 4 — Feature engineering:**
```python
# NOTE: use F.sql_expr() for string comparisons to avoid SQL quoting issues
from snowflake.snowpark import functions as F

feature_cols = [c for c in pandas_df.columns if c != "<LABEL_COL>"]
X = pandas_df[feature_cols]
y = pandas_df["<LABEL_COL>"]
```

**Cell 5 — Train/test split:**
```python
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42
)
```

**Cell 6 — Train model:**
```python
model = xgb.XGBClassifier(
    n_estimators=100,
    max_depth=5,
    learning_rate=0.1,
    use_label_encoder=False,
    eval_metric="logloss",
)
model.fit(X_train, y_train)
```

**Cell 7 — Evaluate:**
```python
y_pred = model.predict(X_test)
accuracy  = accuracy_score(y_test, y_pred)
precision = precision_score(y_test, y_pred, average="weighted")
recall    = recall_score(y_test, y_pred, average="weighted")
f1        = f1_score(y_test, y_pred, average="weighted")

print(f"Accuracy:  {accuracy:.4f}")
print(f"Precision: {precision:.4f}")
print(f"Recall:    {recall:.4f}")
print(f"F1 Score:  {f1:.4f}")
```

> ⚠️ **STOP:** Review metrics before registering. If accuracy/F1 is below acceptable threshold, iterate on features or hyperparameters before proceeding.

**Cell 8 — Register model (see ml-registry skill for details):**
```python
reg = Registry(session=session, database_name="<DATABASE>", schema_name="<SCHEMA>")
mv = reg.log_model(
    model,
    model_name="<MODEL_NAME>",
    # omit version_name — let Snowflake auto-generate to avoid conflicts
    sample_input_data=X_train[:10],
    metrics={"accuracy": float(accuracy), "f1": float(f1)},
    comment="Trained on <SOURCE_TABLE> data",
)
print(f"Registered: {mv.model_name} version {mv.version_name}")
```

---

## Path B: Snowpark ML Pipeline (Warehouse-based, reproducible preprocessing)

```python
from snowflake.ml.modeling.pipeline import Pipeline
from snowflake.ml.modeling.preprocessing import StandardScaler, OneHotEncoder
from snowflake.ml.modeling.xgboost import XGBClassifier

cat_cols = ["<cat_col1>", "<cat_col2>"]
num_cols = ["<num_col1>", "<num_col2>"]
feature_cols = [f"{c}_enc" for c in cat_cols] + [f"{c}_scaled" for c in num_cols]

pipeline = Pipeline([
    ("encoder", OneHotEncoder(
        input_cols=cat_cols,
        output_cols=[f"{c}_enc" for c in cat_cols]
    )),
    ("scaler", StandardScaler(
        input_cols=num_cols,
        output_cols=[f"{c}_scaled" for c in num_cols]
    )),
    ("model", XGBClassifier(
        input_cols=feature_cols,
        label_cols=["LABEL"],
        output_cols=["PRED"]
    )),
])
pipeline.fit(train_df)
predictions = pipeline.predict(test_df)
```

> **NOTE:** Snowpark ML Pipeline / `snowflake.ml.modeling.*` class models **cannot** be deployed to GPU SPCS. Extract the native model object first if SPCS GPU serving is needed.

---

### Anti-Patterns

| Anti-Pattern | Problem | Fix |
|---|---|---|
| `snowflake.ml.modeling.ensemble.*` | Old API; stored proc permission errors | Use OSS XGBoost/sklearn directly |
| `session.call()` with ML functions | Incompatible with ML function models | Use `session.sql()` |
| `F.col("COL") == "value"` | SQL quoting error | `F.sql_expr("COL = 'value'")` |
| `df.to_pandas()` for large data | Not optimized; memory spill | `DataConnector.from_dataframe(df).to_pandas()` |
| `version_name="v1"` in `log_model` | Conflicts on re-run | Omit; let Snowflake auto-generate |

---

### Success Criteria

- [ ] Data loads without error from source table
- [ ] Model trains and metrics are evaluated
- [ ] Metrics reviewed before registration
- [ ] Model registered in Model Registry (proceed to ml-registry for management)

---
name: iot-pipeline-builder-phase2
description: Create NORMALIZED schema and Dynamic Tables that flatten VARIANT columns to typed columns
---

# Phase 2: Normalize via Dynamic Tables

## Step 2.1: Get warehouse name

```sql
SELECT CURRENT_WAREHOUSE();
```

Store the result as `MY_WH`. Use it in every `WAREHOUSE = <MY_WH>` clause below — do NOT hardcode `COMPUTE_WH`.

---

## Step 2.2: Create the target schema

```sql
CREATE SCHEMA IF NOT EXISTS <MY_DB>.<MY_NORM_SCHEMA>;
```

---

## Step 2.3: Generate a DT for each raw table

For each table discovered in Phase 1, create a Dynamic Table using these patterns.

**Always include `INITIALIZE = ON_CREATE`** so the table is populated immediately on creation. Without it, row counts will be 0 until the first scheduled refresh.

### Pattern A — Table with a VARIANT array column (e.g., `resources`, `signal_samples`)

Create **one row per array element** using `LATERAL FLATTEN`:

```sql
CREATE OR REPLACE DYNAMIC TABLE <MY_DB>.<MY_NORM_SCHEMA>.DT_<TABLE>_FLAT
TARGET_LAG = '5 minutes'
WAREHOUSE = <MY_WH>
REFRESH_MODE = AUTO
INITIALIZE = ON_CREATE
AS
SELECT
    t.<SCALAR_COL_1>,
    t.<SCALAR_COL_2>,
    -- extract scalar fields from top-level VARIANT
    t.PAYLOAD:<field1>::STRING     AS <field1>,
    t.PAYLOAD:<field2>::NUMBER     AS <field2>,
    -- if there's a nested object (e.g., connectivity block):
    t.PAYLOAD:<block>:<subfield>::STRING AS <subfield>,
    -- from the flattened array element:
    f.value:<resource_field>::NUMBER AS <resource_field>,
    f.value:<name_field>::STRING     AS <name_field>
FROM <MY_DB>.<MY_RAW_SCHEMA>.<TABLE> t,
LATERAL FLATTEN(INPUT => t.PAYLOAD:<array_path>) f;
```

**For tables where some rows lack the array** (e.g., old firmware with flat JSON):
Use `LEFT JOIN LATERAL FLATTEN(INPUT => ..., OUTER => TRUE)` to preserve rows with null/empty arrays.

### Pattern B — Table with only flat VARIANT (no arrays)

Extract scalar values directly; no LATERAL FLATTEN needed:

```sql
CREATE OR REPLACE DYNAMIC TABLE <MY_DB>.<MY_NORM_SCHEMA>.DT_<TABLE>_ENRICHED
TARGET_LAG = '10 minutes'
WAREHOUSE = <MY_WH>
REFRESH_MODE = AUTO
INITIALIZE = ON_CREATE
AS
SELECT
    t.<SCALAR_COL_1>,
    t.<SCALAR_COL_2>,
    t.PAYLOAD:<path1>::STRING         AS <col1>,
    t.PAYLOAD:<path2>::NUMBER         AS <col2>,
    t.PAYLOAD:<nested>:<subpath>::NUMBER AS <nested_col>,
    -- only use CURRENT_TIMESTAMP() for display; avoid in persistent cols to keep INCREMENTAL mode
    CASE WHEN t.RESOLVED_AT IS NOT NULL
         THEN DATEDIFF('minute', t.CREATED_AT, t.RESOLVED_AT)
         ELSE NULL
    END AS RESOLUTION_MINUTES
FROM <MY_DB>.<MY_RAW_SCHEMA>.<TABLE> t;
```

> ⚠️ **Avoid `CURRENT_TIMESTAMP()` in DT AS-SELECT.** It forces `REFRESH_MODE = FULL` because the expression is non-deterministic. Compute live durations in the SV METRICS or in queries instead.

---

## Step 2.4: Special handling rules

| Issue detected | Fix |
|----------------|-----|
| Nullable timestamp (`EVENT_TIME` sometimes null) | `COALESCE(EVENT_TIME, RECEIVED_AT) AS EVENT_TIME_CLEAN` |
| Mixed-type numeric (string OR number) | `TRY_CAST(PAYLOAD:<field>::STRING AS NUMBER) AS <field>` |
| Hex-encoded ID | Keep as `::STRING` — do not cast to NUMBER |
| Array may be empty or null | Use `LEFT JOIN LATERAL FLATTEN(INPUT => ..., OUTER => TRUE)` |
| Categorical integer codes | Add a human-readable derived column (see SENSOR_TYPE below) |

### Categorical code → human-readable label

If the source has integer codes that users would phrase as words (e.g., object types, event types), add a derived string column in the DT:

```sql
CASE <code_column>
    WHEN <val1> THEN '<label1>'
    WHEN <val2> THEN '<label2>'
    ELSE 'Unknown'
END AS <label_column>
```

Expose the label column as a DIMENSION in the SV (not the integer code). This prevents Cortex Analyst from having to guess that "temperature" maps to `object_id = 3303`.

---

## Step 2.5: Add a DEVICES anchor table

**This table is required for the Semantic View RELATIONSHIPS to work.**

After creating the per-reading/per-event DTs, create one DT that has **one row per unique device** — this becomes the anchor table for all REFERENCES in the SV:

```sql
CREATE OR REPLACE DYNAMIC TABLE <MY_DB>.<MY_NORM_SCHEMA>.DT_DEVICES
TARGET_LAG = '5 minutes'
WAREHOUSE = <MY_WH>
REFRESH_MODE = AUTO
INITIALIZE = ON_CREATE
AS
SELECT DISTINCT
    DEVICE_IMEI
FROM <MY_DB>.<MY_RAW_SCHEMA>.<PRIMARY_TELEMETRY_TABLE>
WHERE DEVICE_IMEI IS NOT NULL;
```

> `PRIMARY KEY (DEVICE_IMEI)` — this is the join anchor. Every other DT that has a DEVICE_IMEI column will reference this table in the SV RELATIONSHIPS clause.

> If the source telemetry table has more device-level attributes you want surfaced (last seen, technology, latest RSRP), you can enrich here with `QUALIFY ROW_NUMBER() OVER (PARTITION BY DEVICE_IMEI ORDER BY <timestamp> DESC) = 1`.

---

## Step 2.6: Verify

```sql
-- Row counts vs source
SELECT '<TABLE1>' AS tbl, COUNT(1) AS cnt FROM <MY_DB>.<MY_NORM_SCHEMA>.DT_<TABLE1>_FLAT
UNION ALL SELECT '<TABLE2>', COUNT(1) FROM <MY_DB>.<MY_NORM_SCHEMA>.DT_<TABLE2>_FLAT
UNION ALL SELECT 'DT_DEVICES', COUNT(1) FROM <MY_DB>.<MY_NORM_SCHEMA>.DT_DEVICES;
```

If row count in a flattened DT > source, that's expected (multiplier = avg array length). If any DT shows 0 rows, check that `INITIALIZE = ON_CREATE` was included and that the source table has data.

Proceed immediately to **Phase 3** — no user stop.

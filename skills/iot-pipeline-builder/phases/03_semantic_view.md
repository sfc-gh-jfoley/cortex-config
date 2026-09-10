---
name: iot-pipeline-builder-phase3
description: Build a Semantic View over the normalized Dynamic Tables — classify columns, detect relationships, generate DDL
---

# Phase 3: Semantic View

## Step 3.1: Profile the normalized tables

```sql
SELECT * FROM <MY_DB>.<MY_NORM_SCHEMA>.DT_DEVICES LIMIT 10;
SELECT * FROM <MY_DB>.<MY_NORM_SCHEMA>.DT_<TABLE1>_FLAT LIMIT 10;
SELECT * FROM <MY_DB>.<MY_NORM_SCHEMA>.DT_<TABLE2>_FLAT LIMIT 10;
-- repeat for each DT
```

From the output, note:
- Column names and types per table
- Which tables have a `DEVICE_IMEI` column (or equivalent join key)
- Numeric columns that are measurements → **FACTS**
- Categorical/string columns → **DIMENSIONS**
- Timestamp columns → **TIME_DIMENSION** (pick one primary event timestamp per table)
- Aggregations that make business sense → **METRICS**

---

## Step 3.2: Create the AGENTS schema

```sql
CREATE SCHEMA IF NOT EXISTS <MY_DB>.<MY_AGENTS_SCHEMA>;
```

---

## Step 3.3: RELATIONSHIPS rule — always use DT_DEVICES as anchor

> ⚠️ **Critical.** Snowflake SV `REFERENCES` requires the right-hand column to be the `PRIMARY KEY` of the referenced table. A telemetry fact table has `PRIMARY KEY (RECORD_ID)` — one row per reading, not per device. Declaring `n (DEVICE_IMEI) REFERENCES t (RECORD_ID)` passes the PK check but is semantically wrong. Declaring `n (DEVICE_IMEI) REFERENCES t (DEVICE_IMEI)` fails with: *"referenced key must be primary or unique key of the referenced entity."*
>
> **Fix:** `DT_DEVICES` has `PRIMARY KEY (DEVICE_IMEI)`. All other tables reference `devices (DEVICE_IMEI)`. This gives Cortex Analyst correct, working join paths.

---

## Step 3.4: Generate and execute the Semantic View DDL

Mandatory clause order: `TABLES → RELATIONSHIPS → FACTS → DIMENSIONS → METRICS`

```sql
CREATE OR REPLACE SEMANTIC VIEW <MY_DB>.<MY_AGENTS_SCHEMA>.<SV_NAME>
TABLES (
    -- DT_DEVICES is the anchor — always first
    d AS <MY_DB>.<MY_NORM_SCHEMA>.DT_DEVICES
        PRIMARY KEY (DEVICE_IMEI)
        WITH SYNONYMS ('<device>', '<unit>', '<sensor>')
        COMMENT = 'One row per unique device. Primary join anchor across all tables.',
    -- per-reading and per-event tables reference d
    t AS <MY_DB>.<MY_NORM_SCHEMA>.DT_<TABLE1>_FLAT
        PRIMARY KEY (<pk_col>)
        WITH SYNONYMS ('<business_name1>', '<business_name2>')
        COMMENT = '<what this table contains>'
    -- repeat for each DT
)
RELATIONSHIPS (
    -- every table with DEVICE_IMEI references the anchor
    t (DEVICE_IMEI) REFERENCES d (DEVICE_IMEI),
    n (DEVICE_IMEI) REFERENCES d (DEVICE_IMEI),
    i (DEVICE_IMEI) REFERENCES d (DEVICE_IMEI)
    -- add any other FK relationships (e.g., incidents to sites) here
)
FACTS (
    -- numeric measurement columns: <alias>.<col> AS <col>
    -- alias must match the TABLES alias above
    t.<numeric_col> AS <numeric_col>
        COMMENT = '<what this number means, units if applicable>'
)
DIMENSIONS (
    -- all categorical, string, boolean, ID, and timestamp columns
    -- expose DEVICE_IMEI from d (the anchor), not from t/n/i
    d.DEVICE_IMEI AS DEVICE_IMEI
        COMMENT = 'Unique device identifier. Join key across all tables.',
    t.<dim_col> AS <dim_col>
        COMMENT = '<what this dimension represents>'
    -- expose human-readable label columns (e.g., SENSOR_TYPE), not raw codes
)
METRICS (
    AVG_<metric> AS AVG(<alias>.<fact_col>)
        COMMENT = '<what the average represents, thresholds if known>'
)
COMMENT = '<one sentence: what domain this SV covers, what questions it can answer>';
```

### Column alias rule (critical)

`AS col_name` must exactly match the **physical column name** in the DT. Never alias to a different name.

### Duplicate column names across tables

If two DTs share a column name (e.g., `DEVICE_IMEI` in both `t` and `n`), define it from **one table only** — preferably from `d` (the anchor). Do not re-declare it.

---

## Step 3.5: Verify

```sql
DESCRIBE SEMANTIC VIEW <MY_DB>.<MY_AGENTS_SCHEMA>.<SV_NAME>;
```

If this fails, check in order:
1. Clause order: `TABLES → RELATIONSHIPS → FACTS → DIMENSIONS → METRICS`
2. Every `AS col_name` matches the physical column name exactly
3. Every `REFERENCES` right-hand column is the `PRIMARY KEY` of that table
4. No column declared twice across tables

Auto-fix and re-execute before proceeding. Do not move to Phase 4 until `DESCRIBE` succeeds.

Store the SV FQN as `MY_SV_FQN = '<MY_DB>.<MY_AGENTS_SCHEMA>.<SV_NAME>'`.

Proceed immediately to **Phase 4** — no user stop.

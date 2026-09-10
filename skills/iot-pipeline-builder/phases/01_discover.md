---
name: iot-pipeline-builder-phase1
description: Discover raw table structure — VARIANT columns, array paths, nulls, join keys
---

# Phase 1: Discover

## Step 1.1: Get the source schema

If the user already mentioned a database and schema (e.g., `ATT_IOT_DEMO.RAW`), use that.
Otherwise ask once:

> "Which `DB.SCHEMA` holds your raw tables?"

Store as `MY_DB` and `MY_RAW_SCHEMA`. Set `MY_NORM_SCHEMA = NORMALIZED` and `MY_AGENTS_SCHEMA = AGENTS`.

---

## Step 1.2: List tables

```sql
SHOW TABLES IN SCHEMA <MY_DB>.<MY_RAW_SCHEMA>;
```

Note all table names. Store as `RAW_TABLES`.

---

## Step 1.3: Describe + sample each table

For each table in `RAW_TABLES`, run:

```sql
DESCRIBE TABLE <MY_DB>.<MY_RAW_SCHEMA>.<TABLE>;
SELECT * FROM <MY_DB>.<MY_RAW_SCHEMA>.<TABLE> LIMIT 3;
```

From the results, identify:
- **VARIANT columns** — note which ones contain arrays vs flat JSON objects
- **Array paths** — e.g., `PAYLOAD:resources`, `PAYLOAD:signal_samples`
- **Nullable timestamps** — if `EVENT_TIME` is sometimes null, note it (clock drift → use COALESCE)
- **Mixed-type fields** — e.g., `battery_mv` that might be string or number → mark for TRY_CAST
- **Join keys** — columns shared across tables (e.g., `DEVICE_IMEI`, `SITE_ID`)
- **Primary key candidates** — e.g., `RECORD_ID`, `CDR_ID`, `INCIDENT_ID`

---

## Step 1.4: Summary

Print a brief 3-5 bullet summary:
- How many tables found
- Which VARIANT columns have arrays to flatten
- Any clock drift / null timestamp columns
- Detected join key
- Any type mismatch columns

Then proceed immediately to **Phase 2** — no user stop.

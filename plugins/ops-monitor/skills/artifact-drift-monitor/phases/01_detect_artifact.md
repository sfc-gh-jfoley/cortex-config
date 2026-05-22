---
name: artifact-drift-monitor-phase1
description: Detect artifact type, confirm lookback window with per-type defaults
---

# Phase 1: Detect Artifact Type & Confirm Lookback

## Step 1.1: Identify artifact type

Parse the user's request:

| User says | Artifact type |
|-----------|--------------|
| semantic view, SV, `CREATE SEMANTIC VIEW` | `sv` |
| dynamic table, DT, `CREATE DYNAMIC TABLE` | `dynamic_table` |
| cortex agent, agent, Snowflake Intelligence | `cortex_agent` |
| cortex search, search service | `cortex_search` |

If unclear, ask:
```
Which artifact do you want to check for drift?
  A) Semantic View
  B) Dynamic Table
  C) Cortex Agent
  D) Cortex Search
```

Store as `ARTIFACT_TYPE`.

---

## Step 1.2: Confirm lookback window

Different artifacts need different lookback windows. Present the default and let the user override:

| Artifact type | Default lookback | Rationale |
|--------------|-----------------|-----------|
| `sv` | **90 days** | Stable artifact — needs enough query volume for statistical signal. Shorter windows undercount infrequent but important query patterns. |
| `dynamic_table` | **30 days** | Schema drift is recent by definition — columns added to source tables in the last month are the action items. Older history adds noise. |
| `cortex_agent` | **60 days** | Balances new intent patterns against churn from seasonal/old queries. |
| `cortex_search` | **60 days** | Filter pattern detection needs moderate history to avoid acting on one-off queries. |

Confirm with user:
```
Default lookback for <artifact_type>: <N> days.
  Press Enter to accept, or type a different number of days.
```

Store as `LOOKBACK_DAYS`.

**Statistical signal floor**: If query population (Step 2.1 / 3.1) returns < 20 queries total, warn:
> "Low query volume (<20 queries in <LOOKBACK_DAYS> days) — recommendations may not be statistically representative. Consider extending the lookback window."

---

## Step 1.3: Get artifact name

Ask for or confirm the fully qualified name (DB.SCHEMA.NAME). Verify it exists:

```sql
SHOW SEMANTIC VIEWS LIKE '<name>';
-- or: SHOW DYNAMIC TABLES LIKE '<name>';
```

Store as `ARTIFACT_NAME`.

---

## Step 1.4: Fetch artifact definition

For **Semantic View**:
```sql
SELECT GET_DDL('semantic_view', '<ARTIFACT_NAME>');
```
Parse: source table list → `SV_TABLES`, column list → `SV_COLUMNS`, metric list → `SV_METRICS`.
Also count current facts + dimensions → `SV_COLUMN_COUNT` (used later for complexity budget check).

For **Dynamic Table**:
```sql
SELECT GET_DDL('dynamic_table', '<ARTIFACT_NAME>');
```
Parse: source tables → `DT_SOURCE_TABLES`, output columns → `DT_COLUMNS`, uses `SELECT *` → `DT_SELECT_STAR`.

For **Cortex Agent** / **Cortex Search**: capture tool list, linked SVs, indexed columns.

---

## Step 1.5: Dispatch

| ARTIFACT_TYPE | Next phase |
|--------------|-----------|
| sv | phases/02_sv_drift.md |
| dynamic_table | phases/03_dt_schema_drift.md |
| cortex_agent | phases/04_agent_drift.md |
| cortex_search | phases/05_search_drift.md |

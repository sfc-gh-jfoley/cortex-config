---
name: artifact-drift-monitor-phase6
description: Present scored suggestions, get user approval per item, generate DDL only for approved changes
---

# Phase 6: Enhancement Manifest, Approval Gate & Remediation

Takes `GAP_SUGGESTIONS` from the drift phase and presents each with ADD/SKIP recommendation and rationale.
**No DDL is generated until the user approves specific items.**

---

## Step 6.1: Sort and group suggestions

Sort `GAP_SUGGESTIONS` by:
1. Severity (dropped columns always first)
2. Score descending
3. Type (TABLE_GAP, NEW_COLUMN, COLUMN_GAP, TYPE_DRIFT, INDEX_GAP)

---

## Step 6.2: Present the enhancement manifest

```
╔══════════════════════════════════════════════════════════════════════════════╗
║  ARTIFACT DRIFT MONITOR — ENHANCEMENT MANIFEST                               ║
║  Artifact: <ARTIFACT_NAME>   Type: <ARTIFACT_TYPE>                           ║
║  Analysis window: <LOOKBACK_DAYS> days   |   <QUERY_POPULATION_SIZE> queries ║
╠══════════════════════════════════════════════════════════════════════════════╣
```

### Format for each suggestion

```
[N]  ⚠️  <TYPE>  —  <PRIORITY>
     Item:          <item name / table / column>
     Why ADD:       <specific evidence: query_count, user_count, usage_context, etc.>
     Why SKIP:      <risk or noise: adds N new dimensions, ETL column, large table, etc.>
     Recommendation: <ADD / REVIEW / SKIP>
```

#### Example — TABLE_GAP (ADD):
```
[1]  📊  TABLE_GAP  —  HIGH
     Item:          COX_AUTO_HOL.PUBLIC.VINSOLUTIONS_LEADS
     Why ADD:       847 queries / 12 users (31% of traffic) — heavily co-queried with SV
                    source tables; clean single FK join to DEALERS via DEALER_ID
     Why SKIP:      Adds ~18 new columns (SV currently at 49 total → 67 after)
     Recommendation: ADD  ✓
```

#### Example — TABLE_GAP (SKIP):
```
[2]  📊  TABLE_GAP  —  LOW
     Item:          COX_AUTO_HOL.PUBLIC._ETL_LOG_TABLE
     Why ADD:       34 queries / 2 users (1.2% of traffic)
     Why SKIP:      Table name matches ETL audit pattern; likely pipeline noise,
                    not a user-facing query. Adding would pollute dimension list.
     Recommendation: SKIP  ✗
```

#### Example — NEW_COLUMN (REVIEW):
```
[3]  🔄  DT NEW_COLUMN  —  MED
     Item:          SOURCE_VEHICLES_STREAM.CONDITION_GRADE_V2 (VARCHAR)
     Why ADD:       New column added to source on 2026-04-22; business-sounding name,
                    clean VARCHAR type, consistent with existing CONDITION_GRADE pattern
     Why SKIP:      Ordinal position 47 — added recently, may still be in rollout;
                    only 40% non-null so far
     Recommendation: REVIEW  ?
```

#### Example — COLUMN_GAP (ADD):
```
[4]  📊  COLUMN_GAP  —  HIGH
     Item:          VEHICLES.ACQUISITION_DATE
     Why ADD:       523 WHERE-clause references across 8 users — users are clearly
                    trying to filter by acquisition date but SV doesn't expose it
     Why SKIP:      None — DATE column, clean addition
     Recommendation: ADD  ✓
```

#### Example — dropped column (HIGH, always fix):
```
[5]  🚨  DROPPED_COLUMN  —  HIGH  ← DT REFRESH WILL FAIL
     Item:          SOURCE_VEHICLES.LEGACY_GRADE_CODE
     Why ADD fix:   Column was removed from source table on 2026-04-20;
                    DT SELECT still references it → refresh will error on next cycle
     Why SKIP:      No reason to skip — this will break your pipeline
     Recommendation: ADD (remove from DT DDL)  ✓
```

#### Bypass signals (informational only — no DDL):
```
ℹ️   BYPASS  —  INFO
     23 users running direct SQL against SV source tables without using the SV
     Top bypasser: analyst_user1 (94 direct queries)
     Action: no DDL change — consider user education or checking for SV coverage gaps
```

---

## Step 6.3: Approval gate

⚠️ **STOPPING POINT** — Present the full manifest and wait for user input.

After presenting all suggestions, show:

```
╠══════════════════════════════════════════════════════════════════════════════╣
║  APPROVAL REQUIRED — Review suggestions and choose for each:                 ║
║                                                                               ║
║  For each item [N], type:                                                    ║
║    A  →  Approve this change (will generate DDL)                             ║
║    S  →  Skip / reject this change                                           ║
║    ?  →  Ask for more detail before deciding                                 ║
║                                                                               ║
║  Shortcuts:                                                                  ║
║    approve all ADD       →  approve every item with recommendation ADD       ║
║    approve HIGH          →  approve every HIGH priority item                 ║
║    approve all           →  approve everything (review carefully first)      ║
║    skip all SKIP         →  auto-reject every item with recommendation SKIP  ║
╚══════════════════════════════════════════════════════════════════════════════╝

Your choices (e.g. "1A 2S 3A 4A 5A"):
```

Accept approval input in any format:
- `1A 2S 3A 4A 5A`
- `approve all ADD` → auto-approve every recommendation=ADD item
- `approve HIGH` → auto-approve every HIGH priority item
- `1? ` → respond with additional context for item 1, then ask again

Store approved items as `APPROVED_CHANGES`.

---

## Step 6.4: Generate DDL — approved items only

Generate remediation DDL **only** for items in `APPROVED_CHANGES`. Skip everything else.

### Semantic View — approved column additions

```sql
-- Adding approved columns requires CREATE OR REPLACE (semantic views have no ALTER ADD COLUMN)
-- Fetch current DDL as the base:
SELECT GET_DDL('semantic_view', '<ARTIFACT_NAME>');

-- Add each approved column to the appropriate FACTS or DIMENSIONS block:
-- Example — adding VEHICLES.ACQUISITION_DATE (approved TIME_DIMENSION):
-- In the DIMENSIONS block, add:
--   <table_alias>.ACQUISITION_DATE AS ACQUISITION_DATE
--     COMMENT 'Date the vehicle was acquired into inventory'

-- Full CREATE OR REPLACE with all approved additions:
CREATE OR REPLACE SEMANTIC VIEW <ARTIFACT_NAME>
  TABLES ( ... )          -- unchanged
  RELATIONSHIPS ( ... )   -- unchanged
  FACTS (
    -- existing facts ...
    -- approved new facts here
  )
  DIMENSIONS (
    -- existing dims ...
    -- approved new dims here (each with updated COMMENT including sample_values)
  )
  METRICS ( ... )         -- unchanged
  COMMENT = '...'
  AI_SQL_GENERATION '...';
```

### Semantic View — approved table additions

Recommend running `semantic-view-ddl` skill in "expand SV" mode:
```
The approved table addition requires full Phase 2–5 classification for the new table.
Recommended: run the semantic-view-ddl skill and say "expand existing SV <name> with <table>".
```

### Dynamic Table — approved column additions

```sql
-- CREATE OR REPLACE is required — ALTER DYNAMIC TABLE cannot add columns
CREATE OR REPLACE DYNAMIC TABLE <ARTIFACT_NAME>
  TARGET_LAG = '<target_lag>'
  WAREHOUSE  = <warehouse>
AS
SELECT
  -- All existing columns (unchanged):
  <existing_col_1>,
  <existing_col_2>,
  -- ... (all current DT columns) ...

  -- Approved new source columns:
  <source_table>.<approved_col_1>,   -- <data_type> — added <date_detected>
  <source_table>.<approved_col_2>    -- <data_type> — added <date_detected>
FROM <source_tables_and_joins>;
```

### Dynamic Table — approved type fixes

```sql
CREATE OR REPLACE DYNAMIC TABLE <ARTIFACT_NAME>
  TARGET_LAG = '<target_lag>'
  WAREHOUSE  = <warehouse>
AS
SELECT
  -- ...
  CAST(<col> AS <new_source_type>) AS <col>,  -- type widened: <old_type> → <new_type>
  -- ...
FROM <source_tables_and_joins>;
```

### Dynamic Table — dropped column removal (always approved)

```sql
CREATE OR REPLACE DYNAMIC TABLE <ARTIFACT_NAME>
  TARGET_LAG = '<target_lag>'
  WAREHOUSE  = <warehouse>
AS
SELECT
  -- All columns EXCEPT dropped: <DROPPED_COLUMN_NAME>
  <col_1>,
  <col_2>
  -- ...
FROM <source_tables_and_joins>;
```

### SELECT * DT — source added columns

```sql
-- SELECT * does NOT auto-expand in Snowflake Dynamic Tables.
-- Recreate to capture new source columns:

-- Option A: Keep SELECT * (captures all current source columns including new ones)
CREATE OR REPLACE DYNAMIC TABLE <ARTIFACT_NAME>
  TARGET_LAG = '<target_lag>'
  WAREHOUSE  = <warehouse>
AS SELECT * FROM <source_table>;

-- Option B (recommended): Switch to explicit column list for future-proof control
CREATE OR REPLACE DYNAMIC TABLE <ARTIFACT_NAME>
  TARGET_LAG = '<target_lag>'
  WAREHOUSE  = <warehouse>
AS
SELECT
  <col_1>,
  <col_2>,
  -- ... all approved new columns ...
  <new_col_1>,  -- new as of <date_detected>, approved by user
  <new_col_2>   -- new as of <date_detected>, approved by user
FROM <source_table>;
```

### Cortex Search — approved filter columns

```sql
CREATE OR REPLACE CORTEX SEARCH SERVICE <ARTIFACT_NAME>
  ON <search_column>
  ATTRIBUTES <existing_attrs>, <approved_new_filter_col>
  TARGET_LAG = '<target_lag>'
  WAREHOUSE  = <warehouse>
AS <source_query>;
```

---

## Step 6.5: Final summary

```
╔══════════════════════════════════════════════════════════════════════════════╗
║  REMEDIATION PLAN                                                            ║
╠══════════════════════════════════════════════════════════════════════════════╣
  Suggestions reviewed:  <total_suggestions>
  Approved:              <approved_count>
  Skipped:               <skipped_count>

  DDL generated for:     <approved_count> items
  Apply order:
    1. Dropped column fixes (prevents refresh failure)  — apply IMMEDIATELY
    2. Type fixes                                       — apply before next refresh
    3. New column/table additions                       — apply when convenient

  Review DDL above before applying. Each block is independent — apply selectively.

  Next run:  Schedule in <LOOKBACK_DAYS / 3> days to catch the next drift cycle.
╚══════════════════════════════════════════════════════════════════════════════╝
```

⚠️ **STOPPING POINT** — present the DDL blocks and final summary. Wait for user to confirm before executing anything.

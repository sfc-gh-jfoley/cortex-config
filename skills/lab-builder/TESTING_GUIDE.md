# Lab Testing Guide

> Actionable test playbook for all Snowflake hands-on lab modules.
> Run the right layer at the right time — before, during, and after every workshop.

---

## Overview

The current `validate.sql` pattern checks *completion* (did the object get created?).
This guide adds layers so the SE catches problems before participants do.

```
Layer 0 — Grant Audit                  → Run WHEN BUILDING the lab + night before workshop (SE verifies DBA work)
Layer 1 — Pre-Lab Environment Check    → Run BEFORE the lab (facilitator + participant)
Layer 2 — Module-Level Completion      → Run AFTER each module (participant self-check)
Layer 3 — Data-Aware Correctness       → Run AFTER data is loaded (facilitator QA)
Layer 4 — End-to-End Smoke Test        → Run the NIGHT BEFORE a workshop (SE)
+ CoCo Prompt Determinism Testing      → Run BEFORE any live CoCo-guided delivery
```

**Ownership model:**
- Customer DBA runs `facilitator_setup.sql` (provisioning)
- Account SE runs `grant_audit.sql` (verification) — SE must sign off before participants receive pre-work
- Participants run `hol_setup.sql` (their own schema/data)

---

## Layer 0 — Grant Audit (SE Verification)

**Run when:** Building a new lab AND the night before any workshop.

This is the SE's sign-off that the customer DBA provisioned everything correctly.
Every row in `grant_audit.sql` must show ✓ PASS before you send participants the pre-work doc.
Any ✗ FAIL = contact the DBA with the specific GRANT statement shown in the result.

**Template:** `labs/_template/grant_audit.sql`

---

### 0.1 Isolation Pattern Decision

Before building a new lab, answer this question and put the answer in README.md `**Isolation:**`:

| Question | Answer |
|----------|--------|
| Is this a shared customer account? | → Pattern A (schema-per-user) |
| Does each participant have their own sandbox? | → Pattern B (db-per-user) |
| Does the lab use dbt with separate catalogs? | → Pattern B |
| Everything else | → Pattern A |

This choice drives Section B of `grant_audit.sql` — the authoritative list of what the DBA
must configure in `facilitator_setup.sql`.

---

### 0.2 Per-Module Grant Requirements

Share this table with the DBA when handing off `facilitator_setup.sql`.
The SE verifies each line using `grant_audit.sql` Section A.

| Module Type | Required Grant | FUTURE SCHEMAS supported? |
|-------------|----------------|--------------------------|
| Base (all labs) | `USAGE ON DATABASE`, `CREATE SCHEMA ON DATABASE`, `USAGE ON WAREHOUSE` | — |
| Cortex AI | `GRANT DATABASE ROLE SNOWFLAKE.CORTEX_USER TO ROLE <HOL_ROLE>` | — (DB role, not schema) |
| Streamlit in Snowflake | `CREATE STREAMLIT ON FUTURE SCHEMAS IN DATABASE <LAB_DB>` | ✓ Pattern A |
| Dynamic Tables | `CREATE DYNAMIC TABLE ON FUTURE SCHEMAS IN DATABASE <LAB_DB>` | ✓ Pattern A |
| Snowflake Notebooks | `CREATE NOTEBOOK ON FUTURE SCHEMAS IN DATABASE <LAB_DB>` | ✓ Pattern A |
| dbt | `CREATE TABLE + CREATE VIEW ON FUTURE SCHEMAS IN DATABASE <LAB_DB>` | ✓ Pattern A |
| ML Jobs / SPCS | `CREATE COMPUTE POOL` (ACCOUNTADMIN + quota approval) | ✗ Facilitator-only |

---

### 0.3 Running grant_audit.sql

```sql
-- 1. Open grant_audit.sql for the lab (or use labs/_template/grant_audit.sql)
-- 2. Set the variables at the top:
SET hol_role  = 'HOL_ROLE_NAME';       -- confirm with DBA
SET hol_db    = 'LAB_DB_NAME';         -- from README.md
SET hol_wh    = 'COMPUTE_WH';          -- confirm with DBA
SET isolation = 'schema';              -- from README.md Isolation: field

-- 3. Uncomment the module sections that match this lab's features
-- 4. Run Section A — every row must show ✓ PASS

-- 5. Run Section C — confirm participant users are listed
-- 6. Screenshot the results for your records
```

**Failure flow:**
1. Any ✗ FAIL row → copy the `fix_sql` value from that row
2. Email or Slack to DBA: "Please run: `<fix_sql>`"
3. Re-run `grant_audit.sql` after DBA confirms
4. Do not send pre-work doc until all rows = ✓

---

### 0.4 Night-Before Re-Run

Grants can be revoked accidentally (role recreation, account policy changes). Run
`grant_audit.sql` again the night before the workshop as a final sign-off, even if
you ran it successfully when building the lab.

---

## Layer 1 — Pre-Lab Environment Check

Run these checks before the lab starts. For instructor-led workshops, the facilitator
runs them during account provisioning. For self-paced labs, participants run them in
Module 00 (Setup).

**Goal:** Fail fast on account/permission issues before a participant spends 20 minutes
getting to the point where they need Cortex.

---

### 1.1 Account Capability Check

Tests that the required Snowflake features are enabled in this account.

```sql
-- ============================================================
-- Account Capability Check
-- ============================================================
-- Run as ACCOUNTADMIN or a role with IMPORTED PRIVILEGES on SNOWFLAKE DB.
-- Expected: all rows = TRUE.
-- ============================================================

SELECT feature, enabled FROM (

    -- Cortex Complete (LLM access)
    SELECT
        'Cortex Complete (LLM)' AS feature,
        TRY_CAST(
            SNOWFLAKE.CORTEX.COMPLETE('snowflake-arctic', 'Reply with the single word OK') 
            AS VARCHAR
        ) IS NOT NULL AS enabled

    UNION ALL

    -- Semantic Views
    SELECT
        'Semantic Views (INFORMATION_SCHEMA)',
        (SELECT COUNT(*) FROM INFORMATION_SCHEMA.SEMANTIC_VIEWS) >= 0

    UNION ALL

    -- Cortex Search Services
    SELECT
        'Cortex Search Services (INFORMATION_SCHEMA)',
        (SELECT COUNT(*) FROM INFORMATION_SCHEMA.CORTEX_SEARCH_SERVICES) >= 0

    UNION ALL

    -- Cortex Agents
    SELECT
        'Cortex Agents (INFORMATION_SCHEMA)',
        (SELECT COUNT(*) FROM INFORMATION_SCHEMA.CORTEX_AGENTS) >= 0

    UNION ALL

    -- Streamlit in Snowflake
    SELECT
        'Streamlit in Snowflake (INFORMATION_SCHEMA)',
        (SELECT COUNT(*) FROM INFORMATION_SCHEMA.STREAMLITS) >= 0

    UNION ALL

    -- Dynamic Tables
    SELECT
        'Dynamic Tables (INFORMATION_SCHEMA)',
        (SELECT COUNT(*) FROM INFORMATION_SCHEMA.DYNAMIC_TABLES) >= 0

    UNION ALL

    -- Snowflake Notebooks
    SELECT
        'Notebooks (INFORMATION_SCHEMA)',
        (SELECT COUNT(*) FROM INFORMATION_SCHEMA.NOTEBOOKS) >= 0

)
ORDER BY feature;
```

**What to do if a feature returns FALSE or errors:**

| Feature | Failure Cause | Fix |
|---------|---------------|-----|
| Cortex Complete | Region doesn't support Cortex, or account is trial | Use a Cortex-enabled region (US/EU West); contact Snowflake SE |
| Semantic Views | Account below Enterprise edition | Upgrade or use a different trial account |
| Cortex Search / Agents | Preview feature not yet GA in this region | Request enablement via your account team |
| Streamlit | Not enabled in older accounts | Run `ALTER ACCOUNT SET ENABLE_STREAMLIT_UI = TRUE` as ACCOUNTADMIN |

---

### 1.2 Role and Permission Check

Tests that the participant's role has the grants needed to complete the lab.

```sql
-- ============================================================
-- Role and Permission Check
-- ============================================================
-- Replace <LAB_ROLE> with the role participants will use (e.g., SYSADMIN or a custom role).
-- Replace <LAB_DB> and <LAB_WH> with the lab database and warehouse.
-- ============================================================

SET lab_role = '<LAB_ROLE>';
SET lab_db   = '<LAB_DB>';
SET lab_wh   = '<LAB_WH>';

SELECT check_name, result FROM (

    -- Can the role USE the lab warehouse?
    SELECT
        'Warehouse access: ' || $lab_wh AS check_name,
        CASE WHEN (
            SELECT COUNT(*) FROM INFORMATION_SCHEMA.ENABLED_ROLES er
            JOIN SNOWFLAKE.ACCOUNT_USAGE.GRANTS_TO_ROLES g
              ON g.GRANTEE_NAME = er.ROLE_NAME
            WHERE g.PRIVILEGE = 'USAGE'
              AND g.GRANTED_ON = 'WAREHOUSE'
              AND g.NAME = UPPER($lab_wh)
        ) > 0 THEN '✓ PASS' ELSE '✗ FAIL — grant USAGE ON WAREHOUSE to role' END AS result

    UNION ALL

    -- Can the role CREATE SCHEMA in the lab database?
    SELECT
        'CREATE SCHEMA on: ' || $lab_db,
        CASE WHEN (
            SELECT COUNT(*) FROM SNOWFLAKE.ACCOUNT_USAGE.GRANTS_TO_ROLES
            WHERE GRANTEE_NAME = UPPER($lab_role)
              AND PRIVILEGE IN ('CREATE SCHEMA', 'OWNERSHIP')
              AND GRANTED_ON = 'DATABASE'
              AND NAME = UPPER($lab_db)
        ) > 0 THEN '✓ PASS' ELSE '✗ FAIL — grant CREATE SCHEMA ON DATABASE to role' END

    UNION ALL

    -- Does the role have the CORTEX_USER database role?
    SELECT
        'CORTEX_USER database role',
        CASE WHEN (
            SELECT COUNT(*) FROM SNOWFLAKE.ACCOUNT_USAGE.GRANTS_TO_ROLES
            WHERE GRANTEE_NAME = UPPER($lab_role)
              AND GRANTED_ON = 'DATABASE ROLE'
              AND NAME = 'SNOWFLAKE.CORTEX_USER'
        ) > 0 THEN '✓ PASS' ELSE '✗ FAIL — GRANT DATABASE ROLE SNOWFLAKE.CORTEX_USER TO ROLE <LAB_ROLE>' END

)
ORDER BY check_name;
```

**Quick fix for common failures:**

```sql
-- Grant Cortex access to the lab role
GRANT DATABASE ROLE SNOWFLAKE.CORTEX_USER TO ROLE <LAB_ROLE>;

-- Grant warehouse access
GRANT USAGE ON WAREHOUSE <LAB_WH> TO ROLE <LAB_ROLE>;

-- Grant schema creation
GRANT CREATE SCHEMA ON DATABASE <LAB_DB> TO ROLE <LAB_ROLE>;
```

---

### 1.3 Data Availability Check

Tests that the lab dataset is loaded with expected row counts.
Copy and adapt for each lab — replace table names and expected counts.

```sql
-- ============================================================
-- Data Availability Check (template — adapt per lab)
-- ============================================================
-- Replace <LAB_DB>, <LAB_SCHEMA>, table names, and expected counts.
-- Tolerance: use BETWEEN for synthetic data that may vary slightly.
-- ============================================================

USE DATABASE <LAB_DB>;

SELECT sort_key, table_name, expected_rows, actual_rows,
    CASE WHEN actual_rows = expected_rows THEN '✓ PASS'
         WHEN actual_rows = 0             THEN '✗ FAIL — table empty, re-run setup.sql'
         ELSE                                  '⚠ WARN — row count differs from expected'
    END AS status
FROM (
    SELECT 1, 'STREAMING_SESSIONS',        50000, (SELECT COUNT(*) FROM <LAB_SCHEMA>.STREAMING_SESSIONS)
    UNION ALL
    SELECT 2, 'STREAMING_VIEWERSHIP_EVENTS', 125000, (SELECT COUNT(*) FROM <LAB_SCHEMA>.STREAMING_VIEWERSHIP_EVENTS)
    UNION ALL
    SELECT 3, 'DIM_TITLE',                 12, (SELECT COUNT(*) FROM <LAB_SCHEMA>.DIM_TITLE)
) t(sort_key, table_name, expected_rows, actual_rows)
ORDER BY sort_key;
```

**Row count tolerance pattern** — use when synthetic data has variance:

```sql
-- BETWEEN pattern for synthetic data
CASE WHEN (SELECT COUNT(*) FROM <LAB_SCHEMA>.<TABLE>) BETWEEN 45000 AND 55000
     THEN '✓ PASS' ELSE '✗ FAIL — unexpected row count' END
```

---

### 1.4 CoCo CLI Connection Check (Facilitator Prompt)

For CoCo-guided labs, verify participants have a working connection before the lab.
Give participants this prompt to paste into their CoCo session:

```
What Snowflake databases do I have access to with my current role?
List them as a simple bullet list.
```

**Expected behavior:** CoCo executes `SHOW DATABASES` and returns a list that includes the lab database. If CoCo responds with a connection error or shows no databases, resolve before proceeding.

**If CoCo can't connect:**

```bash
# Check active connection
snow connection list

# Test connection
snow connection test -c default

# Re-authenticate if expired
snow connection add  # or re-run setup for the target connection
```

---

### 1.5 `pre_check.sql` Template

Drop this in `labs/<lab-slug>/sql/pre_check.sql`. It runs all pre-lab checks
and returns a single pass/fail table.

```sql
-- ============================================================
-- Pre-Lab Environment Check: <Lab Title>
-- Run this BEFORE starting the lab.
-- All rows must show ✓ PASS before proceeding.
-- ============================================================

USE ROLE <LAB_ROLE>;
USE DATABASE <LAB_DB>;
USE WAREHOUSE <LAB_WH>;

SELECT sort_key, check_name, status FROM (

    -- CAPABILITY: Cortex LLM
    SELECT 1, 'Cortex LLM available',
        CASE WHEN TRY_CAST(
            SNOWFLAKE.CORTEX.COMPLETE('snowflake-arctic', 'Reply OK') AS VARCHAR
        ) IS NOT NULL THEN '✓ PASS' ELSE '✗ FAIL — Cortex not enabled in this account/region' END

    UNION ALL

    -- CAPABILITY: Required INFORMATION_SCHEMA views accessible
    SELECT 2, 'INFORMATION_SCHEMA accessible',
        CASE WHEN (SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = '<LAB_SCHEMA>') >= 0
             THEN '✓ PASS' ELSE '✗ FAIL — cannot read INFORMATION_SCHEMA' END

    UNION ALL

    -- PERMISSION: CORTEX_USER database role
    SELECT 3, 'CORTEX_USER role granted',
        CASE WHEN IS_DATABASE_ROLE_IN_SESSION('SNOWFLAKE.CORTEX_USER')
             THEN '✓ PASS' ELSE '✗ FAIL — GRANT DATABASE ROLE SNOWFLAKE.CORTEX_USER TO ROLE <LAB_ROLE>' END

    UNION ALL

    -- DATA: Core tables loaded
    SELECT 4, 'Lab tables loaded (<N> tables)',
        CASE WHEN (
            SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_SCHEMA = '<LAB_SCHEMA>'
              AND TABLE_NAME IN (/* list expected table names */)
        ) = <N> THEN '✓ PASS' ELSE '✗ FAIL — re-run sql/setup.sql' END

    UNION ALL

    -- DATA: Primary table has expected row count
    SELECT 5, 'Primary table row count',
        CASE WHEN (SELECT COUNT(*) FROM <LAB_SCHEMA>.<PRIMARY_TABLE>)
                  BETWEEN <MIN_ROWS> AND <MAX_ROWS>
             THEN '✓ PASS' ELSE '✗ FAIL — data not loaded correctly' END

)
ORDER BY sort_key;

-- All rows must show ✓ PASS before starting the lab.
-- On any failure, resolve the issue and re-run this script.
```

---

## Layer 2 — Module-Level Completion Checks

Each module's `validate.sql` checks that the participant built the right object.
These extend the base `validate.sql` pattern from `_template/sql/validate.sql`
with object-type-specific check SQL.

---

### 2.1 Semantic View Labs

```sql
-- Check: semantic view exists
SELECT COUNT(*) AS sv_count
FROM INFORMATION_SCHEMA.SEMANTIC_VIEWS
WHERE SEMANTIC_VIEW_NAME = '<EXPECTED_SV_NAME>';
-- Expected: 1

-- Check: semantic view has minimum dimension count
-- (Use SHOW + result scan to avoid parsing YAML columns)
SHOW SEMANTIC VIEWS LIKE '<EXPECTED_SV_NAME>';
SELECT COUNT(*) AS dim_count
FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()))
WHERE "name" = '<EXPECTED_SV_NAME>';
-- Expected: 1 (view exists with at least the fields defined in the lab)

-- In validate.sql UNION ALL pattern:
SELECT N, 'Module N: <SV_NAME> semantic view created',
    CASE WHEN (
        SELECT COUNT(*) FROM INFORMATION_SCHEMA.SEMANTIC_VIEWS
        WHERE SEMANTIC_VIEW_NAME ILIKE '%<SV_NAME_FRAGMENT>%'
    ) > 0 THEN 'PASS' ELSE 'FAIL' END
```

**ILIKE with wildcards** is preferred over exact match because participants may use
slightly different names (e.g., `MY_SV` vs `MY_SV_V1`). Adjust if exact naming matters.

---

### 2.2 Streamlit in Snowflake (SiS) Labs

```sql
-- Check: Streamlit app exists
SELECT COUNT(*) AS app_count
FROM INFORMATION_SCHEMA.STREAMLITS
WHERE NAME = '<APP_NAME>';
-- Expected: 1
-- Note: INFORMATION_SCHEMA.STREAMLITS is available in Snowflake 2023+ accounts.

-- Check: app is in the expected schema
SELECT NAME, SCHEMA_NAME, DATABASE_NAME
FROM INFORMATION_SCHEMA.STREAMLITS
WHERE NAME ILIKE '%<APP_NAME_FRAGMENT>%';

-- In validate.sql UNION ALL pattern:
SELECT N, 'Module N: <APP_NAME> Streamlit app deployed',
    CASE WHEN (
        SELECT COUNT(*) FROM INFORMATION_SCHEMA.STREAMLITS
        WHERE NAME ILIKE '%<APP_NAME_FRAGMENT>%'
    ) > 0 THEN 'PASS' ELSE 'FAIL' END
```

**Deployment notes for facilitators:**
- `GRANT USAGE ON STREAMLIT <APP_NAME> TO ROLE <PARTICIPANT_ROLE>` is the sharing mechanism (not URL-based).
- Multi-page apps require `snow streamlit deploy --replace` from the directory containing both `app.py` and `pages/`.
- The `requests` library raises `ModuleNotFoundError` in SiS managed runtime — validate by checking the app loads, not by testing `import requests`.

---

### 2.3 dbt Labs

```sql
-- Check: staging view exists
SELECT COUNT(*) AS view_count
FROM INFORMATION_SCHEMA.VIEWS
WHERE TABLE_SCHEMA = '<DBT_SCHEMA>'
  AND TABLE_NAME = 'STG_<MODEL_NAME>';
-- Expected: 1

-- Check: mart table exists and has data
SELECT COUNT(*) AS row_count
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA = '<DBT_SCHEMA>'
  AND TABLE_NAME = 'MART_<MODEL_NAME>'
  AND ROW_COUNT > 0;
-- Expected: 1

-- Check: dbt test results (if dbt artifacts are accessible)
SELECT COUNT(*) AS failed_tests
FROM <DBT_SCHEMA>.dbt_test_results
WHERE status = 'fail';
-- Expected: 0

-- In validate.sql UNION ALL pattern:
SELECT 1, 'Module 2: staging views created',
    CASE WHEN (
        SELECT COUNT(*) FROM INFORMATION_SCHEMA.VIEWS
        WHERE TABLE_SCHEMA = UPPER('<DBT_SCHEMA>')
          AND TABLE_NAME ILIKE 'STG_%'
    ) >= <EXPECTED_STAGING_VIEW_COUNT> THEN 'PASS' ELSE 'FAIL' END

UNION ALL

SELECT 2, 'Module 3: mart tables created with data',
    CASE WHEN (
        SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_SCHEMA = UPPER('<DBT_SCHEMA>')
          AND TABLE_NAME ILIKE 'MART_%'
          AND ROW_COUNT > 0
    ) >= <EXPECTED_MART_COUNT> THEN 'PASS' ELSE 'FAIL' END
```

---

### 2.4 Dynamic Tables Labs

```sql
-- Check: dynamic table exists
SELECT COUNT(*) AS dt_count
FROM INFORMATION_SCHEMA.DYNAMIC_TABLES
WHERE TABLE_NAME = '<DT_NAME>';
-- Expected: 1

-- Check: dynamic table has completed at least one refresh
SELECT
    TABLE_NAME,
    TARGET_LAG,
    SCHEDULING_STATE,
    LAST_COMPLETED_REFRESH_TIME,
    LAST_COMPLETED_REFRESH_STATE
FROM INFORMATION_SCHEMA.DYNAMIC_TABLES
WHERE TABLE_NAME = '<DT_NAME>';
-- Expected: LAST_COMPLETED_REFRESH_STATE = 'SUCCEEDED'

-- Check: dynamic table has data
SELECT COUNT(*) FROM <SCHEMA>.<DT_NAME>;
-- Expected: > 0

-- In validate.sql UNION ALL pattern:
SELECT N, 'Module N: <DT_NAME> dynamic table refreshed successfully',
    CASE WHEN (
        SELECT COUNT(*) FROM INFORMATION_SCHEMA.DYNAMIC_TABLES
        WHERE TABLE_NAME = UPPER('<DT_NAME>')
          AND LAST_COMPLETED_REFRESH_STATE = 'SUCCEEDED'
    ) > 0 THEN 'PASS' ELSE 'FAIL' END
```

---

### 2.5 Cortex Search Labs

```sql
-- Check: Cortex Search service exists
SELECT COUNT(*) AS css_count
FROM INFORMATION_SCHEMA.CORTEX_SEARCH_SERVICES
WHERE SERVICE_NAME = '<CSS_NAME>';
-- Expected: 1

-- Check: service is in ACTIVE state
SELECT SERVICE_NAME, STATE, CREATED
FROM INFORMATION_SCHEMA.CORTEX_SEARCH_SERVICES
WHERE SERVICE_NAME ILIKE '%<CSS_NAME_FRAGMENT>%';
-- Expected: STATE = 'ACTIVE'

-- In validate.sql UNION ALL pattern:
SELECT N, 'Module N: <CSS_NAME> Cortex Search service active',
    CASE WHEN (
        SELECT COUNT(*) FROM INFORMATION_SCHEMA.CORTEX_SEARCH_SERVICES
        WHERE SERVICE_NAME ILIKE '%<CSS_NAME_FRAGMENT>%'
    ) > 0 THEN 'PASS' ELSE 'FAIL' END
```

---

### 2.6 Cortex Agent Labs

```sql
-- Check: agent exists
SELECT COUNT(*) AS agent_count
FROM INFORMATION_SCHEMA.CORTEX_AGENTS
WHERE AGENT_NAME = '<AGENT_NAME>';
-- Expected: 1

-- Functional check: agent returns a non-empty response
-- Use TRY_PARSE_JSON to avoid hard failures if the agent errors.
SELECT
    CASE WHEN LENGTH(
        TRY_PARSE_JSON(
            SNOWFLAKE.CORTEX.DATA_AGENT_RUN(
                '<DB>.<SCHEMA>.<AGENT_NAME>',
                '{"messages":[{"role":"user","content":[{"type":"text","text":"How many rows are in the primary table?"}]}]}'
            )
        )::STRING
    ) > 0 THEN '✓ PASS — agent responded'
    ELSE '✗ FAIL — agent returned empty or null' END AS agent_functional_check;

-- In validate.sql UNION ALL pattern:
SELECT N, 'Module N: <AGENT_NAME> agent created',
    CASE WHEN (
        SELECT COUNT(*) FROM INFORMATION_SCHEMA.CORTEX_AGENTS
        WHERE AGENT_NAME ILIKE '%<AGENT_NAME_FRAGMENT>%'
    ) > 0 THEN 'PASS' ELSE 'FAIL' END
```

**Important:** The functional agent check (`DATA_AGENT_RUN`) can take 5-15 seconds.
Keep it in the facilitator smoke test (Layer 4) rather than the participant validate.sql
to avoid slow feedback loops during the workshop.

---

### 2.7 Snowflake Notebooks Labs

```sql
-- Check: notebook exists
SELECT COUNT(*) AS nb_count
FROM INFORMATION_SCHEMA.NOTEBOOKS
WHERE NAME = '<NOTEBOOK_NAME>';
-- Expected: 1

-- Check: notebook is in a runnable state
SELECT NAME, STATE, CREATED
FROM INFORMATION_SCHEMA.NOTEBOOKS
WHERE NAME ILIKE '%<NOTEBOOK_NAME_FRAGMENT>%';
-- Expected: STATE = 'ACTIVE' or 'AVAILABLE'
```

---

### 2.8 `module_N_check.sql` Template

```sql
-- ============================================================
-- Module N Completion Check: <Module Title>
-- Run this after completing Module N.
-- ============================================================

USE DATABASE <LAB_DB>;
USE SCHEMA <LAB_SCHEMA>;

SELECT sort_key, check_name, status,
    CASE status WHEN 'PASS' THEN '✓' ELSE '✗ re-run Module N' END AS icon
FROM (

    -- Check N.1: <description>
    SELECT 1,
        'N.1: <what was built>',
        CASE WHEN (
            -- Object existence check — adapt to the object type above
            SELECT COUNT(*) FROM INFORMATION_SCHEMA.<CATALOG_VIEW>
            WHERE <NAME_COLUMN> ILIKE '%<EXPECTED_NAME>%'
        ) > 0 THEN 'PASS' ELSE 'FAIL' END

    UNION ALL

    -- Check N.2: <description>
    SELECT 2,
        'N.2: <data check description>',
        CASE WHEN (SELECT COUNT(*) FROM <TABLE_OR_VIEW>) > 0
             THEN 'PASS' ELSE 'FAIL' END

)
ORDER BY sort_key;
```

---

## Layer 3 — Data-Aware Correctness Tests

Layer 2 checks *existence*. Layer 3 checks *correctness* — are the values right?
Run these as part of facilitator QA after dataset setup.

---

### 3.1 Row Count Range Checks

Use BETWEEN for synthetic data that may have slight variance across setups.

```sql
-- ============================================================
-- Row Count Range Checks
-- ============================================================

SELECT table_name, actual, expected_range, status FROM (
    SELECT
        'STREAMING_SESSIONS'     AS table_name,
        COUNT(*)                 AS actual,
        '45,000–55,000'          AS expected_range,
        CASE WHEN COUNT(*) BETWEEN 45000 AND 55000
             THEN '✓ PASS' ELSE '✗ FAIL' END AS status
    FROM HOL.STREAMING_SESSIONS

    UNION ALL

    SELECT
        'STREAMING_VIEWERSHIP_EVENTS',
        COUNT(*),
        '100,000–150,000',
        CASE WHEN COUNT(*) BETWEEN 100000 AND 150000
             THEN '✓ PASS' ELSE '✗ FAIL' END
    FROM HOL.STREAMING_VIEWERSHIP_EVENTS

    UNION ALL

    SELECT
        'DIM_TITLE',
        COUNT(*),
        '10–20',
        CASE WHEN COUNT(*) BETWEEN 10 AND 20
             THEN '✓ PASS' ELSE '✗ FAIL' END
    FROM HOL.DIM_TITLE
);
```

---

### 3.2 Column Completeness (No NULLs in Key Columns)

```sql
-- ============================================================
-- Column Completeness Check
-- ============================================================

SELECT column_check, null_count, status FROM (

    SELECT
        'STREAMING_SESSIONS.SESSION_ID nulls' AS column_check,
        COUNT(*) AS null_count,
        CASE WHEN COUNT(*) = 0 THEN '✓ PASS' ELSE '✗ FAIL' END AS status
    FROM HOL.STREAMING_SESSIONS
    WHERE SESSION_ID IS NULL

    UNION ALL

    SELECT
        'STREAMING_SESSIONS.USER_ID nulls',
        COUNT(*),
        CASE WHEN COUNT(*) = 0 THEN '✓ PASS' ELSE '✗ FAIL' END
    FROM HOL.STREAMING_SESSIONS
    WHERE USER_ID IS NULL

    UNION ALL

    SELECT
        'STREAMING_VIEWERSHIP_EVENTS.TITLE_ID nulls',
        COUNT(*),
        CASE WHEN COUNT(*) = 0 THEN '✓ PASS' ELSE '✗ FAIL' END
    FROM HOL.STREAMING_VIEWERSHIP_EVENTS
    WHERE TITLE_ID IS NULL

);
```

---

### 3.3 Join Integrity (FK → PK Orphan Check)

```sql
-- ============================================================
-- Join Integrity Check
-- Detects FK values in FACT that don't exist in DIM.
-- ============================================================

SELECT fk_check, orphan_count, status FROM (

    -- STREAMING_SESSIONS.PLATFORM_ID → DIM_PLATFORM.PLATFORM_ID
    SELECT
        'STREAMING_SESSIONS.PLATFORM_ID → DIM_PLATFORM' AS fk_check,
        COUNT(*) AS orphan_count,
        CASE WHEN COUNT(*) = 0 THEN '✓ PASS' ELSE '✗ FAIL — orphaned FK values' END AS status
    FROM HOL.STREAMING_SESSIONS s
    LEFT JOIN HOL.DIM_PLATFORM p ON s.PLATFORM_ID = p.PLATFORM_ID
    WHERE p.PLATFORM_ID IS NULL

    UNION ALL

    -- STREAMING_VIEWERSHIP_EVENTS.TITLE_ID → DIM_TITLE.TITLE_ID
    SELECT
        'STREAMING_VIEWERSHIP_EVENTS.TITLE_ID → DIM_TITLE',
        COUNT(*),
        CASE WHEN COUNT(*) = 0 THEN '✓ PASS' ELSE '✗ FAIL — orphaned FK values' END
    FROM HOL.STREAMING_VIEWERSHIP_EVENTS e
    LEFT JOIN HOL.DIM_TITLE t ON e.TITLE_ID = t.TITLE_ID
    WHERE t.TITLE_ID IS NULL

);
```

---

### 3.4 Aggregation Sanity Checks

```sql
-- ============================================================
-- Aggregation Sanity Checks
-- Validates that computed values fall within expected ranges.
-- ============================================================

SELECT metric, value, expected, status FROM (

    -- Total watch minutes must be positive
    SELECT
        'Total watch minutes > 0'      AS metric,
        SUM(WATCH_DURATION_MINUTES)    AS value,
        '> 0'                          AS expected,
        CASE WHEN SUM(WATCH_DURATION_MINUTES) > 0
             THEN '✓ PASS' ELSE '✗ FAIL' END AS status
    FROM HOL.STREAMING_SESSIONS

    UNION ALL

    -- Average session length within plausible range
    SELECT
        'Avg session length (minutes)',
        ROUND(AVG(WATCH_DURATION_MINUTES), 1),
        'BETWEEN 1 AND 300',
        CASE WHEN AVG(WATCH_DURATION_MINUTES) BETWEEN 1 AND 300
             THEN '✓ PASS' ELSE '✗ FAIL' END
    FROM HOL.STREAMING_SESSIONS

    UNION ALL

    -- Ticket/satisfaction scores in valid range (if applicable)
    SELECT
        'Avg ticket score BETWEEN 1 AND 5',
        ROUND(AVG(TICKET_SCORE), 2),
        'BETWEEN 1.0 AND 5.0',
        CASE WHEN AVG(TICKET_SCORE) BETWEEN 1.0 AND 5.0
             THEN '✓ PASS' ELSE '✗ FAIL' END
    FROM HOL.SUPPORT_TICKETS

);
```

---

### 3.5 AI Output Quality Spot Check

A proxy for "did the LLM return a meaningful response" without requiring a human to read it.
Length > a threshold is not a guarantee of quality, but it catches empty/null/error responses.

```sql
-- ============================================================
-- AI Output Quality Spot Check
-- ============================================================

SELECT check_name, response_length, status FROM (

    -- Cortex Complete returns non-trivial response
    SELECT
        'CORTEX.COMPLETE returns > 20 characters'  AS check_name,
        LENGTH(SNOWFLAKE.CORTEX.COMPLETE(
            'snowflake-arctic',
            'Summarize in one sentence: Cortex AI provides AI capabilities inside Snowflake.'
        ))                                          AS response_length,
        CASE WHEN LENGTH(SNOWFLAKE.CORTEX.COMPLETE(
            'snowflake-arctic',
            'Summarize in one sentence: Cortex AI provides AI capabilities inside Snowflake.'
        )) > 20
        THEN '✓ PASS' ELSE '✗ FAIL — LLM returned empty or very short response' END AS status

    UNION ALL

    -- AI_SUMMARIZE on a known column returns non-trivial output
    SELECT
        'AI_SUMMARIZE returns > 20 characters',
        LENGTH(AI_SUMMARIZE(DESCRIPTION)),
        CASE WHEN LENGTH(AI_SUMMARIZE(DESCRIPTION)) > 20
             THEN '✓ PASS' ELSE '✗ FAIL' END
    FROM HOL.DIM_TITLE
    LIMIT 1

);
```

**Note:** These checks consume Cortex credits. Run them once during facilitator QA,
not as part of the participant validate.sql.

---

### 3.6 Dynamic Table Freshness Check

```sql
-- ============================================================
-- Dynamic Table Freshness Check
-- Validates last refresh is within the configured target lag.
-- ============================================================

SELECT
    TABLE_NAME,
    TARGET_LAG,
    LAST_COMPLETED_REFRESH_TIME,
    TIMESTAMPDIFF(
        SECOND,
        LAST_COMPLETED_REFRESH_TIME,
        CURRENT_TIMESTAMP()
    ) AS seconds_since_refresh,
    CASE
        WHEN LAST_COMPLETED_REFRESH_TIME IS NULL
            THEN '✗ FAIL — never refreshed'
        WHEN TIMESTAMPDIFF(SECOND, LAST_COMPLETED_REFRESH_TIME, CURRENT_TIMESTAMP()) > <TARGET_LAG_SECONDS>
            THEN '✗ FAIL — refresh overdue (last refresh > target lag ago)'
        WHEN LAST_COMPLETED_REFRESH_STATE != 'SUCCEEDED'
            THEN '✗ FAIL — last refresh did not succeed: ' || LAST_COMPLETED_REFRESH_STATE
        ELSE '✓ PASS — refreshed within target lag'
    END AS status
FROM INFORMATION_SCHEMA.DYNAMIC_TABLES
WHERE TABLE_NAME IN ('<DT_NAME_1>', '<DT_NAME_2>')
ORDER BY TABLE_NAME;
```

---

### 3.7 `data_quality_check.sql` Template

```sql
-- ============================================================
-- Data Quality Check: <Lab Title>
-- Run AFTER setup.sql — confirms data is loaded correctly.
-- Intended for facilitator QA, not participant validation.
-- ============================================================

USE DATABASE <LAB_DB>;

SELECT sort_key, check_name, details, status FROM (

    -- 1. Row count range checks
    SELECT 1, '<PRIMARY_TABLE> row count in range',
        'Expected: BETWEEN <MIN> AND <MAX>',
        CASE WHEN (SELECT COUNT(*) FROM <LAB_SCHEMA>.<PRIMARY_TABLE>)
                  BETWEEN <MIN_ROWS> AND <MAX_ROWS>
             THEN '✓ PASS' ELSE '✗ FAIL' END

    UNION ALL

    -- 2. No NULLs in primary key
    SELECT 2, '<PRIMARY_TABLE>.<PK_COLUMN> has no NULLs',
        'Primary key integrity',
        CASE WHEN (SELECT COUNT(*) FROM <LAB_SCHEMA>.<PRIMARY_TABLE>
                   WHERE <PK_COLUMN> IS NULL) = 0
             THEN '✓ PASS' ELSE '✗ FAIL — NULL PKs detected' END

    UNION ALL

    -- 3. FK integrity
    SELECT 3, '<FACT>.<FK_COLUMN> → <DIM>.<PK_COLUMN> integrity',
        'No orphaned FK values',
        CASE WHEN (
            SELECT COUNT(*) FROM <LAB_SCHEMA>.<FACT> f
            LEFT JOIN <LAB_SCHEMA>.<DIM> d ON f.<FK_COLUMN> = d.<PK_COLUMN>
            WHERE d.<PK_COLUMN> IS NULL
        ) = 0 THEN '✓ PASS' ELSE '✗ FAIL — orphaned FK values exist' END

    UNION ALL

    -- 4. Aggregation sanity
    SELECT 4, '<METRIC_COLUMN> is in valid range',
        'Expected: BETWEEN <MIN_VAL> AND <MAX_VAL>',
        CASE WHEN (SELECT AVG(<METRIC_COLUMN>) FROM <LAB_SCHEMA>.<TABLE>)
                  BETWEEN <MIN_VAL> AND <MAX_VAL>
             THEN '✓ PASS' ELSE '✗ FAIL — metric out of range' END

)
ORDER BY sort_key;
```

---

## Layer 4 — End-to-End Smoke Test

Run this the night before a workshop. It consolidates all layers and outputs
a single `READY / NOT_READY` verdict with specific failure messages.

---

### 4.1 Smoke Test Pattern

```sql
-- ============================================================
-- End-to-End Smoke Test: <Lab Title>
-- Run the night before workshop delivery.
-- Expected final output: a single row with status = READY.
-- ============================================================

-- Step 1: Run pre-check
-- (Copy the body of pre_check.sql here, or use a stored procedure)

-- Step 2: Run all module checks
-- (Copy the UNION ALL blocks from each validate.sql here)

-- Step 3: Run data quality check
-- (Copy data_quality_check.sql body here)

-- Step 4: Aggregate into a single verdict
WITH all_checks AS (
    -- Pre-check results
    SELECT 'pre_check' AS layer, sort_key, check_name, status
    FROM ( /* paste pre_check.sql body */ )

    UNION ALL

    -- Module completion checks
    SELECT 'module_checks', sort_key, check_name, status
    FROM ( /* paste validate.sql body */ )

    UNION ALL

    -- Data quality checks
    SELECT 'data_quality', sort_key, check_name, status
    FROM ( /* paste data_quality_check.sql body */ )
),

failures AS (
    SELECT layer, check_name, status
    FROM all_checks
    WHERE status NOT ILIKE '%PASS%'
      AND status NOT ILIKE '%SKIP%'
)

SELECT
    CASE WHEN (SELECT COUNT(*) FROM failures) = 0
         THEN '✅ READY — all checks passed'
         ELSE '❌ NOT_READY — ' || (SELECT COUNT(*) FROM failures)::STRING || ' check(s) failed'
    END AS smoke_test_result,
    (SELECT COUNT(*) FROM all_checks)  AS total_checks,
    (SELECT COUNT(*) FROM failures)    AS failed_checks;

-- If NOT_READY, review the detail:
-- SELECT * FROM failures ORDER BY layer, check_name;
```

---

### 4.2 SE Pre-Workshop Checklist

The night before delivery, run through these steps in order:

```
1.  snow connection test -c default          # verify CoCo connects to the workshop account
2.  Run pre_check.sql                        # verify account capability + permissions
3.  Run setup.sql                            # (re)load data fresh
4.  Run data_quality_check.sql               # verify data loaded correctly
5.  Run validate.sql                         # verify all objectives would pass if done manually
6.  Run smoke_test.sql                       # single consolidated verdict
7.  Spot-test one CoCo prompt from the lab   # verify CoCo produces expected output
8.  Check facilitator_guide.md timing        # confirm your agenda matches lab duration
```

---

## CoCo Prompt Determinism Testing

CoCo-guided labs depend on prompts that produce consistent, convergent results
across participants. A prompt that works for you during development may produce
wildly different results for a participant using a different session context.

---

### What It Tests

The `prompt-determinism-tester` skill swarms 3 independent Plan agents against
each prompt and scores convergence on 6 dimensions:

| Dimension | Weight | What It Checks |
|-----------|--------|----------------|
| DDL Structure | 30% | Same table names, column names, data types |
| Object Names | 20% | Same semantic view / agent / table names |
| Execution Sequence | 15% | Steps occur in the same order |
| Feature Usage | 15% | Same Snowflake features invoked |
| Output Artifacts | 10% | Same files / objects produced |
| Row Counts | 10% | Same synthetic data volumes (if applicable) |

**Convergence threshold: 90%** — all 6 dimensions must score ≥ 90% before the prompt
is considered lab-safe. The skill enforces a sequential gate: Prompt N must reach 90%
before Prompt N+1 is tested.

---

### When to Run

Run the determinism tester:
- **Before any first live delivery** of a new lab (required)
- **After any prompt edit** (even small wording changes can shift convergence)
- **After data schema changes** (new columns/tables change what CoCo infers)

Do not skip this step for customer-facing workshops. A non-deterministic prompt
causes one participant to succeed and another to fail with no reproducible path.

---

### How to Invoke

In a CoCo session from the lab directory:

```
Use the prompt-determinism-tester skill. Test all prompts in prompts/01_easy_path.txt
for this lab. The lab database is MY_DB, schema HOL, warehouse COMPUTE_WH.
Run in AUTO mode — rewrite and retest any prompt that scores below 90%.
```

Or for a single prompt:

```
Use the prompt-determinism-tester skill. Test this single prompt for determinism:

"[paste prompt here]"

Lab context: database MY_DB, schema HOL, warehouse COMPUTE_WH, tables: SESSIONS, EVENTS, DIM_TITLE.
```

---

### Interpreting Results

| Score | Meaning | Action |
|-------|---------|--------|
| 90–100% | Lab-safe | No changes needed |
| 75–89% | Borderline | Rewrite recommended; acceptable for internal SE-only labs |
| 50–74% | Non-deterministic | Must rewrite before any delivery |
| < 50% | Fails | Prompt is too open-ended; rewrite required |

---

### Common Failure Patterns

**1. No schema context**

```
# BAD — CoCo has to guess
"Build a semantic view for streaming analytics."

# GOOD — CoCo has everything it needs
"I'm working in Snowflake database SONY_SPE_DEMO, schema HOL, warehouse COMPUTE_WH.
I have these tables: STREAMING_SESSIONS (session_id, user_id, platform_id, watch_duration_minutes),
DIM_TITLE (title_id, title_name, genre), DIM_PLATFORM (platform_id, platform_name).
Build a semantic view called SPE_STREAMING_ANALYTICS with dimensions for title, platform,
and genre, and metrics for total watch minutes and unique user count."
```

**2. Open-ended "improve" instructions**

```
# BAD — CoCo's interpretation of "improve" varies
"Improve the semantic view to make it more useful for analysts."

# GOOD — specific, bounded ask
"Add a metric called AVG_WATCH_DURATION_MINUTES to the SPE_STREAMING_ANALYTICS semantic view.
It should be the average of WATCH_DURATION_MINUTES from STREAMING_SESSIONS."
```

**3. No expected output specified**

```
# BAD — success criteria ambiguous
"Create a Cortex Search service on the title data."

# GOOD — expected output named
"Create a Cortex Search service called TITLE_SEARCH on the TITLE_NAME and DESCRIPTION
columns of HOL.DIM_TITLE. Use the warehouse COMPUTE_WH."
```

**4. Multi-step prompt with branching**

```
# BAD — step 2 depends on step 1's output which varies
"First explore the data, then decide which columns to use for a semantic view, then build it."

# GOOD — each step is bounded
"Step 1: Show me a sample of 5 rows from HOL.STREAMING_SESSIONS.
Step 2: Build a semantic view called SPE_STREAMING_ANALYTICS using these exact columns:
  dimensions: title_id, platform_id, region_id
  metrics: SUM(watch_duration_minutes) AS total_minutes, COUNT(DISTINCT user_id) AS unique_users"
```

---

## Testing by Lab Type — Quick Reference

| Lab | pre_check | module_checks | data_quality | smoke_test | determinism |
|-----|-----------|---------------|--------------|------------|-------------|
| **coco_semviews** | Required — Cortex + CORTEX_USER role + table load | SV existence + dimension count per module | Row count range + FK integrity on fact tables | Required before all deliveries | Required — 6 prompts, AUTO mode |
| **sony_spe** | Required — Cortex Complete + Cortex Search capability | SV + CSS + Agent existence (via validate.sql) | STREAMING_SESSIONS 50K rows, VIEWERSHIP_EVENTS 125K, no NULL SESSION_IDs | Required (facilitator) | N/A — Snowsight-only, no CoCo prompts |
| **cox_cci** | Required — dbt CLI, Cortex, Dynamic Table capability, CORTEX_USER | dbt views/marts per session; DT refresh state; SV per session | dbt model row counts, DT lag compliance, SV aggregation sanity | Required — 2-session lab; run full smoke test for each session | Required — Session 2 has CoCo optimization prompts |
| **streamlit-sis** | Required — Streamlit enabled + `INFORMATION_SCHEMA.STREAMLITS` accessible | STREAMLITS existence per module; skip `requests` library test (ModuleNotFoundError expected) | App loads without error (manual check); `GRANT USAGE` sharing verified | Required — verify `snow streamlit deploy` from correct directory | Required for any CoCo-assisted deployment prompts |
| **snowflake-notebooks** | Required — Notebooks enabled + `INFORMATION_SCHEMA.NOTEBOOKS` accessible | NOTEBOOKS existence + STATE = ACTIVE per module | Notebook cell output contains expected values (manual check) | Required | Required if CoCo generates notebook code |
| **dbt-snowflake** | Required — dbt CLI installed, Snowflake connection in profiles.yml | Staging views + mart tables existence + row count > 0 | Model row count ranges + FK integrity between marts | Required | Required — CoCo-guided dbt model generation prompts |
| **dynamic-tables** | Required — Dynamic Tables enabled + target warehouse access | DT existence + LAST_COMPLETED_REFRESH_STATE = SUCCEEDED | DT row count > 0 + freshness within target lag | Required | Required if prompts guide DT creation |

---

## File Placement Reference

```
labs/<lab-slug>/
├── sql/
│   ├── setup.sql              # Data load (existing)
│   ├── validate.sql           # Module completion checks — Layer 2 (existing)
│   ├── pre_check.sql          # Environment checks — Layer 1 (add per lab)
│   ├── data_quality_check.sql # Correctness checks — Layer 3 (add per lab)
│   └── smoke_test.sql         # Combined Layer 1+2+3 — Layer 4 (add per lab)
├── prompts/
│   └── *.txt                  # CoCo prompts (run through determinism tester)
└── solutions/
    └── facilitator_notes.md   # Known failure modes + facilitator fixes
```

---

## Appendix: INFORMATION_SCHEMA Views by Object Type

Quick reference for object existence checks in validate.sql:

| Object Type | INFORMATION_SCHEMA View | Key Column |
|-------------|------------------------|------------|
| Table | `INFORMATION_SCHEMA.TABLES` | `TABLE_NAME` |
| View | `INFORMATION_SCHEMA.VIEWS` | `TABLE_NAME` |
| Semantic View | `INFORMATION_SCHEMA.SEMANTIC_VIEWS` | `SEMANTIC_VIEW_NAME` |
| Streamlit App | `INFORMATION_SCHEMA.STREAMLITS` | `NAME` |
| Dynamic Table | `INFORMATION_SCHEMA.DYNAMIC_TABLES` | `TABLE_NAME` |
| Cortex Search | `INFORMATION_SCHEMA.CORTEX_SEARCH_SERVICES` | `SERVICE_NAME` |
| Cortex Agent | `INFORMATION_SCHEMA.CORTEX_AGENTS` | `AGENT_NAME` |
| Notebook | `INFORMATION_SCHEMA.NOTEBOOKS` | `NAME` |
| Stage | `INFORMATION_SCHEMA.STAGES` | `STAGE_NAME` |
| Task | `INFORMATION_SCHEMA.TASKS` | `TASK_NAME` |
| Alert | `INFORMATION_SCHEMA.ALERTS` | `ALERT_NAME` |

All views support `ILIKE '%FRAGMENT%'` for partial name matching.
Use exact match (`= 'NAME'`) when lab instructions specify exact object names.
Use `ILIKE` when participants may use slight variations.

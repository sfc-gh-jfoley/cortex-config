-- ============================================================
-- SE Grant Verification: <Lab Name>
-- ── OWNERSHIP ──────────────────────────────────────────────
-- Provisioned by: Customer DBA (runs facilitator_setup.sql)
-- Verified by:    Account SE (runs THIS script after DBA completes)
-- ── WHEN TO RUN ────────────────────────────────────────────
-- 1. When building a new lab: confirm every row = ✓ before scheduling
-- 2. Night before workshop: re-run as final sign-off
-- 3. After any DBA change: re-run to confirm nothing regressed
-- ── SIGN-OFF ───────────────────────────────────────────────
-- Every row must show ✓ PASS before you send participants pre-work.
-- Any ✗ FAIL = contact DBA with the missing grant shown in the message.
-- ============================================================

-- ── SET THESE VARIABLES ────────────────────────────────────
-- Confirm with the DBA before running:
SET hol_role       = 'HOL_ROLE';          -- ← participant role the DBA created
SET hol_db         = 'LAB_DATABASE';      -- ← lab database name
SET hol_wh         = 'COMPUTE_WH';        -- ← warehouse granted to participants
SET isolation      = 'schema';            -- ← 'schema' (Pattern A) or 'db' (Pattern B)

-- ============================================================
-- SECTION A — SE Verification
-- Run this to confirm the DBA's work is complete.
-- Each row = one grant. All rows must show ✓ PASS.
-- ============================================================

SELECT
    sort_key,
    module,
    grant_needed,
    CASE is_granted
        WHEN TRUE  THEN '✓ PASS'
        ELSE '✗ FAIL — send DBA: ' || fix_sql
    END AS verification_result
FROM (

    -- ── BASE: Warehouse usage ───────────────────────────────
    SELECT 1 AS sort_key,
        '00 base' AS module,
        'USAGE ON WAREHOUSE' AS grant_needed,
        (SELECT COUNT(*) > 0
         FROM SNOWFLAKE.ACCOUNT_USAGE.GRANTS_TO_ROLES
         WHERE GRANTEE_NAME = UPPER($hol_role)
           AND PRIVILEGE = 'USAGE'
           AND GRANTED_ON = 'WAREHOUSE'
           AND NAME = UPPER($hol_wh)
           AND DELETED_ON IS NULL) AS is_granted,
        'GRANT USAGE ON WAREHOUSE IDENTIFIER($hol_wh) TO ROLE IDENTIFIER($hol_role);' AS fix_sql

    UNION ALL

    -- ── BASE: Database usage (both patterns) ───────────────
    SELECT 2,
        '00 base',
        'USAGE ON DATABASE ' || UPPER($hol_db),
        (SELECT COUNT(*) > 0
         FROM SNOWFLAKE.ACCOUNT_USAGE.GRANTS_TO_ROLES
         WHERE GRANTEE_NAME = UPPER($hol_role)
           AND PRIVILEGE = 'USAGE'
           AND GRANTED_ON = 'DATABASE'
           AND NAME = UPPER($hol_db)
           AND DELETED_ON IS NULL),
        'GRANT USAGE ON DATABASE IDENTIFIER($hol_db) TO ROLE IDENTIFIER($hol_role);'

    UNION ALL

    -- ── PATTERN A: CREATE SCHEMA privilege ─────────────────
    -- Only relevant for schema-per-user isolation.
    -- For db-per-user (Pattern B), comment this block out.
    SELECT 3,
        '00 base (Pattern A)',
        'CREATE SCHEMA ON DATABASE ' || UPPER($hol_db),
        (SELECT COUNT(*) > 0
         FROM SNOWFLAKE.ACCOUNT_USAGE.GRANTS_TO_ROLES
         WHERE GRANTEE_NAME = UPPER($hol_role)
           AND PRIVILEGE = 'CREATE SCHEMA'
           AND GRANTED_ON = 'DATABASE'
           AND NAME = UPPER($hol_db)
           AND DELETED_ON IS NULL),
        'GRANT CREATE SCHEMA ON DATABASE IDENTIFIER($hol_db) TO ROLE IDENTIFIER($hol_role);'

    UNION ALL

    -- ── CORTEX: SNOWFLAKE.CORTEX_USER database role ────────
    -- Required for ALL labs that use SNOWFLAKE.CORTEX.COMPLETE or Cortex Search.
    -- Comment out if lab has no Cortex features.
    SELECT 10,
        '0X cortex',
        'DATABASE ROLE SNOWFLAKE.CORTEX_USER',
        (SELECT COUNT(*) > 0
         FROM SNOWFLAKE.ACCOUNT_USAGE.GRANTS_TO_ROLES
         WHERE GRANTEE_NAME = UPPER($hol_role)
           AND PRIVILEGE = 'USAGE'
           AND GRANTED_ON = 'DATABASE ROLE'
           AND NAME = 'SNOWFLAKE.CORTEX_USER'
           AND DELETED_ON IS NULL),
        'GRANT DATABASE ROLE SNOWFLAKE.CORTEX_USER TO ROLE IDENTIFIER($hol_role);'

    -- ── STREAMLIT: CREATE STREAMLIT on schema ──────────────
    -- Uncomment for Streamlit-in-Snowflake labs.
    -- For Pattern A, DBA should use FUTURE SCHEMAS (see fix_sql).
    -- UNION ALL
    -- SELECT 20,
    --     '0X streamlit',
    --     'CREATE STREAMLIT ON FUTURE SCHEMAS IN DATABASE ' || UPPER($hol_db),
    --     (SELECT COUNT(*) > 0
    --      FROM SNOWFLAKE.ACCOUNT_USAGE.GRANTS_TO_ROLES
    --      WHERE GRANTEE_NAME = UPPER($hol_role)
    --        AND PRIVILEGE = 'CREATE STREAMLIT'
    --        AND GRANT_OPTION = FALSE
    --        AND DELETED_ON IS NULL),
    --     'GRANT CREATE STREAMLIT ON FUTURE SCHEMAS IN DATABASE IDENTIFIER($hol_db) TO ROLE IDENTIFIER($hol_role);'

    -- ── DYNAMIC TABLES: CREATE DYNAMIC TABLE ───────────────
    -- Uncomment for Dynamic Tables labs.
    -- UNION ALL
    -- SELECT 21,
    --     '0X dynamic_tables',
    --     'CREATE DYNAMIC TABLE ON FUTURE SCHEMAS IN DATABASE ' || UPPER($hol_db),
    --     (SELECT COUNT(*) > 0
    --      FROM SNOWFLAKE.ACCOUNT_USAGE.GRANTS_TO_ROLES
    --      WHERE GRANTEE_NAME = UPPER($hol_role)
    --        AND PRIVILEGE = 'CREATE DYNAMIC TABLE'
    --        AND DELETED_ON IS NULL),
    --     'GRANT CREATE DYNAMIC TABLE ON FUTURE SCHEMAS IN DATABASE IDENTIFIER($hol_db) TO ROLE IDENTIFIER($hol_role);'

    -- ── NOTEBOOKS: CREATE NOTEBOOK ─────────────────────────
    -- Uncomment for Snowflake Notebooks labs.
    -- UNION ALL
    -- SELECT 22,
    --     '0X notebooks',
    --     'CREATE NOTEBOOK ON FUTURE SCHEMAS IN DATABASE ' || UPPER($hol_db),
    --     (SELECT COUNT(*) > 0
    --      FROM SNOWFLAKE.ACCOUNT_USAGE.GRANTS_TO_ROLES
    --      WHERE GRANTEE_NAME = UPPER($hol_role)
    --        AND PRIVILEGE = 'CREATE NOTEBOOK'
    --        AND DELETED_ON IS NULL),
    --     'GRANT CREATE NOTEBOOK ON FUTURE SCHEMAS IN DATABASE IDENTIFIER($hol_db) TO ROLE IDENTIFIER($hol_role);'

    -- ── DBT: CREATE TABLE / VIEW (write models) ─────────────
    -- Uncomment for dbt labs.
    -- UNION ALL
    -- SELECT 23,
    --     '0X dbt',
    --     'CREATE TABLE ON FUTURE SCHEMAS IN DATABASE ' || UPPER($hol_db),
    --     (SELECT COUNT(*) > 0
    --      FROM SNOWFLAKE.ACCOUNT_USAGE.GRANTS_TO_ROLES
    --      WHERE GRANTEE_NAME = UPPER($hol_role)
    --        AND PRIVILEGE = 'CREATE TABLE'
    --        AND DELETED_ON IS NULL),
    --     'GRANT CREATE TABLE ON FUTURE SCHEMAS IN DATABASE IDENTIFIER($hol_db) TO ROLE IDENTIFIER($hol_role);'

)
ORDER BY sort_key;


-- ============================================================
-- SECTION B — DBA Grant Block (reference)
-- Share this section with the DBA as the authoritative list
-- of what needs to be in facilitator_setup.sql.
-- SECTION A above verifies these are in place.
-- ============================================================

-- The DBA runs these in facilitator_setup.sql.
-- Replace <LAB_DB>, <HOL_ROLE>, <HOL_WH> with actual values.

/*
USE ROLE ACCOUNTADMIN;

-- ── BASE (all labs) ─────────────────────────────────────────
CREATE ROLE IF NOT EXISTS <HOL_ROLE>;
GRANT USAGE ON WAREHOUSE <HOL_WH> TO ROLE <HOL_ROLE>;

-- Pattern A (schema-per-user) — pick ONE of these two lines:
GRANT USAGE ON DATABASE <LAB_DB> TO ROLE <HOL_ROLE>;
GRANT CREATE SCHEMA ON DATABASE <LAB_DB> TO ROLE <HOL_ROLE>;

-- Pattern B (db-per-user) — run for EACH participant database:
-- GRANT OWNERSHIP ON DATABASE <HOL_USERNAME_DB> TO ROLE <HOL_ROLE> COPY CURRENT GRANTS;

-- ── CORTEX (if lab uses Cortex AI) ──────────────────────────
GRANT DATABASE ROLE SNOWFLAKE.CORTEX_USER TO ROLE <HOL_ROLE>;

-- ── STREAMLIT (if lab has SiS module) ───────────────────────
GRANT CREATE STREAMLIT ON FUTURE SCHEMAS IN DATABASE <LAB_DB> TO ROLE <HOL_ROLE>;

-- ── DYNAMIC TABLES (if lab has DT module) ───────────────────
GRANT CREATE DYNAMIC TABLE ON FUTURE SCHEMAS IN DATABASE <LAB_DB> TO ROLE <HOL_ROLE>;

-- ── NOTEBOOKS (if lab has Notebooks module) ─────────────────
GRANT CREATE NOTEBOOK ON FUTURE SCHEMAS IN DATABASE <LAB_DB> TO ROLE <HOL_ROLE>;

-- ── DBT (if lab has dbt module) ─────────────────────────────
GRANT CREATE TABLE ON FUTURE SCHEMAS IN DATABASE <LAB_DB> TO ROLE <HOL_ROLE>;
GRANT CREATE VIEW  ON FUTURE SCHEMAS IN DATABASE <LAB_DB> TO ROLE <HOL_ROLE>;

-- ── PARTICIPANT USERS (one per attendee) ────────────────────
-- DBA creates participant accounts and assigns to HOL_ROLE:
-- CREATE USER IF NOT EXISTS <USERNAME> ...;
-- GRANT ROLE <HOL_ROLE> TO USER <USERNAME>;
*/


-- ============================================================
-- SECTION C — Participant List Check
-- Confirm the expected participant usernames have the HOL_ROLE.
-- Run this after the DBA sends you the participant user list.
-- ============================================================

-- Replace with actual participant usernames before running:
-- SELECT grantee_name AS username, 'HOL_ROLE granted' AS status
-- FROM SNOWFLAKE.ACCOUNT_USAGE.GRANTS_TO_USERS
-- WHERE ROLE = UPPER('<HOL_ROLE>')
--   AND DELETED_ON IS NULL
-- ORDER BY grantee_name;

-- Expected: one row per confirmed participant.
-- If a participant is missing → ask DBA: GRANT ROLE <HOL_ROLE> TO USER <username>;

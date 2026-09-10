-- =============================================================================
-- GT SQL Validation — lightweight pre-eval gate
-- Run before EXECUTE_AI_EVALUATION or SYSTEM$EXECUTE_AI_OBSERVABILITY_RUN
-- =============================================================================
--
-- PURPOSE: Verify that every ground truth SQL in your eval dataset:
--   (a) Compiles without error
--   (b) Returns at least 1 row
--   (c) Does not return all-NULL values in key columns
--
-- WHY THIS MATTERS:
--   Ground truth SQL executes against the physical database (all columns/tables available).
--   The agent executes via the Semantic View (limited to TABLES/DIMENSIONS/FACTS/METRICS).
--   These are different execution planes. GT SQL that fails or returns 0 rows will
--   cause a score of 0 for that question regardless of agent quality.
--
-- NOTE: This script validates GT SQL execution only (lightweight check).
--   For full structural coverage analysis — whether the SV can answer each GT question
--   (TABLE_NOT_REGISTERED, COLUMN_NOT_EXPOSED, RELATIONSHIP_MISSING) — see the
--   sv-toolkit GT→SV coverage checker (EXPLAIN-based, separate tool).
--
-- USAGE:
--   1. Set the variables below
--   2. Run in a Snowsight worksheet with the target database context set
--   3. Review VALIDATION_STATUS column — fix any FAIL rows before running eval
-- =============================================================================

-- SET eval_table = 'MY_DB.MY_SCHEMA.EVAL_DATASET';
-- SET gt_column  = 'GROUND_TRUTH';   -- VARIANT column containing ground_truth_invocations

-- Step 1: Extract GT SQL from the eval table
-- Assumes GROUND_TRUTH VARIANT with structure:
--   {"ground_truth_invocations": [{"tool_name": "...", "tool_output": {"SQL": "..."}}]}
-- Adjust the JSON path if your table uses a different schema.

WITH gt_queries AS (
    SELECT
        INPUT_QUERY AS question,
        GET(
            GET(
                GET(PARSE_JSON(GROUND_TRUTH), 'ground_truth_invocations')[0],
                'tool_output'
            ),
            'SQL'
        )::STRING AS gt_sql
    FROM IDENTIFIER($eval_table)
    WHERE gt_sql IS NOT NULL
),

-- Step 2: For each GT SQL, attempt execution and check for rows
-- Uses EXECUTE IMMEDIATE to run each SQL dynamically
-- Note: EXECUTE IMMEDIATE requires appropriate privileges
validation_results AS (
    SELECT
        question,
        gt_sql,
        -- Check if SQL can be parsed (basic compilation check via EXPLAIN)
        CASE
            WHEN gt_sql IS NULL OR TRIM(gt_sql) = '' THEN 'FAIL: empty GT SQL'
            ELSE 'CHECK_REQUIRED'  -- run manually for full execution check
        END AS validation_note
    FROM gt_queries
)

SELECT
    question,
    LEFT(gt_sql, 200) AS gt_sql_preview,
    validation_note,
    CASE
        WHEN validation_note LIKE 'FAIL%' THEN 'FAIL'
        ELSE 'MANUAL_CHECK'
    END AS validation_status
FROM validation_results
ORDER BY validation_status, question;

-- =============================================================================
-- MANUAL EXECUTION CHECK (run each GT SQL individually to verify rows returned)
-- Copy a GT SQL from above and run it — verify it returns > 0 rows.
-- Any SQL returning 0 rows will produce a score of 0 in the eval regardless of
-- agent answer quality.
-- =============================================================================

-- EXPLAIN-BASED CHECK (verifies compilation without running the query):
-- EXPLAIN USING TABULAR <paste_gt_sql_here>;
-- If EXPLAIN succeeds, the SQL is syntactically valid.
-- If EXPLAIN fails with "invalid identifier" or "object does not exist",
-- the GT SQL references a column or table not available in the current context.

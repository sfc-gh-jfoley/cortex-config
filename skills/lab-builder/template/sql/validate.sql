-- ============================================================
-- Lab Completion Validator: <Lab Title>
-- Run this after completing all modules.
-- Each row prints PASS or FAIL for one learning objective.
-- ============================================================

USE DATABASE <LAB_DB>;
USE SCHEMA <LAB_SCHEMA>;

SELECT
    sort_key,
    check_name,
    status,
    CASE status WHEN 'PASS' THEN '✓' ELSE '✗' END AS icon,
    result
FROM (
    -- Objective 1: <describe>
    SELECT
        1                                                   AS sort_key,
        'Objective 1: <description>'                        AS check_name,
        CASE WHEN (SELECT COUNT(*) FROM <object>) > 0
             THEN 'PASS' ELSE 'FAIL'
        END                                                 AS status,
        CASE WHEN (SELECT COUNT(*) FROM <object>) > 0
             THEN 'Ready' ELSE 'Re-run the setup for Objective 1'
        END                                                 AS result

    UNION ALL

    -- Objective 2: <describe>
    SELECT
        2,
        'Objective 2: <description>',
        CASE WHEN (SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES
                   WHERE TABLE_SCHEMA = '<LAB_SCHEMA>'
                   AND TABLE_NAME = '<EXPECTED_TABLE>') > 0
             THEN 'PASS' ELSE 'FAIL'
        END,
        CASE WHEN (SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES
                   WHERE TABLE_SCHEMA = '<LAB_SCHEMA>'
                   AND TABLE_NAME = '<EXPECTED_TABLE>') > 0
             THEN 'Ready' ELSE 'Table <EXPECTED_TABLE> not found — re-run Module 2'
        END

    UNION ALL

    -- Objective 3: <describe>
    SELECT
        3,
        'Objective 3: <description>',
        CASE WHEN (SELECT COUNT(*) FROM INFORMATION_SCHEMA.SEMANTIC_VIEWS
                   WHERE SEMANTIC_VIEW_NAME = '<EXPECTED_SV>') > 0
             THEN 'PASS' ELSE 'FAIL'
        END,
        CASE WHEN (SELECT COUNT(*) FROM INFORMATION_SCHEMA.SEMANTIC_VIEWS
                   WHERE SEMANTIC_VIEW_NAME = '<EXPECTED_SV>') > 0
             THEN 'Ready' ELSE 'Semantic view <EXPECTED_SV> not found — re-run Module 3'
        END
)
ORDER BY sort_key;
-- All rows should show PASS. If any FAIL, re-run the relevant module.

-- sv_coverage_checker_deploy.sql
-- Run with: USE DATABASE <db>; USE SCHEMA <schema>; USE WAREHOUSE <wh>;

-- Step 1: create internal stage (if it doesn't exist)
CREATE STAGE IF NOT EXISTS SV_TOOLKIT_STAGE
    COMMENT = 'Stage for sv-toolkit Snowpark Python procedures';

-- Step 2: upload the Python file (run from your local machine)
-- snow sql -q "PUT file:///path/to/sv_coverage_checker.py @SV_TOOLKIT_STAGE/ AUTO_COMPRESS=FALSE OVERWRITE=TRUE"

-- Step 3: create the procedure
CREATE OR REPLACE PROCEDURE SV_COVERAGE_CHECKER(
    GT_TABLE VARCHAR,
    SV_NAME  VARCHAR
)
RETURNS VARIANT
LANGUAGE PYTHON
RUNTIME_VERSION = '3.11'
PACKAGES = ('snowflake-snowpark-python')
IMPORTS = ('@SV_TOOLKIT_STAGE/sv_coverage_checker.py')
HANDLER = 'sv_coverage_checker.sv_coverage_checker'
EXECUTE AS CALLER
COMMENT = 'GT SQL vs Semantic View coverage checker. Diffs explain-plan workload manifest against SV DDL. Returns gaps[] + verdicts[] + summary{}.';

-- Step 4: verify
DESCRIBE PROCEDURE SV_COVERAGE_CHECKER(VARCHAR, VARCHAR);

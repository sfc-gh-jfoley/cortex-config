-- ============================================================
-- Lab Setup: <Lab Title>
-- Database: <LAB_DB>
-- Schema:   <LAB_SCHEMA>
-- Idempotent: YES — safe to re-run (uses CREATE OR REPLACE)
-- ============================================================

-- Create lab database and schema
CREATE DATABASE IF NOT EXISTS <LAB_DB>;
USE DATABASE <LAB_DB>;
CREATE SCHEMA IF NOT EXISTS <LAB_SCHEMA>;
USE SCHEMA <LAB_SCHEMA>;

-- ============================================================
-- Tables
-- ============================================================

CREATE OR REPLACE TABLE TABLE_A (
    ID          NUMBER      NOT NULL,
    NAME        VARCHAR(100),
    CREATED_AT  TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP()
);

CREATE OR REPLACE TABLE TABLE_B (
    ID          NUMBER      NOT NULL,
    A_ID        NUMBER      REFERENCES TABLE_A(ID),  -- NOTE: Snowflake FKs are informational only — not enforced at runtime
    VALUE       FLOAT,
    STATUS      VARCHAR(20)
);

-- ============================================================
-- Synthetic Data
-- ============================================================

INSERT INTO TABLE_A (ID, NAME) VALUES
    (1, 'Row One'),
    (2, 'Row Two'),
    (3, 'Row Three');

INSERT INTO TABLE_B (ID, A_ID, VALUE, STATUS) VALUES
    (1, 1, 100.0, 'active'),
    (2, 1,  75.5, 'active'),
    (3, 2,  50.0, 'inactive');

-- ============================================================
-- Verification (run manually to confirm setup)
-- ============================================================
SELECT 'TABLE_A' AS table_name, COUNT(*) AS row_count FROM TABLE_A
UNION ALL
SELECT 'TABLE_B', COUNT(*) FROM TABLE_B;
-- Expected: TABLE_A=3, TABLE_B=3

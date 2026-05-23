-- ============================================================
-- Lab Teardown — Pattern A (Schema-per-User Isolation)
-- Drops only the participant's schema from the shared lab database.
-- The shared database is LEFT INTACT.
-- ============================================================
-- SAFETY WARNING: This file is for Pattern A labs ONLY.
-- NEVER use this file for Pattern B (database-per-user) labs —
-- those must use teardown_pattern_b.sql instead.
-- ============================================================

USE DATABASE IDENTIFIER($MY_DB);

DROP SCHEMA IF EXISTS IDENTIFIER($MY_SCHEMA);

-- Verify cleanup
SELECT 'Teardown complete. Schema ' || $MY_SCHEMA || ' removed from ' || $MY_DB || '.' AS status;

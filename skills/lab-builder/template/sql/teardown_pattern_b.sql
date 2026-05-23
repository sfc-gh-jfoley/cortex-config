-- ============================================================
-- Lab Teardown — Pattern B (Database-per-User Isolation)
-- Drops the participant's entire dedicated lab database.
-- ============================================================
-- SAFETY WARNING: This file is for Pattern B labs ONLY.
-- NEVER use this file for Pattern A (schema-per-user) labs —
-- that would drop the shared lab database and affect ALL participants.
-- ============================================================

DROP DATABASE IF EXISTS IDENTIFIER($MY_DB);

-- Verify cleanup
SELECT 'Teardown complete. Database ' || $MY_DB || ' removed.' AS status;

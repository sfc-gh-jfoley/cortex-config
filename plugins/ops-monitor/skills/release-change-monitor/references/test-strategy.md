# Test Strategy — BCR Bundle Testing Workflow

## Overview

Snowflake's behavior change bundle system provides built-in opt-in/opt-out mechanisms that enable safe testing before changes become mandatory. This reference describes how to leverage these mechanisms for a structured test plan.

## Prerequisites

- **Non-production account** (dev/QA) with representative pipeline copies
- **ACCOUNTADMIN** role (required for `SYSTEM$ENABLE_BEHAVIOR_CHANGE_BUNDLE`)
- Pipeline inventory and impact analysis from Phases 2-3

## Test Plan Structure

### Step 1 — Verify Current Bundle Status

```sql
-- Check current Snowflake version
SELECT CURRENT_VERSION();

-- List behavior change bundles and their status
-- (No direct SQL for this — check the docs page or use the announcements index)
```

Check the bundle lifecycle status:
- If **Disabled by Default** → safe to enable for testing, can disable after
- If **Enabled by Default** → already active unless explicitly disabled; test by disabling then re-enabling
- If **Generally Enabled** → cannot toggle; must be compliant

### Step 2 — Prepare Test Environment

**Option A: Dedicated test account (recommended)**
- Use a separate Snowflake account designated for early access testing
- Clone production data via data sharing or replication
- This isolates testing from any dev work

**Option B: Dev/QA account with bundle toggle**
- Use existing dev account
- Enable the bundle, run tests, disable when done

**Clone critical objects for testing:**

```sql
CREATE DATABASE <db>_BCR_TEST CLONE <db>;
```

This gives a zero-copy snapshot to test against without affecting dev pipelines.

### Step 3 — Enable the Bundle

```sql
-- Enable the target bundle for testing
SELECT SYSTEM$ENABLE_BEHAVIOR_CHANGE_BUNDLE('<YYYY_NN>');
```

Verify it's enabled:
```sql
SELECT SYSTEM$BEHAVIOR_CHANGE_BUNDLE_STATUS('<YYYY_NN>');
```

### Step 4 — Run Pipeline Regression Tests

For each CRITICAL and WARNING item from the impact analysis, run targeted tests:

#### 4a — Task-Based Pipelines

```sql
-- Execute the task manually (in test database)
EXECUTE TASK <db>_BCR_TEST.<schema>.<task_name>;

-- Check task history for failures
SELECT *
FROM TABLE(INFORMATION_SCHEMA.TASK_HISTORY(
  TASK_NAME => '<task_name>',
  SCHEDULED_TIME_RANGE_START => DATEADD('hour', -1, CURRENT_TIMESTAMP())
))
ORDER BY SCHEDULED_TIME DESC;
```

#### 4b — Stored Procedures

```sql
-- Call the procedure with representative inputs
CALL <db>_BCR_TEST.<schema>.<procedure_name>(<test_args>);

-- Compare output to expected results
```

#### 4c — Dynamic Tables

```sql
-- Force refresh
ALTER DYNAMIC TABLE <db>_BCR_TEST.<schema>.<dt_name> REFRESH;

-- Check refresh history
SELECT *
FROM TABLE(INFORMATION_SCHEMA.DYNAMIC_TABLE_REFRESH_HISTORY(
  NAME => '<db>_BCR_TEST.<schema>.<dt_name>'
))
ORDER BY REFRESH_START_TIME DESC
LIMIT 5;
```

#### 4d — Views and Queries

```sql
-- Run representative queries against test clone
SELECT * FROM <db>_BCR_TEST.<schema>.<view_name> LIMIT 100;

-- Compare row counts and sample values to production baseline
SELECT COUNT(*) FROM <db>_BCR_TEST.<schema>.<view_name>;
```

#### 4e — Data Loading (Pipes/COPY)

```sql
-- Test COPY INTO with representative files
COPY INTO <db>_BCR_TEST.<schema>.<table>
FROM @<stage>/<test_file>
ON_ERROR = 'CONTINUE'
VALIDATION_MODE = 'RETURN_ALL_ERRORS';
```

### Step 5 — Record Results

For each test:

| Test # | Object | Test Type | Result | Notes |
|--------|--------|-----------|--------|-------|
| 1 | PROD.ETL.PARSE_JSON_PROC | Procedure call | PASS/FAIL | Description of failure |
| 2 | PROD.ETL.DAILY_LOAD_TASK | Task execution | PASS/FAIL | Error message if any |

### Step 6 — Apply Fixes and Re-Test

For any FAIL results:
1. Apply the remediation from Phase 4 to the test clone objects
2. Re-run the failed tests
3. Verify PASS
4. Mark the remediation item as "tested and ready"

### Step 7 — Disable Bundle (if in Testing Period)

```sql
-- Disable after testing (only works during Testing and Opt-out periods)
SELECT SYSTEM$DISABLE_BEHAVIOR_CHANGE_BUNDLE('<YYYY_NN>');
```

### Step 8 — Apply Fixes to Production

Once all tests pass:

1. Apply remediation SQL to production objects (use the before/after diffs from Phase 4)
2. Do NOT enable the bundle in production — let it follow the natural lifecycle
3. When the bundle moves to Enabled by Default, production will already be compliant

### Step 9 — Clean Up

```sql
-- Drop test clone
DROP DATABASE <db>_BCR_TEST;
```

## Recommended Test Cadence

| Bundle Lifecycle Stage | Action |
|----------------------|--------|
| **Disabled by Default (Month 1)** | Enable in dev → run full regression → apply fixes → disable |
| **Enabled by Default (Month 2)** | Verify production is compliant. If not, disable in prod while fixing, then re-enable. |
| **Generally Enabled (Month 3)** | No action possible. Must be compliant. |

**Ideal timeline:**
- Week 1-2 after bundle introduction: Run Phases 1-3 (scan + impact)
- Week 2-3: Generate remediation plan (Phase 4), apply fixes in dev
- Week 3-4: Run test strategy (Phase 5), validate all fixes
- Before Month 2: Deploy fixes to production

## Automation Opportunities

For customers who want to automate this:

1. **Snowflake Task** — Schedule a monthly task that runs `SYSTEM$BEHAVIOR_CHANGE_BUNDLE_STATUS` and alerts via email/Slack if a new bundle is detected
2. **Notification Integration** — Use Snowflake's notification integration to send alerts when bundle status changes
3. **CI/CD Integration** — Include BCR bundle testing in deployment pipelines:
   - Enable upcoming bundle → run test suite → fail pipeline if tests break → report results

## Rollback

If a bundle causes production issues and is in the opt-out period:

```sql
-- Emergency disable in production
SELECT SYSTEM$DISABLE_BEHAVIOR_CHANGE_BUNDLE('<YYYY_NN>');
```

If the bundle is Generally Enabled and causing issues:
- Contact Snowflake Support to request a temporary exemption for specific changes
- Apply fixes as quickly as possible

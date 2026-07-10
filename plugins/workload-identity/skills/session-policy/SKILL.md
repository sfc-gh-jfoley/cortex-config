---
name: session-policy
description: >
  Create and manage Snowflake Session Policies (GA Apr 2026). Set session
  lifespan constraints (SESSION_MAX_LIFESPAN_MINS, SESSION_UI_MAX_LIFESPAN_MINS),
  apply policies to roles, and troubleshoot session expiration issues.
---

# Session Policy Sub-Skill

Create and manage Snowflake Session Policies to enforce maximum session lifespans and UI-specific idle timeouts.

## Overview

Session Policies (GA Apr 2026) allow you to:
- Set `SESSION_MAX_LIFESPAN_MINS` — maximum total session lifetime (from login to logout)
- Set `SESSION_UI_MAX_LIFESPAN_MINS` — maximum UI-specific idle timeout (Snowsight, Classic Console)
- Apply policies to roles to enforce organizational session requirements
- Audit session policy violations and enforce expiration

This sub-skill guides you through:
1. **Phase 0**: Prerequisites and constraints
2. **Phase 1**: Choose policy strategy (max lifespan vs idle timeout)
3. **Phase 2**: Create SESSION POLICY
4. **Phase 3**: Apply policy to role
5. **Phase 4**: Test and troubleshoot

---

## Phase 0: Prerequisites and Constraints

Before creating a session policy, verify:

- ✅ Snowflake account on any edition (feature is GA)
- ✅ Current role has `CREATE SESSION POLICY` privilege in the database
- ✅ Target role exists (or will be created)
- ✅ You understand the difference between max lifespan and UI-specific timeout

**Check your setup:**

```sql
-- 1. Verify current role has CREATE privilege
SHOW GRANTS ON DATABASE <DB>;
-- Look for CREATE SESSION POLICY in the results

-- 2. List existing session policies
SHOW SESSION POLICIES IN DATABASE <DB>;

-- 3. Check active session lifespan for comparison
SELECT
  SESSION_ID,
  USER_NAME,
  CREATED_ON,
  UPDATED_ON
FROM TABLE(INFORMATION_SCHEMA.SESSIONS())
ORDER BY CREATED_ON DESC
LIMIT 10;
```

If you lack `CREATE SESSION POLICY` privilege, ask your account admin to grant it:
```sql
GRANT CREATE SESSION POLICY ON DATABASE <DB> TO ROLE <YOUR_ROLE>;
```

---

## Phase 1: Choose Policy Strategy

Session policies enforce two types of constraints:

### Strategy A: Max Lifespan (Total Session Duration)

**When to use:**
- Enforce strict session expiration (e.g., "no session lasts longer than 12 hours")
- Comply with security policies that require re-authentication
- Prevent long-running unattended sessions

**Example:**
```
SESSION_MAX_LIFESPAN_MINS = 720  (12 hours)
```

After 720 minutes of total session time (regardless of activity), user must log out and log back in.

### Strategy B: UI-Specific Idle Timeout

**When to use:**
- Protect against unattended Snowsight/UI sessions
- Allow programmatic (SDK/API) sessions to run longer without interruption
- Enforce "log out after N minutes of inactivity" in UI only

**Example:**
```
SESSION_UI_MAX_LIFESPAN_MINS = 60  (1 hour UI timeout)
```

After 60 minutes of inactivity in Snowsight, session expires. SDKs and `snow` CLI are unaffected.

### Strategy C: Both (Combined)

**When to use:**
- Enforce both total lifespan AND UI-specific timeout
- E.g., "max 12 hours total, but UI logs out after 60 min inactivity"

**Example:**
```
SESSION_MAX_LIFESPAN_MINS = 720
SESSION_UI_MAX_LIFESPAN_MINS = 60
```

---

## Phase 2: Create SESSION POLICY

Choose your strategy above and execute the corresponding CREATE statement.

### Option A: Max Lifespan Only

```sql
CREATE SESSION POLICY <DB>.<SCHEMA>.<POLICY_NAME>
  SESSION_MAX_LIFESPAN_MINS = 720;  -- 12 hours
```

**Common values:**
- `480` = 8 hours
- `720` = 12 hours
- `1440` = 24 hours

### Option B: UI-Specific Idle Timeout Only

```sql
CREATE SESSION POLICY <DB>.<SCHEMA>.<POLICY_NAME>
  SESSION_UI_MAX_LIFESPAN_MINS = 60;  -- 1 hour UI timeout
```

**Common values:**
- `30` = 30 minutes
- `60` = 1 hour
- `120` = 2 hours

### Option C: Both Constraints

```sql
CREATE SESSION POLICY <DB>.<SCHEMA>.<POLICY_NAME>
  SESSION_MAX_LIFESPAN_MINS = 720
  SESSION_UI_MAX_LIFESPAN_MINS = 60;
```

---

## Phase 3: Apply Policy to Role

After creating the policy, attach it to one or more roles:

```sql
-- Single role
ALTER ROLE <ROLE_NAME> SET SESSION POLICY <DB>.<SCHEMA>.<POLICY_NAME>;

-- Multiple roles (one command per role, or use a loop)
ALTER ROLE analyst_role SET SESSION POLICY <DB>.<SCHEMA>.<POLICY_NAME>;
ALTER ROLE data_engineer_role SET SESSION POLICY <DB>.<SCHEMA>.<POLICY_NAME>;
ALTER ROLE finance_role SET SESSION POLICY <DB>.<SCHEMA>.<POLICY_NAME>;
```

**Verify the role has the policy attached:**

```sql
SHOW GRANTS ON ROLE <ROLE_NAME>;
-- Look for SESSION POLICY in the results

-- Or describe the role to see applied policies
DESC ROLE <ROLE_NAME>;
```

---

## Phase 4: Test and Troubleshoot

### Test: Verify Policy Is Active

1. **Log in as a user with the target role:**
   ```sql
   USE ROLE <ROLE_NAME>;
   SELECT CURRENT_SESSION_LIFESPAN_MINS(), CURRENT_UI_SESSION_LIFESPAN_MINS();
   ```

2. **For UI timeout:** Open Snowsight, wait for the timeout period to elapse, and verify session expires
   - If `SESSION_UI_MAX_LIFESPAN_MINS = 60`, wait 60 minutes of inactivity
   - Snowsight will prompt to re-authenticate

3. **For max lifespan:** Monitor session and verify expiration after the max duration
   ```sql
   SELECT
     SESSION_ID,
     USER_NAME,
     CREATED_ON,
     TIMEDIFF(MINUTE, CREATED_ON, CURRENT_TIMESTAMP()) AS minutes_active
   FROM TABLE(INFORMATION_SCHEMA.SESSIONS())
   WHERE USER_NAME = '<TEST_USER>';
   ```

### Troubleshoot: Session Not Expiring

**Symptom:** User session does not expire after the configured timeout

**Root causes and fixes:**

1. **Policy not attached to role:**
   ```sql
   -- Verify policy attachment
   SHOW GRANTS ON ROLE <ROLE_NAME> LIKE '%SESSION%';
   
   -- Re-attach if missing
   ALTER ROLE <ROLE_NAME> SET SESSION POLICY <DB>.<SCHEMA>.<POLICY_NAME>;
   ```

2. **User has multiple roles with conflicting policies:**
   ```sql
   -- Check all roles
   SHOW ROLES GRANTED TO USER <USERNAME>;
   
   -- Each role may have its own policy; the most restrictive applies
   ```

3. **Session was created before policy was attached:**
   - User must log out and log back in for the policy to take effect
   - Existing sessions are not retroactively terminated

4. **UI timeout not working in SDK/CLI:**
   - `SESSION_UI_MAX_LIFESPAN_MINS` applies ONLY to Snowsight/web UI
   - SDKs (`snowflake-connector-python`, `snowpark`) and `snow` CLI are unaffected
   - Use `SESSION_MAX_LIFESPAN_MINS` for all-channel enforcement

### Troubleshoot: Overly Aggressive Expiration

**Symptom:** Users are logged out too frequently (timeout is too short)

**Solution:**

```sql
-- Increase the timeout
ALTER SESSION POLICY <DB>.<SCHEMA>.<POLICY_NAME>
  SET SESSION_UI_MAX_LIFESPAN_MINS = 120;  -- Increase from 60 to 120 minutes

-- Or remove the policy from the role
ALTER ROLE <ROLE_NAME> UNSET SESSION POLICY;
```

---

## Common Patterns

### Pattern 1: Strict Security (Finance/Compliance)

```sql
CREATE SESSION POLICY prod_finance_strict
  SESSION_MAX_LIFESPAN_MINS = 480      -- 8 hours max
  SESSION_UI_MAX_LIFESPAN_MINS = 30;   -- 30 min UI timeout

ALTER ROLE finance_analyst SET SESSION POLICY prod_finance_strict;
ALTER ROLE finance_manager SET SESSION POLICY prod_finance_strict;
```

### Pattern 2: Balanced (Data Science)

```sql
CREATE SESSION POLICY data_science_balanced
  SESSION_MAX_LIFESPAN_MINS = 1440       -- 24 hours max
  SESSION_UI_MAX_LIFESPAN_MINS = 120;    -- 2 hours UI timeout

ALTER ROLE data_scientist SET SESSION POLICY data_science_balanced;
```

### Pattern 3: Long-Running Jobs (Automation)

```sql
CREATE SESSION POLICY automation_batch_jobs
  SESSION_MAX_LIFESPAN_MINS = 10080;     -- 7 days max (for batch jobs)

ALTER ROLE automation_service SET SESSION POLICY automation_batch_jobs;
-- Note: No UI timeout set; SDKs can run for up to 7 days
```

---

## Audit and Monitor

### View all session policies in your database:

```sql
SHOW SESSION POLICIES IN DATABASE <DB>;
```

### View policies applied to a role:

```sql
SHOW GRANTS ON ROLE <ROLE_NAME> LIKE '%SESSION%';
```

### View active sessions and their current lifespan:

```sql
SELECT
  SESSION_ID,
  USER_NAME,
  CREATED_ON,
  TIMEDIFF(MINUTE, CREATED_ON, CURRENT_TIMESTAMP()) AS minutes_active,
  CURRENT_SESSION_LIFESPAN_MINS() AS max_session_mins,
  CURRENT_UI_SESSION_LIFESPAN_MINS() AS ui_timeout_mins
FROM TABLE(INFORMATION_SCHEMA.SESSIONS())
ORDER BY CREATED_ON DESC;
```

---

## Next Steps

- **Need to update an existing policy?** Use `ALTER SESSION POLICY`
- **Need to remove a policy from a role?** Use `ALTER ROLE <ROLE> UNSET SESSION POLICY`
- **Need to delete a policy?** Use `DROP SESSION POLICY <DB>.<SCHEMA>.<POLICY_NAME>`
- **Experiencing session expirations?** See "Troubleshoot" section above

---
name: session-policy
description: >
  Create and manage Snowflake Session Policies (GA Apr 2026). Set session
  lifespan constraints (SESSION_MAX_LIFESPAN_MINS, SESSION_UI_MAX_LIFESPAN_MINS),
  apply policies to roles, and troubleshoot session expiration issues.
triggers:
  - session policy
  - session timeout
  - session expiration
  - session lifespan
  - SESSION_MAX_LIFESPAN_MINS
  - SESSION_UI_MAX_LIFESPAN_MINS
  - re-authentication
  - idle timeout
  - session management
---

# Session Policy Skill

Create and manage Snowflake Session Policies to enforce maximum session lifespans and UI-specific idle timeouts.

## Overview

Session Policies (GA Apr 2026) allow you to:
- Set `SESSION_MAX_LIFESPAN_MINS` — maximum total session lifetime (from login to logout)
- Set `SESSION_UI_MAX_LIFESPAN_MINS` — maximum UI-specific idle timeout (Snowsight, Classic Console)
- Apply policies to roles to enforce organizational session requirements
- Audit session policy violations and enforce expiration

This skill guides you through:
1. **Phase 0**: Prerequisites and constraints
2. **Phase 1**: Choose policy strategy (max lifespan vs idle timeout)
3. **Phase 2**: Create SESSION POLICY
4. **Phase 3**: Apply policy to role
5. **Phase 4**: Test and troubleshoot

---

## Phase 0: Prerequisites and Constraints

Before creating a session policy, verify:

- Snowflake account on any edition (feature is GA)
- Current role has `CREATE SESSION POLICY` privilege in the database
- Target role exists (or will be created)
- You understand the difference between max lifespan and UI-specific timeout

```sql
-- Verify current role has CREATE privilege
SHOW GRANTS ON DATABASE <DB>;
-- Look for CREATE SESSION POLICY in the results

-- List existing session policies
SHOW SESSION POLICIES IN DATABASE <DB>;
```

If you lack `CREATE SESSION POLICY` privilege:
```sql
GRANT CREATE SESSION POLICY ON DATABASE <DB> TO ROLE <YOUR_ROLE>;
```

---

## Phase 1: Choose Policy Strategy

### Strategy A: Max Lifespan (Total Session Duration)

Enforce "no session lasts longer than N hours" regardless of activity. After the limit,
users must re-authenticate. Applies to all clients (UI, SDK, CLI).

```
SESSION_MAX_LIFESPAN_MINS = 720  (12 hours)
```

### Strategy B: UI-Specific Idle Timeout

Protect against unattended Snowsight sessions. Programmatic clients (SDK, CLI) are unaffected.

```
SESSION_UI_MAX_LIFESPAN_MINS = 60  (1 hour UI inactivity timeout)
```

### Strategy C: Both

```
SESSION_MAX_LIFESPAN_MINS = 720        -- 12h absolute max
SESSION_UI_MAX_LIFESPAN_MINS = 60      -- 1h UI inactivity
```

---

## Phase 2: Create SESSION POLICY

```sql
-- Max lifespan only
CREATE SESSION POLICY <DB>.<SCHEMA>.<POLICY_NAME>
  SESSION_MAX_LIFESPAN_MINS = 720;

-- UI idle timeout only
CREATE SESSION POLICY <DB>.<SCHEMA>.<POLICY_NAME>
  SESSION_UI_MAX_LIFESPAN_MINS = 60;

-- Both constraints
CREATE SESSION POLICY <DB>.<SCHEMA>.<POLICY_NAME>
  SESSION_MAX_LIFESPAN_MINS = 720
  SESSION_UI_MAX_LIFESPAN_MINS = 60;
```

Common values: `480` = 8h, `720` = 12h, `1440` = 24h, `10080` = 7 days

---

## Phase 3: Apply Policy to Role

```sql
ALTER ROLE <ROLE_NAME> SET SESSION POLICY <DB>.<SCHEMA>.<POLICY_NAME>;

-- Verify
SHOW GRANTS ON ROLE <ROLE_NAME>;
```

Changes apply to new sessions only. Existing sessions are not terminated retroactively.

---

## Phase 4: Test and Troubleshoot

### Verify policy is active
```sql
USE ROLE <ROLE_NAME>;
SELECT CURRENT_SESSION_LIFESPAN_MINS(), CURRENT_UI_SESSION_LIFESPAN_MINS();
```

### Session not expiring?
1. Policy not attached to role → re-run `ALTER ROLE ... SET SESSION POLICY`
2. Session created before policy was applied → user must log out/in
3. SDK/CLI not expiring on UI timeout → expected; `SESSION_UI_MAX_LIFESPAN_MINS` is UI-only

### Expiration too aggressive?
```sql
ALTER SESSION POLICY <DB>.<SCHEMA>.<POLICY_NAME>
  SET SESSION_UI_MAX_LIFESPAN_MINS = 120;

-- Or remove from role
ALTER ROLE <ROLE_NAME> UNSET SESSION POLICY;
```

---

## Common Patterns

```sql
-- Finance/Compliance: strict
CREATE SESSION POLICY finance_strict
  SESSION_MAX_LIFESPAN_MINS = 480
  SESSION_UI_MAX_LIFESPAN_MINS = 30;
ALTER ROLE finance_analyst SET SESSION POLICY finance_strict;

-- Data Science: balanced
CREATE SESSION POLICY ds_balanced
  SESSION_MAX_LIFESPAN_MINS = 1440
  SESSION_UI_MAX_LIFESPAN_MINS = 120;
ALTER ROLE data_scientist SET SESSION POLICY ds_balanced;

-- Automation: long-running jobs
CREATE SESSION POLICY automation_long
  SESSION_MAX_LIFESPAN_MINS = 10080;  -- 7 days, no UI timeout
ALTER ROLE automation_service SET SESSION POLICY automation_long;
```

---

## Audit

```sql
-- All session policies
SHOW SESSION POLICIES IN DATABASE <DB>;

-- Active sessions and lifespan
SELECT SESSION_ID, USER_NAME, CREATED_ON,
  TIMEDIFF(MINUTE, CREATED_ON, CURRENT_TIMESTAMP()) AS minutes_active
FROM TABLE(INFORMATION_SCHEMA.SESSIONS())
ORDER BY CREATED_ON DESC;
```

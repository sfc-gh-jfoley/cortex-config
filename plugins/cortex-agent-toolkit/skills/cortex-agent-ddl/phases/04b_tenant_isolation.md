---
name: cortex-agent-ddl-phase4b-tenant-isolation
description: Multitenant isolation patterns — RAP + session attribute wiring for agents serving multiple tenants. Activated conditionally when IS_MULTITENANT=true in Phase 1.
---

# Phase 4b: Tenant Isolation (Conditional)

## When this phase activates

This phase runs **only** when `IS_MULTITENANT = true` was set in Phase 1 (Step 1.2.5). If `IS_MULTITENANT = false`, skip directly to Phase 5.

**Insert point**: After Phase 4 (Assemble Spec), before Phase 5 (Self-Check).

---

## Purpose

Document and wire the tenant isolation pattern for agents that serve multiple tenants from shared base tables. The agent's generated SQL queries must automatically scope to the calling tenant's data — no tenant can see another tenant's rows.

**Key insight**: Cortex Analyst generates SQL against the semantic view's source tables. Row Access Policies (RAPs) on those base tables automatically scope all agent-generated queries. The agent spec itself does not need tenant-aware logic — isolation happens at the data layer.

---

## Step 4b.1: Choose isolation pattern

Present the three patterns and help the user pick:

```
Your agent serves multiple tenants. How should tenant identity be determined at query time?

  A) User-per-tenant — each tenant logs in as a distinct Snowflake user
     RAP filters on CURRENT_USER()
     Best for: direct Snowflake access, small tenant count

  B) Role-per-tenant — each tenant is assigned a Snowflake role (e.g., TENANT_ACME_ROLE)
     RAP filters on CURRENT_ROLE()
     Caller passes X-Snowflake-Role header in DATA_AGENT_RUN
     Best for: RBAC-heavy orgs, moderate tenant count

  C) Session attribute — middleware sets a trusted session attribute (e.g., tenant_id)
     RAP filters on SYS_CONTEXT('SNOWFLAKE$SESSION_ATTRIBUTES', 'tenant_id')
     Caller passes `variables` block in DATA_AGENT_RUN with is_immutable_session_attribute
     Best for: API-driven access, large tenant count, SaaS platforms

     ⚠️  SECURITY: Pattern C is ONLY secure when the session attribute is set by
     trusted middleware (Snowflake's auth flow, a controlled API gateway, or
     is_immutable_session_attribute in the DATA_AGENT_RUN payload). It is NOT
     secure if arbitrary SQL callers can SET the attribute directly.
```

Store as `TENANT_PATTERN` (one of `"user"`, `"role"`, `"session_attribute"`).

---

## Step 4b.2: Identify tenant-scoped tables

Ask:

```
Which base tables contain tenant-specific data?
List the FQN of each table that needs a RAP:
  e.g., ANALYTICS_DB.PUBLIC.ORDERS
        ANALYTICS_DB.PUBLIC.CUSTOMERS
```

Also ask:

```
What is the tenant identifier column in these tables?
  e.g., TENANT_ID, ORG_ID, ACCOUNT_ID
```

Store as `TENANT_TABLES` (list of FQNs) and `TENANT_ID_COLUMN`.

---

## Step 4b.3: Verify RAP exists or generate DDL

For each table in `TENANT_TABLES`, check if a RAP is already attached:

```sql
SHOW ROW ACCESS POLICIES ON TABLE <TABLE_FQN>;
```

### If RAP already exists:

```
✓ <TABLE_FQN> — RAP already attached: <policy_name>
  Verify it filters on the chosen pattern (<TENANT_PATTERN>).
```

### If no RAP exists:

Generate the RAP DDL based on `TENANT_PATTERN`:

**Pattern A (user-per-tenant):**

```sql
-- Entitlement table mapping users to tenants
CREATE TABLE IF NOT EXISTS <AGENT_DB>.<AGENT_SCHEMA>.USER_TENANT_MAP (
  USERNAME       VARCHAR NOT NULL,
  TENANT_ID      VARCHAR NOT NULL
);

-- Row access policy
CREATE OR REPLACE ROW ACCESS POLICY <AGENT_DB>.<AGENT_SCHEMA>.RAP_TENANT_BY_USER
  AS (tenant_id_val VARCHAR) RETURNS BOOLEAN ->
    EXISTS (
      SELECT 1
      FROM <AGENT_DB>.<AGENT_SCHEMA>.USER_TENANT_MAP
      WHERE USERNAME = CURRENT_USER()
        AND TENANT_ID = tenant_id_val
    );

-- Attach to each table
ALTER TABLE <TABLE_FQN> ADD ROW ACCESS POLICY
  <AGENT_DB>.<AGENT_SCHEMA>.RAP_TENANT_BY_USER ON (<TENANT_ID_COLUMN>);
```

**Pattern B (role-per-tenant):**

```sql
-- Entitlement table mapping roles to tenants
CREATE TABLE IF NOT EXISTS <AGENT_DB>.<AGENT_SCHEMA>.ROLE_TENANT_MAP (
  ROLE_NAME      VARCHAR NOT NULL,
  TENANT_ID      VARCHAR NOT NULL
);

-- Row access policy
CREATE OR REPLACE ROW ACCESS POLICY <AGENT_DB>.<AGENT_SCHEMA>.RAP_TENANT_BY_ROLE
  AS (tenant_id_val VARCHAR) RETURNS BOOLEAN ->
    EXISTS (
      SELECT 1
      FROM <AGENT_DB>.<AGENT_SCHEMA>.ROLE_TENANT_MAP
      WHERE ROLE_NAME = CURRENT_ROLE()
        AND TENANT_ID = tenant_id_val
    );

-- Attach to each table
ALTER TABLE <TABLE_FQN> ADD ROW ACCESS POLICY
  <AGENT_DB>.<AGENT_SCHEMA>.RAP_TENANT_BY_ROLE ON (<TENANT_ID_COLUMN>);
```

**Pattern C (session attribute):**

```sql
-- Memoizable UDF for entitlement check (PRODUCTION)
CREATE OR REPLACE FUNCTION <AGENT_DB>.<AGENT_SCHEMA>.GET_TENANT_ID()
  RETURNS VARCHAR
  LANGUAGE SQL
  MEMOIZABLE
AS
$$
  SELECT SYS_CONTEXT('SNOWFLAKE$SESSION_ATTRIBUTES', 'tenant_id')
$$;

-- Row access policy using memoizable UDF
CREATE OR REPLACE ROW ACCESS POLICY <AGENT_DB>.<AGENT_SCHEMA>.RAP_TENANT_BY_SESSION
  AS (tenant_id_val VARCHAR) RETURNS BOOLEAN ->
    tenant_id_val = <AGENT_DB>.<AGENT_SCHEMA>.GET_TENANT_ID();

-- Attach to each table
ALTER TABLE <TABLE_FQN> ADD ROW ACCESS POLICY
  <AGENT_DB>.<AGENT_SCHEMA>.RAP_TENANT_BY_SESSION ON (<TENANT_ID_COLUMN>);
```

> **Worksheet testing only** — Use this variant to test RAP behavior in a Snowsight worksheet without needing the full `variables` block or `SET_SYS_CONTEXT` call. Do NOT deploy this to production.
>
> ```sql
> -- TEST-ONLY UDF with mutable variable fallback
> CREATE OR REPLACE FUNCTION <AGENT_DB>.<AGENT_SCHEMA>.GET_TENANT_ID_TEST()
>   RETURNS VARCHAR
>   LANGUAGE SQL
> AS
> $$
>   SELECT COALESCE(
>     SYS_CONTEXT('SNOWFLAKE$SESSION_ATTRIBUTES', 'tenant_id'),
>     GETVARIABLE('TENANT_ID')
>   )
> $$;
>
> -- Test usage:
> SET TENANT_ID = 'ACME_CORP';
> SELECT * FROM <TABLE> WHERE 1=1;  -- RAP filters automatically
> ```

> ⚠️ **Do NOT execute this DDL automatically.** Present it to the user for review and delegate execution to the `data-governance` skill (`data-policy` sub-skill) if the user wants guided policy creation. This phase provides the patterns; `data-governance` owns policy lifecycle.

---

## Step 4b.4: Document invocation pattern

Based on `TENANT_PATTERN`, show the user how the agent must be called to pass tenant context:

**Pattern A (user-per-tenant):**
```
No special invocation needed — CURRENT_USER() is automatically available.
Ensure the USER_TENANT_MAP table is populated for each tenant user.
```

**Pattern B (role-per-tenant):**
```sql
-- Caller must set the role via X-Snowflake-Role header or USE ROLE before calling
-- In DATA_AGENT_RUN:
SELECT SNOWFLAKE.CORTEX.DATA_AGENT_RUN(
  '<AGENT_FQN>',
  PARSE_JSON('{
    "messages": [{"role": "user", "content": "Show me my orders"}]
  }')
);
-- The calling session's CURRENT_ROLE() determines tenant scope
```

**Pattern C (session attribute):**
```sql
-- Via DATA_AGENT_RUN variables block (preferred — immutable):
SELECT SNOWFLAKE.CORTEX.DATA_AGENT_RUN(
  '<AGENT_FQN>',
  PARSE_JSON('{
    "messages": [{"role": "user", "content": "Show me my orders"}],
    "variables": {
      "tenant_id": {
        "value": "ACME_CORP",
        "is_immutable_session_attribute": true
      }
    }
  }')
);
```

> ⚠️ **API caveat**: The `variables` block with `is_immutable_session_attribute` is documented in Snowflake's multitenant agent patterns but may be in preview. Verify availability in your account before customer-facing use. If unavailable, use `SET_SYS_CONTEXT` before calling DATA_AGENT_RUN in the same session as a fallback:
> ```sql
> CALL SET_SYS_CONTEXT('SNOWFLAKE$SESSION_ATTRIBUTES', 'tenant_id', 'ACME_CORP');
> SELECT SNOWFLAKE.CORTEX.DATA_AGENT_RUN(...);
> ```

---

## Step 4b.5: Record tenant isolation metadata

Store the following for use in Phase 5 (self-check WARN #17) and Phase 7 (smoke test):

| Variable | Contents |
|----------|----------|
| `IS_MULTITENANT` | `true` |
| `TENANT_PATTERN` | `"user"`, `"role"`, or `"session_attribute"` |
| `TENANT_TABLES` | List of table FQNs with RAPs |
| `TENANT_ID_COLUMN` | Column name used for tenant filtering |
| `RAP_STATUS` | `"existing"` or `"generated"` per table |

---

## Step 4b.6: Proceed to Phase 5

No stopping point here — the user already approved the pattern choice. Proceed directly to Phase 5 (Self-Check), which will now include WARN #17 for multitenant validation.

```
Tenant isolation configured:
  Pattern:    <TENANT_PATTERN>
  Tables:     <N> tables with RAP coverage
  Invocation: <summary of how to pass tenant context>

Proceeding to Phase 5 — self-check will validate multitenancy setup.
```

---

## Session attribute function reference

| Function | Purpose |
|----------|---------|
| `SET_SYS_CONTEXT('SNOWFLAKE$SESSION_ATTRIBUTES', 'key', 'val')` | Set **immutable** session attribute (cannot be changed once set in session) |
| `SYS_CONTEXT('SNOWFLAKE$SESSION_ATTRIBUTES', 'key')` | **Read** immutable session attribute (use in RAPs for Pattern C) |
| `SET key = 'val'` / `SET_SYS_CONTEXT(NULL, 'key', 'val')` | Set **mutable** session variable (can be changed, suitable for connection pools) |
| `GETVARIABLE('key')` / `SYS_CONTEXT(NULL, 'key')` | **Read** mutable session variable |

> **Pattern C RAPs** MUST use `SYS_CONTEXT('SNOWFLAKE$SESSION_ATTRIBUTES', ...)` — the immutable form.
> The `GETVARIABLE()` fallback in the COALESCE pattern is for interactive testing only (allows `SET tenant_id = 'X'` in worksheets without needing the full `variables` block).

---

## Output variables passed to next phases

| Variable | Contents |
|----------|----------|
| `IS_MULTITENANT` | `true` |
| `TENANT_PATTERN` | Selected isolation pattern |
| `TENANT_TABLES` | List of table FQNs requiring RAP |
| `TENANT_ID_COLUMN` | Tenant identifier column name |
| `RAP_STATUS` | Per-table RAP status |

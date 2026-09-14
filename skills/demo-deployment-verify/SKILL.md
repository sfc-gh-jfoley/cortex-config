---
name: demo-deployment-verify
description: "Audit a local demo/lab directory against a Snowflake account, deploy missing objects, and loop build-test-fix until the demo runs clean. Use when: checking demo readiness, deploying a lab, verifying account state. Triggers: is this demo fully deployed, review this dir what's needed to run this lab, what is deployed in the account, fix the issues and retest until everything works, deploy everything missing to <db>"
version: 1.0.0
---

# Skill: demo-deployment-verify

Audits a local demo or lab directory against a target Snowflake account, deploys only
what is missing, then loops build-test-fix until the demo runs end to end — or until
the loop cap is hit and the problem escalates to you.

## When to Use

- A demo directory exists locally and you need to know if the account is ready to run it.
- You want to deploy the missing pieces without re-running everything from scratch.
- A demo failed live and you want to diagnose what's missing or broken.

## When NOT to Use

- **Authoring a new lab package from scratch.** That is `lab-builder` —
  load `~/.snowflake/cortex/vault/skills/lab-builder/SKILL.md` instead.
- **Tearing down an entire lab.** Use `lab-builder`'s teardown workflow for that.
- **Account-wide audits** unrelated to a specific demo directory.

## Prerequisites

- A local demo/lab directory with at least one SQL setup script.
- An active Snowflake connection (`sql_execute` working).
- A non-ACCOUNTADMIN role with CREATE privileges on the target database.
  If the scripts reference a project role (e.g. `<lab>_ADMIN`), use or create that role.
  Running as ACCOUNTADMIN masks missing grants — the demo will pass your test and
  fail the customer's.

## Workflow

### Phase 1 — Inventory Local Assets

Scan the directory for:

| Asset type | Typical files |
|---|---|
| Setup SQL | `setup.sql`, `deploy.sql`, `**/create_*.sql` |
| Semantic views | `.yaml` / `.yml` with semantic-view structure |
| Cortex agents | JSON specs or `CREATE AGENT` in SQL |
| Search services | `CREATE CORTEX SEARCH SERVICE` in SQL |
| Data loads | `COPY INTO`, `INSERT`, staged file references |
| Talk track / personas | `.md`, `.html` docs describing the demo flow |
| Streamlit apps | `app.py` + `environment.yml` patterns |

Parse the SQL scripts to extract the intended `DATABASE.SCHEMA` — look for `USE DATABASE`,
`CREATE SCHEMA`, or fully-qualified object names. Do not guess a database name that isn't
in the scripts.

### Phase 2 — Context Report (STOPPING POINT)

Before touching anything, report:

```
Account:    SELECT CURRENT_ACCOUNT()
Role:       SELECT CURRENT_ROLE()
Warehouse:  SELECT CURRENT_WAREHOUSE()
Target:     <DB.SCHEMA from Phase 1>
```

**Stop and confirm with the user.** Deploying into the wrong account is the most
expensive failure in this workflow — it is silent and only discovered when the real
account is still empty. Do not proceed until the user explicitly confirms.

If the current role is ACCOUNTADMIN, warn and ask the user to switch to a project role.

### Phase 3 — Diff Deployed vs Expected

Use SHOW commands to check what exists in the target scope:

- `SHOW SCHEMAS IN DATABASE <db>`
- `SHOW TABLES IN SCHEMA <db.schema>`
- `SHOW VIEWS IN SCHEMA <db.schema>`
- `SHOW SEMANTIC VIEWS IN SCHEMA <db.schema>`
- `SHOW AGENTS IN SCHEMA <db.schema>`

For commands you are unsure about (e.g. search services), run
`cortex search docs "<object type> SHOW command"` to confirm syntax first.

Emit a diff table:

```
| Asset              | Expected | Found | Action   |
|--------------------|----------|-------|----------|
| SCHEMA analytics   | ✓        | ✗     | CREATE   |
| TABLE raw_events   | ✓        | ✓     | skip     |
| SEMANTIC VIEW sv1  | ✓        | ✗     | CREATE   |
| AGENT demo_agent   | ✓        | ✗     | CREATE   |
```

### Phase 4 — Deploy Missing Objects

Deploy in dependency order — earlier objects are prerequisites for later ones:

1. Database (if missing and scripts contain `CREATE DATABASE`)
2. Schemas
3. Tables and data loads (`COPY INTO`, inserts, stage references)
4. Semantic views
5. Cortex search services
6. Cortex agents
7. Grants (to consumer/demo roles)

Run each CREATE from the original setup scripts where possible rather than
rewriting the DDL. If a script bundles multiple objects, extract and run only
the missing statements.

### Phase 5 — Smoke Test (CRITICAL)

Test under the **consumer role**, not the owner role. A demo that only works
as owner will fail when presented. If the scripts define a consumer role
(e.g. `<lab>_USER`), `USE ROLE` to it before testing.

Run:
- Representative queries from the talk track or setup scripts.
- Agent invocation via `SELECT SNOWFLAKE.CORTEX.DATA_AGENT_RUN(...)` if an agent exists.
- A semantic-view query if one was deployed.
- Grant verification: confirm the consumer role can access all objects.

Record each test with: test name, pass/fail, error message if any.

### Phase 6 — Fix-Retest Loop

**Bounded to 5 iterations.** An unbounded retry loop against a live account burns
credits and can oscillate between two failure states forever — e.g. a grant fix
breaks a view, fixing the view re-breaks the grant.

Each iteration must:
1. Record the specific error and the fix attempted.
2. Apply the fix.
3. Re-run the failing test(s).
4. Compare the error count to the previous iteration.

**Hard stop:** if an iteration does not reduce the error count, stop the loop
and escalate to the user with the full error log. Do not retry the same fix twice.

### Phase 7 — Readiness Summary

Produce:
- The diff table from Phase 3 (updated with final state).
- Deploy log: each object created, with status.
- Smoke-test results: each test, pass/fail, errors.
- Remaining gaps: anything that still fails or is missing (e.g. no talk track,
  no persona doc, a grant that requires SECURITYADMIN).

## Stopping Points

1. **After Phase 2 context report** — confirm correct account before any deploy.
2. **Before any DROP or destructive action** — name the objects and get explicit confirmation.
3. **At loop exhaustion (5 iterations)** — escalate; do not continue silently.
4. **If ACCOUNTADMIN is the active role** — warn and pause for role switch.

## Output

A readiness report containing:

```
## Demo Readiness: <lab name>
Account: <account> | Role: <role> | Target: <db.schema>

### Deployment Diff
<table from Phase 3/7>

### Deploy Log
<objects created, in order>

### Smoke Tests
<test name — pass/fail — error if any>

### Remaining Gaps
<anything unresolved>
```

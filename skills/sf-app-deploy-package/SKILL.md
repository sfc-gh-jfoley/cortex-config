---
name: sf-app-deploy-package
description: "Deploy a Streamlit-in-Snowflake monitoring/dashboard app with least-privilege roles into an existing database/schema, verify every SQL statement actually executes, and package an installer zip for sharing. Use when: deploying a SiS app to a target account, standing up a role model for an app, verifying dashboard SQL before handoff, packaging an app for distribution. Triggers: deploy this app to <db>, has all the SQL been tested for accuracy, never do this as ACCOUNTADMIN set up a role, package the app and installer into a zip, do all objects live in the schema"
version: 1.0.0
---

# Skill: sf-app-deploy-package

Deploy a Streamlit-in-Snowflake monitoring/dashboard app into an existing database and
schema, with a least-privilege role model, every SQL statement verified against the
account, and a versioned installer zip at the end. This skill owns deployment discipline
and packaging — it does not own how to write Streamlit code.

## When to Use

- Deploying a SiS monitoring/dashboard app to a customer or internal account
- Setting up roles/grants for an app that other people (not just you) will run
- The user asks whether the dashboard SQL has actually been executed and verified
- Packaging an app + installer + teardown script for handoff or distribution
- Auditing an existing deployment for objects that landed in PUBLIC or ACCOUNTADMIN usage

## When NOT to Use

- Writing or iterating on Streamlit UI code with no deployment/role-model component —
  that's plain Streamlit authoring
- One-off personal scratch apps with no other consumers and no handoff — the role model
  and packaging overhead isn't worth it
- Native Apps Framework or SPCS container apps — different lifecycle, different skill

## Prerequisites

- Target database and schema already exist, or the user has approved creating them
- `snow` CLI configured against the target connection
- You are NOT operating as ACCOUNTADMIN for object creation or grants (see Role Model)

## Role Model

Three tiers, because collapsing them into one role is the single most common way these
deployments get flagged in review:

1. **Owner/admin role** — creates and owns the database objects (tables, views, the
   Streamlit object itself). This is a dedicated project role, never ACCOUNTADMIN.
   ACCOUNTADMIN masks grant bugs: everything succeeds regardless of whether the role
   model is actually correct, so you find out it's broken only when a real consumer
   role hits a permission wall after you've left.
2. **Operator role** — can run/refresh the app and underlying refresh jobs, but does not
   own objects. This is what a scheduled task or an on-call SE should use.
3. **Viewer/consumer role** — read-only, granted USAGE on the Streamlit app and SELECT
   on curated secure views only, never on base tables.

Grant the app runtime access to secure views, not base tables. This caps blast radius if
the app or a prompt injected into it is compromised — a leaked view grant exposes only
what the view projects, not the full table — and it keeps the consumer grant surface
small enough to actually review in five minutes.

For exact `CREATE ROLE` / `GRANT` / `CREATE STREAMLIT` syntax you're not certain of, run
`cortex search docs "<topic>"` first. Do not invent Snowflake SQL or CLI syntax.

## Workflow

### Phase 1 — Resolve target and detect existing ownership

- Confirm target database/schema with the user if not explicit.
- Before creating anything, check for pre-existing roles with a similar name, and check
  who owns the target database (`SHOW DATABASES`, `DESCRIBE DATABASE`, or `cortex search
  docs` for the right introspection command if unsure).
- If a role or database is owned by a DIFFERENT app or team, **reuse it, don't recreate
  it**. Dropping or redefining a shared role is the failure mode that silently breaks an
  unrelated deployment elsewhere in the account — and there's no signal from inside this
  deployment that tells you it happened.
- **Stopping point:** if you detect a pre-existing role or a foreign-owned database,
  stop and confirm with the user how to proceed before creating or altering anything.

### Phase 2 — Roles and grants

- Create (or verify) the three roles from the Role Model above under the dedicated
  project admin role — never ACCOUNTADMIN.
- Grant object ownership to the owner role, run/refresh privileges to the operator role,
  and SELECT on curated secure views only to the viewer role.
- Grant the app's own runtime role read access to secure views, not base tables.

### Phase 3 — Execute and verify every statement

- Run every setup statement and every dashboard query against the real account. Fix
  syntax and type errors as you go — don't defer them.
- A dashboard whose SQL was never executed is not a deployment, it's a draft. Type
  errors in aggregate columns (e.g. a `SUM` over a column that's actually a string) only
  surface at query time, not at write time, so reading the SQL is not sufficient
  verification.
- For the Streamlit app itself — authoring, `snow streamlit deploy`, `st.connection`,
  theming, SiS-specific runtime constraints — load the bundled
  `developing-with-streamlit-in-snowflake` skill via the skill tool and follow it. Do not
  re-derive SiS deployment mechanics here.

### Phase 4 — Assert placement

- Confirm no objects landed in `PUBLIC` — every table, view, and the Streamlit object
  itself should be in the target schema.
- Confirm the dependency manifest (`environment.yml` or equivalent) matches every package
  the app actually imports at runtime. A missing package fails only on first open, after
  you've already handed off — this is not caught by a syntax check.

### Phase 5 — Package for handoff

- Build a versioned zip containing: installer SQL (idempotent, ordered by phase above),
  a README (what it deploys, role model, how to run it), and a teardown script.
- Place copies wherever the user asked (local path, workspace, etc.).
- **Stopping point:** before running any teardown script, print the exact objects and
  roles it will drop and get explicit confirmation. Teardown is destructive and the
  wrong invocation drops more than the current deployment if roles were reused per
  Phase 1.

## Stopping Points

- After Phase 1, when a pre-existing role or a foreign-owned database is detected.
- Before executing any teardown script, regardless of who asked for it.

## Output

- Verification checklist (tick every row before declaring done):

  | Check | Status |
  |---|---|
  | Every setup + dashboard statement executed against the account | |
  | Zero objects in PUBLIC | |
  | Consumer/viewer role tested with its own SELECT | |
  | Manifest matches runtime imports | |
  | Teardown script reviewed and dry-run confirmed | |

- The deployed app, reachable by the viewer role.
- A versioned installer zip (installer SQL + README + teardown script) at the requested
  location(s).
- A deployment report listing: objects created, grants applied per role, and the full
  list of statements verified.

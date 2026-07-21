---
name: cortex-agent-versioning-reference
description: Agent versioning lifecycle — LIVE vs named versions, commit/alias/rollback SQL, DATA_AGENT_RUN version suffix, REST API versioned endpoint, CI/CD patterns
last_verified: 2026-07-21
---

# Cortex Agent Versioning — Reference

Agent versioning separates the development workflow from the production workflow. You iterate on
the **live version** (mutable), commit it to create a **named version** (immutable snapshot),
assign an alias like `production`, and route traffic to that alias. Rolling back is reassigning
the alias — no code change needed by callers.

---

## Version types

| Type | Mutability | Created by | Use for |
|---|---|---|---|
| **Live** | Mutable | Automatically at agent creation; or `ALTER AGENT ... ADD LIVE VERSION` | Active development, interactive testing |
| **Named** (VERSION$N) | Immutable | `ALTER AGENT ... COMMIT` or import from stage | Stable deployments, CI/CD targets |

Each agent can have at most one live version at a time. Named versions are assigned
sequential system IDs: `VERSION$1`, `VERSION$2`, etc.

---

## SQL command reference

### Commit live version → create named version

```sql
ALTER AGENT <db>.<schema>.<name> COMMIT
  COMMENT = 'Production release Q3 2026';
-- Creates VERSION$N (next in sequence). Live version is NOT auto-recreated.
```

### Create a new live version (resume development)

```sql
-- From the most recently committed named version:
ALTER AGENT <db>.<schema>.<name> ADD LIVE VERSION FROM LAST
  COMMENT = 'Resuming dev from v3';

-- With an alias on the live version:
ALTER AGENT <db>.<schema>.<name> ADD LIVE VERSION dev FROM LAST;
```

### Import a named version from a stage (CI/CD)

```sql
-- From a Snowflake stage (e.g. Git-connected):
ALTER AGENT <db>.<schema>.<name> ADD VERSION FROM @<db>.<schema>.<stage>/agents/<name>/
  COMMENT = 'Deployed from feature branch merge';

-- Create agent directly from stage (infra-as-code):
CREATE AGENT <db>.<schema>.<name>
  COMMENT = 'Deployed by CI pipeline'
  FROM @<db>.<schema>.<stage>/agents/<name>/;
```

### Assign and move aliases

```sql
-- Assign alias to a named version:
ALTER AGENT <db>.<schema>.<name>
  MODIFY VERSION VERSION$3 SET ALIAS = production;

-- Promote new version (reassign alias — callers need no changes):
ALTER AGENT <db>.<schema>.<name>
  MODIFY VERSION VERSION$4 SET ALIAS = production;

-- Assign alias to live version:
ALTER AGENT <db>.<schema>.<name>
  MODIFY LIVE VERSION SET ALIAS = dev;
```

### Set default version

```sql
-- Explicit named version:
ALTER AGENT <db>.<schema>.<name> SET DEFAULT_VERSION = 'VERSION$3';

-- Or use a shortcut:
ALTER AGENT <db>.<schema>.<name> SET DEFAULT_VERSION = LAST;
```

### Inspect and clean up

```sql
-- List all versions:
SHOW VERSIONS IN AGENT <db>.<schema>.<name>;

-- Drop a named version (cannot drop live version):
ALTER AGENT <db>.<schema>.<name> DROP VERSION VERSION$1;
```

---

## Version shortcuts

Use these anywhere a version identifier is accepted (SQL suffix, REST path, stage URI):

| Shortcut | Resolves to |
|---|---|
| `LIVE` | The current live (mutable) version |
| `FIRST` | The first committed named version |
| `LAST` | The most recently committed named version |
| `DEFAULT` | The version set as the agent's default (falls back to LAST if unset) |

---

## Targeting a version in DATA_AGENT_RUN

Append `!<version>` to the agent FQN:

```sql
-- Specific named version:
SELECT SNOWFLAKE.CORTEX.DATA_AGENT_RUN(
  'MY_DB.MY_SCHEMA.MY_AGENT!VERSION$2',
  $${"messages":[{"role":"user","content":[{"type":"text","text":"Hello"}]}]}$$
);

-- Named alias:
SELECT SNOWFLAKE.CORTEX.DATA_AGENT_RUN(
  'MY_DB.MY_SCHEMA.MY_AGENT!production',
  $${"messages":[{"role":"user","content":[{"type":"text","text":"Hello"}]}]}$$
);

-- Live (draft) version — for development testing:
SELECT SNOWFLAKE.CORTEX.DATA_AGENT_RUN(
  'MY_DB.MY_SCHEMA.MY_AGENT!LIVE',
  $${"messages":[{"role":"user","content":[{"type":"text","text":"Hello"}]}]}$$
);

-- Default version (same as omitting the suffix):
SELECT SNOWFLAKE.CORTEX.DATA_AGENT_RUN(
  'MY_DB.MY_SCHEMA.MY_AGENT!DEFAULT',
  $${"messages":[{"role":"user","content":[{"type":"text","text":"Hello"}]}]}$$
);
```

> **Note**: If the agent name itself contains a `!` character, quote that segment:
> `'db.schema."my!agent"!LIVE'`

---

## REST API — versioned endpoint

```
POST /api/v2/databases/{database}/schemas/{schema}/agents/{name}/versions/{version}:run
```

The `{version}` path parameter accepts any of:

| Identifier | Example |
|---|---|
| System version name | `VERSION%242` (URL-encoded `VERSION$2`) |
| User-defined alias | `production` |
| Shortcut | `FIRST`, `LAST`, `DEFAULT`, `LIVE` |

By default the API streams responses as server-sent events (SSE). To receive a single JSON
response, set `"stream": false` in the request body.

---

## Stage URI scheme

Each version has an internal stage path readable via the `snow://agent/` URI:

```
snow://agent/<agent_name>/versions/<version>/[<file_name>]
```

```sql
-- List all files in the production version:
LIST snow://agent/my_agent/versions/production/;

-- Download the agent spec from a specific version:
GET snow://agent/my_agent/versions/VERSION$2/agent.yaml file:///tmp/;
```

Stage operations are **read-only** — useful for auditing, diffing versions, and debugging.

---

## CI/CD workflow patterns

### Standard commit-based flow

```
1. Develop  — edit live version in Snowsight or via ALTER AGENT MODIFY LIVE VERSION SET SPECIFICATION
2. Commit   — ALTER AGENT ... COMMIT  →  creates VERSION$N
3. Test     — route test traffic to VERSION$N (or alias 'staging')
4. Promote  — ALTER AGENT ... MODIFY VERSION VERSION$N SET ALIAS = production
5. Rollback — ALTER AGENT ... MODIFY VERSION VERSION$<prev> SET ALIAS = production
```

### Git-first import flow (no live version needed)

```
1. Develop  — edit agent YAML in Git repo
2. Merge    — PR review + merge to main
3. Import   — ALTER AGENT ... ADD VERSION FROM @my_repo/tags/v2.1/agents/my_agent/
4. Deploy   — ALTER AGENT ... MODIFY VERSION <new> SET ALIAS = production
```

---

## Error cheat sheet

| Symptom | Cause | Fix |
|---|---|---|
| `DATA_AGENT_RUN` returns "agent not found" with `!VERSION$N` | Version was dropped or wrong agent FQN | Run `SHOW VERSIONS IN AGENT` to confirm version exists |
| `ALTER AGENT ... COMMIT` fails with "no live version" | Live version was never created or was already committed | Run `ALTER AGENT ... ADD LIVE VERSION FROM LAST` first |
| Alias reassignment rejected | Alias already assigned to another version | Drop the existing alias with `MODIFY VERSION <old> SET ALIAS = NULL` or reassign directly (overwrites) |
| `DROP VERSION` on live version | Cannot drop live version | Commit it first, then drop the resulting named version if needed |

---

## Limitations

- Each agent has **at most one live version** at a time.
- After committing, the live version is **not auto-recreated** — call `ADD LIVE VERSION FROM LAST` to resume.
- Named versions are **immutable** — only metadata (comment, alias) can be updated.
- Aliases are **case-sensitive** when created with double-quoted identifiers; otherwise stored uppercase.
- Each alias must be **unique within an agent**.

# Remediation Plan — Generate Fix Plans for Behavior Changes

## Overview

For each CRITICAL and WARNING impact item from Phase 3, generate an actionable remediation plan with code changes, priority, and deadlines.

## Remediation Entry Structure

Each remediation item should contain:

```
## [SEV] Change Title (Bundle YYYY_NN)

**Deadline:** <date when Generally Enabled>
**Priority:** <URGENT / HIGH / MEDIUM based on lifecycle + severity>
**Status:** [ ] Not started

### What's Changing
<Plain-English explanation of the behavior change>

### Affected Objects
- `DATABASE.SCHEMA.OBJECT_NAME` (type: TASK/PROCEDURE/VIEW/etc.)
- `DATABASE.SCHEMA.OBJECT_NAME_2`

### Current Code (Before)
```sql
<existing SQL that will break or behave differently>
```

### Fixed Code (After)
```sql
<updated SQL that works with the new behavior>
```

### Validation Query
```sql
<query to verify the fix is correct — run in dev with bundle enabled>
```

### Notes
<any caveats, edge cases, or dependencies>
```

## Priority Assignment

Combine bundle lifecycle status with severity:

| Lifecycle Status | CRITICAL Severity | WARNING Severity |
|-----------------|-------------------|------------------|
| Disabled by Default | HIGH | MEDIUM |
| Enabled by Default | URGENT | HIGH |
| Generally Enabled | URGENT (overdue!) | URGENT |

**Timeline guidance:**

| Priority | Recommended action window |
|----------|--------------------------|
| URGENT | Fix within 1 week. Bundle is active or imminent. |
| HIGH | Fix within 2-4 weeks. Bundle is in testing period. |
| MEDIUM | Fix within 1-2 months. Ambiguous impact, monitor closely. |

## Common Remediation Patterns

### Pattern 1: Function Behavior Change

The function still exists but returns different results for certain inputs.

**Fix approach:** Add explicit handling for the edge case that changed.

```sql
-- Before (relies on old implicit behavior)
SELECT FLATTEN(input => col) FROM table;

-- After (explicit NULL handling for new behavior)
SELECT FLATTEN(input => COALESCE(col, ARRAY_CONSTRUCT())) FROM table;
```

### Pattern 2: Default Parameter Change

A function or command default changed (e.g., ON_ERROR, STRIP_OUTER_ARRAY).

**Fix approach:** Explicitly set the parameter to the old default value.

```sql
-- Before (relied on old default)
COPY INTO my_table FROM @my_stage;

-- After (explicitly set old default)
COPY INTO my_table FROM @my_stage
  ON_ERROR = 'ABORT_STATEMENT';  -- was implicit, now must be explicit
```

### Pattern 3: SQL Syntax Deprecation

Old syntax is removed or no longer valid.

**Fix approach:** Migrate to the new syntax.

```sql
-- Before (deprecated syntax)
CREATE TABLE t1 LIKE t2;

-- After (new syntax)
CREATE TABLE t1 USING TEMPLATE (SELECT * FROM TABLE(INFER_SCHEMA(...)));
```

### Pattern 4: Security / RBAC Change

Permission model changed — queries may fail with access errors.

**Fix approach:** Grant new required privileges.

```sql
-- New privilege required
GRANT <NEW_PRIVILEGE> ON <OBJECT> TO ROLE <role>;
```

### Pattern 5: Data Type Behavior Change

Type casting or comparison semantics changed.

**Fix approach:** Add explicit CAST or type annotations.

```sql
-- Before (implicit cast worked differently)
SELECT * FROM t WHERE varchar_col = 123;

-- After (explicit cast for deterministic behavior)
SELECT * FROM t WHERE varchar_col = '123';
```

## Generating Remediation Items

For each CRITICAL/WARNING from the impact analysis:

1. Read the "Action Required" from the Snowflake docs (captured in Phase 1)
2. Fetch the DDL of each affected object (`GET_DDL`)
3. Identify the specific lines that need changing
4. Generate before/after SQL diffs
5. Write a validation query that can be run in dev with the bundle enabled
6. Assign priority based on the matrix above

## Output

Produce the remediation plan as either:
- A Markdown checklist (inline or Google Doc)
- A spreadsheet with columns: Priority, Bundle, Change, Object, Status, Fix Description, Deadline

Offer both formats via `ask_user_question`.

## Tracking

If the user wants to track remediation progress:
- Save the checklist to `/memories/release-monitor/remediation-{YYYY_NN}.md`
- On subsequent runs, check off completed items and highlight remaining work
- Alert if deadline is approaching and items are still open

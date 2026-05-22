# Default Error Runbook

Seed data for the ERROR_RUNBOOK table. These are deterministic fixes for common errors that don't need LLM reasoning.

## Seed SQL — Task Patterns

```sql
INSERT INTO {DB}.{SCHEMA}.ERROR_RUNBOOK (ERROR_PATTERN, ERROR_CATEGORY, OBJECT_TYPE, FIX_TEMPLATE, DESCRIPTION, CONFIDENCE) VALUES
('does not exist or not authorized', 'OBJECT_NOT_FOUND', 'ALL', 'SELECT ''NEEDS_LLM_SCHEMA_LOOKUP''', 'Object reference error — requires schema inspection to find correct name', 0.3),
('Numeric value .* is not recognized', 'TYPE_ERROR', 'ALL', 'SELECT ''NEEDS_LLM_CAST_FIX''', 'Type casting error — LLM should inspect column types and add TRY_CAST', 0.4),
('Division by zero', 'RUNTIME_ERROR', 'ALL', 'SELECT ''NEEDS_LLM_NULLIF_FIX''', 'Division by zero — LLM should wrap denominator with NULLIF(x, 0)', 0.6),
('Warehouse .* does not exist', 'CONFIG_ERROR', 'TASK', 'ALTER TASK {TASK_NAME} SET WAREHOUSE = ''{DEFAULT_WAREHOUSE}''', 'Warehouse reference error — reset to default warehouse', 0.9),
('exceeds maximum allowed duration', 'TIMEOUT', 'TASK', 'ALTER TASK {TASK_NAME} SET USER_TASK_TIMEOUT_MS = 7200000', 'Task timeout — increase to 2 hours', 0.8),
('Statement produced more columns', 'SCHEMA_MISMATCH', 'ALL', 'SELECT ''NEEDS_LLM_COLUMN_FIX''', 'Column count mismatch — LLM should inspect target table schema', 0.3),
('cannot change column', 'SCHEMA_MISMATCH', 'ALL', 'SELECT ''NEEDS_LLM_ALTER_FIX''', 'Column type mismatch — LLM should generate ALTER TABLE or CAST', 0.4),
('suspended', 'TASK_STATE', 'TASK', 'ALTER TASK {TASK_NAME} RESUME', 'Task is suspended — resume it', 0.95);
```

## Seed SQL — Dynamic Table Patterns

```sql
INSERT INTO {DB}.{SCHEMA}.ERROR_RUNBOOK (ERROR_PATTERN, ERROR_CATEGORY, OBJECT_TYPE, FIX_TEMPLATE, DESCRIPTION, CONFIDENCE) VALUES
('UPSTREAM_FAILED', 'DT_CASCADE', 'DYNAMIC_TABLE', 'SELECT ''NEEDS_LLM_UPSTREAM_FIX''', 'Upstream DT failed — walk the graph to find and fix root cause DT', 0.2),
('TARGET_LAG', 'DT_LAG', 'DYNAMIC_TABLE', 'ALTER DYNAMIC TABLE {DT_NAME} SET TARGET_LAG = ''10 minutes''', 'Target lag too tight — relax to 10 minutes', 0.7),
('Warehouse .* does not exist', 'CONFIG_ERROR', 'DYNAMIC_TABLE', 'ALTER DYNAMIC TABLE {DT_NAME} SET WAREHOUSE = ''{DEFAULT_WAREHOUSE}''', 'DT warehouse reference error — reset to default', 0.9),
('SCHEDULING_STATE.*SUSPENDED', 'DT_STATE', 'DYNAMIC_TABLE', 'ALTER DYNAMIC TABLE {DT_NAME} RESUME RECLUSTER', 'DT is suspended — resume it', 0.9),
('Unsupported subquery', 'DT_QUERY_ERROR', 'DYNAMIC_TABLE', 'SELECT ''NEEDS_LLM_QUERY_REWRITE''', 'DT query uses unsupported pattern — LLM should rewrite to incrementalizable form', 0.3),
('not incrementalizable', 'DT_REFRESH_MODE', 'DYNAMIC_TABLE', 'SELECT ''NEEDS_LLM_INCREMENTAL_FIX''', 'DT query not incrementalizable — LLM should review refresh_mode_reason and restructure', 0.3);
```

## Notes

- Entries with `NEEDS_LLM_*` as the fix template signal the diagnose procedure to fall through to LLM reasoning
- `OBJECT_TYPE` column filters runbook entries: TASK-only fixes won't apply to DT failures and vice versa. `ALL` applies to both.
- Confidence values are used by guardrails: high-confidence runbook entries bypass review, low-confidence ones trigger LLM
- `{DT_NAME}` placeholder is used for dynamic table fixes, `{TASK_NAME}` for task fixes
- Users should add patterns specific to their environment (custom UDFs, external functions, etc.)

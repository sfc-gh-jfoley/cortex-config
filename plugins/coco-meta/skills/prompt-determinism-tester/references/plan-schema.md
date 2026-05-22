# Build Plan Schema

Each swarm agent MUST produce its plan in this exact format. This is the contract that enables automated comparison.

## Format

```
BUILD_PLAN:
  OBJECTS:
    - name: <FULLY_QUALIFIED_OBJECT_NAME>
      type: <TABLE|VIEW|DYNAMIC_TABLE|SEMANTIC_VIEW|AGENT|STAGE|FUNCTION|PROCEDURE|TASK|STREAM>
      ddl_action: <CREATE|CREATE_OR_REPLACE|ALTER|INSERT>
      row_count: <integer or NULL if not a data table>
      depends_on: [<list of object names this depends on, empty if none>]
      columns:
        - name: <COLUMN_NAME>
          type: <DATA_TYPE e.g. VARCHAR, NUMBER(10,2), TIMESTAMP_NTZ, VARIANT, BOOLEAN>
          nullable: <TRUE|FALSE>
          note: <optional — only if column has DEFAULT, IDENTITY, or special constraint>
      notes: <one-line description of purpose>

  SEQUENCE:
    1. <object_name> — <ddl_action>
    2. <object_name> — <ddl_action>
    ...

  ARTIFACTS:
    - <file or object produced as final output, e.g. "semantic view", "agent spec JSON", "Streamlit app">

  SNOWFLAKE_FEATURES:
    - <feature used: DYNAMIC_TABLE, SEMANTIC_VIEW, CORTEX_AGENT, AI_SENTIMENT, AI_CLASSIFY, AI_EXTRACT, AI_COMPLETE, VARIANT_PARSE, FLATTEN, CLUSTER_BY, SEARCH_OPTIMIZATION, etc.>
```

## Rules

1. **OBJECTS** — Every DDL/DML object the build would create. Use fully qualified names where possible (DB.SCHEMA.NAME). If the prompt uses SET variables, use the variable reference (e.g., `$MY_DB.$MY_SCHEMA.TABLE_NAME`).

2. **SEQUENCE** — The execution order. Objects that depend on others must come after their dependencies. Number sequentially starting at 1.

3. **ROW_COUNT** — For tables with INSERT statements, state the exact row count the build would produce. For views/DTs/SVs, use NULL.

4. **ARTIFACTS** — Final deliverables the prompt asks for (not intermediate objects). These are what the lab attendee walks away with.

5. **SNOWFLAKE_FEATURES** — Snowflake-specific features the build uses. This catches divergence where one agent uses a Dynamic Table and another uses a scheduled Task, or one uses AI_CLASSIFY and another uses CORTEX.COMPLETE with a classification prompt.

6. **COLUMNS** — For tables and Dynamic Tables, list every column with name, type, and nullable. This is critical — downstream objects (DTs, SVs, Agents) depend on the exact DDL structure. Omit for non-table objects (views, agents, etc.).

7. **TYPES MATTER** — Use Snowflake canonical types. `VARCHAR` and `STRING` are equivalent (normalize to `VARCHAR`). `NUMBER` and `INT` are NOT equivalent — `NUMBER(38,0)` vs `NUMBER(10,2)` changes downstream behavior. Be precise.

## What to IGNORE

- Actual data values (synthetic data content is irrelevant)
- Exact SQL syntax (formatting, alias style, comment style)
- Warehouse selection
- Role/permission grants (unless the prompt explicitly asks for them)
- `VARCHAR` vs `STRING` vs `TEXT` (all equivalent in Snowflake)
- `TIMESTAMP_NTZ` vs `TIMESTAMP` without timezone spec (equivalent)

## What MUST MATCH

- Table names (exact, case-insensitive)
- Column names (exact, case-insensitive)
- Column data types (numeric precision matters: NUMBER(10,2) vs FLOAT)
- Column order (position matters for SELECT * patterns)
- Object types (TABLE vs VIEW vs DYNAMIC_TABLE)
- Row counts for seeded tables
- DDL execution sequence (dependency order)

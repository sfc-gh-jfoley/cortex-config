---
name: sv-ddl-phase5-generate
description: Generate the CREATE SEMANTIC VIEW DDL from classified columns and relationships, with built-in self-check before presenting to user
---

# Phase 5: Generate DDL

## Purpose
Build the complete `CREATE OR REPLACE SEMANTIC VIEW` statement from the classified columns, relationships, and descriptions collected in Phases 1-4.

**Read [../reference/ddl_syntax.md](../reference/ddl_syntax.md) before generating any DDL.**

---

## Step 5.0.5: FILTER label feature probe

`LABELS = (FILTER)` went GA on May 5, 2026. Accounts on older deployments may not support it yet.

**Before generating DDL**, if any `filter_candidate: true` columns exist in `COLUMN_CLASSES`, run this probe:

```sql
-- Feature probe: test if LABELS = (FILTER) syntax is supported
CREATE OR REPLACE SEMANTIC VIEW <SV_DB>.<SV_SCHEMA>.__FILTER_PROBE
  TABLES ( <first_source_object> PRIMARY KEY (<any_pk_col>) )
  FACTS ( <table_alias>.probe_filter LABELS = (FILTER) AS TRUE )
  COMMENT = 'Feature probe — will be dropped immediately';
```

- **If CREATE succeeds**: Set `FILTER_SUPPORTED = true`. Drop the probe immediately:
  ```sql
  DROP SEMANTIC VIEW IF EXISTS <SV_DB>.<SV_SCHEMA>.__FILTER_PROBE;
  ```
- **If CREATE fails** (syntax error on LABELS): Set `FILTER_SUPPORTED = false`. Emit a note to the user:
  ```
  ℹ️  LABELS = (FILTER) is not yet available on this account.
      Boolean filter expressions will be emitted as plain facts/dimensions instead.
      They still work — Cortex Analyst can use boolean columns in WHERE clauses.
      This feature will become available when your account receives the May 2026 release.
  ```

If no `filter_candidate: true` columns exist, skip this step entirely.

---

## Step 5.1: Build the TABLES clause

For each table in `SOURCE_OBJECTS`, generate the table entry.

**Template**:
```sql
<logical_alias> AS <DB>.<SCHEMA>.<PHYSICAL_TABLE>
  PRIMARY KEY ( <pk_col> [ , ... ] )       -- from RELATIONSHIPS.PRIMARY_KEYS
  WITH SYNONYMS = ( '<alias1>', '<alias2>' )  -- from BUSINESS_CONTEXT or table description
  COMMENT = '<table description>'            -- from COLUMN_DESCRIPTIONS or BUSINESS_CONTEXT
```

If `RANGE_JOIN_CANDIDATES` exist for this table (from Phase 3), add the range constraint:
```sql
<logical_alias> AS <DB>.<SCHEMA>.<PHYSICAL_TABLE>
  PRIMARY KEY ( <pk_col> [ , ... ] )
  CONSTRAINT <table>_range DISTINCT RANGE BETWEEN <start_col> AND <end_col> EXCLUSIVE
  WITH SYNONYMS = ( '<alias1>', '<alias2>' )
  COMMENT = '<table description>'
```

Rules:
- `logical_alias` should be lowercase + underscore for readability: `vehicles`, `dealers`, `orders`
- If no primary key was confirmed in Phase 4, use `UNIQUE (<best_candidate>)` instead
- Table COMMENT = generated table-level description from Phase 2
- DISTINCT RANGE BETWEEN columns must be from the same table and same type (DATE/TIMESTAMP/NUMBER) — both `start_col` and `end_col` must be physical columns in this table

> ⚠️ **HARD REQUIREMENTS — will cause CREATE or runtime failure without them:**
>
> 1. **Fully qualified table names** — every table MUST use `DATABASE.SCHEMA.TABLE` format. Never use bare table names or schema.table format. Run `SELECT CURRENT_DATABASE(), CURRENT_SCHEMA()` if unsure.
>
> **RECOMMENDED (WARN if missing, skill will still proceed):**
>
> 2. **COMMENT on every table and column** — strongly improves Cortex Analyst question matching. The skill will generate these automatically from Phase 2 profiling, but won't block if they're absent.
> 3. **PRIMARY KEY or UNIQUE on tables** — without it, RELATIONSHIPS referencing this table will fail. Single-table SVs or tables not in any relationship are fine without one.
> 4. **WITH SYNONYMS on tables and columns** — improves question matching but not functionally required.
>
> The skill will auto-generate COMMENTs and SYNONYMS when possible. If it can't (no profiling data), it will proceed with a WARN rather than blocking.

---

## Step 5.2: Build the RELATIONSHIPS clause

For each relationship in `RELATIONSHIPS`:

```sql
<rel_name> AS <left_alias> ( <left_col> ) REFERENCES <right_alias>
```

Naming convention for `rel_name`: `<left_alias>_to_<right_alias>` (e.g. `line_items_to_orders`)

If the right table has a different PK column name than the FK column:
```sql
<rel_name> AS <left_alias> ( <fk_col> ) REFERENCES <right_alias> ( <pk_col> )
```

For `ASOF_RELATIONSHIPS` (from Phase 4), emit point-in-time join syntax:
```sql
<rel_name> AS <left_alias> ( <fk_col>, <date_col> ) REFERENCES <right_alias> ( <pk_col>, ASOF <effective_date> )
```

For `RANGE_RELATIONSHIPS` (from Phase 4), emit range join syntax:
```sql
<rel_name> AS <left_alias> ( <date_col> ) REFERENCES <right_alias> ( BETWEEN <start_col> AND <end_col> EXCLUSIVE )
```

Present ASOF and Range relationships in a clearly labeled subsection so the user can review them separately from standard FK joins.

---

## Step 5.3: Build the FACTS clause

For each column with `class = "FACT"` in `COLUMN_CLASSES`:

```sql
<table_alias>.<fact_name> AS <physical_col_name>
  WITH SYNONYMS = ( '<syn1>', '<syn2>' )
  COMMENT = '<description>'
```

⚠️ **CRITICAL RULE**: For direct column references, the alias after `AS` **must exactly match the source object's column name**.
- ✅ `orders.O_TOTALPRICE AS O_TOTALPRICE`
- ❌ `orders.total_price AS O_TOTALPRICE` → will fail with "invalid identifier"

For computed expressions (derived facts), the new name is fine:
- ✅ `line_items.discounted_price AS L_EXTENDEDPRICE * (1 - L_DISCOUNT)`

If the column is tagged `filter_candidate: true` in `COLUMN_CLASSES` AND its expression resolves to BOOLEAN, emit the FILTER label:
```sql
<table_alias>.<fact_name>
  LABELS = ( FILTER )
  AS <boolean_expr>
  COMMENT = '<description>'
```

> ⚠️ **FILTER Deployment Guard**: Before emitting ANY `LABELS = (FILTER)` entries, run a feature probe first (see Step 5.0.5 above). If the probe fails, emit these as plain boolean facts WITHOUT the LABELS clause — they still work as boolean expressions that Cortex Analyst can use in WHERE clauses, just without the explicit FILTER semantic hint.

**Duplicate column names across source objects**: if two objects both have `AMOUNT`, define it in **one table only** (the primary source). Skip the duplicate in the other table.

---

## Step 5.4: Build the DIMENSIONS clause

For each column with `class = "DIMENSION"` or `class = "TIME_DIMENSION"`:

```sql
<table_alias>.<dim_name> AS <physical_col_name>
  WITH SYNONYMS = ( '<syn1>', '<syn2>' )
  COMMENT = '<description>'
```

Same alias rule applies: alias must match the source column name for direct references.

If the column is tagged `filter_candidate: true` in `COLUMN_CLASSES` AND is BOOLEAN type, emit the FILTER label (only if Step 5.0.5 probe passed):
```sql
<table_alias>.<dim_name>
  LABELS = ( FILTER )
  AS <physical_col_name>
  COMMENT = '<description>'
```

> If the FILTER probe failed in Step 5.0.5, emit these as plain boolean dimensions without LABELS.

For computed dimensions (e.g. extracting year from date):
```sql
<table_alias>.order_year AS YEAR(<physical_date_col>)
  COMMENT = 'Calendar year extracted from order date'
```

---

## Step 5.5: Build the METRICS clause

For each entry in `PROPOSED_METRICS`:

```sql
<table_alias>.<metric_name>
  [ USING ( <rel_name> ) ]      -- only if MULTI_REL_PAIRS includes this table pair
  AS <aggregate_expr>
  WITH SYNONYMS = ( '<syn1>', '<syn2>' )
  COMMENT = '<description>'
```

Add `USING` clause for any metric that is ambiguous due to multiple relationship paths (from `MULTI_REL_PAIRS`).

---

## Step 5.5.5: Build Window Function Metrics

For each entry in `WINDOW_METRIC_CANDIDATES` (from Phase 3):

```sql
<table_alias>.<metric_name> AS <window_function>( <metric_ref> ) OVER (
  [ PARTITION BY EXCLUDING <dims_to_exclude> ]
  [ ORDER BY <ordering_dim> [ ASC | DESC ] ]
  [ <window_frame> ]
)
  COMMENT = '<description>'
```

Rules:
- Inner `<metric_ref>` must reference a metric already defined in the same table's METRICS section — if it doesn't exist, define it first (as PRIVATE if it shouldn't be user-facing)
- Cannot use aggregates or subqueries in PARTITION BY
- EXCLUDING dims must be accessible dimensions from the same entity
- `PARTITION BY EXCLUDING` removes specified dims from the partition at query time (dynamic)
- Common patterns:
  - Running total: `SUM(<metric>) OVER (ORDER BY <time_dim> ROWS UNBOUNDED PRECEDING)`
  - Rolling average: `AVG(<metric>) OVER (ORDER BY <time_dim> ROWS 6 PRECEDING)`
  - Rank: `RANK() OVER (PARTITION BY EXCLUDING <time_dim> ORDER BY <metric> DESC)`
  - Period-over-period: `LAG(<metric>) OVER (ORDER BY <time_dim>)`

---

## Step 5.6: Build AI_SQL_GENERATION instructions

Compose a targeted instruction block from `BUSINESS_CONTEXT`:

```sql
AI_SQL_GENERATION '
  <summarize key SQL generation rules derived from business context>
  Examples:
  - Always filter by STATUS = ''ACTIVE'' unless user asks for all statuses.
  - Use ACQUISITION_DATE for time-based filtering, not LAST_MODIFIED_AT.
  - Prefer COUNT(DISTINCT DEALER_ID) for unique dealer counts.
'
```

### AI_QUESTION_CATEGORIZATION (conditional)

Only generate this clause if `BUSINESS_CONTEXT` mentions sensitive data, question boundaries, scope limitations, or data access restrictions.

```sql
AI_QUESTION_CATEGORIZATION '
  <instructions for routing/rejecting questions based on BUSINESS_CONTEXT>
  Examples:
  - Questions about individual employee salaries: reject with "This view does not expose individual compensation data"
  - Questions about future predictions: clarify "This view contains historical data only. Do you want trends?"
  - Questions outside the domain scope: reject with "This semantic view covers <domain> only"
'
```

Rules:
- Derive categorization rules from BUSINESS_CONTEXT — do not invent restrictions the user didn't specify
- Include at least one "reject" example and one "clarify" example when applicable
- Keep instructions concise — Cortex Analyst uses these at query time

---

## Step 5.7: Assemble the full DDL

Combine all sections in the **mandatory order**: TABLES → RELATIONSHIPS → FACTS → DIMENSIONS → METRICS

Template:
```sql
CREATE OR REPLACE SEMANTIC VIEW <SV_DB>.<SV_SCHEMA>.<SV_NAME>
  TABLES (
    <table entries>
  )
  RELATIONSHIPS (
    <relationship entries>
  )
  FACTS (
    <fact entries>
  )
  DIMENSIONS (
    <dimension entries>
  )
  METRICS (
    <metric entries>
  )
  COMMENT = '<semantic view description>'
  AI_SQL_GENERATION '<generation instructions>'
  [ AI_QUESTION_CATEGORIZATION '<categorization instructions>' ];
```

If no relationships (user declined in Phase 4 or single table): omit the RELATIONSHIPS block entirely (do not leave it empty).

---

## Step 5.8: Self-check before presenting to user

Before showing the DDL to the user, perform these checks internally.

### Analyst Posture (MANDATORY mindset for all checks below)

Adopt the posture of a skeptical data analyst who has been burned by silent wrong results. Apply these principles:

1. **Never trust the PK declaration** — assume it's wrong until you verify: is this column actually unique in this table, or is it a FK that happens to be named like a PK? If the column declared as PK also appears as a FK in another table, it is almost certainly NOT unique here.
2. **Never trust that SUM is correct** — for every SUM metric, ask: "If I sum this across all dates, does the result make business sense?" If the answer is "no, that would double-count" → it's a snapshot and needs NON ADDITIVE BY.
3. **Never trust that a relationship is complete** — for every table in TABLES, verify it participates in at least one relationship. Orphaned tables are invisible time bombs.
4. **Never trust that synonyms are unique** — analysts will use the most obvious word ("revenue", "amount", "total"). If two definitions share that word, Cortex Analyst will refuse the question. Check every synonym for overlap.
5. **Assume the metric grain is wrong** — if a metric lives on a parent table but dimensions are only reachable through a child, the numbers WILL be inflated. Verify the join path exists at the correct grain.
6. **NON ADDITIVE BY only works with SUM, AVG, MIN, MAX** — never apply it to COUNT, COUNT DISTINCT, or derived expressions. If the semi-additive audit flags a COUNT DISTINCT metric, the fix is NOT to add NON ADDITIVE BY — instead, rethink whether the metric definition itself is correct for snapshot data.

This posture applies to EVERY check below. When in doubt, flag for the user rather than silently passing.

### Syntax self-checks (all must pass)

| Check | How to verify |
|-------|--------------|
| Clause order: TABLES → RELATIONSHIPS → FACTS → DIMENSIONS → METRICS | Read the generated DDL top-to-bottom. If RELATIONSHIPS is omitted (single-table only), order is TABLES → FACTS → DIMENSIONS → METRICS. |
| Every fact/dim with direct column ref has alias = source column name | Compare `AS <alias>` against `DESCRIBE TABLE` column list |
| No duplicate column names across FACTS sections | Scan all FACTS entries for repeated alias names |
| Every REFERENCES table has PRIMARY KEY or UNIQUE defined | Check TABLES clause for each right-hand table in RELATIONSHIPS |
| USING clause present for every metric involving a MULTI_REL_PAIRS table pair | Cross-reference metrics against MULTI_REL_PAIRS list |
| No empty RELATIONSHIPS block | If the DDL contains a `RELATIONSHIPS (` clause, it MUST have at least one relationship defined inside — empty `RELATIONSHIPS ()` is a syntax error. If no relationships exist, omit the clause entirely. For multi-table SVs with no relationships defined, the Step 5.7 inference should have already prompted the user. |
| Source object names are fully qualified (`DB.SCHEMA.OBJECT`) | Scan TABLES clause — every object in `AS <name>` must match pattern `\w+\.\w+\.\w+` (3-part name). Bare names or 2-part names are FAIL. |
| PRIMARY KEY or UNIQUE defined for tables in TABLES | WARN if missing — strongly recommended for multi-table SVs. Without it, RELATIONSHIPS cannot reference this table. Single-table SVs without a PK are acceptable. |
| WITH SYNONYMS and COMMENT on column entries | WARN if missing. The skill should auto-generate both from Phase 2 profiling. If absent, note degraded Analyst quality but do not block. |
| String literals in metric expressions use single-quotes with NO extra escaping — `COUNT_IF(OUTCOME = 'WON')` is correct; `COUNT_IF(OUTCOME = ''WON'')` is **wrong** and will fail at execution | Scan every `AS <aggregate_expr>` in METRICS for `''` double-quote patterns |
| Non-standard column names (from `NON_STANDARD_COLUMNS`) are double-quoted **everywhere** they appear: in `AS <alias>`, inside computed expressions, and in `AI_SQL_GENERATION` examples. Use `REPLACE(col_name, '"', '""')` for names that themselves contain a double-quote character. Example: `t."user@email.com" AS "user@email.com"`. Standard names (`[A-Z0-9_]` only, not starting with digit) need no quoting. | Cross-reference every column name in FACTS/DIMENSIONS/METRICS against `NON_STANDARD_COLUMNS`; fail if any appears unquoted |
| FILTER label only on boolean expressions | For every entry with `LABELS = (FILTER)`, verify the `AS <expr>` resolves to BOOLEAN type. Non-boolean FILTER labels will cause runtime errors. |
| Window metric references valid inner metric | For every window function metric, verify the inner `<metric_ref>` exists as a defined metric in the same table's METRICS section. Missing inner metrics will fail at creation. |
| PARTITION BY EXCLUDING dims are accessible | For every `PARTITION BY EXCLUDING <dims>`, verify each excluded dimension is defined and accessible from the same entity. Inaccessible dims cause silent wrong results. |
| ASOF column type is DATE/TIMESTAMP/NUMBER | For every ASOF relationship, verify the ASOF-marked column's data type is DATE, TIMESTAMP_*, or NUMBER. Other types are not supported for point-in-time joins. |
| COMMENT placement is AFTER all clauses | Verify COMMENT = '...' appears only after METRICS (or last present clause), never before TABLES or between clauses. Top-level COMMENT is NOT part of any clause block. |
| No COMMENT inside RELATIONSHIPS block | Verify no relationship definition includes a COMMENT — relationship grammar only supports: `<name> AS <left> (<col>) REFERENCES <right> [(<col>)]`. COMMENT on relationships is NOT supported syntax. |
| All SYNONYMS use `WITH SYNONYMS = (...)` prefix | Verify every SYNONYMS entry uses `WITH SYNONYMS = ('...', '...')` — bare `SYNONYMS = (...)` without `WITH` will fail. Must appear on tables, facts, dims (not relationships, not metrics without WITH). |

### Semantic correctness checks (all must pass)

| Check | How to verify |
|-------|--------------|
| Every table in TABLES appears in at least one RELATIONSHIP (orphan detection) | Scan RELATIONSHIPS for each table alias — any table not mentioned on either side of any relationship (and there is more than one table) is orphaned. Queries using its dimensions will error: "must be related to and have an equal or lower level of granularity" |
| No metric is defined at a coarser grain than dimensions reachable only through a child table (fan trap) | If a metric's table connects to a dimension table only via a child/bridge table (e.g., metric on ORDERS, dimension on ORDER_ITEMS → PRODUCTS), flag with a concrete fix suggestion: "Metric `SUM(orders.revenue)` at ORDERS grain cannot be safely grouped by PRODUCTS dimensions — the join through LINE_ITEMS will inflate results by ~N× (items per order)." Offer two options: (A) Move the metric to the bridge table: `line_items.revenue AS SUM(LINE_ITEMS.EXTENDED_PRICE)` — grouped by product dimensions directly. (B) Create a pre-aggregated bridge metric at order grain if the user truly needs order-level revenue by product: suggest a derived fact or pre-aggregated view. Present both options and let the user decide. |
| Every PRIMARY KEY declaration uses the actually-unique column (cardinality-lie warning) | If the column declared as PK also appears as a FK column in another table's RELATIONSHIPS left-hand side, **warn** — it is likely not unique in this table. A wrong PK silently disables fan-trap guards and inflates numbers. Verify: `SELECT COUNT(*), COUNT(DISTINCT pk_col) FROM table` — if they differ, the PK is wrong. |
| No synonym appears in more than one definition (synonym overlap) | Collect all WITH SYNONYMS values across all FACTS, DIMENSIONS, and METRICS entries. If any synonym string appears in two or more definitions, flag — Cortex Analyst will refuse questions using the ambiguous term. Remove or scope the duplicate synonym. |
| Every SUM metric on a snapshot-grain table prompts NON ADDITIVE BY review (semi-additive audit) | If the table's COMMENT or any column COMMENT contains keywords: 'snapshot', 'balance', 'headcount', 'inventory', 'pipeline', 'open deals', 'active subscribers' — AND the metric uses SUM or COUNT — flag for review: "This looks like snapshot data. Should this metric use `NON ADDITIVE BY (<time_dimension> DESC)`?" Accept if user confirms SUM is intentional. |

### Self-check output

Present internally (not to user yet):
```
Self-check: 23/23 checks passed ✓
Proceeding to present DDL.
```

If any check fails — **fix the DDL first**, then re-run self-check. Do not present broken DDL to user.

---

## Step 5.8.5: Run syntax validation

After the internal self-check passes, validate the generated DDL with a compilation check
before presenting to the user:

```sql
-- Validate the DDL compiles without executing
-- Use only_compile=true via sql_execute, or run sv_validator.py if available
```

Alternatively, if the `scripts/sv_validator.py` script is available in this skill directory,
run it against the generated DDL file for a doc-backed second pass:

```bash
uv run python scripts/sv_validator.py <ddl_file.sql>
```

- **FAIL** → fix the issues reported, re-run Step 5.8 self-check, then re-run validation
- **WARN** → note warnings in the Step 5.9 presentation summary
- **PASS** → proceed

---

## Step 5.9: Present DDL to user

Present the full DDL in a code block. Include a brief summary:

```
✅ DDL generated — self-check passed

Semantic View: <SV_DB>.<SV_SCHEMA>.<SV_NAME>
  Tables:        N  (<list of logical aliases>)
  Relationships: N
  Facts:         N  (direct column references)
  Dimensions:    N  (including N time dimensions)
  Metrics:       N  (aggregate expressions)

[DDL here]

Next step: Phase 6 — execute and validate.
Type 'go' to execute, or make edits first.
```

⚠️ **STOPPING POINT** — Wait for user to approve or request changes.

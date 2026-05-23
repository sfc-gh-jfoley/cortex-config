---
name: sv-ddl-phase2-profile-describe
description: Profile source objects and use CORTEX.COMPLETE to auto-generate column descriptions, synonyms, and sample values
---

# Phase 2: Profile & Auto-Describe

## Purpose
Profile each source object's data and use `SNOWFLAKE.CORTEX.COMPLETE` to generate:
- Column descriptions (1-2 sentences, business-readable)
- Synonyms (2-3 natural language aliases)
- Sample values (5 representative values for categorical columns)

This is the programmatic equivalent of what Snowsight does manually when you describe a semantic view column.

---

## Step 2.0: Source system and doc context classification

Before profiling, classify `DOC_CONTEXT` so Phase 2 can inject the right context into CORTEX.COMPLETE.

**Known source systems** (case-insensitive match against `DOC_CONTEXT`):

| Match | SOURCE_SYSTEM | Injection text |
|-------|--------------|----------------|
| `salesforce` / `sfdc` / `sf crm` | `Salesforce` | "This data originates from Salesforce CRM. Apply standard SFDC object/field conventions: ACCOUNT_ID → Account.Id, OPPORTUNITY_STAGE → Opportunity.StageName, LEAD_SOURCE → Lead.LeadSource, etc. Use Salesforce Help field definitions where the column name maps to a known SFDC field." |
| `hubspot` | `HubSpot` | "This data originates from HubSpot. Apply HubSpot CRM property naming conventions: contact properties, deal stages, company properties, lifecycle stages." |
| `sap` | `SAP` | "This data originates from SAP. Column names follow SAP ABAP naming conventions (e.g. KUNNR=customer number, MATNR=material number, VBELN=sales document). Apply standard SAP module terminology." |
| `workday` | `Workday` | "This data originates from Workday HCM/Finance. Apply Workday object naming: Worker, Position, Cost Center, Ledger Account conventions." |
| `marketo` | `Marketo` | "This data originates from Marketo. Apply Marketo lead/activity/program field naming conventions." |
| `netsuite` | `NetSuite` | "This data originates from NetSuite ERP. Apply NetSuite record type and field naming conventions (e.g. tranid=transaction ID, entity=customer/vendor)." |
| `zendesk` | `Zendesk` | "This data originates from Zendesk. Apply Zendesk ticket/user/organization field naming conventions." |
| `servicenow` | `ServiceNow` | "This data originates from ServiceNow. Apply ServiceNow ITSM table/field naming conventions (e.g. sys_id, caller_id, assignment_group)." |

**Logic:**

```
If DOC_CONTEXT matches a known source system name:
  Set SOURCE_SYSTEM = "<matched name>"
  Set SOURCE_SYSTEM_PROMPT = "<injection text from table above>"
  Set DOC_CONTEXT_TYPE = "source_system"

Else if DOC_CONTEXT was parsed as a CSV data dictionary (has table_name, column_name, description cols):
  Set DOC_CONTEXT_TYPE = "data_dict"
  Pre-populate COLUMN_DESCRIPTIONS from CSV rows directly — no AI inference needed for matched rows
  Store unmatched columns (those not in CSV) in UNMATCHED_COLUMNS for AI inference in Step 2.2

Else if DOC_CONTEXT is non-null text:
  Set DOC_CONTEXT_TYPE = "text"
  Set SOURCE_SYSTEM = null

Else:
  Set DOC_CONTEXT_TYPE = null
  Set SOURCE_SYSTEM = null
```

If `DOC_CONTEXT_TYPE = "data_dict"` and all columns are matched from the CSV: skip Step 2.2 entirely and go directly to Step 2.3 (apply comments). If only some are matched, run Step 2.2 only for unmatched columns.

---

## Step 2.1: Profile each source object

**If `AUTO_SAMPLE = false`**: skip sample value collection (the `ARRAY_AGG(DISTINCT ...)` queries below). Set `sample_values = []` for all columns and proceed directly to Step 2.2 after running the column catalog query only.

> **Note**: The profiling queries below use `DESCRIBE TABLE` and `SELECT` statements. These work for all supported source types (tables, views, dynamic tables, secure views) because Snowflake's `DESCRIBE TABLE` command works on views and dynamic tables as well. No branching is needed for standard profiling.

For **each object** in `SOURCE_OBJECTS`, run this profiling query. Replace `<OBJECT>` with the fully qualified name.

```sql
SELECT
    c.COLUMN_NAME,
    c.DATA_TYPE,
    c.COMMENT,
    c.IS_NULLABLE,
    c.CHARACTER_MAXIMUM_LENGTH,
    COUNT_IF(t.<col> IS NOT NULL)            AS non_null_count,
    COUNT_IF(t.<col> IS NULL)                AS null_count,
    COUNT(DISTINCT t.<col>)                  AS distinct_count,
    COUNT(*)                                 AS total_rows
FROM INFORMATION_SCHEMA.COLUMNS c
WHERE c.TABLE_CATALOG = '<db>'
  AND c.TABLE_SCHEMA  = '<schema>'
  AND c.TABLE_NAME    = '<table>'
ORDER BY c.ORDINAL_POSITION;
```

**Note**: The `non_null_count`/`null_count`/`distinct_count` columns above are illustrative — run a separate count query per column for tables with wide schemas. For most tables, use the simplified profiling query below:

```sql
-- Simplified profiling: row count + column catalog
SELECT
    COLUMN_NAME,
    DATA_TYPE,
    COMMENT,
    IS_NULLABLE
FROM <db>.INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = '<schema>'
  AND TABLE_NAME   = '<table>'
ORDER BY ORDINAL_POSITION;

-- Row count
SELECT COUNT(*) AS total_rows FROM <db>.<schema>.<table>;
```

Then for **categorical columns** (VARCHAR, BOOLEAN, DATE) with manageable cardinality — get sample values:

```sql
SELECT ARRAY_AGG(DISTINCT <col>::VARCHAR) WITHIN GROUP (ORDER BY <col>::VARCHAR)
FROM (SELECT <col> FROM <db>.<schema>.<table> LIMIT 500) t
WHERE <col> IS NOT NULL;
```

Store results as `TABLE_PROFILES` — a per-table dict of column metadata.

---

## Step 2.1.5: Non-standard identifier scan

After collecting column names from DESCRIBE / INFORMATION_SCHEMA, scan **every column name** across all source objects for characters that require double-quote wrapping.

**A column name is non-standard if it:**
- Contains any character outside `A-Z`, `0-9`, `_` (after uppercasing)
- Starts with a digit
- Contains SQL-significant chars: `@`, `.`, `-`, `:`, `|`, `"`, `(`, `)`, space, or tab
- Matches patterns suggesting auto-generation: contains `||`, `current_timestamp`, `::`, numeric suffix after special char

**Detection query** (run once per table):

```sql
SELECT
    COLUMN_NAME,
    CASE
        WHEN COLUMN_NAME != UPPER(REGEXP_REPLACE(COLUMN_NAME, '[^A-Z0-9_]', ''))
             OR REGEXP_LIKE(COLUMN_NAME, '^[0-9].*')
        THEN TRUE
        ELSE FALSE
    END AS needs_quoting,
    '"' || REPLACE(COLUMN_NAME, '"', '""') || '"' AS safe_quoted_form
FROM <db>.INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = '<schema>'
  AND TABLE_NAME   = '<table>'
  AND (
      COLUMN_NAME != UPPER(REGEXP_REPLACE(COLUMN_NAME, '[^A-Z0-9_]', ''))
      OR REGEXP_LIKE(COLUMN_NAME, '^[0-9].*')
  )
ORDER BY ORDINAL_POSITION;
```

**If any non-standard columns are found:**

1. Store them in `NON_STANDARD_COLUMNS` as a dict: `{original_name: safe_quoted_form}`
2. Print a warning block before the description preview:

```
⚠️  NON-STANDARD COLUMN IDENTIFIERS DETECTED

These column names require double-quote wrapping in all DDL expressions.
They will be quoted automatically in the generated semantic view.

  Table: <TABLE>
  ┌─────────────────────────────────────┬──────────────────────────────────────────┐
  │ Column name (raw)                   │ Safe quoted form                         │
  ├─────────────────────────────────────┼──────────────────────────────────────────┤
  │ user@email.com                      │ "user@email.com"                         │
  │ dev_||@_||timestamp:_:_._old        │ "dev_||@_||timestamp:_:_._old"           │
  │ 2023_revenue                        │ "2023_revenue"                           │
  └─────────────────────────────────────┴──────────────────────────────────────────┘

  These columns will be classified normally in Phase 3 but will be
  excluded from FACTS/DIMENSIONS/METRICS unless you explicitly include them.
  Recommendation: SKIP non-standard columns in classification unless they
  carry essential business value — they create fragile DDL.
```

3. In Phase 3 classification, **default non-standard columns to SKIP** with the note `[non-standard identifier — skipped by default]`. The user can override to DIMENSION/FACT if needed.
4. If a non-standard column IS kept (user overrides to DIMENSION/FACT), flag it in Phase 5 so Rule 9 wraps it in double-quotes everywhere it appears in the DDL — including inside computed expressions.

---

## Step 2.2: Auto-describe with CORTEX.COMPLETE

For each column, build and execute a CORTEX.COMPLETE prompt.

**Prompt template** (use `complete_fast` alias for speed, `complete_quality` alias for quality — see `~/.snowflake/cortex/vault/LLMs.md`):

```sql
SELECT SNOWFLAKE.CORTEX.COMPLETE(
  'mistral-7b',  -- complete_fast alias from LLMs.md
  CONCAT(
    'You are a data documentation expert. Generate metadata for a database column.\n',
    'Respond ONLY with a JSON object — no explanation, no markdown fences.\n\n',
    'Table: ', '<table_name>', '\n',
    'Column: ', '<col_name>', '\n',
    'Data type: ', '<data_type>', '\n',
    'Nullable: ', '<is_nullable>', '\n',
    'Distinct values (approx): ', '<distinct_count>', '\n',
    'Sample values: ', '<sample_values_csv>', '\n',
    'Existing comment: ', '<existing_comment_or_none>', '\n',
    'Business context: ', '<BUSINESS_CONTEXT>', '\n',
    CASE
      WHEN '<DOC_CONTEXT_TYPE>' = 'source_system'
           THEN CONCAT('Source system: ', '<SOURCE_SYSTEM>', '\n', '<SOURCE_SYSTEM_PROMPT>', '\n')
      WHEN '<DOC_CONTEXT_TYPE>' = 'text'
           THEN CONCAT('Documentation context:\n', '<DOC_CONTEXT>', '\n')
      ELSE ''
    END,
    '\n',
    'Return exactly this JSON structure:\n',
    '{"description": "1-2 sentence business description",',
    '"synonyms": ["alias1","alias2","alias3"],',
    '"sample_values": ["val1","val2","val3","val4","val5"]',
    '}'
  )
) AS col_metadata;
```

**Batch strategy**: For tables with many columns (>20), batch 5 columns per CORTEX.COMPLETE call to reduce latency:

```sql
SELECT SNOWFLAKE.CORTEX.COMPLETE(
  'mistral-7b',  -- complete_fast alias from LLMs.md
  CONCAT(
    'Generate JSON metadata for these ', <N>, ' columns from table <table_name>.\n',
    'Business context: <BUSINESS_CONTEXT>\n',
    'Return a JSON array, one object per column with keys: column_name, description, synonyms, sample_values.\n\n',
    'Columns:\n',
    '1. <col1> (<type1>) sample values: <samples1>\n',
    '2. <col2> (<type2>) sample values: <samples2>\n',
    ...
  )
) AS batch_metadata;
```

Parse the JSON result and store as `COLUMN_DESCRIPTIONS` — a dict keyed by `table.column`.

---

## Step 2.3: Apply descriptions as COMMENT ON COLUMN

After generating descriptions, apply them to Snowflake so FastGen or DESCRIBE will pick them up:

```sql
-- Apply table comment
COMMENT ON TABLE <db>.<schema>.<table>
  IS '<generated table description>';

-- Apply per-column comments (repeat for each column)
ALTER TABLE <db>.<schema>.<table>
  ALTER COLUMN <col_name> COMMENT '<generated description>';
```

**Note**: This modifies the source objects (applies COMMENT ON COLUMN). If that's not acceptable, set `APPLY_COMMENTS = false` and skip this step — descriptions will be injected directly into the DDL COMMENT clauses in Phase 5.

Ask user: "Apply descriptions as COMMENT ON COLUMN in Snowflake? (yes = updates source objects, no = inject into DDL only)"

---

## Step 2.4: Present description preview

Show a sample of 3-5 generated descriptions for user review:

```
Auto-description preview (3 of N columns):

  DEALER_ID (VARCHAR)
    → Description: "Unique identifier for each dealership in the network."
    → Synonyms: dealer id, dealership id, dealer code
    → Sample values: DLR-001, DLR-042, DLR-118

  DAYS_IN_INVENTORY (NUMBER)
    → Description: "Number of days a vehicle has been on the lot since acquisition."
    → Synonyms: lot age, days on lot, inventory age
    → Sample values: 3, 14, 47, 62, 89

  LISTING_STATUS (VARCHAR)
    → Description: "Current listing status of the vehicle on the marketplace."
    → Synonyms: status, availability, listing state
    → Sample values: ACTIVE, SOLD, EXPIRED, PENDING

Proceed with these descriptions? (yes / regenerate / skip descriptions)
```

⚠️ **STOPPING POINT** — Wait for user approval before continuing to Phase 3.

---

## Output variables

| Variable | Contents |
|----------|----------|
| `TABLE_PROFILES` | Per-table dict: column name → {data_type, nullable, distinct_count, sample_values} |
| `COLUMN_DESCRIPTIONS` | Per-column dict: table.col → {description, synonyms, sample_values} |
| `APPLY_COMMENTS` | Boolean — whether COMMENTs were written to source objects |
| `NON_STANDARD_COLUMNS` | Dict of flagged columns: `{original_name: safe_quoted_form}` — empty if all names are clean |

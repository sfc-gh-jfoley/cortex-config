---
name: sv-ddl-phase1-context
description: Context gathering for DDL-based semantic view creation — tables, business intent, and optional documentation
---

# Phase 1: Context Gathering

## Purpose
Collect everything needed before touching Snowflake: source objects, business context, and optional data dictionary.
This phase has **one mandatory stopping point** — wait for user input before proceeding to Phase 2.

---

## Step 1.1: Get semantic view target

Ask for three things in a single message:

1. **Semantic view name** — valid SQL identifier, uppercase recommended: `DEALER_360_SV`
2. **Target database + schema** — where the SV will be created: `MY_DB.PUBLIC`
3. **Snowflake connection** — which connection to use (or "default")

Store as:
- `SV_NAME`
- `SV_DB`, `SV_SCHEMA`
- `SV_CONNECTION`

---

## Step 1.2: Get source objects

Ask: "Which objects should this semantic view cover? Provide fully qualified names: `DB.SCHEMA.OBJECT_NAME`. These can be tables, views, dynamic tables, or secure views."

Accept any of:
- A list of object names (one per line or comma-separated)
- A SQL query you want modeled (extract objects from it)
- A description of the domain (e.g. "our dealer management tables in AUTOTRADER_DB.PROD")

Extract fully qualified object names. Store as `SOURCE_OBJECTS` list.

---

## Step 1.2.1: Detect object types

For each source object, determine its type:

```sql
SHOW OBJECTS LIKE '<object_name>' IN SCHEMA <db>.<schema>;
```

Classify each as one of:
- `TABLE` — standard table
- `VIEW` — standard or secure view
- `DYNAMIC TABLE` — dynamic table
- `SEMANTIC VIEW` — another semantic view (composable — **not yet supported**, warn user)

Store as `SOURCE_OBJECT_TYPES` dict: `{fqn: type}`.

**If any object is a SEMANTIC VIEW**: Warn the user:
> "Composable semantic views (referencing one SV from another) are in Private Preview and not yet generally available. This skill does not yet support SV-as-source. Consider using the underlying physical tables instead, or wait for composable SV PrPr enrollment."

**Verification**: Each object must be queryable. For TABLE/VIEW/DYNAMIC TABLE, run:
```sql
SELECT * FROM <fqn> LIMIT 1;
```

If any object is inaccessible, **stop and report** which objects failed before proceeding.

---

## Step 1.3: Get business context

Ask: "What business questions should this semantic view answer? What are the key metrics and dimensions users care about?"

Accept free-form text. This feeds directly into:
- AI_SQL_GENERATION instructions
- Description generation prompts in Phase 2
- Metric/dimension classification in Phase 3

Store as `BUSINESS_CONTEXT`.

---

## Step 1.4: Optional — source system, documentation, or lineage context

Ask: "Do you have source system, documentation, or lineage information that would help identify this data? (default: No)"

Accept any of the following — accept whatever the user provides without requiring a specific format:

- **Source system name** — e.g. `"Salesforce"`, `"HubSpot"`, `"SAP"`, `"Workday"`, `"Marketo"`, `"NetSuite"`, `"Zendesk"`, `"ServiceNow"`
  → CoCo applies known field naming conventions during description generation in Phase 2
- **File path** — `.md`, `.txt`, `.csv` (data dictionary), `.yaml`, `.pdf`
  → Read file with `cat <file_path>`; if CSV, parse for `table_name`, `column_name`, `description` columns
- **Pasted text** — ERD notes, column definitions, lineage diagram description, data catalog export
- **Nothing / No** — skip and proceed

If a file path is provided, read and store content. If CSV format, parse for: `table_name`, `column_name`, `description` columns.

If nothing provided or user says "No", set `DOC_CONTEXT = null`.

Store as `DOC_CONTEXT`.

---

## Step 1.4.5: Sample data for descriptions

Ask: "Sample source data to improve descriptions? (default: Yes)"

```
Yes → run ARRAY_AGG(DISTINCT ...) per categorical column in Phase 2
      → descriptions will include representative values from actual data
No  → descriptions generated from column names + data types only
      → faster; no data access beyond INFORMATION_SCHEMA
```

Store as `AUTO_SAMPLE = true / false` (default true).

---

## Step 1.5: MTT and PII governance intake

Ask all questions together in a single message — do not split into multiple rounds.

If the user types **`s`** (or "skip") at any point in this step, immediately set
`IS_MTT=false`, `TENANT_COLUMNS=[]`, `PII_SCAN_MODE="skip"`, `REGULATED_MODE=false`
and proceed directly to Phase 2 — skip the rest of Step 1.5.

```
(Type 's' to skip governance questions and proceed directly to Phase 2)

Three quick governance questions before we profile the source objects:

1. Multi-tenancy: Is this schema shared across multiple customers, orgs, or tenants?
   (e.g., a SaaS product where each customer's data lives in the same tables)
   → Yes / No
   If yes: which column(s) define the tenant boundary?
   (e.g., ACCOUNT_ID, ORG_ID, TENANT_ID, CLIENT_ID — one column is typical)

2. PII scanning: How thorough should PII detection be?
   A) Name patterns only  — fast; flags columns named EMAIL, SSN, PHONE, DOB, ADDRESS, etc.
   B) Name patterns + SYSTEM$CLASSIFY  — thorough; runs Snowflake's built-in classifier
      on each source object (~10-30s per object, requires APPLY DATA PRIVACY CLASSIFICATION privilege)
   C) Skip PII scanning  — I'll handle governance separately

3. Regulated environment: Is this SV for HIPAA, GDPR, PCI, or SOX compliance?
   → Yes / No  (if yes, governance warnings become hard stops rather than advisory notes)
```

Store responses as:
- `IS_MTT` — `true` / `false`
- `TENANT_COLUMNS` — list of tenant discriminator column names (empty if IS_MTT=false)
- `PII_SCAN_MODE` — `"patterns"` | `"classify"` | `"skip"`
- `REGULATED_MODE` — `true` / `false`

**If IS_MTT = true**: note that tenant columns will be forced to DIMENSION in Phase 3 and a row access policy will be recommended at the end of Phase 3.

**If PII_SCAN_MODE = "classify"**: SYSTEM$CLASSIFY will be run per table in Phase 3 Step 3.1 before any column-name pattern checks.

**If REGULATED_MODE = true**: governance notes in Phase 3 Step 3.4 become hard stopping points.

---

## ⚠️ MANDATORY STOP

Present this summary before proceeding:

```
Context collected:
  SV name:        <SV_NAME>
  Target:         <SV_DB>.<SV_SCHEMA>
  Tables:         <N> source objects — <list>
  Connection:     <SV_CONNECTION>
  Doc context:    <"source system: Salesforce" | "file: path/to/file.csv" | "pasted text (N chars)" | "none">
  Sample data:    <"yes" | "no — column names + types only">
  Multi-tenant:   <"yes — tenant col: <TENANT_COLUMNS>" | "no">
  PII scan mode:  <"name patterns" | "SYSTEM$CLASSIFY" | "skip">
  Regulated mode: <"yes (HIPAA/GDPR/PCI/SOX)" | "no">
```

Wait for user to confirm or correct before loading Phase 2.

---

## Output variables passed to next phases

| Variable | Contents |
|----------|----------|
| `SV_NAME` | Semantic view identifier |
| `SV_DB`, `SV_SCHEMA` | Target location |
| `SV_CONNECTION` | Active Snowflake connection name |
| `SOURCE_OBJECTS` | List of fully qualified source object names |
| `SOURCE_OBJECT_TYPES` | Dict mapping each FQN to its type (TABLE, VIEW, DYNAMIC TABLE) |
| `BUSINESS_CONTEXT` | Free-form business description |
| `DOC_CONTEXT` | Documentation text, source system name, or null |
| `AUTO_SAMPLE` | true/false — whether to sample source data in Phase 2 |
| `IS_MTT` | true/false — multi-tenant schema |
| `TENANT_COLUMNS` | List of tenant discriminator column names |
| `PII_SCAN_MODE` | "patterns" \| "classify" \| "skip" |
| `REGULATED_MODE` | true/false — regulated compliance environment (HIPAA/GDPR/PCI/SOX) |

---
name: sv-ddl-phase3-classify
description: Classify each column as FACT, DIMENSION, TIME_DIMENSION, METRIC, or SKIP based on data type and business context
---

# Phase 3: Column Classification

## Purpose
Decide which columns become FACTS, DIMENSIONS, METRICS, or are skipped.
This is the most important design decision — wrong classification causes bad SQL generation from Cortex Analyst.

---

## Step 3.0: Governance pre-pass (runs before heuristics)

### 3.0-A: Lock tenant columns (IS_MTT = true only)

If `IS_MTT = true`, immediately mark every column in `TENANT_COLUMNS` as **DIMENSION — LOCKED**.
These columns are never overridable to SKIP, FACT, or PRIVATE — they must be visible dimensions so
Cortex Analyst can filter by tenant. Skip them in all heuristic checks below.

```
Locked tenant dimensions: <TENANT_COLUMNS>
Reason: MTT schema — tenant boundary columns must be DIMENSION in every SV.
```

### 3.0-B: PII scan

Branch on `PII_SCAN_MODE`:

**Mode: `"patterns"` (default)**
Flag any column whose name matches:
`EMAIL`, `E_MAIL`, `SSN`, `TAX_ID`, `PHONE`, `MOBILE`, `FAX`, `DOB`, `BIRTH_DATE`, `BIRTHDAY`,
`ADDRESS`, `STREET`, `ZIPCODE`, `ZIP_CODE`, `POSTAL`, `FIRST_NAME`, `LAST_NAME`, `FULL_NAME`,
`GENDER`, `IP_ADDRESS`, `CREDIT_CARD`, `PASSPORT`, `LICENSE`, `NPI`, `MRN`, `PATIENT_ID`

Store matched columns as `PII_FLAGGED`.

**Mode: `"classify"` (SYSTEM$CLASSIFY)**
Run Snowflake's built-in classifier on each source table. Requires `APPLY DATA PRIVACY CLASSIFICATION` privilege.

```sql
-- Run per source table:
SELECT SYSTEM$CLASSIFY('<DB>.<SCHEMA>.<TABLE>', {'auto_tag': false});
```

Parse the JSON result: collect all columns where `privacy_category` is `'IDENTIFIER'` or `'QUASI_IDENTIFIER'`
or `semantic_category` is non-null. Merge with name-pattern results.
Store as `PII_FLAGGED` (deduplicated).

⚠️ If SYSTEM$CLASSIFY returns an access error, fall back to name patterns and note the fallback as a warning.

**Mode: `"skip"`**
Set `PII_FLAGGED = []`. Skip all PII checks. A governance follow-up note will appear at the end of Phase 3.

---

## Step 3.0-C: Variable resolution (if VARIABLES clause exists)

If the semantic view definition includes a top-level `VARIABLES` clause, resolve all variable references in fact/dimension/metric expressions before classifying.

**Process**:
1. Parse the `VARIABLES` block and collect all variable names
2. Scan all expressions in FACTS, DIMENSIONS, and METRICS for `$var_name` references
3. For each `$var_name` found, verify it exists in the VARIABLES block
4. If any undefined variable is found, produce an error: "Variable `$undefined_var` is referenced in expression but not defined in VARIABLES block. Add it to VARIABLES or remove the reference."
5. Store validated variables in `RESOLVED_VARIABLES` for Phase 5 reference

**Example**:
```sql
VARIABLES (
  region_filter AS VARCHAR = 'US_EAST'
)
FACTS (
  orders.revenue AS SUM(amount) WHERE region = $region_filter
)
```
When classifying, confirm `$region_filter` is defined in VARIABLES block.

**Best-practice**: Variables can only be used in WHERE filters and aggregations. Referencing variables in relationship join conditions will produce an error at CREATE time.

---

## Step 3.1: Auto-classify using heuristics

Apply these rules to every column in `TABLE_PROFILES`. Start with the heuristic classification, then refine with business context.

### Classification rules (apply in order)

| Priority | Condition | Classification |
|----------|-----------|---------------|
| 0 | Column is in `PII_FLAGGED` (from Step 3.0-B) | **⚠️ PII — flag for governance check** (default: SKIP; keep as DIMENSION only with user approval; NEVER reclassify as FACT to use PRIVATE modifier) |
| 1 | `DATE`, `TIMESTAMP`, `DATETIME`, `TIMESTAMP_NTZ`, `TIMESTAMP_LTZ` | **TIME_DIMENSION** |
| 2 | Column name ends with `_ID`, `_KEY`, `_CODE`, `_NBR`, `_NUM`, `_SK` | **DIMENSION** (even if numeric — it's an identifier, not a measure) |
| 3 | Column name starts with or contains `IS_`, `HAS_`, `FLAG` | **DIMENSION** (boolean/flag) — also tag `filter_candidate: true` |
| 4 | `BOOLEAN` type | **DIMENSION** — also tag `filter_candidate: true` |
| 5 | `VARCHAR`, `TEXT`, `CHAR` | **DIMENSION** |
| 6 | `NUMBER`, `INTEGER`, `FLOAT`, `DECIMAL` with distinct_count / total_rows > 0.5 (high cardinality ratio → likely a measure) | **FACT** |
| 7 | `NUMBER`, `INTEGER`, `FLOAT` with low cardinality (< 20 distinct values) | **DIMENSION** (categorical numeric — e.g. STATUS_CODE, RATING) |
| 8 | Column name contains `AMOUNT`, `PRICE`, `REVENUE`, `COST`, `TOTAL`, `SUM`, `COUNT`, `QTY`, `QUANTITY` | **FACT** |
| 9 | Internal/ETL columns: `_CREATED_AT`, `_UPDATED_AT`, `_ETL`, `_LOAD_`, `_BATCH_`, `_DW_` | **SKIP** (exclude from SV) |
| 10 | All other numeric columns | **FACT** (default) |

### Aggregate/computed metrics

Metrics are NOT raw columns — they are aggregate expressions you define:
- `COUNT(*)` → total row count
- `SUM(revenue_col)` → total revenue
- `AVG(price_col)` → average price
- `COUNT(DISTINCT id_col)` → unique count

Propose sensible metrics based on `BUSINESS_CONTEXT` and the available FACT columns.

---

## Step 3.1.5: Temporal Pattern Detection

Scan `TABLE_PROFILES` for temporal column patterns that enable ASOF and range joins in Phase 4.

### Range join candidates (temporal pairs)

Look for column **pairs** in the same table matching these patterns:
- `EFFECTIVE_DATE` + `EXPIRY_DATE`
- `START_DATE` + `END_DATE`
- `VALID_FROM` + `VALID_TO`
- `*_START` + `*_END` where both are `DATE` or `TIMESTAMP` type
- `BEGIN_DATE` + `END_DATE`

For each match, record in `RANGE_JOIN_CANDIDATES`:
```json
{ "table": "<TABLE>", "start_col": "<START_COL>", "end_col": "<END_COL>", "range_join_candidate": true }
```

### ASOF join candidates (single temporal columns)

In dimension/lookup tables (tables with low row counts or tables whose names suggest reference data: `*_RATES`, `*_PRICES`, `*_CONFIG`, `*_HISTORY`), detect single temporal columns:
- `EFFECTIVE_DATE`, `AS_OF_DATE`, `SNAPSHOT_DATE`, `PRICE_DATE`, `VALID_FROM`, `RATE_DATE`

For each match, record in `ASOF_CANDIDATES`:
```json
{ "table": "<TABLE>", "asof_col": "<COL>", "asof_candidate": true }
```

---

## Step 3.1.6: Window Metric Detection

Detect tables and columns that are candidates for window function metrics.

### Keyword scan

Search table COMMENTs, column COMMENTs, and `BUSINESS_CONTEXT` for these keywords:
`running total`, `cumulative`, `year over year`, `YoY`, `MoM`, `period over period`,
`moving average`, `rolling`, `rank`, `percentile`, `growth rate`, `QoQ`, `WoW`

### Candidate tagging

If any keywords match for a table, tag it as `window_metric_candidate: true` and propose specific window metrics in `WINDOW_METRIC_CANDIDATES`:

| Keyword pattern | Proposed metric template |
|----------------|------------------------|
| `running total`, `cumulative` | `running_total_<fact>` AS `SUM(<fact>) OVER (ORDER BY <time_dim>)` |
| `moving average`, `rolling` | `rolling_avg_<fact>` AS `AVG(<fact>) OVER (ORDER BY <time_dim> ROWS 6 PRECEDING)` |
| `rank`, `percentile` | `<fact>_rank` AS `RANK() OVER (PARTITION BY EXCLUDING <time_dim> ORDER BY <metric> DESC)` |
| `YoY`, `year over year`, `growth rate` | `<fact>_yoy_growth` AS `(SUM(<fact>) - LAG(SUM(<fact>)) OVER (ORDER BY <year_dim>)) / NULLIF(LAG(SUM(<fact>)) OVER (ORDER BY <year_dim>), 0)` |
| `MoM`, `QoQ`, `WoW`, `period over period` | Same pattern as YoY but with appropriate time grain |

These are suggestions only — they will be refined in Phase 5 when the actual DDL is generated.

---

## Step 3.2: Present classification table for review

Format the output as a table grouped by table name. Show auto-classification + user can override:

```
Column Classification for <TABLE_NAME>
(Edit classifications before proceeding)

Column                  | Type      | Classification    | Reason
------------------------|-----------|-------------------|--------------------------------
DEALER_ID               | VARCHAR   | DIMENSION         | ID-like name
DEALER_NAME             | VARCHAR   | DIMENSION         | text
DAYS_IN_INVENTORY       | NUMBER    | FACT              | numeric measure
LISTING_STATUS          | VARCHAR   | DIMENSION         | categorical text
LIST_PRICE              | NUMBER    | FACT              | contains PRICE
ACQUISITION_DATE        | DATE      | TIME_DIMENSION    | date type
LAST_MODIFIED_AT        | TIMESTAMP | SKIP              | ETL/audit column
LOAD_BATCH_ID           | VARCHAR   | SKIP              | ETL column pattern

Proposed METRICS (aggregate expressions):
  • total_vehicles     AS COUNT(*)                          — total vehicle count
  • avg_days_on_lot    AS AVG(DAYS_IN_INVENTORY)            — average days on lot
  • avg_list_price     AS AVG(LIST_PRICE)                   — average listing price
  • total_list_value   AS SUM(LIST_PRICE)                   — total inventory value

Override any classification? (type column name and new type, or 'ok' to proceed)
```

⚠️ **STOPPING POINT** — Wait for user to confirm or override classifications.

---

## Step 3.3: Apply user overrides

Accept overrides in any format:
- `DAYS_IN_INVENTORY → DIMENSION` (user knows it's capped at 0-365, categorical)
- `LISTING_STATUS → SKIP` (not relevant for this SV)
- Add a new metric: `active_count AS COUNT_IF(LISTING_STATUS = 'ACTIVE')`

Store the final classification as `COLUMN_CLASSES`:
```json
{
  "VEHICLES_TABLE": {
    "DEALER_ID":          { "class": "DIMENSION", "description": "...", "synonyms": [...] },
    "DAYS_IN_INVENTORY":  { "class": "FACT",      "description": "...", "synonyms": [...] },
    "ACQUISITION_DATE":   { "class": "TIME_DIMENSION", ... },
    "LAST_MODIFIED_AT":   { "class": "SKIP" }
  },
  "metrics": [
    { "table": "VEHICLES_TABLE", "name": "total_vehicles",  "expr": "COUNT(*)" },
    { "table": "VEHICLES_TABLE", "name": "avg_days_on_lot", "expr": "AVG(DAYS_IN_INVENTORY)" }
  ]
}
```

---

## Step 3.4: Governance notes (non-blocking)

Run this step **after** user overrides are accepted (Step 3.3 complete).

**Regulated mode override**: If `REGULATED_MODE = true`, treat every advisory note below as a hard
⚠️ **STOPPING POINT** — require explicit user confirmation before proceeding to Phase 4. This
restores the original blocking behavior for HIPAA/GDPR/PCI/SOX environments.

**Short-circuit conditions** (vary by case):

- `PII_SCAN_MODE = "skip"` → show only the ℹ️ skip note at the bottom of this section, then continue
- `PII_FLAGGED` is empty AND `IS_MTT = false` → continue silently (no panel)
- `PII_FLAGGED` non-empty but `PII_KEPT_AS_DIMENSION` is empty AND `IS_MTT = false`:
  → show the **PII auto-SKIP notice** below (not the full panel), then continue

**Full panel** — present when `PII_KEPT_AS_DIMENSION` is non-empty OR `IS_MTT = true`.
Continue automatically unless the user types "mask", "rap", or "stop":

```
─── Governance Notes ───────────────────────────────────────────
PII columns kept as DIMENSION: <table.column list, or "none">
  → Masking policies recommended (type "mask" to set up now)

MTT: <TENANT_COLUMNS> locked as DIMENSION ✓   [only if IS_MTT=true]
  → Row access policy recommended (type "rap" to set up now)
────────────────────────────────────────────────────────────────
Type "mask", "rap", or press Enter / "ok" to continue to Phase 4.
```

Only render the MTT line if `IS_MTT = true`.
Only render the PII line if `PII_KEPT_AS_DIMENSION` is non-empty.

**PII auto-SKIP notice** — show when `PII_FLAGGED` non-empty but none kept as DIMENSION:

```
ℹ️  <N> PII column(s) detected and auto-classified as SKIP: <column list>.
    They will not appear in the semantic view.
    Type "mask" to include them with a masking policy, or press Enter to continue.
```

Wait for user input here (default: continue on Enter/"ok").

**If user types "mask"**: note "load data-governance skill → data-policy workflow" and pause.
Resume semantic-view-ddl from Phase 4 when masking setup is complete.

**If user types "rap"**: Present the RAP pattern decision tree below (informational), then
hand off to `data-governance` skill for actual DDL generation.

#### RAP Pattern Summary (informational — data-governance skill generates the DDL)

Help the user pick the right pattern before handing off:

```
Which tenant isolation pattern fits your architecture?

  Pattern A — User-per-tenant (simplest)
    Each tenant maps to a distinct Snowflake user.
    RAP filters on: CURRENT_USER()
    Best for: internal teams, named service accounts per tenant.
    Example predicate: tenant_id = CURRENT_USER()

  Pattern B — Role-per-tenant
    Each tenant maps to a Snowflake role; users are granted one role.
    RAP filters on: CURRENT_ROLE() or IS_ROLE_IN_SESSION()
    Best for: RBAC-heavy orgs, role hierarchy mirrors tenant tree.
    API note: Pass X-Snowflake-Role header in DATA_AGENT_RUN to select role.
    Example predicate: tenant_id = CURRENT_ROLE()

  Pattern C — Session attribute (most flexible, requires trusted middleware)
    Tenant identity is injected via session variable at connection time.
    RAP filters on: SYS_CONTEXT('SNOWFLAKE$SESSION_ATTRIBUTES', 'tenant_id')
    Best for: connection-pooled apps, API gateways, multi-tenant SaaS.
    ⚠️  SECURITY: Pattern C is ONLY secure when the session attribute is set by
        trusted middleware (Snowflake's auth flow, a controlled API gateway).
        If arbitrary SQL callers can SET the variable, tenant isolation is broken.
    Example predicate: tenant_id = SYS_CONTEXT('SNOWFLAKE$SESSION_ATTRIBUTES', 'tenant_id')
```

After the user selects a pattern, note "load data-governance skill → data-policy workflow (row
access policy track, pattern [A/B/C])" and pause. Resume from Phase 4 when done.

**Any other input (Enter, "ok", "continue")**: proceed immediately to Phase 4.

### PII scan was skipped (PII_SCAN_MODE = "skip")

Append a single informational note and continue without waiting:

```
ℹ️  PII scanning was skipped. If these tables contain personal data, consider
    running SYSTEM$CLASSIFY or reviewing string columns manually before deploying
    this SV to production.
```

---

## Output variables

| Variable | Contents |
|----------|----------|
| `COLUMN_CLASSES` | Per-table, per-column classification dict (includes `filter_candidate` tags) |
| `PROPOSED_METRICS` | List of {table, name, expr, description} |
| `PII_FLAGGED` | Columns identified as PII (any scan mode) |
| `PII_KEPT_AS_DIMENSION` | Subset of PII_FLAGGED with final class = DIMENSION |
| `FILTER_CANDIDATES` | List of boolean columns tagged `filter_candidate: true` (Priority 3 and 4 matches) |
| `RANGE_JOIN_CANDIDATES` | List of {table, start_col, end_col} temporal pairs for range joins |
| `ASOF_CANDIDATES` | List of {table, asof_col} single temporal columns for ASOF joins |
| `WINDOW_METRIC_CANDIDATES` | List of {table, metric_name, expr, description} proposed window metrics |

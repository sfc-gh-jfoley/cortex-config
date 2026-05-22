# Customer Guide: Semantic View DDL

This guide walks you through building and maintaining Snowflake Semantic Views using the `semantic-view-ddl` skill. Whether you're creating a new semantic view from scratch or improving an existing one, this document covers the full workflow.

---

## Where to Start

| Your situation | Start at |
|---|---|
| Building a new semantic view from tables | [Phase 1: Context Gathering](#phase-1-context-gathering) |
| Have an SV, want to add verified queries | [Phase 7: Iterate & Enrich](#phase-7-iterate--enrich) |
| Have an SV, want to check for drift/issues | [Phase 8: Drift Monitor](#phase-8-drift-monitor) |
| Have an SV, want to audit quality | [Phase 5: Generate DDL](#phase-5-generate-ddl) (self-check mode) |
| Have an SV, want to re-classify columns | [Phase 3: Classify Columns](#phase-3-classify-columns) |

---

## Trigger Phrases

Type any of these in Cortex Code to invoke this skill:

| What you want | What to type |
|---|---|
| Build a new semantic view | `Create a semantic view for MY_DB.PUBLIC.ORDERS and MY_DB.PUBLIC.CUSTOMERS` |
| Add verified queries to existing SV | `Add verified queries to MY_DB.PUBLIC.ORDERS_SV` |
| Check for schema drift | `Check drift on MY_DB.PUBLIC.ORDERS_SV` |
| Run a quality audit | `Audit my semantic view MY_DB.PUBLIC.ORDERS_SV` |
| Generate descriptions for columns | `Describe columns in MY_DB.PUBLIC.ORDERS_SV` |
| Full health check | `Semantic view health check on MY_DB.PUBLIC.ORDERS_SV` |

---

## Phase 1: Context Gathering

**Purpose:** Identify the tables to model, the business domain, and where the semantic view will live.

**What you'll need:**
- Fully qualified table names (e.g., `MY_DB.PUBLIC.ORDERS`)
- Target database and schema for the semantic view
- (Optional) A data dictionary, documentation file, or description of the business domain

**What happens:**

1. The skill asks for:
   - Semantic view name (e.g., `ORDERS_SV`)
   - Target database and schema (e.g., `MY_DB.PUBLIC`)
   - Source tables (e.g., `MY_DB.PUBLIC.ORDERS, MY_DB.PUBLIC.CUSTOMERS, MY_DB.PUBLIC.PRODUCTS`)

2. For each table, it verifies access:
   ```sql
   SELECT * FROM MY_DB.PUBLIC.ORDERS LIMIT 1;
   ```

3. (Optional) If you provide documentation context (e.g., "this data comes from Salesforce"), the skill uses that context to generate better descriptions in Phase 2.

**Expected output:**
```
Context confirmed:
  SV Name: ORDERS_SV
  Target: MY_DB.PUBLIC
  Tables: ORDERS, CUSTOMERS, PRODUCTS (3 tables, all accessible)
  Domain: Retail order management

Proceed to Phase 2? (approve / modify)
```

**Approval gate:** You must confirm before the skill proceeds.

---

## Phase 2: Profile & Describe

**Purpose:** Profile each table's data and use AI to generate human-readable column descriptions, synonyms, and sample values.

**What you'll need:**
- Approved context from Phase 1
- No additional input — this phase runs automatically

**What happens:**

1. For each table, the skill runs `DESCRIBE TABLE` and samples data:
   ```sql
   DESCRIBE TABLE MY_DB.PUBLIC.ORDERS;
   SELECT * FROM MY_DB.PUBLIC.ORDERS LIMIT 100;
   ```

2. It uses `SNOWFLAKE.CORTEX.COMPLETE` to generate for each column:
   - **Description** (1-2 sentences): "The total dollar amount of the order after discounts and tax"
   - **Synonyms** (2-3 aliases): "order total", "sale amount", "order value"
   - **Sample values** (for categorical columns): "SHIPPED, PENDING, CANCELLED, RETURNED"

3. If you specified a source system (e.g., "Salesforce"), the skill applies domain-specific naming conventions when generating descriptions.

**Expected output:**
```
Column descriptions generated for 3 tables (47 columns total):

ORDERS table (12 columns):
  ORDER_ID        — Unique identifier for each customer order
  ORDER_DATE      — Date the order was placed (synonyms: purchase date, transaction date)
  TOTAL_AMOUNT    — Total dollar amount after discounts and tax (synonyms: order total, sale amount)
  STATUS          — Current order status (values: SHIPPED, PENDING, CANCELLED, RETURNED)
  ...

Review descriptions and approve? (approve / edit specific columns / regenerate)
```

**Approval gate:** You review the generated descriptions. You can edit individual columns or regenerate specific ones before proceeding.

---

## Phase 3: Classify Columns

**Purpose:** Decide which columns become FACTS, DIMENSIONS, METRICS, or are skipped. This is the most impactful design decision — wrong classification causes Cortex Analyst to generate incorrect SQL.

**What you'll need:**
- Approved descriptions from Phase 2

**What happens:**

1. The skill applies heuristic rules to classify each column:

   | Classification | Meaning | Examples |
   |---|---|---|
   | **FACT** | Measurable numeric values that can be aggregated | `TOTAL_AMOUNT`, `QUANTITY`, `DISCOUNT` |
   | **DIMENSION** | Categorical attributes for grouping/filtering | `STATUS`, `REGION`, `PRODUCT_CATEGORY` |
   | **TIME_DIMENSION** | Date/timestamp columns for time-based analysis | `ORDER_DATE`, `SHIP_DATE` |
   | **METRIC** | Pre-defined calculations (aggregations of facts) | `AVG(TOTAL_AMOUNT)`, `COUNT(DISTINCT CUSTOMER_ID)` |
   | **SKIP** | Internal IDs, audit columns, or irrelevant data | `ETL_LOAD_DATE`, `_METADATA_ROW_ID` |

2. A PII scan flags potentially sensitive columns (email, phone, SSN patterns) and marks them for review.

3. For multi-tenant tables, tenant boundary columns are locked as DIMENSIONS (they must always be filterable).

**Expected output:**
```
Column classifications:

ORDERS:
  FACT:           TOTAL_AMOUNT, QUANTITY, DISCOUNT_AMOUNT
  DIMENSION:      STATUS, CHANNEL, PRIORITY
  TIME_DIMENSION: ORDER_DATE, SHIP_DATE
  SKIP:           ETL_BATCH_ID, MODIFIED_TS

CUSTOMERS:
  DIMENSION:      CUSTOMER_NAME, REGION, SEGMENT
  TIME_DIMENSION: SIGNUP_DATE
  SKIP:           INTERNAL_ID

  ⚠️ PII flagged: EMAIL, PHONE — recommend SKIP or masking policy

Review classifications? (approve / reclassify specific columns)
```

**Approval gate:** You confirm or adjust classifications before proceeding.

---

## Phase 4: Relationship Detection

**Purpose:** Identify how tables join to each other. Missing or incorrect relationships are the #1 cause of bad SQL generation from Cortex Analyst.

**What you'll need:**
- Classified columns from Phase 3

**What happens:**

1. The skill scans for foreign key patterns across table pairs:
   - Exact column name matches (e.g., `CUSTOMER_ID` in both ORDERS and CUSTOMERS)
   - Table-prefixed FKs (e.g., ORDERS has `PRODUCT_ID`, PRODUCTS has `PRODUCT_ID` as PK)
   - Suffix patterns (`_KEY`, `_CODE`, `_SK`)

2. It checks for existing FK constraints in Snowflake metadata.

3. For each candidate relationship, it validates cardinality:
   ```sql
   -- Check that the FK actually references valid PK values
   SELECT COUNT(*) FROM ORDERS o
   LEFT JOIN CUSTOMERS c ON o.CUSTOMER_ID = c.CUSTOMER_ID
   WHERE c.CUSTOMER_ID IS NULL;
   ```

4. Special relationship types are detected:
   - **ASOF joins** — point-in-time lookups (e.g., "get the exchange rate valid on the order date")
   - **Range joins** — between start/end date columns (e.g., "effective date ranges")

**Expected output:**
```
Detected relationships:

  orders_to_customers: ORDERS(CUSTOMER_ID) → CUSTOMERS(CUSTOMER_ID)
    Cardinality: many-to-one ✓  |  Orphan rows: 0 ✓

  orders_to_products: ORDERS(PRODUCT_ID) → PRODUCTS(PRODUCT_ID)
    Cardinality: many-to-one ✓  |  Orphan rows: 12 (0.01%) ⚠️

Confirm relationships? (approve / add / remove)
```

**Approval gate:** You confirm the relationship set before DDL generation.

---

## Phase 5: Generate DDL

**Purpose:** Build the complete `CREATE OR REPLACE SEMANTIC VIEW` statement and validate it with 23 self-checks before showing it to you.

**What you'll need:**
- Confirmed relationships from Phase 4

**What happens:**

1. The skill assembles the DDL following mandatory clause order:
   ```sql
   CREATE OR REPLACE SEMANTIC VIEW MY_DB.PUBLIC.ORDERS_SV
     TABLES (...)
     RELATIONSHIPS (...)
     FACTS (...)
     DIMENSIONS (...)
     METRICS (...)
     COMMENT = '...'
   ```

2. **23 self-checks** run against the generated DDL:

   **Syntax checks (9):**
   - Clause order is correct (TABLES → RELATIONSHIPS → FACTS → DIMENSIONS → METRICS)
   - Column aliases match physical column names exactly
   - No duplicate column names across tables
   - PRIMARY KEY or UNIQUE defined for all relationship right-hand tables
   - Valid data types for each section
   - DISTINCT RANGE columns are same type and same table
   - No reserved words used as aliases
   - COMMENT and AI_SQL_GENERATION properly quoted
   - Relationship names follow naming convention

   **Semantic checks (9):**
   - Every table has at least one FACT or DIMENSION
   - No orphaned tables (every table participates in a relationship or has facts/dims)
   - Metrics reference valid fact columns
   - USING clause present when ambiguous relationship paths exist
   - Descriptions are non-empty for all columns
   - Synonyms don't duplicate the column name
   - Sample values match the column's data type
   - Time dimensions have date/timestamp types
   - Filter candidates have reasonable cardinality

3. Any failures are auto-fixed. Warnings are presented for your review.

**Expected output:**
```
Self-check results: 16/18 PASS, 2 WARN, 0 FAIL

  ⚠️ WARN: PRODUCTS table has no metrics defined (consider adding COUNT or SUM)
  ⚠️ WARN: DISCOUNT_AMOUNT has no synonyms

Generated DDL (47 lines):

  CREATE OR REPLACE SEMANTIC VIEW MY_DB.PUBLIC.ORDERS_SV
    TABLES (
      orders AS MY_DB.PUBLIC.ORDERS
        PRIMARY KEY (ORDER_ID)
        ...
    )
    ...

Approve DDL for execution? (approve / fix warnings / edit)
```

**Approval gate:** You must approve the DDL before it's executed.

### Using Phase 5 to Audit an Existing SV

You can run the 23 self-checks against an existing semantic view:

```
Audit my semantic view MY_DB.PUBLIC.ORDERS_SV
```

The skill will DESCRIBE the existing SV, reconstruct its DDL, and run the self-check suite to find quality issues.

---

## Phase 6: Execute & Validate

**Purpose:** Deploy the semantic view and verify it works by running test questions through Cortex Analyst.

**What you'll need:**
- Approved DDL from Phase 5

**What happens:**

1. The DDL is executed:
   ```sql
   CREATE OR REPLACE SEMANTIC VIEW MY_DB.PUBLIC.ORDERS_SV ...
   ```

2. Deployment is confirmed:
   ```sql
   DESCRIBE SEMANTIC VIEW MY_DB.PUBLIC.ORDERS_SV;
   ```

3. The skill runs 3-5 test questions through Cortex Analyst to verify the SV works:
   ```
   Test question: "What was total revenue last month?"
   Generated SQL: SELECT SUM(TOTAL_AMOUNT) FROM ORDERS WHERE ORDER_DATE >= DATEADD('month', -1, CURRENT_DATE())
   Result: ✓ Valid SQL, returns data
   ```

4. If any test question fails (bad SQL, no results, wrong joins), the skill identifies the root cause and loops back to Phase 5 with a specific fix.

**Common errors and their fixes:**

| Error | Root cause | Auto-fix |
|---|---|---|
| `No queryable expression` | No FACTS or DIMENSIONS defined | Add missing FACTS clause |
| `invalid identifier 'X'` | Alias doesn't match physical column name | Correct the AS clause |
| `Duplicate identifier 'X'` | Column defined in multiple tables | Keep in one table only |
| `Ambiguous relationship` | Two paths, no USING clause | Add USING to affected metrics |

**Expected output:**
```
Semantic view deployed successfully ✓

Test results:
  1. "Total revenue last month" — ✓ correct SQL, returns $2.4M
  2. "Orders by region" — ✓ correct SQL, returns 5 regions
  3. "Top customers by spend" — ✓ correct SQL, returns ranked list
  4. "Average order value by product category" — ✓ correct SQL, returns 8 categories
  5. "Month-over-month growth" — ⚠️ SQL runs but uses wrong date column (MODIFIED_TS instead of ORDER_DATE)

4/5 passed. Fix needed: add AI_SQL_GENERATION hint for time-based queries.

Proceed to Phase 7 to add verified queries and fix the date issue? (yes / re-run Phase 5)
```

---

## Phase 7: Iterate & Enrich

**Purpose:** Polish the semantic view after initial validation — add verified queries, tune descriptions, and export for version control.

> **This is the primary entry point for improving existing semantic views.**

**What you'll need:**
- A deployed semantic view (from Phase 6, or one you already have)

**What to type:**
```
Add verified queries to MY_DB.PUBLIC.ORDERS_SV
```

**What happens:**

### 7.1 Add AI_VERIFIED_QUERIES

Verified queries are curated question→SQL pairs embedded in the semantic view. They serve two purposes:
- **Improve accuracy** — Cortex Analyst uses them as examples when generating SQL for similar questions
- **Onboarding** — They appear as starter questions in Snowflake Intelligence

The skill helps you build verified queries:

```
Suggested verified queries based on your semantic view structure:

1. "What is total revenue this month?"
   → SELECT SUM(TOTAL_AMOUNT) FROM ORDERS WHERE ORDER_DATE >= DATE_TRUNC('month', CURRENT_DATE())

2. "How many orders are in each status?"
   → SELECT STATUS, COUNT(*) FROM ORDERS GROUP BY STATUS

3. "Who are our top 10 customers by lifetime spend?"
   → SELECT c.CUSTOMER_NAME, SUM(o.TOTAL_AMOUNT) as total_spend
     FROM ORDERS o JOIN CUSTOMERS c ON o.CUSTOMER_ID = c.CUSTOMER_ID
     GROUP BY c.CUSTOMER_NAME ORDER BY total_spend DESC LIMIT 10

Add these verified queries? (approve all / select specific / add custom)
```

Since `ALTER SEMANTIC VIEW ... SET AI_VERIFIED_QUERIES` is not supported, the skill rebuilds with `CREATE OR REPLACE`, appending the verified queries as the final clause.

### 7.2 Tune Descriptions and Synonyms

If Phase 6 revealed that Cortex Analyst picked wrong columns (e.g., used `MODIFIED_TS` instead of `ORDER_DATE` for time queries), the fix is usually better descriptions:

```
Before: ORDER_DATE — "Date field for orders"
After:  ORDER_DATE — "The date the order was placed by the customer. Use this column for all time-based revenue and order analysis (not MODIFIED_TS, which tracks internal ETL updates)."
```

### 7.3 Add AI_SQL_GENERATION Hints

For complex domains, you can add natural-language hints that guide SQL generation:

```sql
AI_SQL_GENERATION 'When asked about revenue trends over time, always use ORDER_DATE (not MODIFIED_TS). When asked about customer lifetime value, join ORDERS to CUSTOMERS on CUSTOMER_ID and aggregate TOTAL_AMOUNT.'
```

### 7.4 Export Final DDL

The skill can export the complete DDL for version control or HOL scripts:

```
Export the final DDL for MY_DB.PUBLIC.ORDERS_SV
```

**Expected output:** The full `CREATE OR REPLACE SEMANTIC VIEW` statement including all verified queries, descriptions, and hints — ready to paste into a Git repo or workshop script.

---

## Phase 8: Drift Monitor

**Purpose:** Detect when your semantic view has fallen out of sync with actual usage patterns or schema changes. Runs as a one-time check or on a recurring schedule.

> **This phase works standalone** — you don't need to have gone through Phases 1-7.

**What you'll need:**
- A deployed semantic view

**What to type:**
```
Check drift on MY_DB.PUBLIC.ORDERS_SV
```

**What happens:**

1. **Schema drift detection** — Compares the SV definition against current table schemas:
   - New columns added to source tables that aren't in the SV
   - Columns dropped from source tables that are still referenced
   - Data type changes
   - New tables in the schema that relate to existing SV tables

2. **Query pattern analysis** — Examines `ACCOUNT_USAGE.QUERY_HISTORY` to find:
   - Questions users ask that the SV can't answer (missing dimensions/facts)
   - Columns that are never used (candidates for removal)
   - Common filter patterns that should be dimensions

3. **Enrichment gaps** — Checks for:
   - Columns with no description
   - Columns with no synonyms
   - Tables with no verified queries
   - Metrics that could be pre-defined but aren't

4. **Drift score** — Summarizes findings as a prioritized list:
   ```
   Drift Report for MY_DB.PUBLIC.ORDERS_SV:

   🔴 HIGH: 3 new columns in ORDERS table not in SV (PROMO_CODE, GIFT_WRAP, EXPRESS_SHIP)
   🟡 MEDIUM: 5 columns have no description
   🟡 MEDIUM: Users frequently filter by CHANNEL but it's not a dimension
   🟢 LOW: 2 columns in SV are never queried (consider removal)

   Remediation DDL available. Apply fixes? (yes / review each / skip)
   ```

5. **Remediation** — For each finding, the skill generates specific DDL fixes and offers to apply them.

### Scheduled Monitoring

You can set up recurring drift checks:

```
Schedule a weekly drift check on MY_DB.PUBLIC.ORDERS_SV
```

The skill creates a recurring reminder that runs the drift analysis and alerts you to issues.

---

## Improving an Existing Semantic View: Summary

If you already have a semantic view and want to make it better, here are the most common workflows:

| Goal | What to type | Phase used |
|---|---|---|
| Add starter questions for users | `Add verified queries to MY_DB.PUBLIC.ORDERS_SV` | Phase 7 |
| Fix bad SQL generation | `Improve descriptions in MY_DB.PUBLIC.ORDERS_SV` | Phase 7 |
| Add missing columns or tables | `Check drift on MY_DB.PUBLIC.ORDERS_SV` | Phase 8 |
| Full quality audit | `Audit my semantic view MY_DB.PUBLIC.ORDERS_SV` | Phase 5 (self-check mode) |
| Re-classify columns | `Re-classify columns in MY_DB.PUBLIC.ORDERS_SV` | Phase 3-5 |
| Add time-based hints | `Add SQL generation hints to MY_DB.PUBLIC.ORDERS_SV` | Phase 7 |

---

## When to Use This vs. the Bundled `semantic-view` Skill

Cortex Code ships with a bundled `semantic-view` skill. Here's how they differ:

| Capability | This plugin (`semantic-view-ddl`) | Bundled `semantic-view` skill |
|---|---|---|
| Creation path | Pure SQL DDL (`CREATE SEMANTIC VIEW`) | YAML or FastGen |
| AI-generated descriptions | Yes (Phase 2) | Limited |
| Self-check validation | 23 checks before execution | Basic validation |
| Iterative fix loop | Yes (Phases 5-6 loop until passing) | Manual retry |
| Drift monitoring | Yes (Phase 8) | No |
| Tableau/Power BI import | No | Yes (.twb/.pbix) |
| VQR suggestions from query history | No (manual in Phase 7) | Yes (automated) |
| HOL/workshop friendly | Yes (all SQL, no filesystem) | Requires YAML files |

**Rule of thumb:**
- Use **this plugin** when you want full control, self-checking, or are building from scratch with undocumented tables
- Use the **bundled skill** when you have a Tableau workbook to import or want automated VQR suggestions from existing query history

---

## Example: End-to-End New Semantic View

Here's what a full session looks like:

```
You: Create a semantic view for RETAIL_DB.PUBLIC.ORDERS, RETAIL_DB.PUBLIC.CUSTOMERS, RETAIL_DB.PUBLIC.PRODUCTS

CoCo: [Phase 1] I'll create ORDERS_SV in RETAIL_DB.PUBLIC. Verified access to all 3 tables. Proceed?

You: Yes

CoCo: [Phase 2] Generated descriptions for 34 columns across 3 tables. [shows table]
      Review and approve?

You: Approve

CoCo: [Phase 3] Classified columns: 8 facts, 14 dimensions, 4 time dimensions, 3 metrics, 5 skipped.
      ⚠️ PII flagged: CUSTOMER_EMAIL. Recommend SKIP.
      Approve?

You: Approve, and yes skip the email

CoCo: [Phase 4] Detected 2 relationships:
      - orders_to_customers: ORDERS(CUSTOMER_ID) → CUSTOMERS
      - orders_to_products: ORDERS(PRODUCT_ID) → PRODUCTS
      Both validated. Approve?

You: Approve

CoCo: [Phase 5] Generated DDL (52 lines). Self-check: 18/18 PASS.
      [shows DDL]
      Execute?

You: Yes

CoCo: [Phase 6] Deployed ✓. Test results: 5/5 questions passed.
      Proceed to add verified queries?

You: Yes, add 5 good starter questions

CoCo: [Phase 7] Added 5 verified queries. Semantic view is ready.
      Final DDL exported for version control.
```

Total time: ~10 minutes of interactive work.

---

## Troubleshooting

| Problem | Likely cause | Fix |
|---|---|---|
| "No queryable expression" error | No FACTS defined for any table | Ensure at least one numeric column is classified as FACT |
| Cortex Analyst generates wrong joins | Missing or incorrect relationship | Re-run Phase 4 or manually add the relationship |
| Cortex Analyst picks wrong column | Descriptions are too vague | Phase 7: improve descriptions with explicit boundary language |
| Verified queries don't appear in Snowflake Intelligence | VQRs must be added via CREATE OR REPLACE | Re-run Phase 7 (ALTER SET is not supported for VQRs) |
| Phase 2 generates poor descriptions | Not enough sample data or vague column names | Provide a data dictionary as DOC_CONTEXT in Phase 1 |
| Self-check fails repeatedly | Complex schema with many relationships | Simplify: start with fewer tables, add more incrementally |

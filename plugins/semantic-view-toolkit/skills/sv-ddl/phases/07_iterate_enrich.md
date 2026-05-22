---
name: sv-ddl-phase7-iterate-enrich
description: Add AI_VERIFIED_QUERIES, iterate on description quality, and export final DDL for HOLs or version control
---

# Phase 7: Iterate & Enrich

## Purpose
Polish the semantic view after initial validation:
1. Add `AI_VERIFIED_QUERIES` (curated Q&A pairs for Cortex Analyst)
2. Improve descriptions based on what failed in Phase 6
3. Export the final DDL for HOL setup scripts or version control

This phase repeats as many times as needed.

---

## Step 7.1: Generate AI_VERIFIED_QUERIES

`AI_VERIFIED_QUERIES` embeds curated question→SQL pairs directly in the semantic view DDL.
These are displayed as starter questions in Snowflake Intelligence and improve Cortex Analyst's accuracy.

Ask user: "Do you want to add verified queries (example questions and their SQL)? These become the onboarding questions shown in Snowflake Intelligence."

### Add via CREATE OR REPLACE (primary path)

`ALTER SEMANTIC VIEW ... SET AI_VERIFIED_QUERIES` is **not supported** — it returns a syntax error ("unexpected SET"). The only working path is to rebuild with `CREATE OR REPLACE`, using the DDL from Phase 5 as the base, with `AI_VERIFIED_QUERIES` appended as the final clause:

```sql
CREATE OR REPLACE SEMANTIC VIEW <SV_DB>.<SV_SCHEMA>.<SV_NAME>
  TABLES ( ... )
  RELATIONSHIPS ( ... )
  FACTS ( ... )
  DIMENSIONS ( ... )
  METRICS ( ... )
  COMMENT = '...'
  AI_SQL_GENERATION '...'
  AI_VERIFIED_QUERIES (
    q1 AS (
      QUESTION 'What is total order revenue this month?'
      ONBOARDING_QUESTION TRUE
      SQL 'SELECT DATE_TRUNC(''month'', O_ORDERDATE) AS order_month,
                  SUM(O_TOTALPRICE) AS total_revenue
           FROM orders
           GROUP BY 1
           ORDER BY 1 DESC
           LIMIT 1'
    ),
    q2 AS (
      QUESTION 'How many orders are currently pending?'
      ONBOARDING_QUESTION TRUE
      SQL 'SELECT COUNT(*) AS pending_order_count
           FROM orders
           WHERE O_ORDERSTATUS = ''P'''
    ),
    q3 AS (
      QUESTION 'Show average order value by customer market segment'
      SQL 'SELECT C_MKTSEGMENT, AVG(O_TOTALPRICE) AS avg_order_value
           FROM orders
           JOIN customers ON orders.O_CUSTKEY = customers.C_CUSTKEY
           GROUP BY C_MKTSEGMENT
           ORDER BY avg_order_value DESC'
    )
  );
```

> ⚠️ Single quotes inside SQL strings must be escaped as `''` (two single quotes).  
> Use the passing questions from Phase 6 as the foundation — do not invent SQL that hasn't been tested.

---

## Step 7.2: Improve descriptions for failed questions

For each question that failed or warned in Phase 6, improve the relevant column descriptions:

### Option A: Patch individual column descriptions

```sql
-- Improve a dimension description to help Cortex Analyst understand it
ALTER SEMANTIC VIEW <SV_DB>.<SV_SCHEMA>.<SV_NAME>
  ALTER DIMENSION <table_alias>.<dim_name>
  SET COMMENT = '<improved description with explicit values and usage guidance>';
```

### Option B: Rebuild with CREATE OR REPLACE

For multi-column fixes, it's cleaner to `CREATE OR REPLACE` the entire SV with updated COMMENT clauses.
Use the DDL generated in Phase 5 as the base — edit the specific COMMENT strings and re-execute.

After any description change:
1. Re-run the failing questions from Phase 6 Step 6.4
2. If they now pass → PASS ✓
3. If still failing → investigate further or note for `AI_SQL_GENERATION` instruction

---

## Step 7.3: Refine AI_SQL_GENERATION instructions

Based on patterns observed in Phase 6, extend the `AI_SQL_GENERATION` block:

Common additions:
- Default filter clauses: `Always filter LISTING_STATUS = 'ACTIVE' unless the user asks for all statuses`
- Preferred join paths: `When joining vehicles to dealers, use the dealer_to_vehicles relationship`
- Date handling: `Use DATE_TRUNC('month', ACQUISITION_DATE) for monthly grouping`
- Aggregation preferences: `Use COUNT(DISTINCT DEALER_ID) for unique dealer counts, not COUNT(*)`

Update via:
```sql
ALTER SEMANTIC VIEW <SV_DB>.<SV_SCHEMA>.<SV_NAME>
  SET AI_SQL_GENERATION = '<updated instructions>';
```

---

## Step 7.4: Cortex Search Service Linking (optional)

Link text dimensions to existing Cortex Search Services (CSS) for fuzzy/semantic matching in Cortex Analyst queries.

**Discovery:**
```sql
SHOW CORTEX SEARCH SERVICES IN SCHEMA <SV_DB>.<SV_SCHEMA>;
```

For each CSS found, check if any text DIMENSION in the semantic view maps to the CSS's source column. If a match exists, suggest adding `WITH CORTEX SEARCH SERVICE` to the dimension:

```sql
<table_alias>.<dim_name> AS <col>
  WITH CORTEX SEARCH SERVICE <db>.<schema>.<css_name> [ USING <source_col> ]
  COMMENT = '<description>'
```

**Benefit:** Enables fuzzy/semantic matching — e.g., user types "smartphones" and Cortex Analyst matches "Mobile Phone" in the data. Without CSS linking, only exact string matching is available for text dimensions.

**Rules:**
- Only suggest CSS linking for text/VARCHAR dimensions — numeric or date dimensions don't benefit
- The CSS must already exist and be active — do not suggest creating one in this phase
- `USING <source_col>` is only needed if the CSS source column name differs from the dimension's physical column
- Present each CSS linking suggestion as optional — user can accept or skip

Update via `ALTER SEMANTIC VIEW` or include in `CREATE OR REPLACE`:
```sql
ALTER SEMANTIC VIEW <SV_DB>.<SV_SCHEMA>.<SV_NAME>
  ALTER DIMENSION <table_alias>.<dim_name>
  SET CORTEX SEARCH SERVICE = <db>.<schema>.<css_name>;
```

---

## Step 7.5: Governance Tags (optional)

Suggest `WITH TAG` annotations for governance metadata. All TAG suggestions are optional — present them and let the user decide which to apply.

### PII Tags

If `PII_FLAGGED` columns exist (from Phase 3 classification), suggest tagging dimensions containing PII:

```sql
-- On dimensions containing PII:
<table_alias>.<dim_name> AS <col>
  WITH TAG ( 'pii_sensitivity' = 'high' )
  COMMENT = '<description>'
```

### Compliance Tags

If `REGULATED_MODE = true` (from BUSINESS_CONTEXT), suggest tagging the semantic view itself:

```sql
-- On the semantic view:
CREATE OR REPLACE SEMANTIC VIEW <SV_DB>.<SV_SCHEMA>.<SV_NAME>
  ...
  WITH TAG ( 'compliance_scope' = '<HIPAA|GDPR|PCI|SOX>', 'data_classification' = 'confidential' )
```

### Multi-Tenant Tags

If `IS_MTT = true` (multi-tenant table detected), suggest tagging tenant boundary columns:

```sql
-- On tenant-identifying dimensions:
<table_alias>.<tenant_dim> AS <col>
  WITH TAG ( 'tenant_boundary' = 'true' )
  COMMENT = '<description>'
```

**Rules:**
- Tags integrate with Snowflake's native tag system — they are queryable via `TAG_REFERENCES` and compatible with tag-based masking policies
- Do not invent tag categories beyond what the business context supports
- If no PII, compliance, or MTT signals exist, skip this step entirely
- Tags can be applied via `ALTER SEMANTIC VIEW ... SET TAG` or included in `CREATE OR REPLACE`

---

## Step 7.6: Export final DDL

Generate the complete final DDL with all enrichments for:
- HOL setup scripts (`hol_setup.sql`)
- Version control
- Sharing with colleagues

```sql
-- Complete final DDL:
CREATE OR REPLACE SEMANTIC VIEW <SV_DB>.<SV_SCHEMA>.<SV_NAME>
  TABLES ( ... )
  RELATIONSHIPS ( ... )
  FACTS ( ... )
  DIMENSIONS ( ... )
  METRICS ( ... )
  COMMENT = '...'
  AI_SQL_GENERATION '...'
  AI_VERIFIED_QUERIES ( ... );
```

Present this as a complete, self-contained SQL block the user can paste into any worksheet or setup script.

---

## Step 7.7: Final summary

```
✅ Semantic View Complete

  <SV_DB>.<SV_SCHEMA>.<SV_NAME>

  Tables:          N
  Facts:           N
  Dimensions:      N  (including N time dimensions)
  Metrics:         N
  Relationships:   N
  Verified Queries: N  (N marked as onboarding questions)

  Self-test: N/N questions passing
  Descriptions: AI-generated for N columns

  DDL saved above — copy to hol_setup.sql or version control.

Next options:
  - Add this SV to a Cortex Agent   → run cortex-agent-ddl skill
  - Add more verified queries       → repeat Phase 7
  - Schedule drift monitoring       → Phase 8 (weekly/monthly health check)
  - Optimize with Cortex Analyst    → run semantic-view skill (existing/optimization path)
  - A/B test agent configurations   → use the cortex-agent-toolkit plugin's agent-flag-tester skill if installed
```

### Multi-tenant handoff note

If `IS_MTT = true` for this semantic view, append the following note to the final summary:

```
⚠️  Multi-tenant SV: The downstream Cortex Agent MUST use a matching tenant
    isolation pattern (user/role/session-attr). See cortex-agent-ddl Phase 4b
    for the three patterns. RAPs applied to base tables automatically scope
    agent-generated SQL queries because Cortex Analyst generates SQL against
    the SV's source tables — the RAP evaluates at query time regardless of
    whether the query was written by a human or by the AI.
```

⚠️ **STOPPING POINT** — Present final summary and wait for user's next action.

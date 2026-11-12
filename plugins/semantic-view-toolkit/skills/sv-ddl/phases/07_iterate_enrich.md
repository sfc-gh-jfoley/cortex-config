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
4. Create the new SV, or hand an existing SV's changes to gate `SV-PROMOTE`

This phase repeats as many times as needed.

### Where edits go (candidate-copy contract)

Every edit in Steps 7.1–7.5 changes the **working DDL**, then is applied to a candidate, never to
`<SV_FQN>` (see `../../../references/candidate-promotion.md`):

- **New SV** (target does not exist yet): keep editing the Phase 5/6 working DDL and apply it to
  the Phase 6 candidate.
- **Existing SV**: start from `GET_DDL('SEMANTIC_VIEW', '<SV_FQN>')`, create a `cand` candidate
  with `candidate.py` exactly as in Phase 6 Step 6.1, and edit that.

Apply an edit to the candidate by running `candidate.py guard --source <SV_FQN> --target <CAND>`
and then `CREATE OR ALTER SEMANTIC VIEW <CAND>` with the **full** updated definition (omitted
properties are unset). Re-run the Phase 6 checks against `<CAND>` after each edit.

---

## Step 7.1: Generate AI_VERIFIED_QUERIES

`AI_VERIFIED_QUERIES` embeds curated question→SQL pairs directly in the semantic view DDL.
These are displayed as starter questions in Snowflake Intelligence and improve Cortex Analyst's accuracy.

Ask user: "Do you want to add verified queries (example questions and their SQL)? These become the onboarding questions shown in Snowflake Intelligence."

### Add to the full definition

`ALTER SEMANTIC VIEW` cannot change verified queries. Add `AI_VERIFIED_QUERIES` as the final
clause of the full working definition and apply it to the candidate:

- **Existing SV**: adding VQRs is gate `VQR-GEN-INSERT`; existing VQRs are read-only
  (`SV-VQR-MUTATE`). Copy them unchanged from `GET_DDL`.

```sql
CREATE OR ALTER SEMANTIC VIEW <SV_DB>.<SV_SCHEMA>.<CAND>
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

`ALTER SEMANTIC VIEW ... ALTER DIMENSION` is not a supported sub-command. Edit the COMMENT
strings in the working DDL and apply the full definition to the candidate (see "Where edits go").

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

`ALTER SEMANTIC VIEW ... SET AI_SQL_GENERATION` is not a supported sub-command. Add or edit the
`AI_SQL_GENERATION '<instructions>'` clause (after COMMENT) in the working DDL and apply the full
definition to the candidate.

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

`ALTER SEMANTIC VIEW ... ALTER DIMENSION ... SET CORTEX SEARCH SERVICE` is not supported. Add
the linkage to the dimension in the working DDL and apply the full definition to the candidate:

```sql
-- In the DIMENSIONS clause of the full definition:
<table_alias>.<dim_name> AS <col>
  COMMENT = '...'
  WITH CORTEX SEARCH SERVICE <db>.<schema>.<css_name>
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
-- On the semantic view (new SV: in the final CREATE in Step 7.7):
CREATE SEMANTIC VIEW <SV_DB>.<SV_SCHEMA>.<SV_NAME>
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
- `CREATE OR ALTER` cannot add or change tags (existing tags are preserved). For a new SV, put
  tags in the final `CREATE SEMANTIC VIEW`. For an existing SV, `ALTER SEMANTIC VIEW ... SET TAG`
  is a production change and goes through `SV-PROMOTE`.
- See [../reference/multitenant_sv_guidance.md](../reference/multitenant_sv_guidance.md) for tenant columns

---

## Step 7.6: Export final DDL

Generate the complete final DDL with all enrichments for:
- HOL setup scripts (`hol_setup.sql`)
- Version control
- Sharing with colleagues

```sql
-- Complete final DDL:
CREATE SEMANTIC VIEW <SV_DB>.<SV_SCHEMA>.<SV_NAME>
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

## Step 7.7: Create the new SV, or promote

**New SV.** Check for a collision by exact name (not `LIKE`; `_` is a wildcard):

```sql
SHOW SEMANTIC VIEWS IN SCHEMA <SV_DB>.<SV_SCHEMA>;
SELECT COUNT(*) AS existing FROM TABLE(RESULT_SCAN(LAST_QUERY_ID())) WHERE "name" = '<SV_NAME>';
```

If `existing > 0`, stop: the name is taken and this skill does not overwrite it. Use the
existing-SV path instead. Otherwise run the Step 7.6 DDL (plain `CREATE SEMANTIC VIEW`).

**Existing SV.** Stop at gate `SV-PROMOTE` (OPERATOR_REQUIRED in both modes) and follow
`../../../references/candidate-promotion.md` §4: DDL diff, evaluation evidence, consumers
(possibly incomplete), captured grants/tags/materializations, then the operator's choice.

**Both.** Mark the winning candidate `winner` (or `promoted`) and offer gate
`SV-CANDIDATE-CLEANUP` with `candidate.py cleanup-plan` for the rest.

---

## Step 7.8: Final summary

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
  - Add this SV to a Cortex Agent   → agent-ddl skill (cortex-agent-toolkit plugin, if installed)
  - Add more verified queries       → repeat Phase 7
  - Monitor drift                   → sv-watch skill
  - Optimize with Cortex Analyst    → run semantic-view skill (existing/optimization path)
  - A/B test agent configurations   → use the cortex-agent-toolkit plugin's agent-model-tester skill if installed
```

### Multi-tenant handoff note

If `IS_MTT = true` for this semantic view, append the following note to the final summary:

```
⚠️  Multi-tenant SV: The downstream Cortex Agent MUST use a matching tenant
    isolation pattern (user/role/session-attr). See
    ../reference/multitenant_sv_guidance.md and agent-ddl Phase 4b
    (cortex-agent-toolkit) for the three patterns. RAPs applied to base tables automatically scope
    agent-generated SQL queries because Cortex Analyst generates SQL against
    the SV's source tables — the RAP evaluates at query time regardless of
    whether the query was written by a human or by the AI.
```

⚠️ **STOPPING POINT (INTERACTIVE mode)** — Present final summary and wait for user's next action.

**AUTONOMOUS:** a new SV is created in Step 7.7 after the collision check; an existing SV
waits at `SV-PROMOTE` and cleanup waits at `SV-CANDIDATE-CLEANUP`. Log the final summary and
return control.

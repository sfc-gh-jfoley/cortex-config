---
name: sv-discovery-phase5-handoff
description: Generate structured handoff documents for each approved domain, formatted for direct consumption by the semantic-view-ddl skill
---

# Phase 5: Handoff

## Purpose
Produce a structured handoff document for each approved domain. The output must be directly pasteable into `$semantic-view-ddl` Phase 1 (Context Gathering) as the table list, relationship context, and business context inputs.

---

## Step 5A: Generate handoff document per domain

For each domain in `APPROVED_DOMAINS`, generate a self-contained section:

```markdown
---

## Domain: [Domain Name]

**Suggested Semantic View:**
- Database: `<DISCOVERY_DB>` (same as source)
- Schema: `<most common schema in domain tables>` (or PUBLIC)
- Name: `<DOMAIN_NAME>_SV`
- Full FQN: `<DISCOVERY_DB>.<SCHEMA>.<DOMAIN_NAME>_SV`
- Connection: `<SV_CONNECTION>` (from Phase 1)
**Confidence:** HIGH | MEDIUM | LOW
**Column count:** <N> (<size assessment>)

### Tables

| # | Fully Qualified Name | Role |
|---|---|---|
| 1 | <DISCOVERY_DB>.<SCHEMA>.TABLE_A | Central entity |
| 2 | <DISCOVERY_DB>.<SCHEMA>.TABLE_B | Related |
| 3 | <DISCOVERY_DB>.<SCHEMA>.TABLE_C | Related |
| 4 | <DISCOVERY_DB>.<SCHEMA>.TABLE_D | Shared dimension (also in [Other Domain]) |

### Detected Join Keys

| Left Table | Left Column | Right Table | Right Column | Evidence |
|---|---|---|---|---|
| TABLE_A | ID | TABLE_B | A_ID | FK constraint |
| TABLE_B | C_ID | TABLE_C | ID | Column inference + 156 co-queries |
| TABLE_A | D_CODE | TABLE_D | CODE | Column inference + 89 co-queries |

### Top Queried Columns (from ACCESS_HISTORY)

| Column | Table | Access Count (30d) |
|---|---|---|
| STATUS | TABLE_A | 4,521 |
| CREATED_AT | TABLE_A | 3,892 |
| AMOUNT | TABLE_B | 2,103 |
| CATEGORY | TABLE_C | 1,847 |
| NAME | TABLE_D | 1,203 |

(If ACCESS_HISTORY was not available, this section reads: "Column usage data not available — ACCESS_HISTORY was inaccessible during scan.")

### Usage Context

- **Co-query volume:** <N> unique queries reference 2+ tables in this domain (30-day window)
- **Distinct users:** <N> users query these tables together
- **Common patterns:** aggregation by [columns], filtered by [columns], grouped by [columns]

(If QUERY_HISTORY was not available, this section reads: "Query co-occurrence data not available — ACCOUNT_USAGE was inaccessible during scan. Domain grouping is based on FK constraints and column name inference only.")

### Suggested Business Context

(Auto-generated from query patterns — refine when invoking $semantic-view-ddl)

> "This semantic view should answer questions about [domain name]: [top 3 common query patterns observed, e.g., aggregation by status, filtering by date range, joining customers to orders]. Key metrics include [columns with high access count that are numeric]. Primary time dimension: [DATE/TIMESTAMP column with highest access count, if any]."

### Time Dimensions Detected

| Column | Table | Evidence |
|--------|-------|----------|
| <DATE_COLUMN> | <TABLE> | <N> accesses, used in WHERE date filters |

(If no DATE/TIMESTAMP columns found with high usage, note: "No clear time dimension detected — specify manually in $semantic-view-ddl Phase 1")

---
→ To build this semantic view, invoke `$semantic-view-ddl` and provide the tables listed above.
```

Repeat for each domain.

---

## Step 5B: Cross-domain bridge note

If any bridge tables were identified, include a note after all domains:

```markdown
---

## Cross-Domain Shared Dimensions

The following tables appear in multiple domains. Include them in each semantic view that references them:

| Table | Domains | Include In |
|---|---|---|
| <DISCOVERY_DB>.<SCHEMA>.CUSTOMERS | Orders, Support | Both SVs |
| <DISCOVERY_DB>.<SCHEMA>.PRODUCTS | Orders, Inventory | Both SVs |

When building each SV with `$semantic-view-ddl`, include the shared dimension table in the source table list.
```

---

## Step 5C: Present final summary

```
# Discovery Complete

Found <N> recommended semantic view domains:

| # | Domain | Tables | Confidence | Suggested SV Name |
|---|---|---|---|---|
| 1 | [Domain 1] | <N> tables | HIGH | <DB>.<SCHEMA>.<NAME>_SV |
| 2 | [Domain 2] | <N> tables | MEDIUM | <DB>.<SCHEMA>.<NAME>_SV |
| 3 | [Domain 3] | <N> tables | HIGH | <DB>.<SCHEMA>.<NAME>_SV |

Orphan tables (no SV recommended): <N>
Cross-domain bridges: <N> shared dimensions

## Next Steps — 3-Skill Chain

1. **For each domain above**, invoke `$semantic-view-ddl`:
   - Paste the domain section as context when asked for source tables
   - The "Suggested Business Context" is your starting point for the business context question
   - The "Time Dimensions Detected" pre-answers the temporal classification question

2. **After each SV is created**, invoke `$cortex-agent-ddl` (from cortex-agent-toolkit):
   - The agent skill will auto-discover your new SV via SHOW SEMANTIC VIEWS
   - Each SV becomes a tool in the agent
   - For multi-domain deployments: create one agent with multiple SV tools (one per domain)

3. **Optional: Audit periodically** — re-run `$semantic-view-discovery` in Audit mode against deployed SVs to catch drift.

Tip: Start with the highest-confidence domain. Get it deployed as an SV + agent, validate it works, then repeat for remaining domains.
```

---

## Output

The handoff documents are the final output of this skill. No further phases.

| Deliverable | Format |
|----------|----------|
| Domain handoff documents | Markdown sections, one per approved domain |
| Cross-domain bridge note | Markdown table of shared dimensions |
| Summary with next steps | Actionable instructions for `$semantic-view-ddl` |

---
name: cowork-deep-research
description: "Run multi-step investigations across structured and unstructured data with full source tracing. Use when: multi-source research, source attribution, compliance audits, investigative reporting. Triggers: investigate, research, source trace, multi-step analysis, lineage tracking, audit trail."
---

# CoWork Deep Research Skill

End-to-end workflow for multi-step investigations combining structured queries, unstructured search, and analysis — with full source attribution for every finding.

---

## Overview

**Problem**: You need answers that span multiple sources — a SQL query, search results, and manual analysis. How do you coordinate it all and prove where each finding came from?

**Solution**: **Deep Research** provides:
- Multi-step workflow orchestration (SQL + search + analysis steps)
- Source tracing (every finding links back to its originating step)
- Lineage documentation (audit trail for compliance)
- Structured output (findings with source attribution)

---

## Use Cases

### Competitive Analysis
```
Research Question: "What are competitors' pricing strategies?"

Steps:
1. SQL: Query your pricing table
2. Search: Find competitor pricing pages (Cortex Search on web scraped docs)
3. Analysis: Compare and calculate deltas
4. Output: "Competitor X prices 15% lower (Source: web page URL from search result #3)"
```

### Customer Research
```
Research Question: "What technologies does Target use?"

Steps:
1. SQL: Query your customer tech stack database
2. Search: Find Target's tech job postings (from document index)
3. Analysis: Combine, identify tech trends
4. Output: "Target invests heavily in Kubernetes (Source: job posting, 5 mentions)"
```

### Incident Investigation
```
Research Question: "Root cause of Jan 15 outage?"

Steps:
1. SQL: Query system logs table
2. SQL: Query related database performance metrics
3. Search: Find incident report documents (internal KB)
4. Analysis: Correlate findings
5. Output: "Cascading failure triggered by quota exceeded (Source: log entry timestamp 14:32:01)"
```

### Market Sizing
```
Research Question: "TAM for product X?"

Steps:
1. SQL: Query internal market data
2. SQL: Query industry benchmark database
3. Search: Find analyst reports (indexed PDFs)
4. Analysis: Calculate projections
5. Output: "Estimated TAM $50B (Source: analyst report + internal data reconciliation)"
```

---

## Prerequisites

- Snowflake account with CoWork deep research enabled (GA Jul 7, 2026)
- Cortex Search service available (or Cortex Analytics for unstructured analysis)
- SELECT on all tables/views used in investigation steps
- See `PREREQUISITES.md` for full setup

---

## Phase 0: Pre-Flight Checks

```sql
-- 1. CoWork deep research enabled
SELECT SYSTEM$COWORK_STATUS();
-- Expected: DEEP_RESEARCH_ENABLED = true

-- 2. Cortex Search available
SELECT COUNT(*) FROM INFORMATION_SCHEMA.OBJECTS 
WHERE OBJECT_TYPE = 'CORTEX SEARCH SERVICE';
-- Expected: >= 1 (at least one search service)

-- 3. Data access verified
SELECT * FROM <your_research_database>.<your_schema>.* LIMIT 1;
-- Expected: SELECT succeeds
```

---

## Phase 1: Define Research Scope

### 1.1 Research Question

Gather from user:

```
"What is your research question?"
→ Specific, measurable, traceable question

Example good questions:
  ✓ "What are the top 5 pricing strategies among SaaS competitors?"
  ✓ "What technologies does Target's engineering team use?"
  ✓ "What was the root cause of the Jan 15 database outage?"

Example vague questions:
  ✗ "Tell me about competitors"
  ✗ "What's happening in tech?"
  ✗ "Investigate the outage"
```

### 1.2 Data Sources Available

Confirm what data the user can access:

```sql
-- SQL sources
SHOW DATABASES;
SHOW TABLES IN SCHEMA <schema>;

-- Search sources (Cortex Search services)
SHOW CORTEX SEARCH SERVICES IN DATABASE <db>;
SHOW CORTEX SEARCH SERVICES IN SCHEMA <schema>;

-- Unstructured sources (documents, indexed content)
SELECT COUNT(*) FROM TABLE(CORTEX_SEARCH_SERVICE(...));
```

### 1.3 Constraints & Scope

Ask user:
- Timeline (how far back to search?)
- Data sensitivity (can results be logged/archived?)
- Confidence requirements (need multiple sources, or best effort?)
- Output format (report, findings list, query results?)

---

## Phase 2: Plan Multi-Step Workflow

### 2.1 Step Sequencing

Plan a sequence of steps that builds toward the research question.

**Example: Competitive pricing research**

```
Step 1 (SQL): Your pricing
  └─ Query: SELECT PRODUCT, PRICE FROM pricing_table WHERE product IN ('A', 'B', 'C')
  └─ Output: [A: $100, B: $200, C: $150]

Step 2 (SQL): Competitor public pricing
  └─ Query: SELECT COMPETITOR, PRODUCT_EQUIV, PUBLIC_PRICE FROM competitor_pricing
  └─ Output: [CompX ProductA: $85, CompX ProductB: $180, ...]

Step 3 (Search): Competitor pricing pages (if not in database)
  └─ Query: CORTEX_SEARCH over indexed competitor websites
  └─ Input: ['pricing', 'cost', 'SaaS plans']
  └─ Output: [Search result #1: CompY pricing page, #2: CompZ pricing, ...]

Step 4 (Analysis): Compare & calculate deltas
  └─ Aggregate steps 1-3
  └─ Calculate: delta_vs_comptx = our_price - comptx_price
  └─ Output: Summary table with deltas
```

### 2.2 Dependency Graph

Identify dependencies between steps:

```
Step 1 (SQL: your pricing)
  └─ independent (no upstream dependency)

Step 2 (SQL: competitor pricing)
  └─ independent (no upstream dependency)

Step 3 (Search: competitor websites)
  └─ independent (can run in parallel with steps 1-2)

Step 4 (Analysis: compare)
  └─ depends on steps 1-3 (needs output from all)

Parallelizable: Steps 1, 2, 3 → then Step 4
```

### 2.3 Source Tracing Strategy

Decide how you'll trace each finding back to its source:

| Step Type | Tracing Strategy |
|-----------|------------------|
| SQL query | Record query ID, query text, row count, timestamp |
| Cortex Search | Record search service name, query text, result rank, confidence score |
| Analysis | Record formula, input step references, manual notes |

---

## Phase 3: Execute & Trace Sources

### 3.1 Execute Step 1 (SQL: Your Pricing)

```sql
-- Step 1: Your pricing
WITH our_pricing AS (
  SELECT 
    PRODUCT,
    PRICE,
    CURRENT_TIMESTAMP() AS QUERY_TIMESTAMP
  FROM ANALYTICS_DB.PUBLIC.PRICING
  WHERE PRODUCT IN ('A', 'B', 'C')
)
SELECT * FROM our_pricing;

-- Record:
-- Source: ANALYTICS_DB.PUBLIC.PRICING
-- Query ID: step-1-our-pricing
-- Timestamp: [capture]
-- Row count: [e.g., 3]
```

### 3.2 Execute Step 2 (SQL: Competitor Pricing)

```sql
-- Step 2: Competitor pricing from database
WITH comp_pricing AS (
  SELECT 
    COMPETITOR,
    PRODUCT_EQUIV,
    PUBLIC_PRICE,
    CURRENT_TIMESTAMP() AS QUERY_TIMESTAMP
  FROM MARKET_DB.PUBLIC.COMPETITOR_PRICING
  WHERE COMPETITOR IN ('CompX', 'CompY', 'CompZ')
)
SELECT * FROM comp_pricing;

-- Record:
-- Source: MARKET_DB.PUBLIC.COMPETITOR_PRICING
-- Query ID: step-2-comp-pricing
-- Timestamp: [capture]
-- Row count: [e.g., 9]
```

### 3.3 Execute Step 3 (Cortex Search: Competitor Websites)

```sql
-- Step 3: Search for competitor pricing on indexed websites
SELECT 
  RESULT_RANK,
  RESULT_TEXT,
  CONFIDENCE_SCORE,
  CURRENT_TIMESTAMP() AS SEARCH_TIMESTAMP
FROM TABLE(
  COMPETITOR_PRICING_SEARCH(
    QUERY => 'SaaS pricing plans',
    NUM_RESULTS => 10
  )
);

-- Record:
-- Source: COMPETITOR_PRICING_SEARCH (Cortex Search service)
-- Search ID: step-3-web-search
-- Search terms: 'SaaS pricing plans'
-- Timestamp: [capture]
-- Result count: [e.g., 10]
```

### 3.4 Execute Step 4 (Analysis: Compare & Calculate)

```sql
-- Step 4: Analysis — compare our pricing vs competitor pricing
WITH our_pricing_labeled AS (
  SELECT PRODUCT, PRICE AS OUR_PRICE FROM our_pricing
),
comp_pricing_labeled AS (
  SELECT PRODUCT_EQUIV, PUBLIC_PRICE AS COMP_PRICE FROM comp_pricing
),
analysis AS (
  SELECT 
    COALESCE(o.PRODUCT, c.PRODUCT_EQUIV) AS PRODUCT,
    o.OUR_PRICE,
    c.COMP_PRICE,
    CASE 
      WHEN o.OUR_PRICE > c.COMP_PRICE THEN 'HIGHER'
      WHEN o.OUR_PRICE < c.COMP_PRICE THEN 'LOWER'
      ELSE 'EQUAL'
    END AS PRICE_POSITION,
    (o.OUR_PRICE - c.COMP_PRICE) AS DELTA_DOLLARS,
    ROUND(((o.OUR_PRICE - c.COMP_PRICE) / c.COMP_PRICE * 100), 2) AS DELTA_PCT,
    'step-1 + step-2' AS SOURCE_REFERENCE
  FROM our_pricing_labeled o
  FULL OUTER JOIN comp_pricing_labeled c
    ON o.PRODUCT = c.PRODUCT_EQUIV
)
SELECT * FROM analysis;

-- Record:
-- Analysis ID: step-4-pricing-comparison
-- Inputs: step-1-our-pricing, step-2-comp-pricing
-- Timestamp: [capture]
-- Method: delta calculation
```

---

## Phase 4: Compile Findings with Source Attribution

### 4.1 Structured Output with Source Tracing

Generate findings with full attribution:

```
FINDING #1
  Quote: "Product A: We are 17.65% HIGHER than CompX"
  Values: Our $100 vs CompX $85
  Sources:
    - Step 1 (SQL): ANALYTICS_DB.PUBLIC.PRICING, row 1
    - Step 2 (SQL): MARKET_DB.PUBLIC.COMPETITOR_PRICING, row 1
  Confidence: HIGH (both sources are current as of 2026-07-10)
  Link: "If you need original data, query step-1-our-pricing or step-2-comp-pricing"

FINDING #2
  Quote: "Product B: We are 11.11% LOWER than CompX"
  Values: Our $200 vs CompX $180
  Sources:
    - Step 1 (SQL): ANALYTICS_DB.PUBLIC.PRICING, row 2
    - Step 2 (SQL): MARKET_DB.PUBLIC.COMPETITOR_PRICING, row 2
  Confidence: HIGH
  Link: See above

FINDING #3 (from search)
  Quote: "CompY advertises 'Enterprise plans starting at $50/month'"
  Sources:
    - Step 3 (Search): Result #5 from competitor_pricing_search
    - URL: https://...
    - Rank: 5/10 results
  Confidence: MEDIUM (from search index; rank suggests some relevance uncertainty)
  Link: "If needed, re-run search with different query terms"
```

### 4.2 Compliance / Audit Trail

Create an audit record of the investigation:

```sql
-- Investigation metadata
INSERT INTO INVESTIGATION_LOG (
  INVESTIGATION_ID,
  RESEARCH_QUESTION,
  INVESTIGATOR,
  START_TIMESTAMP,
  END_TIMESTAMP,
  STEP_COUNT,
  SOURCE_COUNT,
  CONFIDENCE_LEVEL,
  FINDINGS_COUNT,
  STATUS
) VALUES (
  'inv-202607-competitive-pricing',
  'What are top competitors pricing strategies?',
  CURRENT_USER(),
  '2026-07-10T08:00:00Z',
  '2026-07-10T08:45:00Z',
  4,
  3,  -- 3 data sources: step-1, step-2, step-3
  'HIGH',
  3,  -- 3 findings extracted
  'COMPLETED'
);

-- Step audit trail
INSERT INTO INVESTIGATION_STEPS (
  INVESTIGATION_ID,
  STEP_NUMBER,
  STEP_TYPE,
  QUERY_TEXT,
  ROWS_RETURNED,
  TIMESTAMP
) VALUES
  ('inv-202607-competitive-pricing', 1, 'SQL', 'SELECT PRODUCT, PRICE FROM ...', 3, '2026-07-10T08:05:00Z'),
  ('inv-202607-competitive-pricing', 2, 'SQL', 'SELECT COMPETITOR, PRODUCT_EQUIV, PUBLIC_PRICE FROM ...', 9, '2026-07-10T08:10:00Z'),
  ('inv-202607-competitive-pricing', 3, 'SEARCH', 'CORTEX_SEARCH(...SaaS pricing plans...)', 10, '2026-07-10T08:15:00Z'),
  ('inv-202607-competitive-pricing', 4, 'ANALYSIS', 'Compare and calculate deltas', 3, '2026-07-10T08:20:00Z');
```

### 4.3 Export & Archive Findings

```sql
-- Create artifact of findings for team access
CREATE ARTIFACT RESEARCH_DB.PUBLIC.competitive_pricing_findings AS
SELECT * FROM <findings_table>;

-- Document retention
COMMENT ON ARTIFACT RESEARCH_DB.PUBLIC.competitive_pricing_findings IS
'Competitive pricing analysis — 2026-07-10.
Investigation ID: inv-202607-competitive-pricing.
Sources: 3 (2 SQL, 1 Cortex Search). Confidence: HIGH.
Archive after: 2026-12-31. Contact research-team@company.com for questions.';
```

---

## Troubleshooting

### Issue: "Step takes too long to execute"
**Solution**: Check for query performance issues:
```sql
-- Profile the slow step
EXPLAIN <step_query>;

-- Consider:
-- 1. Add clustering or search optimization
-- 2. Break into smaller queries (cache intermediate results)
-- 3. Increase warehouse size for parallel execution
```

### Issue: "Cortex Search result has low confidence"
**Solution**: Re-run search with refined terms or check indexing:
```sql
-- Try alternative search terms
SELECT * FROM TABLE(SEARCH_SERVICE(..., QUERY => 'alternative query'));

-- Check search service status
SHOW CORTEX SEARCH SERVICES;
DESCRIBE CORTEX SEARCH SERVICE <name>;
```

### Issue: "Source attribution unclear"
**Solution**: Add explicit metadata to each step:
```sql
-- Explicitly tag each step result
SELECT 
  *,
  'step-1-sql' AS SOURCE_STEP_ID,
  CURRENT_TIMESTAMP() AS SOURCE_TIMESTAMP,
  'ANALYTICS_DB.PUBLIC.PRICING' AS SOURCE_TABLE
FROM your_query;
```

### Issue: "Investigation result needs audit sign-off"
**Solution**: Create compliance record:
```sql
INSERT INTO INVESTIGATION_APPROVALS (
  INVESTIGATION_ID,
  APPROVER_ROLE,
  APPROVAL_TIMESTAMP,
  NOTES
) VALUES (
  'inv-202607-competitive-pricing',
  'COMPLIANCE_REVIEW',
  CURRENT_TIMESTAMP(),
  'Findings reviewed. Source documentation complete. Approved for reporting.'
);
```

---

## Best Practices

1. **Plan before executing**: Outline steps 1-N in Phase 2 before running queries
2. **Trace as you go**: Record source metadata for each step immediately
3. **Use explicit step IDs**: `step-1-our-pricing`, `step-3-web-search` (not `query1`, `search2`)
4. **Document sensitivity**: Mark findings as [PUBLIC], [INTERNAL], [RESTRICTED]
5. **Parallel where possible**: Steps with no dependencies can run together
6. **Archive findings**: Create artifacts for important investigations; log metadata for audit
7. **Link to originals**: Always provide query IDs or search terms so findings can be reproduced

---

## Next Steps

- **Share findings**: Use `$cowork:cowork-artifacts` to create persistent artifact of key findings
- **Iterate**: Re-run with different search terms or time windows
- **Integrate with agents**: Combine deep research results with agent tools for automated next-step actions
- **Schedule recurring**: Automate investigation runs for ongoing competitive monitoring


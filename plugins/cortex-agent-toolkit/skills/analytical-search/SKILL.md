---
name: analytical-search
description: >
  Configure Cortex Search tools for analytical search — corpus-wide analysis across large
  document collections (counts, aggregates, trends). Analytical search is an orchestration
  capability that auto-triggers from a standard cortex_search tool; it is NOT a separate
  tool type. Use this skill to set up the cortex_search configuration that enables it.
triggers:
  - analytical search
  - corpus-wide analysis
  - document aggregation
  - analyze all documents
  - count across documents
  - trend detection in documents
  - AI_FILTER AI_EXTRACT AI_AGG
---

# Analytical Search — Configuration Guide

Analytical search is an **orchestration capability** in Cortex Agents (Public Preview, Jun 30 2026).
It automatically triggers when a query requires corpus-wide analysis — counts, aggregates, trends,
comparisons across many documents — rather than simple retrieval of a few relevant passages.

**There is no `analytical_search` tool type.** You configure a standard `cortex_search` tool.
The agent auto-routes between standard RAG and analytical search based on query intent.

---

## How It Works

```
User query → Agent classifies intent
                │
                ├─ Simple/lookup → Standard RAG (top-k retrieval)
                └─ Analytical    → Analytical search loop:
                                    1. Cortex Search: prune corpus with adaptive depth
                                    2. AI_FILTER / AI_EXTRACT / AI_AGG on result set
                                    3. SQL aggregation + ranking
                                    → Precise, data-backed answer
```

**Adaptive depth**: Instead of fixed top-k, the agent extends search depth while results stay relevant, then stops — avoiding both truncation and wasted compute on irrelevant documents.

---

## Analytical vs. Standard RAG vs. SQL

| Query type | Right approach | Why |
|---|---|---|
| "Find the refund policy section" | Standard RAG | Single passage retrieval |
| "How many support tickets mentioned latency in May?" | Analytical search | Count across full corpus |
| "What % of EMEA sales calls mentioned product X?" | Analytical search | Aggregate across documents |
| "Total revenue by region" (structured data) | cortex_analyst_text_to_sql | Aggregation over structured tables |
| "What new themes emerged in 2025 vs 2024?" | Analytical search | Trend detection across documents |

---

## Setup: Configure cortex_search for Analytical Search

Analytical search uses your existing Cortex Search service. **No new service type required.**

### Step 1: Create a multi-index Cortex Search service

```sql
CREATE OR REPLACE CORTEX SEARCH SERVICE <db>.<schema>.<name>
  TEXT INDEXES CHUNK, DOC_ID [, <other_text_columns>]
  VECTOR INDEXES CHUNK (model = 'snowflake-arctic-embed-l-v2.0')
  ATTRIBUTES <date_col>, <category_col> [, <other_filter_columns>]
  WAREHOUSE = <warehouse_name>
  TARGET_LAG = '1 day'
AS
  SELECT chunk, doc_id, doc_title, date, category, <other_columns>
  FROM <chunks_table>;
```

Multi-index services (both TEXT and VECTOR indexes) perform best for analytical search.

### Step 2: Add the tool to your agent with high max_results

```yaml
tools:
  - tool_spec:
      type: "cortex_search"
      name: "policy_search"
      description: "Search company policies and support cases. Use for analytical questions requiring counts, aggregations, or trends across the full document corpus."

tool_resources:
  policy_search:
    name: "<db>.<schema>.<search_service_name>"
    max_results: "1000"           # High limit enables corpus-wide analysis
    title_column: "doc_title"
    id_column: "doc_id"
    columns_and_descriptions:
      chunk:
        description: "Full text of the document chunk. Searchable content for retrieval."
        type: "string"
        searchable: true
        filterable: false
      category:
        description: "Document category. Values: policy, guide, support_case, contract."
        type: "string"
        searchable: false
        filterable: true
      date:
        description: "Document creation date in YYYY-MM-DD format. Use for time-range filters."
        type: "date"
        searchable: false
        filterable: true
```

**`max_results: 1000` is required for analytical search.** Adaptive depth limits actual compute — the agent stops when results are no longer relevant — so a high limit does not mean high cost on every query.

---

## The Single Most Impactful Configuration: columns_and_descriptions

The agent uses column descriptions to decide which columns to filter on, how to interpret values, and how to frame `AI_EXTRACT` and `AI_FILTER` calls. Every column should describe:

- What the column contains and its expected format
- Sample values or enumerations (`"Values: policy, guide, support_case"`)
- Whether the column is suitable for filtering, searching, or extraction
- Any relationships to other columns

Columns without descriptions are largely invisible to the analytical search orchestration layer.

---

## Performance and Cost

| Aspect | Guidance |
|---|---|
| Response time | 2–6 min typical; up to 15 min for large corpora |
| Cost drivers | Agent orchestration + AI_FILTER / AI_EXTRACT / AI_AGG calls |
| Cost control | Adaptive depth limits unnecessary AI calls |
| CoWork integration | Adds plan mode, clarification questions, chart generation, artifact saving |

---

## Limitations (Public Preview)

- Analytical search does not produce PDF documents
- Intermediate results are not auto-persisted — save before ending session
- Works through CoWork and programmatic agent calls
- If requests originate in CoWork and invoke an agent, usage is attributed to CoWork (affects resource budgets scoping — see css-budgets)

---

## Related Skills

| Skill | Use when |
|---|---|
| `cortex-agent-ddl` | Creating the agent itself |
| `css-setup` | Creating the Cortex Search service backing this tool |
| `css-budgets` | Controlling costs for the underlying search service |
| `cowork-deep-research` | Running analytical search interactively through CoWork |

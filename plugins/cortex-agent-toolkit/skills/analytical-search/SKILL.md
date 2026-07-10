---
name: analytical-search
description: >
  Semantic search over large document collections using AI-powered ranking.
  Use when building agents that need to search and analyze extensive document corpus
  with natural language queries and relevance ranking.
triggers:
  - analytical search
  - document collection search
  - semantic search
  - search documents
  - find documents
---

# Analytical Search Tool for Cortex Agents

Use `analytical_search` tools in Cortex Agents to enable semantic search over large document collections with AI-powered relevance ranking.

---

## When to Use analytical_search

**Use analytical_search when**:
- Querying **large document collections** (1M+ documents)
- Searching **mixed structured/unstructured data** with natural language
- Results need **relevance ranking**, not just keyword matches
- Building **investigative agents** that reason over document context

**Example use cases**:
- "Search company policies and find all sections mentioning seasonal discounts"
- "Find customer complaints about refunds and rank by severity"
- "Locate technical documentation related to API authentication"
- "Search incident reports for patterns involving outage recovery"

---

## Comparison: analytical_search vs. cortex_search vs. cortex_analyst

| Scenario | Tool Type | Why |
|----------|-----------|-----|
| "Find all refund policies" in 500-doc corpus | `cortex_search` | Keyword indexing is sufficient; simple relevance works |
| "Show me refund policies mentioning 'seasonal'" + rank by relevance | `analytical_search` | Semantic ranking + keyword filtering needed |
| "Total refunds by region" (structured data) | `cortex_analyst_text_to_sql` | Aggregation requires SQL; structured query |
| "What are the top 3 policies that address seasonal returns?" | `analytical_search` | Semantic ranking + ranking logic |
| "Find policies AND calculate impact on Q1 revenue" | Hybrid (both tools) | Use `cortex_analyst` for SQL, `analytical_search` for doc retrieval |

**Key difference**: `cortex_search` ranks by keyword match; `analytical_search` ranks by semantic relevance (AI understands meaning).

---

## Agent Tool Spec Reference

When defining a `analytical_search` tool in your agent DDL, use this specification:

```json
{
  "name": "policy_search",
  "type": "analytical_search",
  "description": "Search company policies with semantic ranking. Returns top 10 results ranked by relevance to the query. Results include document title, excerpt, and relevance score.",
  "tool_resources": {
    "document_collection_id": "<collection_id>",
    "max_results": 10
  }
}
```

**Required fields**:
- `type`: Must be `"analytical_search"`
- `tool_resources.document_collection_id`: Snowflake document collection ID (from `INFORMATION_SCHEMA.DOCUMENT_COLLECTIONS`)
- `tool_resources.max_results`: Maximum number of results to return (1–100, typically 10–20)

**Optional**:
- `description`: Use to guide the agent on when to invoke this tool. Mention the document domain (e.g., "company policies", "customer feedback", "technical docs")

---

## Prerequisites

### 1. Document Collection Must Exist

Create a document collection with semantic embeddings:

```sql
CREATE DOCUMENT COLLECTION my_policies
  WITH SEMANTIC EMBEDDINGS;
```

### 2. Collection Must Be Indexed

Verify the collection has semantic embeddings enabled:

```sql
SELECT COLLECTION_ID, NAME, HAS_SEMANTIC_INDEX
FROM INFORMATION_SCHEMA.DOCUMENT_COLLECTIONS
WHERE NAME = 'my_policies';
```

Expected: `HAS_SEMANTIC_INDEX = TRUE`

### 3. Agent Role Must Have USAGE Privilege

Grant the agent execution role access to the collection:

```sql
GRANT USAGE ON DOCUMENT COLLECTION my_policies TO ROLE agent_executor;
```

### 4. Populate the Collection

Load documents into the collection (via INSERT, COPY, or connectors):

```sql
INSERT INTO my_policies (DOCUMENT_BODY, METADATA)
VALUES
  ('Policy text here...', '{"title": "Refund Policy", "type": "policy"}'),
  ('More policy text...', '{"title": "Return Procedures", "type": "policy"}');
```

---

## Phase 0 Collection Verification

Before creating the agent, verify the collection is ready:

```sql
-- Step 1: Check collection exists
SELECT COLLECTION_ID, HAS_SEMANTIC_INDEX
FROM INFORMATION_SCHEMA.DOCUMENT_COLLECTIONS
WHERE NAME = '<collection_name>';
-- Expected: 1 row, HAS_SEMANTIC_INDEX = TRUE

-- Step 2: Check row count
SELECT COUNT(*) FROM <collection_name>;
-- Expected: > 0

-- Step 3: Check current role has access
DESCRIBE DOCUMENT COLLECTION <collection_name>;
-- Expected: no "permission denied" error
```

**If collection not found**: Create it with `CREATE DOCUMENT COLLECTION ... WITH SEMANTIC EMBEDDINGS`

**If no semantic index**: Add it with `ALTER DOCUMENT COLLECTION ... SET SEMANTIC EMBEDDINGS = TRUE`

**If permission denied**: Grant with `GRANT USAGE ON DOCUMENT COLLECTION <name> TO ROLE <role>`

---

## Best Practices

### 1. Keep max_results Reasonable

- `max_results = 5-10`: Fast, focused results (for precise queries)
- `max_results = 10-20`: Balanced (default)
- `max_results = 50+`: Exhaustive, slower (use only for broad "get everything" queries)

**Recommendation**: Start at 10; increase only if agent needs broad context.

### 2. Provide Rich Document Metadata

Include metadata fields that help ranking:

```json
{
  "title": "Q3 Financial Report",
  "category": "finance",
  "date": "2026-07-01",
  "source": "internal_wiki",
  "priority": "high"
}
```

AI uses metadata to improve relevance ranking — results labeled "high priority" or recent dates score higher.

### 3. Test with Representative Queries

Before deploying the agent, test the collection against typical questions:

```sql
SELECT * FROM SEARCH_DOCUMENT_COLLECTION(
  collection => my_policies,
  query => 'What is the refund policy for seasonal items?',
  max_results => 10
);
```

Verify:
- Top 1-3 results are actually relevant
- Irrelevant documents are ranked low
- Collection contains documents that answer the question

### 4. Set up Multiple Collections for Specialized Domains

If your documents span multiple domains (policies, technical docs, customer feedback), create separate collections:

```sql
CREATE DOCUMENT COLLECTION policies WITH SEMANTIC EMBEDDINGS;
CREATE DOCUMENT COLLECTION technical_docs WITH SEMANTIC EMBEDDINGS;
CREATE DOCUMENT COLLECTION customer_feedback WITH SEMANTIC EMBEDDINGS;
```

Then create separate `analytical_search` tools in the agent (one per collection).

### 5. Monitor Query Performance

Document searches can be slower than SQL queries. If agent response time degrades:
- Reduce `max_results`
- Split large collections into domain-specific ones
- Archive old/low-priority documents to separate collections

---

## Related Tools

| Tool | When to use instead |
|---|---|
| `cortex_search` | Simple keyword-based search on indexed collections; lower latency |
| `cortex_analyst_text_to_sql` | Querying structured data (tables, views, semantic views); aggregations |
| `web_search` | Real-time web search; external public information |

---

## Troubleshooting

**"Collection not found" error**
- Verify the collection exists: `SHOW DOCUMENT COLLECTIONS;`
- Check spelling matches `INFORMATION_SCHEMA.DOCUMENT_COLLECTIONS`

**"Permission denied" error**
- Grant USAGE: `GRANT USAGE ON DOCUMENT COLLECTION <name> TO ROLE <agent_role>;`

**"Search returned no results"**
- Verify collection is populated: `SELECT COUNT(*) FROM <collection>;`
- Check documents have semantic embeddings: `SELECT HAS_SEMANTIC_INDEX FROM INFORMATION_SCHEMA.DOCUMENT_COLLECTIONS;`
- Try a simpler query to isolate scope

**"Slow search performance"**
- Reduce `max_results` (default 10 is usually sufficient)
- Filter collection by category/date metadata before search
- Archive old documents to separate collection

---

## Further Reading

- `cortex-agent-ddl` SKILL.md: Full agent creation workflow (includes analytical_search tool spec examples)
- `cortex-agent-toolkit` SKILL.md: Agent lifecycle overview and routing
- `INFORMATION_SCHEMA.DOCUMENT_COLLECTIONS`: System view for collection metadata

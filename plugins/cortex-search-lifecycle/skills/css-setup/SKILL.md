---
name: css-setup
description: >
  Create and configure Cortex Search Services. DDL patterns for CREATE CORTEX SEARCH SERVICE,
  warehouse selection, target_lag configuration, and source table setup best practices.
  Use when setting up semantic search for the first time or configuring index freshness.
triggers:
  - create search service
  - cortex search service setup
  - css setup
  - search service ddl
  - target lag configuration
  - search index setup
  - warehouse for search
  - semantic search setup
---

# CSS Setup: Create and Configure Search Services

Complete workflow for creating Cortex Search Services with proper warehouse configuration and index freshness settings.

---

## When to Use This Sub-Skill

Use **css-setup** when:
- Creating your first Cortex Search Service
- Setting up semantic search for a new source table
- Configuring warehouse and target_lag for index computation
- Selecting which columns to index for semantic search
- Understanding CREATE CORTEX SEARCH SERVICE DDL syntax

**Do NOT use this sub-skill for:**
- Managing search budgets (use `$cortex-search-lifecycle:css-budgets`)
- Monitoring search performance (use `$cortex-search-lifecycle:css-monitor`)
- Querying search results (use `$cortex-agent-toolkit` with search results)

---

## Quick Start: Create a Search Service in 5 Steps

### Step 1: Verify Source Table and Columns

```sql
-- Check your source table exists and has searchable content
SELECT 
  COUNT(*) as row_count,
  COUNT(DISTINCT product_id) as unique_ids
FROM products;

-- Verify searchable column has data
SELECT 
  COUNT(*) as non_null_descriptions,
  DATALENGTH(product_description) as avg_bytes
FROM products
WHERE product_description IS NOT NULL;
```

### Step 2: Choose a Warehouse

```sql
-- Option A: Use existing warehouse (if available and sized appropriately)
SHOW WAREHOUSES;

-- Option B: Create dedicated warehouse for search indexing
CREATE WAREHOUSE search_index_wh
  WAREHOUSE_SIZE = MEDIUM
  AUTO_SUSPEND = 60
  AUTO_RESUME = TRUE;

-- Size guide:
-- SMALL: <100K rows
-- MEDIUM: 100K-10M rows (typical)
-- LARGE: 10M-100M rows
-- XL: >100M rows
```

### Step 3: Decide on target_lag

Target lag controls index freshness vs. compute cost:

| Freshness Need | target_lag | Cost | Use Case |
|----------------|-----------|------|----------|
| Real-time | 1-5 minutes | High | Chat, support tickets |
| Frequent | 1 hour | Medium | Product catalogs, daily updates |
| Regular | 4 hours | Medium-Low | Weekly or daily changes |
| Low-frequency | 24 hours | Low | Archives, reference data |
| Static (no refresh) | `NEVER` | Minimal | Historical data, write-once |

```sql
-- Recommended defaults:
-- Real-time data: target_lag = '5 minutes'
-- Regular data: target_lag = '1 hour'
-- Infrequent data: target_lag = '24 hours'
```

### Step 4: Execute CREATE CORTEX SEARCH SERVICE

```sql
-- Syntax: CREATE CORTEX SEARCH SERVICE
CREATE CORTEX SEARCH SERVICE <service_name>
  ON <table_name>(<column1>, <column2>, ...)
  WAREHOUSE = <warehouse_name>
  TARGET_LAG = '<freshness_interval>';

-- Example: Create search service for products
CREATE CORTEX SEARCH SERVICE product_search
  ON products(product_id, product_name, product_description)
  WAREHOUSE = search_index_wh
  TARGET_LAG = '1 hour';
```

### Step 5: Verify Service is Ready

```sql
-- Check service state
SELECT 
  name,
  state,
  indexing_progress_pct,
  created_on,
  last_index_update_ts
FROM ACCOUNT_USAGE.CORTEX_SEARCH_SERVICES
WHERE name = 'product_search';

-- Wait for state to change from INDEXING to READY
-- This can take minutes to hours depending on table size
```

---

## Complete DDL Reference

### CREATE CORTEX SEARCH SERVICE Syntax

```sql
CREATE [OR REPLACE] CORTEX SEARCH SERVICE <service_name>
  ON [database.]schema.table_name(column1 [, column2, ...])
  WAREHOUSE = warehouse_name
  [TARGET_LAG = 'interval']
  [COMMENT = 'description'];
```

### Parameters

| Parameter | Required | Description | Default |
|-----------|----------|-------------|---------|
| `service_name` | Yes | Unique name for search service | N/A |
| `table_name` | Yes | Source table to index (can be schema-qualified) | N/A |
| `column1, column2, ...` | Yes | Columns to index for search (VARCHAR, STRING, TEXT only) | N/A |
| `WAREHOUSE` | Yes | Warehouse for index computation | N/A |
| `TARGET_LAG` | No | Index refresh interval (1 minute to 24 hours or NEVER) | `'1 hour'` |
| `COMMENT` | No | Description of search service | Empty |

---

## Best Practices

### 1. Column Selection

**DO:**
- Index 1-3 most relevant columns for search
- Index TEXT/VARCHAR columns only
- Focus on searchable content (descriptions, titles, etc.)

```sql
-- GOOD: Index only description (most relevant for semantic search)
CREATE CORTEX SEARCH SERVICE product_search
  ON products(product_description)
  WAREHOUSE = search_index_wh;

-- ALSO GOOD: Index name and description (both searchable)
CREATE CORTEX SEARCH SERVICE product_search
  ON products(product_name, product_description)
  WAREHOUSE = search_index_wh;
```

**DON'T:**
- Index numeric or date columns (not text-based)
- Index too many columns (slows indexing, increases cost)
- Index columns with high NULL rates without filtering

```sql
-- BAD: Indexing numeric and date columns
CREATE CORTEX SEARCH SERVICE product_search
  ON products(product_id, price, created_at, product_description)
  WAREHOUSE = search_index_wh;

-- BAD: Too many columns
CREATE CORTEX SEARCH SERVICE product_search
  ON products(product_name, product_description, category, supplier, manufacturer, ...)
  WAREHOUSE = search_index_wh;
```

### 2. Warehouse Sizing

Guide based on source table size:

```sql
-- Check source table size
SELECT 
  COUNT(*) as row_count,
  COUNT(DISTINCT column_name) as unique_values,
  DATALENGTH(text_column) as avg_text_bytes
FROM your_table;

-- Sizing recommendation:
-- <100K rows: SMALL
-- 100K-1M rows: SMALL or MEDIUM
-- 1M-10M rows: MEDIUM
-- 10M-100M rows: LARGE
-- >100M rows: XL

-- Option: Oversize initially, then scale down after first index completes
CREATE WAREHOUSE search_index_wh WAREHOUSE_SIZE = LARGE;
-- After indexing completes: ALTER WAREHOUSE search_index_wh SET WAREHOUSE_SIZE = MEDIUM;
```

### 3. target_lag Selection

**High-frequency updates (real-time data):**
```sql
-- Chat, support tickets, live feeds
CREATE CORTEX SEARCH SERVICE support_tickets_search
  ON support_tickets(ticket_description, ticket_notes)
  WAREHOUSE = search_index_wh
  TARGET_LAG = '5 minutes';  -- Fresh, but expensive
```

**Medium-frequency updates (daily/weekly):**
```sql
-- Product catalogs, pricing, inventory
CREATE CORTEX SEARCH SERVICE products_search
  ON products(product_name, product_description)
  WAREHOUSE = search_index_wh
  TARGET_LAG = '1 hour';  -- Good balance of freshness and cost
```

**Low-frequency or static data:**
```sql
-- Archives, reference data, historical documents
CREATE CORTEX SEARCH SERVICE archives_search
  ON documents(title, content)
  WAREHOUSE = search_index_wh
  TARGET_LAG = '24 hours';  -- Low cost, acceptable staleness

-- Or disable auto-refresh (one-time index):
CREATE CORTEX SEARCH SERVICE archives_search
  ON documents(title, content)
  WAREHOUSE = search_index_wh
  TARGET_LAG = 'NEVER';  -- Minimal cost; refresh manually
```

---

## Monitoring Index Creation

### Track Indexing Progress

```sql
-- Monitor indexing in real-time
SELECT 
  name,
  state,
  indexing_progress_pct,
  CURRENT_TIMESTAMP() as checked_at,
  DATEDIFF(second, created_on, CURRENT_TIMESTAMP()) as seconds_elapsed
FROM ACCOUNT_USAGE.CORTEX_SEARCH_SERVICES
WHERE name = 'product_search'
ORDER BY checked_at DESC;

-- Wait for state to become READY and progress to 100%
```

### What to expect by table size

| Table Size | Typical Index Time | Warehouse Size | Cost |
|------------|-------------------|-----------------|------|
| <100K rows | 5-15 minutes | SMALL | <1 credit |
| 100K-1M rows | 15-60 minutes | MEDIUM | 1-5 credits |
| 1M-10M rows | 1-4 hours | LARGE | 5-20 credits |
| 10M-100M rows | 4-12 hours | XL | 20-100 credits |

---

## Common DDL Variations

### Search Service with Schema-Qualified Table

```sql
CREATE CORTEX SEARCH SERVICE product_search
  ON analytics.search.products(product_description)
  WAREHOUSE = search_index_wh;
```

### Multi-Column Search (Name + Description)

```sql
CREATE CORTEX SEARCH SERVICE products_full_search
  ON products(product_name, product_description)
  WAREHOUSE = search_index_wh
  TARGET_LAG = '1 hour';
```

### Long-Term Index (24-hour refresh)

```sql
CREATE CORTEX SEARCH SERVICE products_daily_search
  ON products(product_description)
  WAREHOUSE = search_index_wh
  TARGET_LAG = '24 hours';
```

### Static Archive (one-time index, no refresh)

```sql
CREATE CORTEX SEARCH SERVICE documents_archive_search
  ON historical_documents(document_text)
  WAREHOUSE = search_index_wh
  TARGET_LAG = 'NEVER';
```

### With Comment for Documentation

```sql
CREATE CORTEX SEARCH SERVICE products_search
  ON products(product_name, product_description)
  WAREHOUSE = search_index_wh
  TARGET_LAG = '1 hour'
  COMMENT = 'Search service for ecommerce product catalog. Indexes product names and descriptions. Updates every hour.';
```

---

## Troubleshooting Setup

| Problem | Cause | Solution |
|---------|-------|----------|
| "CREATE CORTEX SEARCH SERVICE not allowed" | Missing privilege | Check PREREQUISITES.md: Grant CREATE CORTEX SEARCH SERVICE privilege |
| "Warehouse does not exist or not authorized" | Warehouse access | Verify warehouse exists and role has USAGE privilege |
| "Source table does not exist" | Wrong table name | Use schema-qualified name: `schema.table_name` |
| "Service stuck in INDEXING state" | Large table or small warehouse | Wait longer, or increase warehouse size and re-run |
| "Invalid column type" | Non-text column selected | Rerun with VARCHAR/STRING/TEXT columns only |
| "Column not found" | Typo in column name | Verify column names match source table |

---

## After Setup: Next Steps

Once your search service is **READY**:

1. **Query search results** — Use agents or SQL to query search endpoints
   - See `$cortex-agent-toolkit` for agent setup
   - Use `cortex_search_result()` function in SQL

2. **Monitor search health** — Track usage and guardrails compliance
   - See `$cortex-search-lifecycle:css-monitor` for monitoring queries

3. **Set search budgets** — Enforce credit limits and prevent overspend
   - See `$cortex-search-lifecycle:css-budgets` for budget setup

4. **Optimize performance** — Adjust target_lag, columns, or warehouse based on usage patterns
   - Monitor queries via `cortex-agent-toolkit`
   - Analyze costs and freshness tradeoffs

---

## Support and Examples

For more examples, see:
- `README.md` — Example workflows (products, support tickets, archives)
- `PREREQUISITES.md` — Source table and warehouse setup
- `$cortex-search-lifecycle:css-budgets` — Managing search costs
- `$cortex-search-lifecycle:css-monitor` — Monitoring search health

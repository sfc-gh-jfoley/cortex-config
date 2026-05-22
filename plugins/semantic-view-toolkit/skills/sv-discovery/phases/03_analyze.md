---
name: sv-discovery-phase3-analyze
description: Cluster tables into domain groupings using the relationship graph and column usage data. Score domain confidence and identify bridge tables.
---

# Phase 3: Analyze

## Purpose

Take the relationship graph from Phase 2 and cluster tables into semantic view domain groupings. Each domain represents a coherent business area that should become one semantic view.

**Input variables from Phase 2:** `RELATIONSHIP_GRAPH`, `COLUMN_USAGE`, `PK_MAP`, `CONSTRAINTS_AVAILABLE`, `ORPHAN_TABLES`, `SCAN_STRATEGY`  
**Input variables from Phase 1:** `DISCOVERY_DB`, `DISCOVERY_SCHEMAS`, `EXISTING_SVS`, `COVERED_TABLES`, `OBJECT_TYPE_COUNTS`, `MODE`

---

## Step 3A: Connected Components (Initial Clusters)

Identify connected components in the relationship graph using edge traversal. Each connected component becomes an initial domain candidate.

**Algorithm (greedy BFS):**

```
1. Sort edges by combined_confidence DESC
2. Initialize: each table is its own cluster
3. For each edge (table_a, table_b, confidence):
   - If table_a and table_b are in different clusters:
     - If confidence >= 0.60 (MEDIUM or higher):
       - Merge the two clusters
     - If confidence < 0.60 (LOW):
       - Mark as "weak edge" — don't merge yet
4. After processing all edges:
   - Each remaining distinct cluster = one domain candidate
   - Weak edges between clusters = potential cross-domain relationships
```

**Output:**
```
INITIAL_DOMAINS = [
  {domain_id: 1, tables: [table_a, table_b, table_c], internal_edges: [...], weak_external_edges: [...]}
  {domain_id: 2, tables: [table_d, table_e], internal_edges: [...], weak_external_edges: [...]}
]
```

---

## Step 3B: Size Validation and Splitting

Semantic views work best with 3-8 tables. Apply size constraints:

### Too Large (>10 tables)

Split large clusters using modularity-based subdivision:

1. Find the "weakest link" — the edge with lowest confidence within the cluster
2. Remove it and check if the cluster splits into two viable sub-clusters (each ≥2 tables)
3. If yes: split. If no: try the next weakest link.
4. Repeat until all clusters are ≤10 tables or no more splits are viable.

### Too Small (1 table)

Single-table "clusters" are orphans. Handle them:

1. Check if orphan has any LOW confidence edges to existing clusters
2. If yes: attach to the highest-confidence adjacent cluster (note LOW confidence)
3. If no: leave as orphan — will be reported separately in Phase 4

### Bridge Tables

Identify tables that connect two otherwise-separate clusters (high degree, linking roles):

```
For each table T in a cluster:
  If T has edges to ≥2 OTHER clusters:
    T is a bridge table candidate
    Consider including T in BOTH domains (it's a shared dimension)
```

Store bridge tables separately:
```
BRIDGE_TABLES = [{table, connected_domains: [domain_1, domain_2, ...]}]
```

---

## Step 3C: Name Domains

Assign a human-readable domain name based on the tables in each cluster:

**Naming heuristics:**

1. **Schema name** — if all tables in a domain share the same schema, use the schema name
2. **Common prefix** — if tables share a prefix (e.g., `SALES_ORDERS`, `SALES_ITEMS`), use the prefix ("Sales")
3. **Central entity** — identify the table with the most edges and use its singular name ("Orders", "Customers")
4. **LLM fallback** — if no pattern is clear, ask the LLM to suggest a name from the table list

Store as:
```
NAMED_DOMAINS = [
  {domain_name: "Orders", tables: [...], ...}
]
```

---

## Step 3D: Score Domain Confidence

For each domain, compute an overall confidence score. Follow the scoring model in `references/confidence-scoring.md`.

**Domain-level confidence = weighted average of internal edge confidences:**

```
domain_confidence = SUM(edge_confidence * edge_co_query_count) / SUM(edge_co_query_count)
```

If no co-occurrence data is available (no ACCESS_HISTORY), use simple average:
```
domain_confidence = AVG(internal_edge_confidences)
```

**Tier assignment:**
- ≥ 0.85 → HIGH
- 0.60–0.84 → MEDIUM
- 0.30–0.59 → LOW

**Demotion rules:**
- If domain contains ≥1 orphan table (attached via LOW edge): demote one tier
- If domain has >8 tables: demote one tier (size complexity)
- If domain crosses >2 schemas: add note "cross-schema domain" (not auto-demoted, but flagged)

---

## Step 3E: Annotate with Object Types

For each table in each domain, annotate its source type:

| Object Type | Annotation | Design Note |
|-------------|-----------|-------------|
| Base Table | `(base table)` | Standard source |
| View | `(view)` | May reference other databases — check cross-DB deps |
| Dynamic Table | `(dynamic table, lag: Xmin)` | Include TARGET_LAG context |
| External Table | `(external/iceberg)` | Performance note: may be slower for aggregations |
| Materialized View | `(materialized view)` | Watch for double-aggregation if both source and MV included |

For dynamic tables, query the lag:
```sql
SELECT NAME, TARGET_LAG
FROM <DISCOVERY_DB>.INFORMATION_SCHEMA.DYNAMIC_TABLES
WHERE NAME IN (<domain_tables>)
    AND SCHEMA_NAME IN (<DISCOVERY_SCHEMAS>);
```

---

## Step 3F: Cross-Reference Existing SV Coverage

For each domain, check which tables are already covered by existing SVs (from Phase 1's `COVERED_TABLES`):

```
For each domain:
  covered_count = count of tables already in an existing SV
  total_count = count of all tables in domain
  
  If covered_count == total_count:
    domain.status = 'FULLY_COVERED'
  Elif covered_count > 0:
    domain.status = 'PARTIALLY_COVERED'
    domain.uncovered_tables = tables NOT in COVERED_TABLES
    domain.covering_sv = which existing SV covers them
  Else:
    domain.status = 'NOT_COVERED'
```

---

## Step 3G: Identify Join Keys per Domain

For each domain, extract the specific join keys that connect its tables (from `RELATIONSHIP_GRAPH` edges):

```
domain.join_keys = [
  {from_table: 'ORDERS', from_column: 'CUSTOMER_ID', to_table: 'CUSTOMERS', to_column: 'CUSTOMER_ID', confidence: 0.95}
  {from_table: 'ORDER_ITEMS', from_column: 'ORDER_ID', to_table: 'ORDERS', to_column: 'ORDER_ID', confidence: 1.0}
]
```

These join keys feed directly into the `sv-ddl` skill's RELATIONSHIPS section.

---

## Step 3H: Column Importance Ranking

For each table in each domain, rank columns by importance using `COLUMN_USAGE` data:

```
Tier 1 (include in SV):
  - Top 80% by access frequency
  - All PK columns
  - All columns involved in detected join keys
  
Tier 2 (maybe include):
  - Remaining columns with >0 access
  
Tier 3 (likely exclude from SV):
  - Columns with 0 access in 90 days
  - System columns (_METADATA, ROW_INSERTED_AT, etc.)
```

If `COLUMN_USAGE` is unavailable (no ACCESS_HISTORY): include all non-system columns as Tier 1.

---

## Step 3I: Analysis Summary

In GUIDED mode, present the full analysis before Phase 4:

```
Analysis Complete:

Domains Identified: <N>

| # | Domain Name | Tables | Confidence | Coverage | Object Types |
|---|-------------|--------|------------|----------|--------------|
| 1 | Orders      | 5      | HIGH (0.92)| Not covered | 4 base, 1 DT |
| 2 | Marketing   | 3      | MEDIUM (0.71)| Partially covered | 3 base |
| 3 | Support     | 4      | HIGH (0.88)| Not covered | 3 base, 1 view |

Bridge Tables: <N> (shared across multiple domains)
  - DIM_DATE (Orders + Marketing + Support)
  - DIM_REGION (Orders + Marketing)

Orphan Tables: <N> (no clear domain affiliation)
  - STAGING_RAW_EVENTS
  - TEMP_LOAD_LOG

Fully Covered Domains (already have SVs): <N>
  - Finance (covered by FINANCE_SV)
```

**GUIDED mode:** Wait for approval before Phase 4.
**AUTOPILOT mode:** Continue to Phase 4 automatically.

---

## Output Variables Passed to Phase 4

| Variable | Contents |
|----------|----------|
| `NAMED_DOMAINS` | List of domains with name, tables, confidence, coverage status |
| `BRIDGE_TABLES` | Tables shared across domains |
| `ORPHAN_TABLES` | Tables with no domain affiliation |
| `DOMAIN_JOIN_KEYS` | Join keys per domain |
| `COLUMN_IMPORTANCE` | Column tier rankings per table |
| `FULLY_COVERED_DOMAINS` | Domains already served by existing SVs |

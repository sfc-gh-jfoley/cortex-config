---
name: sv-discovery-phase3-analyze
description: Cluster tables into domain groupings using the relationship graph and column usage data. Score domain confidence and identify bridge tables.
---

# Phase 3: Analyze

## Purpose

Take the relationship graph from Phase 2 and identify coherent business areas. Business domains are not automatically separate semantic views; choose SV boundaries using the workload checks below.

**Input variables from Phase 2:** `RELATIONSHIP_GRAPH`, `COLUMN_USAGE`, `PK_MAP`, `CONSTRAINTS_AVAILABLE`, `ORPHAN_TABLES`, `SCAN_STRATEGY`  
**Input variables from Phase 1:** `DISCOVERY_DB`, `DISCOVERY_SCHEMAS`, `EXISTING_SVS`, `COVERED_TABLES`, `OBJECT_TYPE_COUNTS`, `MODE`

---

## Step 3A: Connected Components (Initial Clusters)

Identify shared dimensions **first**, then cluster the rest. Merging every MEDIUM+ edge directly
would fuse all facts through a shared dimension such as `DIM_DATE` into one component, and bridge
detection could then never fire.

**Algorithm:**

```
Let STRONG = edges with combined_confidence >= 0.60 (MEDIUM or higher).

1. Find hubs (shared dimensions):
   - T is a hub if it is the referenced side (the PK/UNIQUE or "to" column) of STRONG edges
     from >= 2 distinct tables.
   - For co-occurrence-only edges (no direction), T is a hub if it has STRONG edges to >= 3
     tables that have no STRONG edge to each other.
2. Remove hubs and their edges; union-find the remaining STRONG edges into core clusters.
   Tables left with no edges are singletons (see "Too Small" below).
3. Re-attach each hub to every core cluster it has a STRONG edge to:
   - attached to 1 cluster  → ordinary member of that cluster
   - attached to >= 2       → BRIDGE_TABLES entry; include it in each of those clusters
4. Edges with combined_confidence < 0.60 between clusters are recorded as weak external edges.
5. Edges with needs_join_key = true may join tables into a cluster but stay flagged (Step 3G).
```

Core clusters are domain *candidates*. Step 3B decides SV boundaries, and may keep clusters that
share bridge tables in one SV.

**Output:**
```
INITIAL_DOMAINS = [
  {domain_id: 1, tables: [table_a, table_b, table_c], internal_edges: [...], weak_external_edges: [...]}
  {domain_id: 2, tables: [table_d, table_e], internal_edges: [...], weak_external_edges: [...]}
]
BRIDGE_TABLES = [{table, connected_domains: [domain_1, domain_2, ...]}]
```

---

## Step 3B: Choose Lightweight SV Boundaries

Prefer the fewest SVs that correctly support the workload. Business domains, channels,
multiple fact tables, different grains, and table count alone are not reasons to split.
Prefer one SV when its estimated size is comfortably within the guideline and its
relationships support the required questions correctly.

Before recommending a split, check:
- Do common questions cross the proposed boundary? Use available questions or usage evidence; if unavailable, label the grouping provisional.
- Can those questions be answered correctly without coordinating multiple tools? Check shared keys and aggregation grains; do not assume results can simply be combined.
- Is there a concrete reason to split: excessive estimated context size, unresolved relationship ambiguity, or genuinely independent workloads?

Shared dimensions alone justify neither merging nor splitting. Validate multi-fact
aggregation and population-versus-transaction metrics during the existing DDL tests.
Give a brief reason for each recommended split and label untested benefits as assumptions.
Use the existing recommendation output: recommendation, reason, and any validation caveat.
No extra approval gate, handoff schema, or mandatory architecture experiment is required.

### Too Small (1 table)

Single-table "clusters" are orphans. Handle them:

1. Check if orphan has any LOW confidence edges to existing clusters
2. If yes: attach to the highest-confidence adjacent cluster (note LOW confidence)
3. If no: leave as orphan — will be reported separately in Phase 4

### Bridge Tables

Bridge tables (shared dimensions) are identified in Step 3A before clustering. When Step 3B keeps
domains separate, include each bridge table in every domain it connects.

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

For each domain, compute an overall confidence score using the domain-level formula
in `../../../references/confidence-scoring.md` (Domain-Level Confidence section).

**Summary:** weighted average of internal edge confidences, weight = MAX(co_query_count, 1).

**Tier assignment:**
- ≥ 0.85 → HIGH
- 0.60–0.84 → MEDIUM
- 0.30–0.59 → LOW

**Demotion rules:**
- If domain contains ≥1 orphan table (attached via LOW edge): demote one tier
- If domain crosses >2 schemas: add note "cross-schema domain" (not auto-demoted, but flagged)
- If Step 3B identifies an unresolved relationship or aggregation-grain ambiguity affecting required questions: demote one tier and record the specific validation needed. Multiple facts, shared dimensions, channels, or different grains alone do not lower confidence or require a split.

---

## Step 3E: Annotate with Object Types

For each table in each domain, annotate its source type:

| Object Type | Annotation | Design Note |
|-------------|-----------|-------------|
| Base Table | `(base table)` | Standard source |
| View | `(view)` | May reference other databases — check cross-DB deps |
| Dynamic Table | `(dynamic table, lag: Xmin)` | Include TARGET_LAG context |
| External Table | `(external table)` | Performance note: may be slower for aggregations |
| Iceberg Table | `(iceberg table)` | `TABLE_TYPE = 'BASE TABLE'`, `IS_ICEBERG = 'YES'` |
| Materialized View | `(materialized view)` | Watch for double-aggregation if both source and MV included |

For dynamic tables, query the lag:
```sql
SHOW DYNAMIC TABLES IN DATABASE <DISCOVERY_DB>
  ->> SELECT "name" AS NAME, "target_lag" AS TARGET_LAG
      FROM $1
      WHERE "name" IN (<domain_tables>)
        AND "schema_name" IN (<DISCOVERY_SCHEMAS>);
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

For each domain, extract the specific join keys that connect its tables. Use only edges with
resolved join columns (`needs_join_key = false`):

```
domain.join_keys = [
  {from_table: 'ORDERS', from_column: 'CUSTOMER_ID', to_table: 'CUSTOMERS', to_column: 'CUSTOMER_ID', confidence: 0.95}
  {from_table: 'ORDER_ITEMS', from_column: 'ORDER_ID', to_table: 'ORDERS', to_column: 'ORDER_ID', confidence: 1.0}
]
domain.unresolved_pairs = [
  {table_a: 'ORDERS', table_b: 'WEB_EVENTS', co_query_count: 120, note: 'needs join key'}
]
```

Join keys feed the `sv-ddl` skill's RELATIONSHIPS section. Never emit a join key with a NULL
column. List `unresolved_pairs` in Phase 4 so the user can supply the columns or drop the pair;
in AUTONOMOUS mode, leave them out of the hand-off and report them.

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

In INTERACTIVE mode, present the full analysis before Phase 4:

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

**INTERACTIVE mode:** Wait for approval before Phase 4.
**AUTONOMOUS mode:** Continue to Phase 4 automatically.

---

## Output Variables Passed to Phase 4

| Variable | Contents |
|----------|----------|
| `NAMED_DOMAINS` | List of domains with name, tables, confidence, coverage status |
| `BRIDGE_TABLES` | Tables shared across domains |
| `ORPHAN_TABLES` | Tables with no domain affiliation |
| `DOMAIN_JOIN_KEYS` | Join keys per domain (resolved columns only) |
| `UNRESOLVED_PAIRS` | Related table pairs per domain that still need a join key |
| `COLUMN_IMPORTANCE` | Column tier rankings per table |
| `FULLY_COVERED_DOMAINS` | Domains already served by existing SVs |

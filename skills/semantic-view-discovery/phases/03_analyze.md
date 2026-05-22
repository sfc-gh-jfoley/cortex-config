---
name: sv-discovery-phase3-analyze
description: Build a unified relationship graph, cluster tables into semantic view domains, score domain quality, and identify orphan tables
---

# Phase 3: Analyze

## Purpose
Combine all evidence from Phase 2 into a unified relationship graph, then cluster tables into recommended semantic view domains. Each domain represents one candidate semantic view.

---

## Step 3A: Build unified relationship graph

Merge all relationship evidence into a single list of table pairs with combined confidence:

### Merge rules (applied per table pair)

For each unique `(table_a, table_b)` pair, combine evidence:

| FK Constraint | Column Match | Co-query Count | Final Confidence |
|:---:|:---:|:---:|:---:|
| Yes | — | — | HIGH |
| No | Yes | ≥ 50 | HIGH (boosted) |
| No | Yes | 10–49 | MEDIUM |
| No | Yes | < 10 | MEDIUM |
| No | No | ≥ 50 | HIGH |
| No | No | 10–49 | MEDIUM |
| No | No | < 10 | LOW |

### Format as relationship table

Present internal working state (not shown to user yet — that's Phase 4):

```
| Source Table | Target Table | Join Key | Evidence | Confidence |
|---|---|---|---|---|
| ORDERS | CUSTOMERS | CUSTOMER_ID | FK constraint + 234 co-queries | HIGH |
| ORDER_ITEMS | PRODUCTS | PRODUCT_ID | Column match + 189 co-queries | HIGH |
| ORDER_ITEMS | ORDERS | ORDER_ID | Column match + 189 co-queries | HIGH |
| SHIPMENTS | ORDERS | ORDER_ID | Column match + 12 co-queries | MEDIUM |
| RETURNS | ORDERS | ORDER_ID | Column match + 3 co-queries | MEDIUM |
| PROMOTIONS | PRODUCTS | PROMO_CODE | Co-query only, 67 co-queries | HIGH |
```

Store as `RELATIONSHIP_GRAPH`.

### Zero-evidence gate

If `RELATIONSHIP_GRAPH` contains zero relationships:

```
⚠️ No table relationships detected.

No FK constraints, no column name matches, and no query co-occurrence found 
for the <N> tables in scope.

This typically means:
- Tables use non-standard naming (no _ID/_KEY suffixes)
- Query history is too sparse (< 30 days or very few users)
- Tables are genuinely independent (each serves a different purpose)

Options:
  A) Broaden the time window (try 90 or 180 days instead of 30)
  B) Manual grouping — tell me which tables belong together and I'll validate
  C) Export the table list for offline review
  D) Proceed with single-table "domains" (each table = its own SV candidate)
```

**GATE: Wait for user selection before proceeding.**

If user picks D, create one domain per table (each table is its own candidate SV). Skip Steps 3B-3C scoring and go directly to 3D (orphan detection — likely all tables will be orphans in this case, so mark them as "standalone candidates" instead).

---

## Step 3B: Cluster tables into domains

### Clustering algorithm

1. **Seed selection**: Start with the table that has the most relationships (highest degree in the graph). This becomes the central entity of Domain 1.

2. **Expansion**: Add all tables directly connected to the seed with HIGH or MEDIUM confidence. This forms the initial cluster.

3. **Size check**:
   - If cluster has 3–8 tables → good domain size, finalize it
   - If cluster has 1–2 tables → mark as "small cluster" (may merge later)
   - If cluster exceeds 10 tables → look for natural split points (see below)

4. **Repeat**: Remove clustered tables from the graph. Select the next highest-degree unclustered table as the seed for Domain 2. Continue until all connected tables are assigned.

5. **Merge small clusters**: If a cluster has only 1–2 tables AND shares a relationship with another cluster, merge it into the nearest domain.

### Splitting oversized clusters (> 10 tables)

When a cluster exceeds 10 tables, apply these splitting heuristics:

1. **Fact/dimension split**: Identify the central fact table(s) — tables with the most FK columns pointing outward. Group each fact table with its directly-referenced dimensions as a separate domain.

2. **Schema boundary**: If tables in the cluster span multiple schemas, split along schema lines.

3. **Co-query community detection**: Within the cluster, find sub-groups of tables that are co-queried frequently with each other but rarely with the rest. These form natural sub-domains.

### Domain naming

Name each domain based on its central entity:
- If the seed table is `ORDERS`, the domain is "Orders"
- If the seed is `CUSTOMERS`, the domain is "Customers"  
- If the domain spans a clear business process (orders + items + shipments), name it after the process: "Order Fulfillment"

---

## Step 3C: Score each domain

For each domain cluster, calculate three quality metrics:

### Cohesion score

Average co-query count between all table pairs **within** the domain.

```
Domain "Orders" (4 tables: ORDERS, ORDER_ITEMS, CUSTOMERS, PRODUCTS)
  ORDERS ↔ ORDER_ITEMS:  189 co-queries
  ORDERS ↔ CUSTOMERS:    234 co-queries
  ORDERS ↔ PRODUCTS:       8 co-queries
  ORDER_ITEMS ↔ CUSTOMERS: 45 co-queries
  ORDER_ITEMS ↔ PRODUCTS: 156 co-queries
  CUSTOMERS ↔ PRODUCTS:    12 co-queries
  Average cohesion: 107.3
```

Higher is better — indicates the tables are genuinely used together.

### Isolation score

Ratio of internal co-queries to external co-queries.

```
Internal co-queries (within domain): 644 total
External co-queries (with tables in other domains): 89 total
Isolation: 644 / (644 + 89) = 87.8%
```

Higher is better — indicates the domain is self-contained. Below 50% suggests the domain boundaries may be wrong.

**Edge case:** If `HAS_ACCOUNT_USAGE = false` (or query history returned zero co-queries), both internal and external counts will be 0. In this case:
- Set isolation score to "N/A (no co-query data available)"
- Rely on relationship confidence (FK/column inference) for domain quality assessment
- Note in the summary: "Isolation scores unavailable — domain boundaries based on structural analysis only"

### Size assessment

Count total columns across all tables in the domain:

| Column Count | Assessment | Recommendation |
|:---:|---|---|
| < 20 | Compact | Good single SV |
| 20–60 | Standard | Good single SV |
| 60–100 | Large | Consider splitting facts from dimensions |
| > 100 | Oversized | Recommend splitting into 2+ SVs |

---

## Step 3D: Identify orphan tables

Tables not assigned to any domain after clustering:

Criteria for orphan status:
- Zero relationships found (no FK, no column match, no co-query evidence)
- Not queried with any other in-scope table in the last 30 days
- May be staging tables, backup tables, or unused legacy tables

List these separately — they likely do not need semantic view coverage.

For each orphan table, note:
- Table name
- Row count (from INFORMATION_SCHEMA.TABLES if available)
- Whether it has any column usage in ACCESS_HISTORY
- Likely reason: "staging table", "no relationships detected", "zero query activity"

---

## Step 3E: Identify cross-domain bridge tables

Some tables naturally appear in multiple domains (shared dimensions). Common examples:
- `CUSTOMERS` referenced by both "Orders" and "Support Cases" domains
- `PRODUCTS` referenced by both "Orders" and "Inventory" domains
- `EMPLOYEES` referenced by both "Sales" and "HR" domains

For each table that has relationships into 2+ domains:
```
Cross-domain bridge: CUSTOMERS
  → Referenced by: Orders domain (via ORDERS.CUSTOMER_ID)
  → Referenced by: Support domain (via SUPPORT_CASES.CUSTOMER_ID)
  → Recommendation: Include in BOTH semantic views as a shared dimension
```

Store as `BRIDGE_TABLES`.

---

## Step 3F: Analysis summary

Compile the full analysis results (internal state — presented to user in Phase 4):

```
Analysis complete:
  Domains identified:    <N>
  Tables assigned:       <N> of <TOTAL_TABLE_COUNT>
  Orphan tables:         <N>
  Cross-domain bridges:  <N>

Domain quality:
  HIGH confidence:   <N> domains (strong FK + co-query evidence)
  MEDIUM confidence: <N> domains (partial evidence)
  LOW confidence:    <N> domains (co-query only, weak signal)

Loading Phase 4 for recommendations...
```

---

## Output variables passed to next phases

| Variable | Contents |
|----------|----------|
| `DOMAINS` | List of `{name, tables[], central_entity, confidence, cohesion, isolation, column_count, size_assessment}` |
| `RELATIONSHIP_GRAPH` | Unified relationship list with merged confidence scores |
| `ORPHAN_TABLES` | List of `{table, row_count, reason}` |
| `BRIDGE_TABLES` | List of `{table, domains[], relationships[]}` |

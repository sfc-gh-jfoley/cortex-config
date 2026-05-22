---
name: semantic-view-discovery
description: Discover optimal semantic view domain groupings from a Snowflake account, or audit existing semantic views against actual query usage patterns. Uses ACCOUNT_USAGE + INFORMATION_SCHEMA only — no Snowhouse.
triggers:
  - semantic view discovery
  - discover semantic views
  - which tables should be in my semantic view
  - recommend SV groupings
  - audit semantic view
  - SV audit
  - semantic view coverage
  - find tables for semantic view
  - SV domain clusters
  - what tables are queried together
---

# Semantic View Discovery Skill

## When to use this skill

Use this skill when:
- You have a Snowflake account with hundreds of tables and need to know which should be in semantic views
- You want data-driven recommendations on how to group tables into SV domains
- You have an existing SV and want to know if it's missing tables, has unused columns, or lacks relationships
- You're starting a new Cortex AI project and need to identify the right tables before building SVs

**This skill does NOT create semantic views — it recommends what to build. Hand off to `semantic-view-ddl` for creation.**

---

## Two Modes

### Mode 1: Discover

**Input:** A database or schema name
**Output:** Recommended SV domain groupings with table lists, join keys, and confidence scores

```
User: "Help me discover what semantic views I should build for ANALYTICS_DB"
→ Discover mode activates
```

### Mode 2: Audit

**Input:** An existing semantic view FQN
**Output:** Improvement recommendations (missing tables, unused dims, relationship gaps)

```
User: "Audit my semantic view ANALYTICS_DB.PUBLIC.SALES_SV"
→ Audit mode activates
```

---

## Discover Mode Workflow

```
Phase 1: Connect & Scope       → user provides database/schema, confirm access
    ↓
Phase 2: Scan                   → FK/PK constraints + QUERY_HISTORY co-occurrence + column analysis
    ↓
Phase 3: Analyze                → cluster tables into domains, score groupings
    ↓
Phase 4: Recommend              → present findings, user adjusts boundaries
    ↓ [STOP: user approves groupings]
Phase 5: Handoff                → output table lists ready for semantic-view-ddl
```

**Stopping points:** Phases 1 and 4 have mandatory user approval gates.

### Phase Reference (Discover)

| Phase | File | Purpose |
|-------|------|---------|
| 1 | [phases/01_connect_scope.md](phases/01_connect_scope.md) | Confirm database, check access, set scope |
| 2 | [phases/02_scan.md](phases/02_scan.md) | FK/PK scan + query co-occurrence + column analysis |
| 3 | [phases/03_analyze.md](phases/03_analyze.md) | Cluster tables into domains, score confidence |
| 4 | [phases/04_recommend.md](phases/04_recommend.md) | Present recommendations, user approval gate |
| 5 | [phases/05_handoff.md](phases/05_handoff.md) | Format output for semantic-view-ddl |

---

## Audit Mode Workflow

```
Phase 10: Connect & Describe    → user provides SV FQN, DESCRIBE it
    ↓
Phase 11: Usage Scan            → query patterns against SV tables, column access frequency
    ↓
Phase 12: Recommend             → present improvement suggestions, user approval gate
```

**Stopping points:** Phases 10 and 12 have mandatory user approval gates.

### Phase Reference (Audit)

| Phase | File | Purpose |
|-------|------|---------|
| 10 | [phases/10_audit_connect.md](phases/10_audit_connect.md) | Get SV FQN, DESCRIBE, extract current structure |
| 11 | [phases/11_audit_scan.md](phases/11_audit_scan.md) | Scan usage patterns against SV tables |
| 12 | [phases/12_audit_recommend.md](phases/12_audit_recommend.md) | Present improvements, user approval |

---

## Data Sources

All queries run on the **customer's own account**. No Snowhouse access required.

| Source | What it provides | Latency |
|--------|-----------------|---------|
| `INFORMATION_SCHEMA.TABLE_CONSTRAINTS` | Declared PK/FK relationships | Real-time |
| `INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS` | FK references between tables | Real-time |
| `INFORMATION_SCHEMA.COLUMNS` | Column names for FK inference (_ID/_KEY matching) | Real-time |
| `SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY` | Table co-occurrence (which tables queried together) | Up to 45 min lag |
| `SNOWFLAKE.ACCOUNT_USAGE.ACCESS_HISTORY` | Column-level usage frequency | Up to 3 hr lag |
| `DESCRIBE SEMANTIC VIEW` | Existing SV structure (Audit mode) | Real-time |

---

## Confidence Scoring

Domain groupings are scored based on evidence strength:

| Score | Label | Evidence |
|-------|-------|----------|
| ≥ 50 co-queries | HIGH | Tables frequently joined/queried together |
| 10–49 co-queries | MEDIUM | Occasional co-usage |
| < 10 co-queries | LOW | Rare co-usage (FK-inferred only) |

FK/PK constraints always boost confidence by one tier (LOW→MEDIUM, MEDIUM→HIGH).

---

## Prerequisites

- Role with `IMPORTED PRIVILEGES` on `SNOWFLAKE` database (for ACCOUNT_USAGE)
- Or `ACCOUNTADMIN` role
- At least 30 days of QUERY_HISTORY for meaningful co-occurrence data

---

## Quick Start

**Discover mode:**
```
$semantic-view-discovery
"Help me discover semantic views for MY_DATABASE"
```

**Audit mode:**
```
$semantic-view-discovery
"Audit MY_DB.MY_SCHEMA.MY_SEMANTIC_VIEW"
```

---

## Handoff to semantic-view-ddl

Discover mode Phase 5 outputs a structured list per domain:

```
## Domain: Orders
Tables: ORDERS, ORDER_ITEMS, CUSTOMERS, PRODUCTS
Join Keys: ORDERS.CUSTOMER_ID → CUSTOMERS.CUSTOMER_ID, ORDER_ITEMS.ORDER_ID → ORDERS.ORDER_ID
Confidence: HIGH (127 co-queries)

→ Invoke semantic-view-ddl with these tables
```

This output is designed to paste directly into `semantic-view-ddl` Phase 1 as context.

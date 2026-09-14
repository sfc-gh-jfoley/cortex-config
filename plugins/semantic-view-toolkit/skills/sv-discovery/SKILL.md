---
name: sv-discovery
description: Discover optimal semantic view domain groupings from a Snowflake account. Uses ACCOUNT_USAGE structured JSON (ACCESS_HISTORY.base_objects_accessed) + INFORMATION_SCHEMA. Supports AUTONOMOUS/INTERACTIVE modes, all queryable object types, and existing-SV detection.
triggers:
  - semantic view discovery
  - discover semantic views
  - which tables should be in my semantic view
  - recommend SV groupings
  - find tables for semantic view
  - SV domain clusters
  - what tables are queried together
  - help me build semantic views
  - sv-discovery
---

# Semantic View Discovery Skill

## When to Use

Use this skill when:
- You have a Snowflake account with many tables and need to know which should be grouped into semantic views
- You want data-driven recommendations on how to cluster tables into SV domains
- You're starting a new Cortex AI project and need to identify the right tables before building SVs
- You want to check which tables are already covered by existing semantic views

**This skill does NOT create semantic views — it recommends what to build. Hand off to `sv-ddl` for creation.**

**For auditing an existing SV against usage patterns, use `sv-audit` instead.**

---

## Two Entry Modes

### Discover (default)

**Input:** A database or schema name
**Output:** Recommended SV domain groupings with table lists, join keys, and confidence scores

```
User: "Help me discover semantic views for MY_DATABASE"
→ Discover mode activates
```

### Audit (redirects)

```
User: "Audit my semantic view ANALYTICS_DB.PUBLIC.SALES_SV"
→ Redirect: "For auditing existing SVs, use the sv-audit skill instead."
```

---

## Interaction Modes: AUTONOMOUS vs INTERACTIVE

**Step Zero:** At the very start, ask the user which mode they prefer:

```
How would you like to run discovery?

A) AUTONOMOUS — minimal interaction, runs through phases automatically, presents final recommendations
B) INTERACTIVE — step-by-step with explanations and approval gates at each phase
```

Use `ask_user_question` for this.

| Mode | Behavior |
|------|----------|
| **AUTONOMOUS** | Runs all phases without stopping. Only pauses on errors, ambiguity, or LOW confidence domains. Presents final recommendations at the end. |
| **INTERACTIVE** | Pauses at each phase gate. Explains what's happening. Asks for approval before proceeding. |

---

## Discover Mode Workflow

```
Phase 1: Connect & Scope       → target DB, check access, detect existing SVs
    ↓
Phase 2: Scan                   → FK/PK + column inference + ACCESS_HISTORY co-occurrence + column usage
    ↓
Phase 3: Analyze                → cluster tables into domains, score groupings
    ↓
Phase 4: Recommend              → present findings, user adjusts boundaries
    ↓ [STOP: user approves groupings]
Phase 5: Handoff                → output table lists ready for sv-ddl
```

**Stopping points:**
- INTERACTIVE mode: Phases 1, 2 (summary), 4 have mandatory approval gates
- AUTONOMOUS mode: Only Phase 4 has a gate (and only for LOW confidence domains)

### Phase Reference

| Phase | File | Purpose |
|-------|------|---------|
| 1 | [phases/01_connect_scope.md](phases/01_connect_scope.md) | Confirm database, check access, detect existing SVs |
| 2 | [phases/02_scan.md](phases/02_scan.md) | FK/PK + column inference + ACCESS_HISTORY co-occurrence |
| 3 | [phases/03_analyze.md](phases/03_analyze.md) | Cluster tables into domains, score confidence |
| 4 | [phases/04_recommend.md](phases/04_recommend.md) | Present recommendations, user approval gate |
| 5 | [phases/05_handoff.md](phases/05_handoff.md) | Format output for sv-ddl |

---

## Data Sources

All queries run on the **customer's own account**. No Snowhouse access required.

| Source | What it provides | Latency |
|--------|-----------------|---------|
| `INFORMATION_SCHEMA.TABLE_CONSTRAINTS` | Declared PK/FK relationships | Real-time |
| `INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS` | FK references between tables | Real-time |
| `INFORMATION_SCHEMA.COLUMNS` | Column names for FK inference | Real-time |
| `INFORMATION_SCHEMA.TABLES` | Base tables, views, materialized views | Real-time |
| `INFORMATION_SCHEMA.DYNAMIC_TABLES` | Dynamic tables in scope | Real-time |
| `SNOWFLAKE.ACCOUNT_USAGE.ACCESS_HISTORY` | Table co-occurrence (structured JSON) + column usage | Up to 3 hr lag |
| `SHOW SEMANTIC VIEWS IN DATABASE` | Existing SVs for coverage detection | Real-time |

**Key change from v1:** We use `ACCESS_HISTORY.base_objects_accessed` (structured JSON with LATERAL FLATTEN) instead of parsing `QUERY_TEXT` from QUERY_HISTORY. This is more reliable and doesn't require regex.

---

## Confidence Scoring

See `../../references/confidence-scoring.md` for the full scoring model.

Summary:

| Tier | Score Range | Meaning |
|------|-------------|---------|
| **HIGH** | 0.85–1.00 | Strong evidence — include without user confirmation |
| **MEDIUM** | 0.60–0.84 | Moderate evidence — suggest for confirmation |
| **LOW** | 0.30–0.59 | Weak evidence — mention but don't auto-include |

---

## Queryable Object Types

This skill discovers ALL queryable object types, not just BASE TABLEs. See `../../references/queryable-objects.md` for detection patterns and design considerations.

| Type | Discovered | Notes |
|------|-----------|-------|
| Base Table | Yes | Primary source |
| View | Yes | May reference other databases |
| Dynamic Table | Yes | Include TARGET_LAG in domain context |
| External Table (Iceberg) | Yes | Performance considerations noted |
| Materialized View | Yes | Watch for double-aggregation |

---

## Prerequisites

- Role with `IMPORTED PRIVILEGES` on `SNOWFLAKE` database (for ACCESS_HISTORY)
- Or `ACCOUNTADMIN` role
- At least 30 days of query activity for meaningful co-occurrence data
- If ACCESS_HISTORY unavailable: skill still works with INFORMATION_SCHEMA only (reduced accuracy)

---

## Quick Start

```
$sv-discovery
"Help me discover semantic views for ANALYTICS_DB"
```

```
$sv-discovery
"What tables in PROD_DW.SALES should go together in a semantic view?"
```

---

## Handoff to sv-ddl

Phase 5 outputs a structured list per domain:

```
## Domain: Orders
Tables: ORDERS, ORDER_ITEMS, CUSTOMERS, PRODUCTS
Source Types: base table, base table, base table, dynamic table
Join Keys: ORDERS.CUSTOMER_ID → CUSTOMERS.CUSTOMER_ID, ORDER_ITEMS.ORDER_ID → ORDERS.ORDER_ID
Confidence: HIGH (127 co-queries)
Existing SV Coverage: None (these tables are not in any existing SV)

→ Invoke sv-ddl with these tables
```

---

## Next Steps After Discovery

1. **sv-ddl** — Build DDL for the recommended SV groupings; multiple business domains may share one SV (see Phase 3B).
2. **sv-evaluation** — Evaluate the new SV's quality with VQRs
3. **sv-gepa-optimizer** — Optimize the SV if evaluation scores are low

### Size guardrail — keep each SV under ~100,000 tokens

There is no table-count target. Use **~100,000 tokens** as a context-size guideline, not an automatic split rule or a guarantee of accuracy. Prefer the fewest SVs that correctly support the workload; check common cross-boundary questions and relationship/grain compatibility before splitting (Phase 3B).

When you present domain groupings in Phase 4, **estimate the token size** of each proposed SV. SV DDL tokenizes at roughly 2–3 characters per token (SQL keywords, quoted identifiers, and structural delimiters are denser than prose — not the standard ~4 chars/token rule of thumb). Use **~2.5 characters per token** as the heuristic for serialized DDL including all table/column/metric/relationship descriptions and VQR SQL. If a proposed grouping exceeds ~100K tokens:
- Consider trimming unnecessary metadata or splitting along workload boundaries; account for repeated dimensions and descriptions in split SVs.
- Record a brief reason and cross-boundary query caveat for any split. Label size estimates and untested performance benefits as assumptions.

For SVs that must be large (densely connected single-domain), flag the pruning risk in the handoff so the author knows to keep descriptions concise and columns business-relevant.

---

## State Persistence

After discovery completes, Phase 5 will ask where to persist results before creating any objects:

```
Where should I create it?
  A) <DISCOVERY_DB>._SV_TOOLKIT_META  (default)
  B) A different database/schema
  C) Skip
```

This applies in both AUTONOMOUS and INTERACTIVE modes. No schema or table is created until the user confirms a target location.

Once confirmed, Phase 5 creates:

```sql
CREATE SCHEMA IF NOT EXISTS <TARGET_SCHEMA>;
CREATE TABLE IF NOT EXISTS <TARGET_SCHEMA>.DISCOVERY_STATE (
    discovery_id VARCHAR DEFAULT UUID_STRING(),
    discovery_timestamp TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    database_name VARCHAR,
    schemas_analyzed VARIANT,
    domains VARIANT,
    relationship_graph VARIANT,
    orphan_tables VARIANT,
    bridge_tables VARIANT,
    mode VARCHAR,
    existing_svs VARIANT,
    column_importance VARIANT,
    adjustment_log VARIANT,
    PRIMARY KEY (discovery_id)
);
```

This enables:
- Resuming an interrupted discovery
- Comparing discoveries over time (schema evolution)
- Feeding domain context to other toolkit skills

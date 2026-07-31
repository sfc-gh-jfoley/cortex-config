---
name: sv-discovery
description: Discover optimal semantic view domain groupings from a Snowflake account. Uses ACCOUNT_USAGE structured JSON (ACCESS_HISTORY.base_objects_accessed) + INFORMATION_SCHEMA. Supports AUTOPILOT/GUIDED modes, all queryable object types, and existing-SV detection.
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

## Interaction Modes: AUTOPILOT vs GUIDED

**Step Zero:** At the very start, ask the user which mode they prefer:

```
How would you like to run discovery?

A) AUTOPILOT — minimal interaction, runs through phases automatically, presents final recommendations
B) GUIDED — step-by-step with explanations and approval gates at each phase
```

Use `ask_user_question` for this.

| Mode | Behavior |
|------|----------|
| **AUTOPILOT** | Runs all phases without stopping. Only pauses on errors, ambiguity, or LOW confidence domains. Presents final recommendations at the end. |
| **GUIDED** | Pauses at each phase gate. Explains what's happening. Asks for approval before proceeding. |

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
- GUIDED mode: Phases 1, 2 (summary), 4 have mandatory approval gates
- AUTOPILOT mode: Only Phase 4 has a gate (and only for LOW confidence domains)

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

See `references/confidence-scoring.md` for the full scoring model.

Summary:

| Tier | Score Range | Meaning |
|------|-------------|---------|
| **HIGH** | 0.85–1.00 | Strong evidence — include without user confirmation |
| **MEDIUM** | 0.60–0.84 | Moderate evidence — suggest for confirmation |
| **LOW** | 0.30–0.59 | Weak evidence — mention but don't auto-include |

---

## Queryable Object Types

This skill discovers ALL queryable object types, not just BASE TABLEs. See `references/queryable-objects.md` for detection patterns and design considerations.

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

1. **sv-ddl** — Build the semantic view DDL for each recommended domain
2. **sv-evaluation** — Evaluate the new SV's quality with VQRs
3. **sv-gepa-optimizer** — Optimize the SV if evaluation scores are low

### Size guardrail — keep each SV under ~100,000 tokens

There's no hard limit on semantic view size, but as an SV grows past roughly 100,000 tokens, the combined size of the SV, agent instructions, and conversation history approaches the LLM's context window. At that point Cortex Agents may need to **prune** the SV to fit — which adds latency and reduces answer quality. Treat ~100K tokens as a guideline, not a fixed threshold.

When you present domain groupings in Phase 4, **estimate the token size** of each proposed SV (a rough heuristic: ~1 token per ~4 characters of serialized DDL, including all table/column/metric/relationship descriptions and VQR SQL). If a proposed grouping exceeds ~100K tokens:
- Recommend splitting it into multiple SVs along sub-domain boundaries (Cortex Agents selects the relevant SV per question).
- Surface the split recommendation in the confidence-score notes for that domain.
- Prefer fewer, focused SVs over one large SV — the official Snowflake guidance is "fewer generally perform better," and customers running 50+ SVs is the ceiling, not the target.

For SVs that must be large (densely connected single-domain), flag the pruning risk in the handoff so the author knows to keep descriptions concise and columns business-relevant.

---

## State Persistence

After discovery completes, offer to persist the relationship graph and domain groupings:

> **DDL/DML safety gate**: Per account mutation policy, before creating `_SV_TOOLKIT_META`
> objects ask the user: "Want me to create a rollback clone first so we can undo this?
> (`CREATE DATABASE <db>_RESTORE CLONE <db>`)"
> If yes, create the clone before proceeding.

```sql
CREATE SCHEMA IF NOT EXISTS <DB>._SV_TOOLKIT_META;
CREATE TABLE IF NOT EXISTS <DB>._SV_TOOLKIT_META.DISCOVERY_STATE (
    discovery_id VARCHAR DEFAULT UUID_STRING(),
    discovery_timestamp TIMESTAMP_NTZ DEFAULT CURRENT_TIMESTAMP(),
    database_name VARCHAR,
    schemas_analyzed VARIANT,
    domains VARIANT,
    relationship_graph VARIANT,
    orphan_tables VARIANT,
    bridge_tables VARIANT,
    mode VARCHAR,
    existing_svs VARIANT
);
```

This enables:
- Resuming an interrupted discovery
- Comparing discoveries over time (schema evolution)
- Feeding domain context to other toolkit skills

---
name: sv-audit
description: >
  Audit an existing semantic view against actual query usage patterns.
  Identifies missing tables, unused columns, relationship gaps, and metric opportunities.
  Uses ACCOUNT_USAGE views for evidence-based recommendations.
triggers:
  - audit semantic view
  - SV audit
  - what's missing in my SV
  - unused columns
  - relationship gaps
  - semantic view coverage
  - audit my SV
  - improve existing SV
---

# SV Audit Skill

## When to Use

Use this skill when you have an existing semantic view and want to know:
- Are there tables frequently joined with SV tables that should be included?
- Are there columns defined in the SV that nobody uses?
- Are there JOIN patterns in user queries with no matching RELATIONSHIP in the SV?
- Are there common aggregation patterns that should be defined as METRICS?
- What's the overall column coverage (SV columns vs total source columns)?

**This skill analyzes but does not modify.** It produces a prioritized recommendation report. Apply changes via sv-ddl or sv-optimization.

---

## Workflow

```
Phase 10: Connect & Describe    → user provides SV FQN, DESCRIBE it, measure coverage
    ↓
Phase 11: Usage Scan            → query patterns, column access, missing table detection
    ↓
Phase 12: Recommend             → prioritized findings, user approval gate
```

**Stopping points:** Phases 10 and 12 have mandatory user approval gates.

---

## Phase Reference

| Phase | File | Purpose |
|-------|------|---------|
| 10 | [phases/10_audit_connect.md](phases/10_audit_connect.md) | Get SV FQN, DESCRIBE, extract structure, measure coverage |
| 11 | [phases/11_audit_scan.md](phases/11_audit_scan.md) | Scan usage patterns against SV tables |
| 12 | [phases/12_audit_recommend.md](phases/12_audit_recommend.md) | Present improvements, priority ranking, user approval |

---

## Data Sources

| Source | What it provides | Latency |
|--------|-----------------|---------|
| `DESCRIBE SEMANTIC VIEW` | Current SV structure | Real-time |
| `SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY` | Query patterns referencing SV tables | Up to 45 min |
| `SNOWFLAKE.ACCOUNT_USAGE.ACCESS_HISTORY` | Column-level usage frequency | Up to 3 hr |
| `INFORMATION_SCHEMA.COLUMNS` | Full column set of underlying tables | Real-time |
| `INFORMATION_SCHEMA.TABLES` | Neighboring tables in same schema | Real-time |

---

## Priority Ranking

Findings are ranked by impact:

| Priority | Category | Impact |
|----------|----------|--------|
| 0 | **Join Type Mismatches** (CRITICAL) | **BLOCKING** — type-mismatched relationship join columns cause every query on that path to fail at runtime; passes SV creation silently |
| 1 | Relationship Gaps | HIGH — without relationships, Analyst can't auto-join |
| 2 | Missing Tables (ADD-classified) | HIGH — frequently joined but invisible to SV |
| 3 | Missing Columns (high access) | MEDIUM — common patterns not served |
| 4 | Metric Opportunities | MEDIUM — pre-defining common aggregations |
| 5 | Unused Columns | LOW — cleanup, reduces complexity |

---

## Prerequisites

- Role with `IMPORTED PRIVILEGES` on `SNOWFLAKE` database (for ACCOUNT_USAGE)
- `SELECT` on the semantic view
- At least 30 days of query history for meaningful results
- Enterprise Edition for ACCESS_HISTORY (optional — falls back to QUERY_HISTORY)

---

## Quick Start

```
$semantic-view-toolkit
"Audit my semantic view: ANALYTICS_DB.PUBLIC.REVENUE_SV"
```

---

## Output Actions

After the audit report, users can:

| Choice | Action |
|--------|--------|
| Apply all recommendations | → Route to sv-ddl with modification instructions |
| Apply selected items | → Route to sv-ddl with filtered instructions |
| Export report only | → Save markdown report for offline review |
| Run evaluation | → Route to sv-evaluation to measure current accuracy |
| Cancel | → End audit, no changes |

---

## Integration with Toolkit

- **Feeds into sv-ddl**: Audit findings become modification instructions for sv-ddl
- **Feeds into sv-evaluation**: After audit, suggest running eval for baseline
- **Fed by sv-watch**: Watch alerts can trigger targeted audits
- **Feeds into sv-optimization**: Audit findings inform which mutation operators to prioritize

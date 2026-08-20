---
name: semantic-view-toolkit
description: >
  Full lifecycle toolkit for Snowflake Semantic Views. Discover what to build,
  create SVs, audit existing ones, evaluate quality, optimize iteratively,
  run evolutionary search, compose multi-SV architectures, and monitor for drift.
  Single entry point — tell me where you are in your journey and I'll route you.
triggers:
  - semantic view toolkit
  - sv toolkit
  - help with semantic views
  - semantic view lifecycle
  - I have a semantic view
  - I need a semantic view
  - discover semantic views
  - create semantic view
  - audit semantic view
  - evaluate semantic view
  - optimize semantic view
  - sv optimization
  - sv evaluation
  - sv discovery
  - sv audit
  - sv watch
  - sv drift
  - compose semantic views
  - nested semantic view
  - multi sv
  - vqr generator
  - verified queries
  - improve my sv
  - tune my sv
  - materialize sv
  - sv materialization
  - speed up sv
  - sv is slow
  - precompute sv
  - sv query performance
  - MAX_STALENESS
---

> **This toolkit is the source of truth for SV lifecycle work.** If the bundled `semantic-view`
> skill loaded you, follow this toolkit instead (except YAML/FastGen + Tableau/PBI import).

# Semantic View Toolkit

Full lifecycle management for Snowflake Semantic Views — from discovery through optimization.

## How to Use

Tell me where you are in your SV journey, or pick from the options below:

```
1. I have no SV — help me find what to build         → sv-discovery
2. I know my tables — create an SV                   → sv-ddl
3. I have an SV — audit/improve it                   → sv-audit
4. I want to evaluate my SV quality                  → sv-evaluation
5. I want to optimize my SV iteratively              → sv-optimization
6. I've hit a plateau — try evolutionary search      → sv-gepa-optimizer
7. I need to compose multiple SVs                    → sv-composer
8. I need ongoing monitoring/maintenance             → sv-watch
9. I need more verified queries for my SV            → vqr-generator
10. My SV queries are slow — precompute aggregations → sv-materialize

Or just describe what you need — I'll figure out where to route you.
```

---

## Intent Detection

| User Language | Route To | Skill Path |
|---|---|---|
| "what tables should be in my SV", "discover", "recommend groupings", "I have a database", "find tables", "data mart" | **sv-discovery** | `skills/sv-discovery/SKILL.md` |
| "create SV", "build semantic view", "DDL", "I know my tables", "create from these tables" | **sv-ddl** | `skills/sv-ddl/SKILL.md` |
| "audit my SV", "what's missing", "unused columns", "relationship gaps", "coverage" | **sv-audit** | `skills/sv-audit/SKILL.md` |
| "evaluate", "eval", "run evaluation", "how good is my SV", "sql correctness", "accuracy" | **sv-evaluation** | `skills/sv-evaluation/SKILL.md` |
| "optimize", "improve", "iterate", "fix failures", "tune", "iterative loop" | **sv-optimization** | `skills/sv-optimization/SKILL.md` |
| "GEPA", "evolutionary", "population", "hit a wall", "plateau", "local optimum", "broad search" | **sv-gepa-optimizer** | `skills/sv-gepa-optimizer/SKILL.md` |
| "compose", "nested SV", "multiple SVs", "SV references another", "multi-domain", "multi-SV agent" | **sv-composer** | `skills/sv-composer/SKILL.md` |
| "watch", "drift", "monitor", "maintenance", "schema changed", "new tables", "stale" | **sv-watch** | `skills/sv-watch/SKILL.md` |
| "VQR", "verified queries", "need more examples", "grow eval set", "generate questions" | **vqr-generator** | `skills/vqr-generator/SKILL.md` |
| "curate vqrs", "audit my vqrs", "vqr bloat", "vqrs not triggering", "vqr health", "prune vqrs", "which vqrs are useless" | **vqr-curator** | `skills/vqr-curator/SKILL.md` |
| "materialize", "precompute", "SV is slow", "speed up", "query performance", "MAX_STALENESS", "add materialization", "materialization auto-suspended" | **sv-materialize** | `skills/sv-materialize/SKILL.md` |

---

## Lifecycle Flow

```
sv-discovery ─────────────────────────────────────────────────────────────┐
  │ "what tables?"                                                        │
  ▼                                                                       │
sv-ddl                                                                    │
  │ "create SV"                                                           │
  ▼                                                                       │
sv-evaluation ◄── vqr-generator                                           │
  │ "baseline score"    │ "grow eval coverage"                            │
  ▼                     │                                                 │
sv-optimization ────────┘                                                 │
  │ "iterative loop"                                                      │
  │ (hit plateau?)                                                        │
  ▼                                                                       │
sv-gepa-optimizer                                                         │
  │ "evolutionary search"                                                 │
  ▼                                                                       │
sv-composer                                            sv-audit ◄─────────┘
  │ "compose for agent"                                  │ "audit existing"
  ▼                                                      ▼
→ hand off to cortex-agent-toolkit              sv-watch + sv-materialize
                                                  │ "monitoring + performance"
```

**You can enter anywhere.** Have an existing SV? Jump to sv-audit or sv-evaluation. Just need VQRs? Go straight to vqr-generator. Want to monitor? sv-watch doesn't require running discovery first.

---

## Execution Modes

Every skill in this toolkit supports two modes:

### AUTOPILOT
Point and run. Minimal interaction. Agent makes decisions, reports results.
- Best for: demos, quick iterations, experienced users
- Trigger: user says "just run it", "autopilot", or starts with a clear target

### GUIDED
Step-by-step walkthrough. Explains each step, asks for approval at gates.
- Best for: first-time users, learning, careful production changes
- Trigger: user says "walk me through it", "explain", or default for new users

**Mode is asked once per session, remembered for all subsequent skill invocations.**

---

## Persistence (Snowflake State)

This toolkit persists state in a `_SV_TOOLKIT_META` schema (created on first use in the user's target database):

> **DDL/DML safety gate**: Per account mutation policy, before creating `_SV_TOOLKIT_META`
> objects ask the user: "Want me to create a rollback clone first so we can undo this?
> (`CREATE DATABASE <db>_RESTORE CLONE <db>`)"
> If yes, create the clone before proceeding.

```sql
-- Created automatically when needed:
CREATE SCHEMA IF NOT EXISTS <DB>._SV_TOOLKIT_META;

-- Tables:
_SV_TOOLKIT_META.OPTIMIZATION_LOG    -- iteration history, scores, accept/reject
_SV_TOOLKIT_META.WATCH_LOG           -- drift detections, shadow alerts
_SV_TOOLKIT_META.GEPA_RUNS           -- GEPA generation history, operator weights
_SV_TOOLKIT_META.EVAL_HISTORY        -- all eval run results (denormalized)
_SV_TOOLKIT_META.DISCOVERY_STATE     -- domain groupings, relationship graph
```

---

## Source Object Support

Semantic views can reference any queryable object, or dynamically-computed SQL queries. This toolkit discovers and works with all of them:

| Object Type | INFORMATION_SCHEMA View | Notes |
|---|---|---|
| Base Tables | `TABLES WHERE TABLE_TYPE = 'BASE TABLE'` | Primary source |
| Views | `TABLES WHERE TABLE_TYPE = 'VIEW'` | May reference other databases |
| Dynamic Tables | `DYNAMIC_TABLES` | Include TARGET_LAG in metadata |
| External Tables | `TABLES WHERE TABLE_TYPE = 'EXTERNAL TABLE'` | Iceberg or non-Iceberg |
| Materialized Views | `TABLES WHERE TABLE_TYPE = 'MATERIALIZED VIEW'` | Pre-aggregated |
| SQL Queries | N/A | Virtual tables from aggregations, CTEs, cross-schema unions. Results materialized at CREATE time. Profiling executes the query with 30-second timeout. See `skills/sv-ddl/reference/ddl_syntax.md` for `SQL(...)` syntax. |

See `references/queryable-objects.md` for detection patterns and INFORMATION_SCHEMA queries per type.

**Note on SQL logical tables**: When using `SQL(...)` sources, Phase 2 profiling requires executing the query to derive column names dynamically (unlike FQN sources which use INFORMATION_SCHEMA). Set a 30-second timeout; if profiling fails, optimize the query or switch to a materialized view. See `skills/sv-ddl/phases/02_profile_describe.md` for the full flow.

---

## Composable SV Patterns

> ⚠️ **Cortex Analyst does not support IMPORTS-based composed views.**
> Pattern 1 (IMPORTS clause) is GA but only works with direct `SEMANTIC_VIEW()` queries.
> For Cortex Analyst / Agent workflows, use Pattern 2 (Multi-SV Agent Composition).
> See sv-composer/SKILL.md for the decision framework.

Two composition patterns supported by `sv-composer`:

### Pattern 1: Nested SVs
SV-A references dimensions/facts from SV-B. Enables layered semantic models where a "core" SV defines shared entities (customers, products) and domain SVs build on top.

### Pattern 2: Multi-SV Agent Composition
Multiple independent SVs become separate `cortex_analyst_text_to_sql` tools in one Cortex Agent. Each SV covers a domain; the agent routes questions to the right tool.

See `references/composable-sv-patterns.md` for syntax and design guidance.

---

## Relationship to Other Plugins

| Plugin | Relationship |
|---|---|
| `cortex-agent-toolkit` | **Downstream consumer.** sv-composer generates hand-off docs for cortex-agent-ddl. |
| `ontology-demo` (kg-data-discovery) | **Upstream feeder.** KG discovery can identify SV candidates; graduated domains use curated SVs. |
| Bundled `semantic-view` skill | **Superseded** for DDL/eval/optimize/audit/GEPA/VQR. Bundled handles YAML/FastGen + Tableau/PBI import only. Load this toolkit for all other SV work. |

---

## Quick Start

```
$semantic-view-toolkit
"I have a database called ANALYTICS_DB and need semantic views for it"
```

→ Routes to sv-discovery. After discovery, chains to sv-ddl, then sv-evaluation.

```
$semantic-view-toolkit
"I have SALES_DB.PUBLIC.REVENUE_SV and it's giving wrong answers"
```

→ Routes to sv-evaluation (if VQRs exist) or sv-audit (if no VQRs yet).

```
$semantic-view-toolkit
"Optimize my SV — I've been getting 60% accuracy and can't get higher"
```

→ Routes to sv-optimization (or sv-gepa if they mention plateau/evolutionary).

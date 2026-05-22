# semantic-view-ddl

A Cortex Code plugin for building, validating, and maintaining Snowflake Semantic Views using pure SQL DDL. Includes AI-generated column descriptions, 23-point self-checks, iterative validation, and drift monitoring.

## Install

```bash
cortex plugin install sfc-gh-jfoley/semantic-view-ddl
```

## Two Workflows

### Build a New Semantic View

Start from tables and end with a deployed, validated semantic view:

```
"Create a semantic view for MY_DB.PUBLIC.ORDERS and MY_DB.PUBLIC.CUSTOMERS"
```

The skill walks you through 6 phases: context gathering → table profiling → column classification → relationship detection → DDL generation (with 23 self-checks) → execution and validation with test questions.

### Improve an Existing Semantic View

Already have a semantic view that needs work? This is the primary use case for many teams:

```
"Add verified queries to my semantic view MY_DB.PUBLIC.ORDERS_SV"
"Check drift on MY_DB.PUBLIC.ORDERS_SV"
"Audit my semantic view MY_DB.PUBLIC.ORDERS_SV for quality issues"
```

The skill can:
- **Add verified queries** (Phase 7) — curated Q&A pairs that improve Cortex Analyst accuracy and appear as starter questions in Snowflake Intelligence
- **Tune descriptions and synonyms** (Phase 7) — fix vague or missing column descriptions that cause bad SQL generation
- **Detect drift** (Phase 8) — find missing tables/columns, schema changes, and enrichment gaps
- **Re-audit classifications** (Phase 3-5) — re-run the 23-point quality check on an existing semantic view to find issues

## When to Use This vs. the Bundled `semantic-view` Skill

| Goal | Use |
|---|---|
| Pure SQL DDL path (HOL-friendly, no YAML, no FastGen) | **This plugin** |
| AI-generated descriptions for undocumented tables | **This plugin** |
| Iterative self-check loop before deploying | **This plugin** |
| Drift monitoring and scheduled maintenance | **This plugin** |
| YAML/FastGen path | Bundled `semantic-view` skill |
| Tableau or Power BI import (.twb/.pbix) | Bundled `semantic-view` skill |
| VQR suggestions from query history | Bundled `semantic-view` skill |

## Prerequisites

- **Snowflake account** with a role that has:
  - `CREATE SEMANTIC VIEW` privilege on the target schema
  - `SELECT` on the source tables you want to model
  - `USAGE` on database, schema, and a warehouse
- **Tables or views** to model (the skill profiles them to generate descriptions)
- **Cortex Code CLI** installed

No Python, no `uv`, no local filesystem required — the entire workflow runs as SQL in your Snowflake account.

## Phase Overview

| Phase | Purpose | Entry point for existing SVs? |
|---|---|---|
| 1. Context Gathering | Identify target tables and business domain | — |
| 2. Profile & Describe | DESCRIBE TABLE + AI-generated descriptions | — |
| 3. Classify Columns | Facts vs dimensions vs metrics | Yes (re-audit) |
| 4. Relationship Detection | FK inference, ASOF joins, range joins | — |
| 5. Generate DDL | CREATE SEMANTIC VIEW with 23 self-checks | Yes (quality audit) |
| 6. Execute & Validate | Deploy, test with Cortex Analyst, iterate | — |
| 7. Iterate & Enrich | Verified queries, synonyms, description polish | **Yes (primary)** |
| 8. Drift Monitor | Schema drift, missing dimensions, query gaps | **Yes (primary)** |

See [CUSTOMER_GUIDE.md](./CUSTOMER_GUIDE.md) for the full phase-by-phase walkthrough.

## What's New in v1.1

- **FILTER label deployment guard** (Phase 5 Step 5.0.5) — probes account for `LABELS = (FILTER)` support before emitting. Falls back to plain boolean expressions on accounts that haven't received the May 2026 release.
- **M:N bridge table detection** (Phase 4 Step 4.2.5) — detects many-to-many relationships, offers to identify existing bridge tables or suggests CREATE TABLE DDL for a new one.
- **No-relationship clarity gate** (Phase 4 Step 4.9) — when auto-detection finds zero relationships across multiple tables, asks targeted questions instead of silently proceeding.
- **Relaxed strictness** — only FQN table names are hard FAIL. PK, SYNONYMS, and COMMENT are WARNs that don't block deployment.
- **Fan trap fix suggestions** — offers concrete DDL alternatives (move metric to bridge table or pre-aggregate) instead of just flagging the problem.
- **Verified query `__table` prefix documentation** — explains the engine's automatic column reference transformation so users aren't surprised.
- **Self-check expanded to 23 checks** (18 syntax + 5 semantic correctness) up from 18.

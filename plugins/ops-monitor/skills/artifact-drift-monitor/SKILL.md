---
name: artifact-drift-monitor
description: >
  Scan ACCOUNT_USAGE query history and object definitions to detect drift between
  deployed Snowflake artifacts and actual usage patterns. Supports semantic views,
  Cortex Agents, Cortex Search, and Dynamic Tables. Produces a prioritized enhancement
  manifest with ADD/SKIP recommendations and rationale, then generates remediation DDL
  only for user-approved items.
version: "1.1"
author: jfoley
markers:
  - .my_skill
---

# Artifact Drift Monitor

## Purpose

Deployed Snowflake AI artifacts drift from reality over time:
- **Semantic Views** — tables are added, columns grow, users bypass the SV with direct SQL
- **Dynamic Tables** — source schemas evolve (new columns, type changes), the DT definition lags behind
- **Cortex Agents** — users ask questions the agent wasn't built for; tool selection fails on new query patterns
- **Cortex Search** — indexed columns no longer reflect what users filter on

This skill queries `ACCOUNT_USAGE` and `INFORMATION_SCHEMA` to surface those gaps as a prioritized manifest with ADD/SKIP recommendations and supporting rationale. The user approves or rejects each suggestion before any DDL is generated.

---

## Trigger phrases

- check SV drift
- enhance semantic view
- what queries am I missing in my semantic view
- scan query history for SV gaps
- semantic view enhancement
- check dynamic table schema drift
- dynamic table source drift
- auto-schema detection
- new columns in source table
- DT behind source schema
- cortex agent drift
- agent query gaps
- cortex search drift
- artifact drift
- check drift

---

## Artifact types

| Artifact | Primary signal | Key gap types |
|----------|---------------|---------------|
| Semantic View | `QUERY_HISTORY` for source tables | Missing tables, missing columns, dimension enrichment, bypass |
| Dynamic Table | `INFORMATION_SCHEMA.COLUMNS` diff | New source columns, type changes, dropped columns |
| Cortex Agent | `AI_OBSERVABILITY_EVENTS` | Unanswered intents, tool routing failures, unseen query patterns |
| Cortex Search | `QUERY_HISTORY` search queries | Missing filter columns, stale indexed fields |

---

## Phases

| Phase | File | What it does |
|-------|------|-------------|
| 1 | phases/01_detect_artifact.md | Identify artifact type, confirm lookback window |
| 2 | phases/02_sv_drift.md | SV query-history drift + ADD/SKIP reasoning per gap |
| 3 | phases/03_dt_schema_drift.md | DT source-schema drift + column scoring |
| 4 | phases/04_agent_drift.md | Cortex Agent intent and tool-routing drift |
| 5 | phases/05_search_drift.md | Cortex Search index gap analysis |
| 6 | phases/06_manifest_remediate.md | Approval gate → DDL only for approved items |

---

## Execution flow

1. Phase 1 — detect artifact type, confirm lookback window
2. Run matching drift phase (2–5)
3. Phase 6 — unified manifest with reasoning → **approval gate** → DDL for approved items only

For "check all drift" requests, run phases 2–5 in sequence before Phase 6.

---

## Output variables

| Variable | Contents |
|----------|---------|
| `ARTIFACT_TYPE` | sv / dynamic_table / cortex_agent / cortex_search |
| `ARTIFACT_NAME` | Fully qualified name |
| `LOOKBACK_DAYS` | Analysis window confirmed with user |
| `GAP_SUGGESTIONS` | All gaps with ADD/SKIP recommendation + rationale |
| `APPROVED_CHANGES` | User-approved subset of GAP_SUGGESTIONS |
| `SCHEMA_DRIFT` | DT-specific: new/changed/dropped columns |
| `BYPASS_SIGNALS` | Users/queries bypassing the artifact |
| `ENHANCEMENT_DDL` | Ready-to-apply DDL generated for APPROVED_CHANGES only |

---

## Related Skills

| Skill | When to use instead |
|-------|-------------------|
| `release-change-monitor` | Proactive monitoring of Snowflake BCR behavior-change bundles for pipeline break risk |
| `self-healing-pipeline` | Automated remediation of pipeline failures without a manual approval gate |
| `dynamic-tables` | Dynamic Table creation, refresh optimization, and pipeline health diagnostics |

---
name: sv-ddl
description: >
  Create or edit Snowflake Semantic Views using native DDL syntax with AI-generated
  descriptions, iterative self-check, and verified query generation. Supports all
  queryable object types (tables, views, DTs, external tables, Iceberg, MVs).
triggers:
  - create semantic view DDL
  - sv ddl
  - create SV
  - build semantic view
  - I know my tables
  - create from these tables
  - HOL semantic view
  - auto describe semantic view
  - check SV drift
  - semantic view drift
  - schedule SV maintenance
  - SV health check
---

# SV DDL Skill

## When to Use

Use this skill when:
- You have a known set of tables/views/DTs and want to create a semantic view
- FastGen/Snowsight wizard produced poor results and you want pure SQL DDL control
- You're building a HOL or workshop setup script (pure SQL, no filesystem)
- You need descriptions generated automatically for undocumented objects
- You want an iterative self-check loop before deploying
- You received handoff output from sv-discovery

**This skill creates semantic views using `CREATE OR REPLACE SEMANTIC VIEW` DDL syntax only — no YAML, no FastGen.**

---

## Source Object Support

This skill handles ALL queryable objects as SV sources:

| Object Type | Detection | Notes |
|---|---|---|
| Base Tables | `TABLE_TYPE = 'BASE TABLE'` | Primary source type |
| Views | `TABLE_TYPE = 'VIEW'` | May reference other databases |
| Dynamic Tables | `INFORMATION_SCHEMA.DYNAMIC_TABLES` | Note TARGET_LAG in metadata |
| External Tables | `TABLE_TYPE = 'EXTERNAL TABLE'` | Iceberg or non-Iceberg |
| Materialized Views | `TABLE_TYPE = 'MATERIALIZED VIEW'` | Pre-aggregated |

See `references/queryable-objects.md` for full details.

---

## Workflow Overview

```
Phase 1: Context Gathering          → tables, business intent, optional docs
    ↓
Phase 2: Profile & Auto-Describe    → CORTEX.COMPLETE generates descriptions per column
    ↓
Phase 3: Classify Columns           → FACT / DIMENSION / TIME_DIMENSION / METRIC / SKIP
    ↓
Phase 4: Relationship Detection     → FK pattern matching + cardinality validation
    ↓
Phase 5: Generate DDL               → BUILD + self-check (23 checks verified)
    ↓ [STOP: user approves DDL]
Phase 6: Execute & Validate         → run DDL → DESCRIBE → self-test question loop
    ↓
    ├── FAIL → back to Phase 5 with specific fixes
    └── PASS → Phase 7
Phase 7: Iterate & Enrich           → AI_VERIFIED_QUERIES + description polish + export
    ↓
Phase 8: Drift Monitor (optional)   → scheduled weekly/monthly health check
```

**Stopping points**: Phases 1, 2, 5, 6, 7 each have a mandatory user approval gate.

**Size guardrail (~100K tokens):** In Phase 5, after generating the DDL, estimate the serialized SV size (~1 token per ~4 chars of DDL including all descriptions, metrics, and VQR SQL). If the SV exceeds ~100,000 tokens, warn the author: Cortex Agents may prune the SV to fit the context window, adding latency and reducing answer quality. Recommend splitting along sub-domain boundaries into multiple SVs (Cortex Agents selects the relevant one per question) or trimming non-business-relevant columns. See `sv-discovery` for the split guidance. This is a guideline, not a hard limit.

---

## Quick Start

To begin, load Phase 1:

**→ Load [phases/01_context.md](phases/01_context.md)**

---

## Phase Reference

| Phase | File | Purpose |
|-------|------|---------|
| 1 | [phases/01_context.md](phases/01_context.md) | Collect tables, business context, optional docs |
| 2 | [phases/02_profile_describe.md](phases/02_profile_describe.md) | Profile data + AI-generate descriptions |
| 3 | [phases/03_classify.md](phases/03_classify.md) | Classify columns: fact/dim/metric/skip |
| 4 | [phases/04_relationships.md](phases/04_relationships.md) | Detect + validate FK relationships |
| 5 | [phases/05_generate_ddl.md](phases/05_generate_ddl.md) | Generate DDL + built-in self-check |
| 6 | [phases/06_execute_validate.md](phases/06_execute_validate.md) | Execute + DESCRIBE + sample question loop |
| 7 | [phases/07_iterate_enrich.md](phases/07_iterate_enrich.md) | Add verified queries, refine, export |
| 8 | [phases/08_drift_monitor.md](phases/08_drift_monitor.md) | Periodic drift detection + scheduled maintenance |

**Reference**: [reference/ddl_syntax.md](reference/ddl_syntax.md) — complete DDL syntax, all grammar rules, error cheat sheet.

---

## Key Design Principles

1. **Self-checking at every phase**: Phase 5 runs 23 checks (18 syntax + 5 semantic correctness) before showing DDL to the user. Phase 6 validates against DESCRIBE output and runs sample questions.

2. **Iterative loop**: Phases 5-6 loop until passing. The agent fixes its own DDL based on structured error output — no copy-paste debugging.

3. **Descriptions by default**: Phase 2 runs CORTEX.COMPLETE against sampled data to generate descriptions, synonyms, and sample_values. Optional docs file (CSV data dict, markdown) further improves quality.

4. **Mandatory stopping points**: User approves at the end of Phase 1, 2, 5, 6, and 7. Nothing is executed without confirmation.

5. **HOL-safe**: All SQL is executable directly in Snowsight. No filesystem required for the core workflow.

---

## Critical DDL Rules (always active)

These rules are embedded in Phase 5's self-check. Reference `reference/ddl_syntax.md` for the full list.

| Rule | |
|------|-|
| Clause order is mandatory | TABLES → RELATIONSHIPS → FACTS → DIMENSIONS → METRICS |
| Direct column alias must match physical name | `AS col_name` must equal the physical column name exactly |
| Duplicate column names across tables | Define from one table only |
| REFERENCES table needs PRIMARY KEY or UNIQUE | Right-hand side of all relationships |
| Multiple relationship paths → use USING | Disambiguate on affected metrics |

---

## Integration with Toolkit

- **Input from sv-discovery**: Phase 1 accepts structured handoff docs from sv-discovery Phase 5
- **Output to sv-evaluation**: After Phase 6, suggest running sv-evaluation for baseline accuracy
- **Output to sv-watch**: Phase 8 can hand off to sv-watch for ongoing monitoring
- **Persist**: After successful creation, offer to log SV metadata to `_SV_TOOLKIT_META`

---

## Relationship to Bundled semantic-view Skill

This skill **does not replace** the bundled `semantic-view` skill. Use each for:

| Goal | Skill to use |
|------|-------------|
| DDL path, HOL, quick creation, unreliable FastGen | **This skill** (sv-ddl) |
| YAML/FastGen path, Tableau import | Bundled `semantic-view` skill |
| Optimize/audit existing semantic view | sv-audit or sv-optimization |
| VQR suggestions, filters & metrics suggestions | sv-optimization or vqr-generator |

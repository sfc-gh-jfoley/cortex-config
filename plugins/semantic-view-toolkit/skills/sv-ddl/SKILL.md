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

**This skill writes native semantic view DDL only — no YAML, no FastGen.** It follows the
candidate-copy contract in [../../references/candidate-promotion.md](../../references/candidate-promotion.md):

- **New SV** (the target name does not exist): Phases 5–7 validate on `cand` candidate copies;
  the target is created once, with plain `CREATE SEMANTIC VIEW`, after a collision check. If the
  name exists, stop — never overwrite it.
- **Existing SV**: changes go to a `cand` candidate and reach production only through gate
  `SV-PROMOTE`.
- The toolkit never uses replace-in-place DDL (`OR REPLACE`) on a semantic view.

---

## Execution Mode

Detect or ask whether to run **INTERACTIVE** or **AUTONOMOUS** (same convention as
`sv-iterative-optimizer` / `agent-optimizer`):

- **INTERACTIVE** (default): every `MANDATORY STOP` / `STOPPING POINT` across phases 1–7 blocks
  for user input, as written.
- **AUTONOMOUS**: courtesy and judgment-call stops resolve to their documented default and
  log the decision instead of blocking (see each phase file for its specific default).
  Genuine data-integrity stops — FAN_TRAP/CHASM_TRAP in Phase 6, `REGULATED_MODE=true`
  governance notes in Phase 3, zero-object/zero-answer conditions — still hard-stop in
  both modes; these aren't judgment calls, they're defects or compliance requirements.
  `SV-PROMOTE` and `SV-CANDIDATE-CLEANUP` are OPERATOR_REQUIRED in both modes
  (see [../../references/gate-inventory.md](../../references/gate-inventory.md)).

Default to INTERACTIVE if the user's preference is unclear. A standing "run to completion" /
"don't stop until done" directive for this task counts as an explicit request for
AUTONOMOUS without asking again.

---

## Source Object Support

This skill handles ALL queryable objects as SV sources:

| Object Type | Detection | Notes |
|---|---|---|
| Base Tables | `TABLE_TYPE = 'BASE TABLE'` | Primary source type |
| Views | `TABLE_TYPE = 'VIEW'` | May reference other databases |
| Dynamic Tables | `SHOW DYNAMIC TABLES` or the `INFORMATION_SCHEMA.DYNAMIC_TABLES()` table function | Note TARGET_LAG in metadata |
| External Tables | `TABLE_TYPE = 'EXTERNAL TABLE'` | Iceberg or non-Iceberg |
| Materialized Views | `TABLE_TYPE = 'MATERIALIZED VIEW'` | Pre-aggregated |

See [../../references/queryable-objects.md](../../references/queryable-objects.md) for full details.

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
Phase 5: Generate DDL               → BUILD + self-check (Step 5.8 checklist)
    ↓ [STOP: user approves DDL]
Phase 6: Execute & Validate         → deploy candidate → DESCRIBE → self-test question loop
    ↓
    ├── FAIL → back to Phase 5 with specific fixes
    └── PASS → Phase 7
Phase 7: Iterate & Enrich           → AI_VERIFIED_QUERIES + description polish
                                      → create new SV, or SV-PROMOTE for an existing one
```

Drift monitoring after deployment is owned by the **sv-watch** skill.

**Stopping points**: Phases 1, 2, 5, 6, 7 each have a mandatory user approval gate. Phase 3
(`REGULATED_MODE`) and Phase 4 (relationship approval) also stop — see each phase file.

**Size guardrail (~100K tokens):** In Phase 5, after generating the DDL, estimate the serialized SV size (~1 token per ~2.5 chars of DDL including all descriptions, metrics, and VQR SQL). If the SV exceeds ~100,000 tokens, warn the author: Cortex Agents may prune the SV to fit the context window, adding latency and reducing answer quality. Recommend splitting along sub-domain boundaries into multiple SVs (Cortex Agents selects the relevant one per question) or trimming non-business-relevant columns. See `sv-discovery` for the split guidance. This is a guideline, not a hard limit.

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
| 8 | [phases/08_drift_monitor.md](phases/08_drift_monitor.md) | Pointer only — drift monitoring lives in sv-watch |

**Reference**: [reference/ddl_syntax.md](reference/ddl_syntax.md) — complete DDL syntax, all grammar rules, error cheat sheet.

**Multi-tenant SVs** (`IS_MTT = true` in Phase 3): read
[reference/multitenant_sv_guidance.md](reference/multitenant_sv_guidance.md) for how row access
policies on base tables scope agent queries and how to classify and tag tenant columns.

---

## Key Design Principles

1. **Self-checking at every phase**: Phase 5 runs the Step 5.8 syntax and semantic-correctness checklists before showing DDL to the user. Phase 6 validates against DESCRIBE output and runs sample questions.

2. **Iterative loop**: Phases 5-6 loop until passing. The agent fixes its own DDL based on structured error output — no copy-paste debugging.

3. **Descriptions by default**: Phase 2 runs CORTEX.COMPLETE against sampled data to generate descriptions, synonyms, and sample_values. Optional docs file (CSV data dict, markdown) further improves quality.

4. **Mandatory stopping points**: User approves at the end of Phase 1, 2, 5, 6, and 7. Nothing is executed without confirmation, and production changes always wait at `SV-PROMOTE`.

5. **HOL-safe**: All SQL is executable directly in Snowsight. No filesystem required for the core workflow.

---

## Critical DDL Rules (always active)

These rules are embedded in Phase 5's self-check. Reference `reference/ddl_syntax.md` for the full list.

| Rule | |
|------|-|
| Clause order is mandatory | TABLES → VARIABLES → RELATIONSHIPS → FACTS → DIMENSIONS → METRICS (VARIABLES after TABLES, not before) |
| Direct column alias must match physical name when column exists in multiple entities | For columns whose name appears in more than one table in the SV (local or imported), alias must equal the physical column name exactly. Custom aliases work when the column name is unique across all entities. If a custom alias still fails with `invalid identifier`, fall back to alias = physical name. |
| Duplicate column names across tables | Define from one table only. If a column name is already an imported dimension, the local table's same-named column cannot be exposed under any alias — omit it entirely. |
| IS_ENUM must be the last dimension modifier | Nothing can follow IS_ENUM — `IS_ENUM COMMENT = '...'` is a hard syntax error. Put COMMENT before IS_ENUM or omit it on that dimension. |
| REFERENCES table needs PRIMARY KEY or UNIQUE | Right-hand side of all relationships |
| Multiple relationship paths → use USING | Disambiguate on affected metrics |
| VARIABLES syntax: no `AS` keyword | `var_name TYPE DEFAULT value` — not `var_name AS TYPE = value` |

---

## Integration with Toolkit

- **Input from sv-discovery**: Phase 1 accepts structured handoff docs from sv-discovery Phase 5
- **Output to sv-evaluation**: After Phase 6, suggest running sv-evaluation for baseline accuracy
- **Output to sv-watch**: after the SV is created or promoted, use sv-watch for drift monitoring
- **Persist**: After successful creation, offer to log SV metadata to `_SV_TOOLKIT_META`

---

## Relationship to Bundled semantic-view Skill

This skill **does not replace** the bundled `semantic-view` skill. Use each for:

| Goal | Skill to use |
|------|-------------|
| DDL path, HOL, quick creation, unreliable FastGen | **This skill** (sv-ddl) |
| YAML/FastGen path, Tableau import | Bundled `semantic-view` skill |
| Optimize/audit existing semantic view | sv-audit or sv-iterative-optimizer |
| VQR suggestions, filters & metrics suggestions | sv-iterative-optimizer or vqr-generator |

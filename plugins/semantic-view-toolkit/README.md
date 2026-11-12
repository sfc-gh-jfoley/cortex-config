# semantic-view-toolkit

A Cortex Code plugin for the full Snowflake Semantic View lifecycle — from discovery through evaluation, optimization, and production monitoring. All workflows use pure SQL DDL, native Snowflake evaluation APIs, and Snowflake-side state persistence.

## Install

Install from wherever you obtained the toolkit — a registry entry, a git clone, or
an archive. The toolkit is self-contained: it has no dependencies outside its own
directory, and no assumptions about where that directory lives.

```bash
# From a local copy:
cortex plugin install /path/to/semantic-view-toolkit
```

All script paths in the skills are relative to the toolkit root, so any install
location works.

## Skills

| Skill | Purpose | When to Use |
|---|---|---|
| `sv-discovery` | Find tables/views/DTs that should be in semantic views, recommend domain groupings | Starting fresh — "I have a database, what SVs do I need?" |
| `sv-ddl` | Create or edit SVs using SQL DDL with AI-generated descriptions, self-check, and validation | Building a new SV from known tables, or editing an existing one |
| `sv-snippet-suggester` | Match a table model to a verified DDL pattern (semi-additive, SCD2, time intelligence, multi-fact) | "Which DDL pattern fits my table model?" |
| `sv-audit` | Audit existing SV against actual query usage patterns | "Is my SV missing tables? Are columns unused?" |
| `sv-evaluation` | Run native Cortex Analyst evaluations (sql_correctness) against VQRs | Measuring SV quality: can Analyst generate correct SQL? |
| `sv-coverage-checker` | Structural check: can the SV answer each eval question's ground-truth SQL? | Before tuning, to separate missing structure from wording problems |
| `sv-iterative-optimizer` | Iterative improvement loop with VQR-based eval and accept/reject gates | Systematically improving accuracy over multiple iterations |
| `sv-gepa-optimizer` | Population-based evolutionary optimization via tournament selection | Sequential optimizer hit a plateau — explore broadly |
| `sv-watch` | Drift detection, schema change monitoring, coverage decay alerts | Ongoing production maintenance |
| `sv-materialize` | Add and manage SV materializations to speed up repeated queries | Measured slow queries on a stable SV |
| `sv-rearchitect` | Multi-SV composition: IMPORTS clause (unverified for Analyst) or multi-tool Agent composition | Multiple domains that need to work together |
| `vqr-generator` | Auto-generate verified query candidates from query history | Need more VQRs for eval coverage |
| `vqr-curator` | Audit existing VQRs: quality, duplicates, activation, coverage gaps | VQR set is noisy or not triggering |

## Entry Point

The plugin has a single router (`SKILL.md`) that detects user intent and dispatches to the right sub-skill. Each skill is also independently invocable from skill-loader.

## Safety: candidate copies

No skill modifies a production semantic view while experimenting. Changes are made on a uniquely named
candidate copy created from `GET_DDL`, evaluated, and promoted only after an explicit operator decision.
See [references/candidate-promotion.md](./references/candidate-promotion.md).

## Key: Verified Queries (VQRs)

The #1 prerequisite for evaluation and optimization is having VQRs on your semantic view. Without them, `EXECUTE_AI_EVALUATION` cannot run. The `vqr-generator` skill helps bootstrap VQRs from query history when none exist.

## Recommended Workflow

```
sv-discovery (find tables, recommend domains)
  └── sv-ddl (create SV from recommendations)
       └── vqr-generator (bootstrap VQRs if none exist)
            └── sv-evaluation (baseline accuracy measurement)
                 ├── sv-iterative-optimizer (iterative improvement)
                 │   └── sv-gepa-optimizer (evolutionary search if stuck)
                 └── sv-rearchitect (compose for multi-domain agent)
                      └── → hand off to cortex-agent-toolkit

sv-audit (enter here if you have an existing SV)
  └── feeds into sv-evaluation or sv-ddl (for fixes)

sv-watch (ongoing, independent of creation workflow)
  └── alerts feed into sv-audit or sv-iterative-optimizer
```

## Source Object Support

SVs can reference any queryable object: base tables, views, dynamic tables, external tables (Iceberg), and materialized views. All discovery and DDL skills handle the full set.

## Persistence

State is persisted in `<DB>._SV_TOOLKIT_META` schema (Snowflake tables). This enables:
- Resumable optimization across sessions
- Drift detection history
- Evaluation score tracking over time
- Promotion decisions (candidate to production)

## Prerequisites

See [PREREQUISITES.md](./PREREQUISITES.md) for roles, permissions, and edition requirements per skill.

See [GUIDE.md](./GUIDE.md) for a walkthrough of the full workflow.

# <Lab Title — industry + theme> — Lab Intake

> Produced for the lab-builder intake fast path. Scenario is a generic <industry> organization.

## Phase 0 — Discovery answers
| Question | Answer |
|---|---|
| Problem to solve | <trying_to of the lead intent, industry language> |
| Audience | <selection.audience> |
| Domain | <data_spec.domain> |
| Features used so far | <generic: "SQL warehouses, stored procedures, AI functions, semantic views, agents"> |
| Outcome after lab | <"better" of each selected intent, as skills participants leave with> |
| Time | <selection.duration_min> min |
| Isolation | <selection.isolation or TBD — confirm with DBA> |

## Phase 0.5 — Curriculum plan
| Module | Title | Pillar | Minutes | Notes |
|---|---|---|---|---|
| 00 | Setup & data load | — | 15 | from data_spec.yaml |
| 01 | <intent A> | ETL | 40 | |
| 02 | <intent B — failure moment> | GenAI | 45 | **failure moment**: <failure_moment.description> → fix: <failure_moment.fix> |
| 03 | <intent C> | Query / ML | 40 | |
| — | Validate + wrap | — | 15 | |

Suggested lab-builder modules to reuse: <e.g. ai-01 Semantic Views Basics, ml-03 Training> (check `labs/_modules/INDEX.md`).

## Hero question
"<selection.hero_question>"

## Synthetic data
See `data_spec.yaml` (archetypes, roles, distributions, scale). Key tables:
| Table | Grain | Purpose |
|---|---|---|
| <ARCHETYPE> | <grain> | <role in story> |

Seeded failure starter: `<data_spec.failure_moment.starter>`

## Account configuration
- Account: TBD
- Warehouse: TBD
- CLI / CoCo availability: TBD
- DBA contact: TBD

## Production path (bonus module)
Include `remap.md` as a bonus exercise: "Use CoCo to find tables in your own account that match these shapes and adapt
module NN to them."

## Open questions
- <anything the SE must confirm: audience mix, isolation, duration>

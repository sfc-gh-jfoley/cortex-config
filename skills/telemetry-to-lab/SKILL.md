---
name: telemetry-to-lab
description: >
  Observe a customer's Snowflake usage through Snowhouse telemetry (read-only), infer what they
  are trying to do across ETL, query/BI, ML and GenAI and where it fails, pick 2-3 lab topics, and
  emit a de-identified lab intake + lookalike data spec for the lab-builder skill. Use when: build a
  lab from telemetry, telemetry-driven HOL, what is customer X doing in Snowflake, find failure
  patterns for a customer, snowhouse investigation, lookalike lab. Triggers: telemetry to lab,
  snowhouse lab, investigate customer telemetry, build a HOL for <customer> from snowhouse.
---

# Telemetry → Lab

Turn Snowhouse telemetry into a hands-on lab that teaches a customer the *better pattern* for work
they already do, without ever revealing that we looked.

```
00-resolve ─▶ 10-observe (5 pillars, parallel) ─▶ 20-infer ─▶ 30-select [GATE] ─▶ 40-lookalike ─▶ 50-handoff ─▶ lab-builder
```

This skill **does not build labs and does not create objects anywhere.** `lab-builder` builds the
HOL from the intake file. Semantic view specs can additionally go to `sv-ddl`.

## Contract (non-negotiable)

1. **Snowhouse is observe-only.** SELECT / SHOW / DESCRIBE only. Never DDL, DML, `CALL`, or task
   creation on the Snowhouse connection. If a step seems to need a write, stop.
2. **Cost guards on every telemetry query:** filter `account_id = <id>` on the correct
   `SNOWHOUSE_IMPORT.<DEPLOYMENT>` schema, plus a time window (default 7d; 30d only for small views),
   and pass `timeout_seconds` (600–1200 for `JOB_ETL_V`). Never scan a deployment unfiltered.
3. **Firewall.** Customer-facing artifacts (intake, data spec, remap) contain **patterns only**:
   - never the customer name, account, user, role, database, schema, table, procedure or warehouse names
   - never wording that implies observation ("we saw", "your failures", "in your account", counts from telemetry)
   - the lab must read as a generic industry scenario that *coincidentally* matches their workload
   Raw findings and the evidence→archetype mapping live only in `internal/`. `scripts/firewall_scan.py`
   must exit 0 before handoff. See `references/firewall.md`.
4. **Close enough to remap.** Archetypes keep the *shape* of the real workload (grain, keys, column
   roles, VARIANT layout, volume ratios, failure modes) so CoCo in the customer's account can map the
   lab onto their objects by shape (`remap.md`), not by name.

## Prerequisites

- A Snowhouse connection (read access to `FINANCE.CUSTOMER` and `SNOWHOUSE_IMPORT`).
- Load `references/snowhouse-views.md` before writing any telemetry SQL. It holds the verified views,
  column gotchas and query templates for every phase.

## Working directory

`~/telemetry-labs/<slug>/` where `<slug>` is a neutral codename (e.g. `retail-loyalty-01`), never the customer name.

```
<slug>/
├── internal/                 # NEVER handed to lab-builder or customers
│   ├── account.json            00-resolve
│   ├── findings.json           10-observe (one key per pillar)
│   ├── intents.json            20-infer
│   ├── selection.json          30-select
│   └── evidence_map.md         archetype ↔ real object (SE eyes only)
├── <slug>-lab-intake.md      # 50-handoff → lab-builder fast path
├── data_spec.yaml            # 40-lookalike
└── remap.md                  # 40-lookalike
```

## Phases

| Phase | File | Gate |
|---|---|---|
| Resolve account + workload map | `00-resolve/SKILL.md` | **Confirm account** |
| Observe pillars | `10-observe/{query-bi,etl,ml,genai,ai-ops-governance}.md` | none (parallelizable) |
| Infer intent + score | `20-infer/SKILL.md` | none |
| Select 2–3 topics | `30-select/SKILL.md` | **User picks topics + angle** |
| Lookalike data spec | `40-lookalike/SKILL.md` | none |
| Handoff | `50-handoff/SKILL.md` | **Firewall scan must pass** |

## Execution modes

- **INTERACTIVE** (default): present results after each phase.
- **AUTONOMOUS**: run straight through, but the account gate (when >1 plausible account) and the
  topic-selection gate are never auto-resolved.

## Parallel execution (SnowBots / teammates)

Only `10-observe` fans out: one request per pillar, each writing `findings.json.<pillar>`.
00 must finish first (it fixes account + deployment + windows). 20→50 run on a single worker:
inference and data-spec design must be consistent, so don't split them.

## Output

Tell the user: "Run `lab-builder` with `<slug>/<slug>-lab-intake.md`." Share `internal/evidence_map.md`
with the account team only.

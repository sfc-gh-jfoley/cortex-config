---
name: agent-load-tester
description: >
  Two-sided load testing for Cortex Agents at 10/25/50/100/200 concurrent users. Profiles eval
  telemetry (think time vs SQL time), screens models with an LLM-step replay (Side 1-B), validates
  with live agent:run calls (Side 1-A), and replays the agent's captured SQL open-loop against
  XS/S/M multi-cluster and Interactive warehouses + interactive tables (Side 2). Produces sizing +
  tuning guidance that routes SQL issues to Snowflake tuning skills and think-time issues to model
  testing. Use when: load test agent, agent concurrency, how many users can my agent handle,
  warehouse sizing for agent, interactive warehouse for agent, think time vs sql time, agent latency
  under load, agent throughput, 429 rate limits.
---

# Agent Load Tester

An agent's latency has two sides, and each gets tested and tuned differently:

- **Side 1, LLM think time:** orchestration, text-to-SQL, and response generation. Usually 80–90%
  of latency. Tuned by model and flags. Tested with **B** (replay the LLM steps; cheap, run first)
  and then **A** (real agent calls; deeper look that also validates the Side 2 load model).
- **Side 2, SQL execution:** regular Snowflake tuning. Tested by replaying the agent's actual SQL at
  the arrival rate the think time produces. No LLM cost.

Read `references/methodology.md` before Phase 1. The key formula:
`concurrent SQL = users / (question_s + pause_s) × sql_calls_per_question × sql_s_per_call`.

## Prerequisites
- An agent with eval runs: traces with `run.name` in `SNOWFLAKE.LOCAL.AI_OBSERVABILITY_EVENTS`.
  If there are none, run `agent-evaluation` first.
- A `snow`/connector named connection. Role needs: ACCOUNT_USAGE read (IMPORTED PRIVILEGES on
  SNOWFLAKE), `SNOWFLAKE.CORTEX_USER`, CREATE WAREHOUSE (Side 2), and USAGE on the agent (Side 1-A).
- REST auth (Phases 2–3): scripts use `SNOWFLAKE_PAT` if set, otherwise the connector session token.
  **Preflight runs one call per model and stops on auth/model errors.** If you see `390104`/`390303`,
  the PAT is stale. Check whether `SNOWFLAKE_PAT` is exported in the shell profile, because it wins
  over the session token. Run with `env -u SNOWFLAKE_PAT ...` or refresh the secret via `/secrets`.
  Never ask the user to paste a token.
- Python environment: `cd <skill_dir> && uv sync`, then `uv run python scripts/<script>.py ...`

## Parameters
| Param | Default | Notes |
|---|---|---|
| `<CONNECTION>` | active | |
| `<AGENT_FQN>` | — | DB.SCHEMA.AGENT |
| `<RUNS>` | all eval runs | `--run` repeatable |
| `<TIERS>` | 10,25,50,100,200 | |
| `<PAUSE_S>` | 30 | user pause between questions; state it in the report |
| `<MODELS>` | current + 1 smaller | for Side 1-B / 1-A clones |
| `<CONFIGS>` | XS_MC, S_MC, M_MC, IWH | `references/config-matrix.md` |
| `<SLA_P95>` | ask | end-to-end target, seconds |
| `<OUT>` | `./lt_out/<agent>` | working dir for all artifacts |

Mode (INTERACTIVE / AUTONOMOUS) is inherited from the toolkit router. Don't ask again.

## Phase 0: Setup and cost gate
1. Confirm the parameters. Run `SHOW AGENTS LIKE '<AGENT>'` and confirm the eval runs exist (query 1
   in `references/telemetry-queries.sql`, filtered to the agent).
2. Optional persistence: `CREATE SCHEMA IF NOT EXISTS <DB>._AGENT_TOOLKIT_META` (auto in AUTONOMOUS).
   Load the JSON artifacts into tables only if the user wants history; otherwise files are enough.
3. **Gate `LOAD-COST-ESTIMATE` (OPERATOR_REQUIRED).** Run Phase 1 first (read-only), then
   `sql_replay.py --dry-run`. Present:
   - Side 1-B: requests ≈ users × duration / (question_s + pause_s) × LLM steps, per tier and model;
     tokens ≈ requests × recorded tok_in/tok_out.
   - Side 1-A: capped calls (`--max-calls`) × the agent's observed credits per call.
   - Side 2: expected queries per cell from the dry run; warehouse-hours per config;
     **Interactive WH bills for at least 24h.**

   Offer a reduced matrix (e.g. tiers 10/50/200, cache OFF only) if the cost is high.

## Phase 1: Profile (read-only)
```bash
uv run python scripts/profile_workload.py --connection <CONNECTION> --agent <AGENT_FQN> \
  --tiers <TIERS> --pause <PAUSE_S> --out <OUT>
```
Produces `profile.json` (think/SQL/other, modeled SQL concurrency), `sql_mix.jsonl` (weighted SQL plus
QUERY_HISTORY stats), `prompts.jsonl`, and `outliers.json`.

**STOP. Present** the think% vs SQL%, the modeled concurrency table, and the outliers.
- If there are outliers (≥10s SQL), recommend tuning first via `workload-performance-analysis`, using
  the query IDs. Sizing around a broken query only measures the broken query. To size
  without them, pass `--exclude-over-ms 10000` to sql_replay and note it in the report.
- If SQL is under 5% of latency, say so plainly: warehouse sizing will barely change end-to-end
  latency, and Side 1 is where the gains are.

## Phase 2: Side 1-B LLM replay (run first)
```bash
SNOWFLAKE_PAT="<snowflake_pat>" uv run python scripts/llm_replay.py --connection <CONNECTION> \
  --in <OUT> --models <MODELS> --tiers <TIERS> --duration 120 --pause <PAUSE_S> --max-requests 2000
```
- It skips the remaining tiers for a model once success drops below 0.8 (the throttling ceiling).
- **STOP. Present** think time per question (p50/p95) by model and tier, plus 429s and TTFT.
  Label the results *directional*. The recorded token counts are in the output; mention them if
  the rebuilt prompts differ a lot from the recorded size.
- Pick 1–2 candidate models for Phase 3. Any model change must later pass `agent-evaluation` /
  `agent-model-tester` for accuracy. Faster but wrong doesn't count.

## Phase 3: Side 1-A live agent calls (deeper look, opt-in)
**Gate `LOAD-AGENT-LIVE` (OPERATOR_REQUIRED):** real LLM spend. Show the call cap and tiers.
- For model comparison, create clones per `agent-model-tester` conventions (`<AGENT>_LT_<MODEL>`).
  Never modify the production agent (`AGENT-PROD-OVERWRITE` applies).
- Run 1–2 tiers (default 25, optionally 100), with no other traffic to that agent during the window:
```bash
SNOWFLAKE_PAT="<snowflake_pat>" uv run python scripts/agent_load.py --connection <CONNECTION> \
  --agent <AGENT_FQN> --in <OUT> --tiers 25 --duration 180 --pause <PAUSE_S> --max-calls 300
# wait for observability ingestion (a few minutes), then:
uv run python scripts/collect_metrics.py --side agent --run-file <OUT>/agent_load_<id>.json --connection <CONNECTION>
```
- **Model check:** observed vs modeled SQL concurrency. Within ~25%, Phase 4 rates are trustworthy.
  Otherwise, re-run Phase 4 with `--rate-scale <observed/modeled>`.

## Phase 4: Side 2 SQL replay
1. **Gate `LOAD-WH-CREATE` (OPERATOR_REQUIRED):** show the DDL from `references/config-matrix.md`
   with the sizes and costs.
   - Build interactive tables for the objects in `sql_mix.jsonl`. `CLUSTER BY` is required; use the
     columns filtered in the captured SQL.
   - Run each rewritten query once on the interactive warehouse and drop any that error from the IWH config.
   - Write `<OUT>/configs.json`, smallest config first.
2. Dry run, then the real run. Before warmup, sql_replay `EXPLAIN`s every distinct SQL and drops
   queries that no longer compile. Eval SQL goes stale as views change; DISH_AGENT lost 15% of traffic
   to `invalid identifier`. Report the dropped share. Sessions use the agent's DB.SCHEMA so unqualified
   names resolve (`--context-schema` overrides).
```bash
uv run python scripts/sql_replay.py --connection <CONNECTION> --in <OUT> --configs <OUT>/configs.json \
  --tiers <TIERS> --duration 180 --cache on,off --dry-run
uv run python scripts/sql_replay.py --connection <CONNECTION> --in <OUT> --configs <OUT>/configs.json \
  --tiers <TIERS> --duration 180 --cache on,off --max-queries 20000
```
   - **What-if for model choice:** add `--question-s <new end-to-end s>` using the Phase 2 or 3 think
     time for the candidate model. A faster model means more SQL per second.
3. Collect the metrics. For immediate results use `--source info --info-db <DB>` (any database you can use; the
   INFORMATION_SCHEMA table function needs a database qualifier). Re-run with the
   default `account_usage` source after about 45 minutes, which adds Interactive fallback detection
   and cluster/load/credit data:
```bash
uv run python scripts/collect_metrics.py --side sql --run-file <OUT>/sql_replay_<id>.json --connection <CONNECTION>
```

## Phase 5: Report and tuning handoff
```bash
uv run python scripts/build_report.py --in <OUT> --llm <OUT>/llm_replay_<id>.json \
  --sql <OUT>/sql_replay_<id>_metrics.json [--agent <OUT>/agent_load_<id>_metrics.json] \
  --sla-p95 <SLA_P95> --cache off
```
Present the predicted end-to-end p95 grid (model × config × tier) and the cheapest passing config per
tier. Then route:

| Signal | Route |
|---|---|
| High SQL exec p95, spill, poor pruning, outliers | `workload-performance-analysis` |
| Queued time grows with users, cluster ceiling hit | `warehouse` |
| Selective, repeated query shapes needing sub-second | `snowflake-interactive` |
| Think time dominates, 429s at target tier | `agent-model-tester` (then `agent-evaluation` gate) |
| Many planning steps per question | `agent-instruction-optimizer` / `agent-optimizer` |

Offer to publish the report (`snowflake-publish-report`) or copy it to a workspace.

## Teardown
**Gate `LOAD-TEARDOWN` (OPERATOR_REQUIRED in INTERACTIVE; AUTO_REMEDIATE in AUTONOMOUS after the
report is written).** Run the teardown block in `references/config-matrix.md`. Report anything left running,
especially the Interactive WH, which keeps billing.

## Stopping points
- Phase 1 present, Phase 2 present, and each OPERATOR_REQUIRED gate:
  `LOAD-COST-ESTIMATE`, `LOAD-AGENT-LIVE`, `LOAD-WH-CREATE`, `LOAD-TEARDOWN`.

## Output
`<OUT>/`: `profile.json`, `sql_mix.jsonl`, `prompts.jsonl`, `outliers.json`, `llm_replay_*.json`,
`agent_load_*[_metrics].json`, `sql_replay_*[_metrics].json`, `configs.json`, `report.md`.

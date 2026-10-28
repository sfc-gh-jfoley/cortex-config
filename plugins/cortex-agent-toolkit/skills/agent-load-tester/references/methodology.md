# Methodology — Two-sided agent load testing

## The two sides

| | Side 1: LLM (think time) | Side 2: SQL (warehouse) |
|---|---|---|
| What | Orchestration planning steps, text-to-SQL, response generation | Generated SQL on `execution_environment.warehouse` |
| Typical share | 78–91% of latency (2 demo accounts, 3,584 eval questions) | 2–5% typical; 60–96% when SQL is pathological |
| Limits under load | Model throughput, token latency, Cortex rate limits (429) | Concurrency, queueing, cluster scale-out, cache, pruning/spill |
| You control | Model choice, flags, instructions, step count | Size, clusters, interactive, clustering/SOS/QAS, query shape |
| How to test | B: replay LLM steps (cheap). A: live agent:run (accurate) | Replay captured SQL open-loop at the derived rate (no LLM) |

## Why think time paces the warehouse

Each user is in a cycle: ask → agent works (think + SQL + other) → user reads/pauses → ask again.

```
questions/s   = users / (question_s + pause_s)
SQL arrival/s = questions/s × sql_calls_per_question
concurrent SQL (Little's law) = SQL arrival/s × sql_s_per_call
```

Example, DISH_AGENT (1.6 SQL calls, 37.6s/question, 1.6s/call, pause 0): 200 users ≈ 8.5 SQL/s ≈ 14
concurrent queries. Sizing should target 14, not 200. With a 30s pause the rate drops by about 45%.

**Consequence:** a faster model (Side 1 win) shortens `question_s` and *raises* SQL pressure. After a
Side 1 change, re-run Side 2 with `--question-s` set to the new end-to-end time.

## Open loop vs closed loop

- **Side 1 is closed loop:** each user waits for its answer before asking again. That's how chat users behave.
- **Side 2 is open loop:** queries arrive on a Poisson schedule whether or not earlier ones finished.
  If the warehouse falls behind, queueing grows, as it would in production. The notebook-style
  "fire N at once" approach is a burst test and understates sustained queueing.

## Side 1-B first, then 1-A

- **B (llm_replay):** prompts are rebuilt from the planning trace records. Telemetry stores only the user turns
  in `planning.messages`, plus the instruction, tool descriptions, and token counts. The tool pads prompts
  to the recorded input token count, because prefill dominates latency, and caps output at the recorded
  output tokens. Treat results as **directional**: use B to screen models and find the throttling tier cheaply.
- **A (agent_load):** real `agent:run` calls. They give the real per-step breakdown under load and the real
  SQL concurrency, which **validates the Side 2 model**. Run at 1–2 tiers with a call cap. Use clones
  for model comparisons and never alter production.

## Measurement rules

- **SQL:** measure on the server (`QUERY_HISTORY` via `QUERY_TAG`), not the client. Report elapsed,
  execution, compile, and overload-queue percentiles separately.
- **Cache:** run Side 2 twice, with `USE_CACHED_RESULT` TRUE and FALSE. Present the result as a range:
  real traffic sits between them, because data changes invalidate the result cache.
- **Warmup:** run each distinct SQL once per config before measuring, so warehouse cache and cluster
  spin-up don't count against the first tier.
- **Steady state:** hold each tier for at least 3 minutes, with a cooldown between cells.
- **Errors:** report success rate and 429s next to the latency percentiles. A throttled run is not a fast run.
- **Client location:** client-side timings include network time to Snowflake. Note the client region.
- **Outliers:** queries far above the median, e.g. ≥10s, are a tuning problem rather than a sizing
  problem. Fix them first (`workload-performance-analysis`), or they will dominate every config.

## Known gaps

- Span data has no warehouse attribute. The source warehouse comes from the `QUERY_HISTORY` join,
  which needs ACCOUNT_USAGE access, and ACCOUNT_USAGE retention is 365 days.
- Agent-issued SQL can't be tagged, so Side 1-A correlates by time window + agent name, using
  traces that have no `run.name`. Avoid other traffic to the same agent during a 1-A run.
- `WAREHOUSE_METERING_HISTORY` is hourly, so per-cell credits are approximate. Long cells or dedicated
  hours give cleaner cost numbers.

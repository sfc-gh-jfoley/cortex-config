---
name: telemetry-to-lab-select
description: Phase 30. Present ranked intents per angle; user selects 2-3 topics for the lab.
parent_skill: telemetry-to-lab
---

# 30 — Select topics  [GATE: never auto-resolved]

**Input:** `internal/intents.json`. **Output:** `internal/selection.json`.

## Present
1. A table of the top 8 intents: id, trying_to, better, pillars, score, confidence, spine.
2. Three ready-made bundles, each 2–3 intents on **one spine**, together covering as many of ETL / Query / ML / GenAI as possible:
   - **DE angle**: pipeline reliability first (ETL → GenAI enrichment → query)
   - **Analyst / AI angle**: governed answers first (SV → agent → evaluation)
   - **Exec / outcomes angle**: highest impact × prod_path, with the ML opportunity included
   For each bundle show: hero question (industry language), module outline, pillars covered, and the **failure moment**
   (the customer's real anti-pattern, reproduced generically).
3. Recommend one bundle and say why.

## Rules
- Prefer a single spine. If the user picks topics on two spines, warn that the lab needs two datasets and roughly 20 more minutes.
- Every bundle must include exactly one failure moment drawn from a `failing_at`.
- If no ML intent scores ≥ 27, offer the best "missed ML opportunity" as an optional module, not a core one.

## Ask
Use `ask_user_question`: bundle (or custom pick), audience, duration, isolation pattern (schema-per-user /
database-per-user) if known.

## Emit `internal/selection.json`
```json
{"bundle":"DE","intents":["I1","I3","I6"],"spine":"S1","audience":"Data Engineers + Analysts","duration_min":180,
 "isolation":"schema-per-user","hero_question":"Which product features are driving negative reviews this month, and in which stores?",
 "failure_moment":{"intent":"I1","generic_form":"nightly full rebuild of an aggregate that times out as volume grows"}}
```

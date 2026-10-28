---
name: telemetry-to-lab-infer
description: Phase 20. Turn pillar findings into scored intents grouped into data spines.
parent_skill: telemetry-to-lab
---

# 20 — Infer intent

**Input:** `internal/findings.json` (all pillars). **Output:** `internal/intents.json`.

## 1. Write intents
For each finding or cluster of related findings, write one intent:
- **trying_to**: the business outcome, in industry language ("tag every product review with sentiment and the feature it mentions")
- **failing_at**: the mechanism that breaks ("monolithic procedure loops LLM calls; cancelled/timeouts; re-processing")
- **better**: the Snowflake pattern ("incremental AI_EXTRACT → AI_CLASSIFY in a dynamic-table pipeline with a process-once ledger")
- **features**: the Snowflake features the lab would teach
- **pillars**: which of ETL / Query / ML / GenAI it touches
- **confidence**: lowest confidence among the contributing findings

Merge findings that share a root cause. A procedure timeout plus high AI spend plus copy-sprawled SVs on the same domain
are one story.

## 2. Score (each dimension 1–5, total = product)
| Dimension | 5 means |
|---|---|
| **impact** | top quartile of hours/credits wasted *or* users affected |
| **lab_fit** | teachable in 30–45 min on synthetic data with a clear before/after |
| **prod_path** | the fix is a pattern the customer could ship in days, no re-platforming |

Down-weight `inferred` intents by one point on impact.

## 3. Group into data spines
A spine is a dataset family that several intents can share, e.g. *product reviews* (raw review text →
classified → feature/sentiment rollups → SV/agent), *store sales* (raw transactions → hourly aggregates → forecast), *loan applications*.
Record per spine: archetype list, pillars covered, intents attached.

## Emit
```json
{"intents":[{"id":"I1","trying_to":"...","failing_at":"...","better":"...","features":["dynamic tables","AI_EXTRACT","AI_CLASSIFY"],
  "pillars":["ETL","GenAI"],"scores":{"impact":5,"lab_fit":5,"prod_path":4},"total":100,"confidence":"inferred","spine":"S1"}],
 "spines":[{"id":"S1","name":"product reviews","archetypes":["review_raw","review_enriched","feature_sentiment_daily"],
  "pillars":["ETL","Query","GenAI","ML"],"intents":["I1","I3","I5"]}]}
```

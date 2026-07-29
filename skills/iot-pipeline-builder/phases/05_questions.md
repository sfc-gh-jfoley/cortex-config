---
name: iot-pipeline-builder-phase5
description: Generate domain-specific sample questions and ready-to-run DATA_AGENT_RUN payloads
---

# Phase 5: Sample Questions

## Step 5.1: Generate questions

Based on the data you've seen across Phases 1-4, generate **8-10 questions** in 3 categories:

**Operational** — what's happening right now:
- Which [entities] are in a [bad state] right now?
- Are there any open [incidents/alerts] affecting multiple [entities]?
- What [metric] is currently [above/below] threshold?

**Analytical** — trends and patterns:
- What is the average [metric] over the past 24 hours by [dimension]?
- Which [dimension] has the most [events] this week?
- Show me the [metric] trend for [entity] over time.

**Investigative** — root cause and anomalies:
- What happened to [specific entity] between [time A] and [time B]?
- Are any [entities] showing unusual [metric] patterns?
- Summarize everything that went wrong at [location] today.

Make the questions specific to the actual columns and domain discovered — use real column names/values where helpful.

---

## Step 5.2: Format output

Print each question as a bullet, grouped by category.

Then print the **ready-to-run SQL** for the 3 most interesting questions:

```sql
SELECT SNOWFLAKE.CORTEX.DATA_AGENT_RUN(
    '<MY_DB>.<MY_AGENTS_SCHEMA>.<AGENT_NAME>',
    '{"messages": [{"role": "user", "content": [{"type": "text", "text": "<QUESTION>"}]}]}'
) AS response;
```

---

## Step 5.3: Done

Print a completion summary:

```
Pipeline complete.

  RAW         →  <MY_DB>.<MY_RAW_SCHEMA> (N tables)
  NORMALIZED  →  <MY_DB>.<MY_NORM_SCHEMA> (N Dynamic Tables, 5-min lag)
  SEMANTIC    →  <MY_SV_FQN>
  AGENT       →  <MY_DB>.<MY_AGENTS_SCHEMA>.<AGENT_NAME>

Open in Snowflake Intelligence:
  Snowsight → Intelligence → find <AGENT_NAME> under <MY_DB>.<MY_AGENTS_SCHEMA>
```

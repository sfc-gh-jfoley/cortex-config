---
last_updated: 2026-05-23T00:00:00Z
updated_by: update-llms.sh
---

# Snowflake Cortex LLMs

> **Skills**: read this file to resolve aliases. Never hardcode version strings like `claude-sonnet-4-5` directly — use an alias so a single update here propagates everywhere.
>
> Usage pattern: Read this file → look up the alias in the table below → use the resolved model string.

---

## Aliases

| Alias              | Current Model      | Use For                                               |
|--------------------|--------------------|-------------------------------------------------------|
| `default_agent`    | `claude-sonnet-4-6`| Agent `models.orchestration` default                  |
| `heavy_agent`      | `claude-opus-4-7`  | Max accuracy agents                                   |
| `fast_agent`       | `claude-haiku-4-5` | Low-latency agents / demos                            |
| `current_opus`     | `claude-opus-4-7`  | Complex reasoning; Architect role in CoCo Task spawns |
| `current_sonnet`   | `claude-sonnet-4-6`| Balanced: code gen, worker CoCo Task spawns           |
| `current_haiku`    | `claude-haiku-4-5` | Fast: model probing, simple completions               |
| `complete_fast`    | `mistral-7b`       | Quick `CORTEX.COMPLETE()` calls (profiling, trivial)  |
| `complete_quality` | `llama3.1-70b`     | Higher-quality open-weight `CORTEX.COMPLETE()` calls  |
| `openai_heavy`     | `openai-gpt-5.2`   | Max accuracy OpenAI agent                             |
| `openai_fast`      | `openai-gpt-5-mini`| Fast OpenAI agent                                     |
| `tester_model`     | `openai-gpt-5.2`   | Cross-model verification (Tester role) — GPT catches Claude Worker blind spots |

---

## Capability Rules

### Agent-eligible (support full tool-use loop)

These models reliably complete the agent tool-use loop and can be used in `models.orchestration`:

- `claude-*` — all tiers (haiku, sonnet, opus)
- `openai-gpt-5`, `openai-gpt-5.1`, `openai-gpt-5.2`, `openai-gpt-5-mini`, `openai-gpt-4.1`

### NOT agent-eligible (COMPLETE() only)

These work with `SNOWFLAKE.CORTEX.COMPLETE()` but **fail the agent tool-use loop**. Do not use in `models.orchestration`:

- `llama3.1-8b`, `llama3.1-70b`, `llama3.1-405b`
- `mistral-7b`, `mistral-large2`
- `deepseek-r1`
- `openai-gpt-5-nano`

### Legacy aliases (still available, avoid for new work)

- `claude-4-sonnet` — legacy alias for an older Sonnet generation
- `claude-4-opus` — legacy alias for an older Opus generation

---

## Available Models (auto-updated)

Sourced from: `SNOWFLAKE.ACCOUNT_USAGE.CORTEX_REST_API_RATE_LIMIT_POLICIES`

| Model              | RPM   | TPM        | Agent? |
|--------------------|-------|------------|--------|
| `claude-4-opus`    | 200   | 200,000    | YES (legacy alias) |
| `claude-4-sonnet`  | 1,200 | 2,000,000  | YES (legacy alias) |
| `claude-haiku-4-5` | 10,000| 5,000,000  | YES    |
| `claude-opus-4-5`  | 10,000| 2,000,000  | YES    |
| `claude-opus-4-6`  | 10,000| 3,000,000  | YES    |
| `claude-opus-4-7`  | 10,000| 3,000,000  | YES    |
| `claude-sonnet-4-5`| 10,000| 5,000,000  | YES    |
| `claude-sonnet-4-6`| 10,000| 6,000,000  | YES    |
| `deepseek-r1`      | 100   | 100,000    | NO     |
| `llama3.1-405b`    | 200   | 200,000    | NO     |
| `llama3.1-70b`     | 400   | 400,000    | NO     |
| `llama3.1-8b`      | 800   | 800,000    | NO     |
| `mistral-7b`       | 400   | 400,000    | NO     |
| `mistral-large2`   | 200   | 600,000    | NO     |
| `openai-gpt-4.1`   | 1,000 | 1,000,000  | YES    |
| `openai-gpt-5`     | 10,000| 1,000,000  | YES    |
| `openai-gpt-5-mini`| 2,000 | 2,000,000  | YES    |
| `openai-gpt-5-nano`| 10,000| 10,000,000 | NO     |
| `openai-gpt-5.1`   | 10,000| 1,000,000  | YES    |
| `openai-gpt-5.2`   | 10,000| 1,000,000  | YES    |

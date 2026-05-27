#!/usr/bin/env bash
# update-llms.sh — Regenerate ~/.snowflake/cortex/vault/LLMs.md
#
# Queries SNOWFLAKE.ACCOUNT_USAGE.CORTEX_REST_API_RATE_LIMIT_POLICIES for the
# current available models on this account, then rebuilds LLMs.md with a fresh
# timestamp. The aliases and capability-rules sections are static (curated here);
# only the "Available Models" table is auto-populated from Snowflake.
#
# Usage:
#   ./scripts/update-llms.sh              # update LLMs.md
#   ./scripts/update-llms.sh --dry-run    # print what would be written, no file change

set -euo pipefail

VAULT="${HOME}/.snowflake/cortex/vault"
OUTPUT="${VAULT}/LLMs.md"
DRY_RUN=false

# Agent-eligible model patterns (prefix match)
is_agent_eligible() {
  local model="$1"
  case "$model" in
    claude-*)       echo "YES" ;;
    openai-gpt-5.* | openai-gpt-5 | openai-gpt-5-mini | openai-gpt-5.1 | openai-gpt-5.2 | openai-gpt-4.1)
                    echo "YES" ;;
    openai-gpt-5-nano) echo "NO" ;;
    openai-*)       echo "YES" ;;
    *)              echo "NO"  ;;
  esac
}

agent_note() {
  local model="$1"
  case "$model" in
    claude-4-sonnet | claude-4-opus) echo " (legacy alias)" ;;
    *) echo "" ;;
  esac
}

[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=true

echo "Querying CORTEX_REST_API_RATE_LIMIT_POLICIES..."

# Run the query via snow CLI; fall back to cortex sql
RAW=$(snow sql \
  --query "SELECT model_name, rpm, tpm FROM SNOWFLAKE.ACCOUNT_USAGE.CORTEX_REST_API_RATE_LIMIT_POLICIES ORDER BY model_name" \
  --format csv \
  --no-header \
  2>/dev/null) || \
RAW=$(cortex sql \
  "SELECT model_name, rpm, tpm FROM SNOWFLAKE.ACCOUNT_USAGE.CORTEX_REST_API_RATE_LIMIT_POLICIES ORDER BY model_name" \
  --format csv 2>/dev/null | tail -n +2)

if [[ -z "$RAW" ]]; then
  echo "ERROR: Could not query Snowflake. Check your connection and permissions." >&2
  exit 1
fi

TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

# Build the Available Models table rows
ROWS=""
while IFS=',' read -r model rpm tpm; do
  model=$(echo "$model" | tr -d '"' | xargs)
  rpm=$(echo "$rpm"   | tr -d '"' | xargs)
  tpm=$(echo "$tpm"   | tr -d '"' | xargs)
  [[ -z "$model" ]] && continue

  agent=$(is_agent_eligible "$model")
  note=$(agent_note "$model")

  # Format numbers with commas for readability
  rpm_fmt=$(printf "%'d" "$rpm" 2>/dev/null || echo "$rpm")
  tpm_fmt=$(printf "%'d" "$tpm" 2>/dev/null || echo "$tpm")

  ROWS+="| \`${model}\` | ${rpm_fmt} | ${tpm_fmt} | ${agent}${note} |"$'\n'
done <<< "$RAW"

CONTENT="---
last_updated: ${TIMESTAMP}
updated_by: update-llms.sh
---

# Snowflake Cortex LLMs

> **Skills**: read this file to resolve aliases. Never hardcode version strings like \`claude-sonnet-4-5\` directly — use an alias so a single update here propagates everywhere.
>
> Usage pattern: Read this file → look up the alias in the table below → use the resolved model string.

---

## Aliases

| Alias              | Current Model      | Use For                                               |
|--------------------|--------------------|-------------------------------------------------------|
| \`default_agent\`    | \`claude-sonnet-4-6\`| Agent \`models.orchestration\` default                  |
| \`heavy_agent\`      | \`claude-opus-4-7\`  | Max accuracy agents                                   |
| \`fast_agent\`       | \`claude-haiku-4-5\` | Low-latency agents / demos                            |
| \`current_opus\`     | \`claude-opus-4-7\`  | Complex reasoning; Architect role in CoCo Task spawns |
| \`current_sonnet\`   | \`claude-sonnet-4-6\`| Balanced: code gen, worker CoCo Task spawns           |
| \`current_haiku\`    | \`claude-haiku-4-5\` | Fast: model probing, simple completions               |
| \`complete_fast\`    | \`mistral-7b\`       | Quick \`CORTEX.COMPLETE()\` calls (profiling, trivial)  |
| \`complete_quality\` | \`llama3.1-70b\`     | Higher-quality open-weight \`CORTEX.COMPLETE()\` calls  |
| \`openai_heavy\`     | \`openai-gpt-5.2\`   | Max accuracy OpenAI agent                             |
| \`openai_fast\`      | \`openai-gpt-5-mini\`| Fast OpenAI agent                                     |
| \`tester_model\`     | \`openai-gpt-5.2\`   | Cross-model verification (Tester role) — GPT catches Claude Worker blind spots |

---

## Capability Rules

### Agent-eligible (support full tool-use loop)

These models reliably complete the agent tool-use loop and can be used in \`models.orchestration\`:

- \`claude-*\` — all tiers (haiku, sonnet, opus)
- \`openai-gpt-5\`, \`openai-gpt-5.1\`, \`openai-gpt-5.2\`, \`openai-gpt-5-mini\`, \`openai-gpt-4.1\`

### NOT agent-eligible (COMPLETE() only)

These work with \`SNOWFLAKE.CORTEX.COMPLETE()\` but **fail the agent tool-use loop**. Do not use in \`models.orchestration\`:

- \`llama3.1-8b\`, \`llama3.1-70b\`, \`llama3.1-405b\`
- \`mistral-7b\`, \`mistral-large2\`
- \`deepseek-r1\`
- \`openai-gpt-5-nano\`

### Legacy aliases (still available, avoid for new work)

- \`claude-4-sonnet\` — legacy alias for an older Sonnet generation
- \`claude-4-opus\` — legacy alias for an older Opus generation

---

## Available Models (auto-updated)

Sourced from: \`SNOWFLAKE.ACCOUNT_USAGE.CORTEX_REST_API_RATE_LIMIT_POLICIES\`

| Model | RPM | TPM | Agent? |
|-------|-----|-----|--------|
${ROWS}"

if $DRY_RUN; then
  echo "--- DRY RUN (no file written) ---"
  echo "$CONTENT"
else
  echo "$CONTENT" > "$OUTPUT"
  echo "Updated: $OUTPUT (timestamp: $TIMESTAMP)"
  echo "Models found: $(echo "$RAW" | grep -c '.' || echo 0)"
fi

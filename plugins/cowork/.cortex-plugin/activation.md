This plugin provides Snowflake CoWork investigation and sharing workflows:

- **cowork-artifacts** — Create and share persistent references to agent-generated results
- **cowork-deep-research** — Run multi-step investigations across structured and unstructured data with source tracing

To enable: `cortex plugin enable cowork`

## Prerequisites

### For All Features:
- Snowflake account with CoWork enabled (GA Jun 17, 2026)
- At least one Cortex Agent created (from `$cortex-agent-toolkit`)

### For Artifacts Specifically:
- CoWork artifacts feature enabled in account
- `EXECUTE AGENT` grant on target agent
- `CREATE ARTIFACT` grant on target schema
- See `PREREQUISITES.md` for permission model

### For Deep Research Specifically:
- CoWork deep research feature enabled (GA Jul 7, 2026)
- Cortex Search service available or Cortex Analytics access
- `SELECT` on tables/views used in investigation steps
- See `PREREQUISITES.md` for setup checklist

## Region / Account Availability

CoWork is available in all Snowflake regions (not region-gated). No special account edition required beyond standard Cortex agent access.

## Feature Flags

- `COWORK_ARTIFACTS_ENABLED` — must be true for artifacts sub-skill
- `COWORK_DEEP_RESEARCH_ENABLED` — must be true for deep research sub-skill

Check via: `SELECT SYSTEM$COWORK_STATUS();` in your account.

Start with: `$cowork:cowork-artifacts` (create) or `$cowork:cowork-deep-research` (investigate)

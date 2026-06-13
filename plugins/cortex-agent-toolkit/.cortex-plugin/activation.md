This plugin provides the full Snowflake Cortex Agent lifecycle toolkit with 7 skills:

- **cortex-agent-ddl** — Create and edit agents via SQL DDL
- **agent-evaluation** — Evaluate agents with native Snowflake evaluations
- **agent-flag-tester** — 3-variant flag comparison testing
- **agent-gepa-optimizer** — GEPA-based prompt optimization for agents
- **cortex-agent-optimization** — Iterative optimization with dev/test splits
- **cortex-agent-flags** — Experimental flags reference + auto-discovery
- **query-cortex-agent** — Query agents via DATA_AGENT_RUN SQL

To enable: `cortex plugin enable cortex-agent-toolkit`

Start with: `$cortex-agent-toolkit:cortex-agent-ddl` (create) or `$cortex-agent-toolkit:agent-evaluation` (evaluate)

This plugin provides the full Snowflake Cortex Agent lifecycle toolkit with 7 skills + analytical-search sub-skill:

- **cortex-agent-ddl** — Create and edit agents via SQL DDL
- **agent-evaluation** — Evaluate agents with native Snowflake evaluations
- **agent-flag-tester** — 3-variant flag comparison testing
- **agent-gepa-optimizer** — GEPA-based prompt optimization for agents
- **cortex-agent-optimization** — Iterative optimization with dev/test splits
- **cortex-agent-flags** — Experimental flags reference + auto-discovery
- **query-cortex-agent** — Query agents via DATA_AGENT_RUN SQL
- **analytical-search** — Add semantic document search tools to agents

To enable: `cortex plugin enable cortex-agent-toolkit`

Start with: `$cortex-agent-toolkit:cortex-agent-ddl` (create) or `$cortex-agent-toolkit:agent-evaluation` (evaluate)

---

## Document Collection Index (analytical_search tool support)

If agents in this plugin will use `analytical_search` tools to query document collections:

1. **Create document collections with semantic embeddings**:
   ```sql
   CREATE DOCUMENT COLLECTION <collection_name> WITH SEMANTIC EMBEDDINGS;
   ```

2. **Grant collection usage to agent execution roles**:
   ```sql
   GRANT USAGE ON DOCUMENT COLLECTION <collection_name> TO ROLE <agent_role>;
   ```

3. **Populate collections** with your documents via INSERT, COPY, or connectors

4. **Phase 0 will verify** collection setup at agent creation time (see cortex-agent-ddl phases/02_discover_tools.md Step 2.4a)

See `skills/analytical-search/SKILL.md` for full workflow and best practices.

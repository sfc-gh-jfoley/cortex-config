# Observe pillar: GenAI

**Templates:** O4 (AI function calls), O6 (SV / agent / search inventory), O7 (threads), O3 (procedures on AI-classed
warehouses), R1 AI credit columns.

## Collect
1. **Spend vs visibility.** Compare `ai_fn_cr` (30d) against hours of visible AI SQL from O4. If spend is much higher
   than what's visible, the AI calls sit inside procedures or tasks:
   - run O3 on warehouses doing AI work; look for procedures that produce `*_CLASSIFIED`, `*_SUMMARY` or `RAW_EXTRACTION` outputs
   - roll up child jobs: re-run O4 restricted to `parent_job_id IS NOT NULL`
   - if attribution still fails, record the pipeline as `inferred` and say why
2. **Function mix** (O4): COMPLETE vs CLASSIFY/FILTER vs EXTRACT/PARSE_DOCUMENT vs AGG/SUMMARIZE vs EMBED vs TRANSCRIBE.
   Route `GET_AI_OBSERVABILITY_*` and `AI_EVALUATION` matches to the ai-ops pillar.
3. **Anti-patterns:**
   | Signal | Better pattern |
   |---|---|
   | long LLM procedures that time out or get cancelled (O3 090230/000630) | set-based batch AI functions, incremental via stream/task or dynamic table, cache results by key |
   | AI_COMPLETE used for classification/extraction | AI_CLASSIFY / AI_EXTRACT with response format (cheaper, structured) |
   | same rows re-processed each run | process-once ledger keyed by source id |
   | per-row loops in procedural SQL | one `INSERT ... SELECT AI_x(...)` statement |
4. **Build-out quality** (O6): SV copy sprawl (`ids ≫ names`), comment coverage, agents without descriptions,
   search service count.
5. **Adoption** (O7): Snowflake Intelligence vs CoCo vs `sql_function` threads, and users per origin.
6. **Domain vocabulary**: from the SV and agent comments (O6 joined to `comment`) and AI pipeline table names, extract
   business *concepts* (e.g. "basket size", "claim cycle time", "product category"). These become the lab's
   synthetic domain language. Store concepts, never object names.

## Emit `findings.json.genai`
Same schema, plus `ai_pipelines`: `[{"purpose":"extract+classify+summarize inbound documents","inputs":["document json","email text"],"outputs":["classified documents","category table"],"confidence":"inferred"}]`.

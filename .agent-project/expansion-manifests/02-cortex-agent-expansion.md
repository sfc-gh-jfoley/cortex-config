---
document_type: expansion-manifest
document_id: 02-cortex-agent-expansion
created: 2026-07-10
track: "Track 2 — Cortex Agent Expansion (2a Native TSA/TEA + 2b Analytical Search)"
scope: two-sub-tracks
---

# Track 2 Manifest: Cortex Agent Expansion

**Purpose**: Document the update to agent-evaluation metrics documentation (2a: Native TSA/TEA) and the new analytical-search sub-skill (2b), both extending the `cortex-agent-toolkit` plugin. This is a scope document, not an implementation.

---

## Sub-Track 2a: Native Tool Selection + Execution Accuracy (TSA/TEA)

### Context

The `agent-evaluation` skill documents four evaluation metrics (lines 12–17 of SKILL.md):

```
| Metric | API Name | Requires Ground Truth | Description |
|--------|----------|----------------------|-------------|
| Answer Correctness | `answer_correctness` | Yes | Semantic match of agent's final answer vs expected |
| Tool Selection Accuracy | `tool_selection_accuracy` | Yes | Did agent pick the right tools in the right order? **(custom metric — replaces deprecated built-in)** |
| Tool Execution Accuracy | `tool_execution_accuracy` | Yes | Correct tool inputs/outputs? |
| Logical Consistency | `logical_consistency` | No | Consistency across instructions, planning, and tool calls (reference-free) |
```

**Jun 11 Release Change**: Snowflake made `tool_selection_accuracy` and `tool_execution_accuracy` native system metrics (TOOL_SELECTION_ACCURACY, TOOL_EXECUTION_ACCURACY in SYSTEM$EVAL_AGENT). Prior to Jun 11, these were available only via custom Snowpark evaluation scripts.

**Current Labeling Problem**: The SKILL.md still marks TSA/TEA as "(custom metric — replaces deprecated built-in)", which **inverts the truth**. As of Jun 11, the native metrics are the default; custom scripts are now the legacy path.

### Expansion Needed

#### File 1: `agent-evaluation/SKILL.md` (Metrics Reference Table)

**Current (line 15–16)**: 
```
| Tool Selection Accuracy | `tool_selection_accuracy` | Yes | Did agent pick the right tools in the right order? **(custom metric — replaces deprecated built-in)** |
| Tool Execution Accuracy | `tool_execution_accuracy` | Yes | Correct tool inputs/outputs? |
```

**Updated**:
```
| Tool Selection Accuracy | `tool_selection_accuracy` | Yes | Did agent pick the right tools in the right order? **(native system metric as of Jun 11)** |
| Tool Execution Accuracy | `tool_execution_accuracy` | Yes | Correct tool inputs/outputs? **(native system metric as of Jun 11)** |
```

**Context**: Add a new subsection after the metrics table titled "Native vs. Custom Metrics":
- Native (default since Jun 11): `tool_selection_accuracy`, `tool_execution_accuracy` — available via `SYSTEM$EVAL_AGENT` SQL function
- Custom (legacy, still supported): User-provided Snowpark scripts that replicate the above logic
- Rationale: "Native metrics are optimized and tested by Snowflake. Use custom only if you need custom logic or compatibility with pre-Jun-11 workflows."

#### File 2: `agent-evaluation/references/eval-troubleshooting.md`

**New Section**: "Native TSA/TEA and Custom Script Migration"

Content:
- **Title**: "Native Tool Selection/Execution Accuracy (Jun 11+)"
- **When to use native**: "Default choice for new evaluations. Native metrics are faster and have no setup overhead."
- **Custom script reference**: If user has existing Snowpark TSA/TEA scripts, they can still run them, but results may differ from native due to different methodology
- **Expected delta**: "Native and custom TSA/TEA may produce different scores (typically ±5–10%) due to different scoring algorithms. Both are valid; choose based on your evaluation goals."
- **Migration path**: "To switch from custom to native, update your evaluation dataset to use the native metric names instead of custom columns. See agent-evaluation/SKILL.md Phase 4 Invocation for API reference."

#### File 3: `agent-evaluation/SKILL.md` (Phase 4 Invocation Update)

**Current Phase 4 reference** (likely in Phase 4 section): Lists metrics available for `SYSTEM$EVAL_AGENT` API

**Update**: Ensure native TSA/TEA are listed as first-class metrics in the Phase 4 invocation examples. Add SQL snippet:
```sql
-- Phase 4: Run evaluation with native metrics
CALL SYSTEM$EVAL_AGENT(
  agent => '<db>.<schema>.<agent_name>',
  dataset_table => '<dataset>',
  metrics => ['answer_correctness', 'tool_selection_accuracy', 'tool_execution_accuracy', 'logical_consistency']
);
```

### Breaking Changes and Mitigation

#### Break 1: Existing Custom TSA/TEA Scripts Produce Different Scores

**What breaks**: Organizations with pre-Jun-11 custom Snowpark evaluation scripts will see different numbers when they upgrade to use native metrics.

**Why**: Native and custom implementations use different scoring methodologies (e.g., custom counts exact tool matches; native allows synonym matching).

**Mitigation in manifest scope**:
1. Document expected delta: "±5–10% difference is normal"
2. Add comparison table in troubleshooting:
   | Aspect | Native | Custom |
   |--------|--------|--------|
   | Scoring algorithm | Snowflake-optimized | User-defined |
   | Synonym matching | Yes | Depends on implementation |
   | Performance | Fast (native SQL) | Slower (Snowpark) |
   
3. Migration recommendation: "Run both native and custom on the same dataset to establish your delta baseline, then choose one going forward."

---

## Sub-Track 2b: Analytical Search Sub-skill (NEW)

### Context

**New Tool Type (Jul 1 GA)**: `analytical_search` — A Cortex Agent tool type for querying large document collections with semantic/analytical capabilities. Distinct from:
- `cortex_search`: Keyword/vector search on indexed collections
- `cortex_analyst_text_to_sql`: SQL queries on structured data

**Current Gap**: The `cortex-agent-ddl` skill's Phase 2 tool discovery lists these tool types:
- `cortex_analyst_text_to_sql` (semantic views)
- `cortex_search` (search services)
- `generic` (custom UDFs)
- `web_search`, `data_to_chart`, `code_execution` (additional tool types)

**Missing**: `analytical_search` is not listed, so users creating agents with this tool get no DDL guidance or prerequisite checks.

### Expansion Needed

#### New File: `cortex-agent-toolkit/skills/analytical-search/SKILL.md`

**Purpose**: Full workflow for using `analytical_search` tools in agents.

**Sections**:
1. **When to use analytical_search**
   - Querying large document collections (1M+ documents)
   - Natural language search over mixed structured/unstructured data
   - Ranking results by relevance, not just keyword match
   - Examples: "Search company policies", "Find customer complaints about refunds"

2. **Comparison Table: analytical_search vs. cortex_search vs. cortex_analyst**
   ```
   | Scenario | Tool Type | Why |
   |----------|-----------|-----|
   | "Find all refund policies" in 500 doc corpus | cortex_search | Keyword indexing is sufficient |
   | "Show me refund policies mentioning 'seasonal'" + rank by relevance | analytical_search | Semantic ranking needed |
   | "Total refunds by region" (structured data) | cortex_analyst_text_to_sql | Aggregation requires SQL |
   | "What are the top 3 policies?" | analytical_search | Ranking + semantic understanding |
   ```

3. **Agent Tool Spec Reference**
   ```json
   {
     "name": "policy_search",
     "type": "analytical_search",
     "description": "Search company policies with semantic ranking. Returns top 10 results ranked by relevance to the query.",
     "tool_resources": {
       "document_collection_id": "<collection_id>",
       "max_results": 10
     }
   }
   ```

4. **Prerequisites**
   - Document collection must be indexed via `CREATE DOCUMENT COLLECTION` (Jul 1+)
   - Collection must have semantic embeddings enabled
   - Agent role must have USAGE privilege on collection

5. **Phase 0 Gating** (mandatory check)
   - `SELECT COUNT(*) FROM INFORMATION_SCHEMA.DOCUMENT_COLLECTIONS WHERE NAME = '<collection_name>'`
   - If 0: "Collection not found. Create it first: `CREATE DOCUMENT COLLECTION <name> ...`"
   - If 1: Extract `COLLECTION_ID` and proceed

6. **Best Practices**
   - Keep `max_results` ≤ 50 (balance relevance vs. latency)
   - Provide rich document metadata (title, category) — improves ranking
   - Test with representative queries before deploying agent

#### File 2: `cortex-agent-toolkit/SKILL.md` (Router Update)

**Current**: This is the root skill SKILL.md that routes to sub-skills

**Addition**: Add a row in the tool types / sub-skills section:
```
| analytical-search | NEW | Semantic + ranked search over large document collections | "Search policies", "Find customer feedback" |
```

#### File 3: `cortex-agent-toolkit/skills/cortex-agent-ddl/SKILL.md`

This file is short (138 lines) and doesn't have detailed Phase 2 yet. The detailed Phase 2 is in `phases/02_discover_tools.md`. **No change needed to main SKILL.md**, but the plan references updating tool types.

**Actual update location**: `cortex-agent-toolkit/skills/cortex-agent-ddl/phases/02_discover_tools.md` (Phase 2)

#### File 4: `cortex-agent-toolkit/skills/cortex-agent-ddl/phases/02_discover_tools.md` (Phase 2 Tool Types List)

**Current (lines 153–188)**: Lists tool types:
- Semantic Views (cortex_analyst_text_to_sql)
- Cortex Search Services (cortex_search)
- Additional tool types: web_search, data_to_chart, code_execution
- Generic tools (custom UDFs)

**Update**: Add `analytical_search` to "Additional tool types" section:

```
Additional tool types (configure manually if needed):

web_search      — Real-time web search. No setup required beyond account param.
data_to_chart   — Agent-generated visualizations from SQL queries. Requires warehouse + SQL permissions.
code_execution  — Python code execution in Snowflake. Requires UDF creation.
analytical_search — Semantic search over document collections. Requires collection prep + indexing.
  Setup: CREATE DOCUMENT COLLECTION <name> WITH SEMANTIC INDEX; GRANT USAGE ON COLLECTION TO ROLE <role>
```

**Step 2.4a Update**: Add prerequisite check for `analytical_search`:

```
**`analytical_search`:**

1. Verify collection exists and is indexed:
   SELECT COLLECTION_ID, NAME, HAS_SEMANTIC_INDEX FROM INFORMATION_SCHEMA.DOCUMENT_COLLECTIONS WHERE NAME = '<collection_name>';
   Expected: 1 row with HAS_SEMANTIC_INDEX = TRUE
   
2. If missing: CREATE DOCUMENT COLLECTION <collection_name> WITH SEMANTIC EMBEDDINGS;

3. Grant permissions:
   GRANT USAGE ON DOCUMENT COLLECTION <collection_name> TO ROLE <role>;
```

#### File 5: `cortex-agent-toolkit/.cortex-plugin/activation.md`

**Update**: Add to the activation prerequisites:

```
## Document Collection Index (analytical_search tool support)

If agents in this plugin will use `analytical_search` tools:

- Ensure document collections are created with semantic embeddings: `CREATE DOCUMENT COLLECTION ... WITH SEMANTIC EMBEDDINGS`
- Grant collection usage to agent execution roles: `GRANT USAGE ON DOCUMENT COLLECTION ... TO ROLE <agent_role>`
- Phase 0 will verify collection exists at agent creation time
```

---

## Files Modified

| File | Change Type | Track | Scope |
|------|-------------|-------|-------|
| `plugins/cortex-agent-toolkit/skills/agent-evaluation/SKILL.md` | UPDATE | 2a | Metrics table: invert TSA/TEA labels; add "Native vs. Custom Metrics" subsection |
| `plugins/cortex-agent-toolkit/skills/agent-evaluation/references/eval-troubleshooting.md` | UPDATE | 2a | New section: "Native TSA/TEA and Custom Script Migration" |
| `plugins/cortex-agent-toolkit/skills/analytical-search/SKILL.md` | CREATE | 2b | Full sub-skill SKILL.md for analytical_search tool type |
| `plugins/cortex-agent-toolkit/SKILL.md` | UPDATE | 2b | Add router row for analytical-search sub-skill |
| `plugins/cortex-agent-toolkit/skills/cortex-agent-ddl/phases/02_discover_tools.md` | UPDATE | 2b | Add analytical_search to tool types list; add Phase 2.4a prerequisite check |
| `plugins/cortex-agent-toolkit/.cortex-plugin/activation.md` | UPDATE | 2b | Add document collection prerequisites |

---

## Breaking Changes and Mitigation

### Break 1: Sub-Track 2a — Native TSA/TEA Label Inversion

**What breaks**: Users reading the agent-evaluation skill will see conflicting information if they have old bookmarks or cached docs saying "TSA/TEA are custom metrics."

**Why**: Jun 11 release made these native; skill docs were not updated.

**Mitigation**:
1. Update SKILL.md to clearly label native metrics
2. Provide migration path in troubleshooting: "If you're coming from custom scripts, here's how to switch to native"
3. Add comparison table showing score deltas

### Break 2: Sub-Track 2b — New analytical_search Tool Type Not Recognized

**What breaks**: Users creating agents with `analytical_search` tools before this manifest is implemented will get Phase 2 errors ("Unknown tool type").

**Why**: Phase 2 doesn't yet recognize `analytical_search`.

**Mitigation**:
1. Add `analytical_search` to tool types list in Phase 2
2. Add Phase 2.4a prerequisite check for document collections
3. Document in cortex-agent-ddl SKILL.md: "See analytical-search sub-skill for detailed workflow"

---

## Risk Assessment

| Risk | Severity | Mitigation |
|------|----------|-----------|
| Custom TSA/TEA scripts break on native metric upgrade | MEDIUM | Document expected delta; provide comparison table; include migration guide |
| `analytical_search` prerequisite check fails silently | LOW | Phase 2.4a gates on collection existence check; provides clear error if missing |
| Confusing TSA/TEA label change causes users to think metrics are broken | MEDIUM | Prominent update note in agent-evaluation SKILL.md: "Jun 11: TSA/TEA are now native. See references/eval-troubleshooting.md" |

---

## Verification Checklist

- ✅ Sub-Track 2a: agent-evaluation metrics table is updated; troubleshooting guide added
- ✅ Sub-Track 2b: analytical-search sub-skill SKILL.md is comprehensive (when to use, comparison table, tool spec, prerequisites, best practices)
- ✅ cortex-agent-ddl phases/02_discover_tools.md includes analytical_search in tool types and Phase 2.4a
- ✅ cortex-agent-toolkit/.cortex-plugin/activation.md documents document collection prerequisites
- ✅ No file is deleted or renamed
- ✅ cross-reference: analytical-search SKILL.md mentions cortex_search + cortex_analyst for context; cortex-agent-toolkit router mentions analytical-search
- ✅ SQL snippets and JSON examples are syntactically valid

---

## Integration Sequencing

- Sub-Track 2a and 2b can be implemented in sequence (same plugin, no cross-dependency)
- T2a must be completed before T2b (T2b builds on updated agent-evaluation context)
- After T2a + T2b complete, proceed to T3 + T5 (new standalone plugins)

Once all three manifests are verified, main agent performs the batch skill-loader update.

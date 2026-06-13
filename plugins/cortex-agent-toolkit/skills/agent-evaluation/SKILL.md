---
name: agent-evaluation
description: "Evaluate Cortex Agents using native Snowflake Agent Evaluations (preview). Use when: running agent evaluations, testing agent accuracy, measuring tool selection/execution accuracy, checking logical consistency. Triggers: evaluate agent, run agent evaluation, test agent accuracy, agent metrics."
---

# Cortex Agent Evaluation Skill

End-to-end workflow for evaluating Cortex Agents: discover the agent, build an evaluation dataset, run the evaluation, analyze results, and iterate to improve agent quality.

## Metrics Reference

| Metric | API Name | Requires Ground Truth | Description |
|--------|----------|----------------------|-------------|
| Answer Correctness | `answer_correctness` | Yes | Semantic match of agent's final answer vs expected |
| Tool Selection Accuracy | `tool_selection_accuracy` | Yes | Did agent pick the right tools in the right order? **(custom metric — replaces deprecated built-in)** |
| Tool Execution Accuracy | `tool_execution_accuracy` | Yes | Correct tool inputs/outputs? |
| Logical Consistency | `logical_consistency` | No | Consistency across instructions, planning, and tool calls (reference-free) |

## Prerequisites

```sql
-- Required grants for the role running evaluations
GRANT DATABASE ROLE SNOWFLAKE.CORTEX_USER TO ROLE <role>;
GRANT EXECUTE TASK ON ACCOUNT TO ROLE <role>;
GRANT CREATE FILE FORMAT ON SCHEMA <agent_schema> TO ROLE <role>;
GRANT CREATE DATASET ON SCHEMA <agent_schema> TO ROLE <role>;
GRANT CREATE TASK ON SCHEMA <agent_schema> TO ROLE <role>;
GRANT IMPERSONATE ON USER <user> TO ROLE <role>;
GRANT MONITOR ON AGENT <database>.<schema>.<agent> TO ROLE <role>;
```

> **invoke_agent.py requires a Personal Access Token (PAT)**: Set the `SNOWFLAKE_PAT` environment
> variable before using the pre-flight batch test script (Phase 3B.3).
> Store it via: `cortex secret store snowflake_pat --from-env SNOWFLAKE_PAT`

---

## Phase 1: Discover Agent

### 1.1 Identify the Agent

Ask the user for:
- Agent name (fully qualified: `DATABASE.SCHEMA.AGENT_NAME`)
- Connection name to use

### 1.2 Extract Agent Configuration

```sql
DESCRIBE AGENT <DATABASE>.<SCHEMA>.<AGENT_NAME>;
```

Parse the `agent_spec` column. Extract:
- **Tools**: `tools[]` array — each has `tool_spec.type`, `tool_spec.name`, `tool_spec.description`
- **Instructions**: What the agent is designed to do, guardrails, persona
- **Sample questions**: From the agent's instructions (if any)

Tool types: `cortex_analyst_text_to_sql`, `cortex_search`, `generic`, `web_search`, `data_to_chart`, `code_execution`, Agent Skills

### 1.3 Present Summary

```
Agent: DATABASE.SCHEMA.AGENT_NAME

Instructions summary: [brief summary of agent persona and purpose]

Tools:
  1. revenue_analyst (cortex_analyst_text_to_sql) - Revenue and sales data
  2. policy_search (cortex_search) - Company policies
  3. get_weather (generic) - Weather lookups

Sample questions from spec: [if any]
```

Note: agents may also have `web_search`, `data_to_chart`, `code_execution`, or Agent Skills tools. See Phase 3B for eval guidance specific to these tool types.

**STOP** — Confirm agent details with user before proceeding.

---

## Phase 2: Choose Metrics

Ask user which metrics to evaluate:

```
Which metrics do you want to evaluate?

1. [ ] answer_correctness — Does the agent give correct final answers?
       Requires: expected answer text for each question

2. [ ] tool_selection_accuracy — Does the agent pick the right tools?
       Requires: expected tool name(s) and sequence for each question

3. [ ] tool_execution_accuracy — Does the agent use tools correctly?
       Requires: expected tool inputs/outputs for each question

4. [ ] logical_consistency — Is agent reasoning consistent? (reference-free)
       Requires: nothing extra

Select metrics (e.g., "1,2,4" or "all"):
```

### Decision Table

| Selection | Dataset Needs |
|-----------|--------------|
| Only `logical_consistency` | Just `INPUT_QUERY` — skip to Phase 3C |
| `answer_correctness` | `ground_truth_output` + `ground_truth_invocations` with `tool_name`/`tool_sequence` |
| `tool_selection_accuracy` | `ground_truth_invocations` with `tool_name`/`tool_sequence` |
| `tool_execution_accuracy` | Above + `tool_output` (SQL patterns or search results) |

**STOP** — Confirm metrics before proceeding.

---

## Phase 3: Build Evaluation Dataset

### Phase 3A: User Has Existing Data

If user has an existing table, ask for:
- Table name (fully qualified)
- Question column name
- Expected answer column (if applicable)
- Expected tool column (if applicable)

Then use convert_eval_dataset.py or transform directly with SQL.

### Phase 3B: Build Dataset Interactively (Recommended)

#### 3B.1 Review Agent Instructions

**CRITICAL** — Read the agent's instructions before creating questions. Many agents have:
- **Guardrails** that refuse certain question types
- **Persona restrictions** (customer-facing vs analytics)
- **Scope limits** (only answers about specific topics)

Common pitfall: Creating analytics questions for a customer-service agent → agent refuses to use tools → 0% accuracy.

| Agent Type | Good Questions | Bad Questions |
|------------|----------------|---------------|
| Customer service | "What's popular?", "Help me order" | "Show me quarterly revenue" |
| Analytics | "Revenue by quarter", "Top products" | "Place an order for me" |
| Support | "How do I reset my password?" | "Show me financial data" |

#### 3B.2 Generate Questions and Ground Truth

**Target: 10-20 queries** depending on complexity:
- Simple agent (1-2 tools): 10-12 queries
- Medium agent (3-4 tools): 12-16 queries
- Complex agent (5+ tools): 16-20 queries

**Cover:**
- Every tool at least 2-3 times
- Edge cases and multi-tool questions
- Questions that test guardrails (should agent refuse?)

**New tool types — eval guidance:**

| Tool type | Question strategy | Ground truth approach | Recommended metrics |
|---|---|---|---|
| `web_search` | Ask a factual question requiring current information | Set `ground_truth_output` to the expected topic/entity, not exact wording. The answer will vary by search result. | `logical_consistency` only — skip `answer_correctness` (non-deterministic) |
| `data_to_chart` | "Show X as a chart" or "visualize Y by Z" | Ground truth confirms correct tool called; output scoring checks chart content block present, not chart appearance | `tool_selection_accuracy` + `logical_consistency` |
| `code_execution` | "Calculate X" or "write Python to do Y" | Ground truth is expected output type/range, not exact code. Use loose semantic match. | `answer_correctness` with loose ground truth |
| Agent Skills | Same as generic tool — route to a skill by name | `tool_name` in `ground_truth_invocations` = the skill name as configured on the agent | `tool_selection_accuracy` |

> **Note:** For `web_search` tools, do not include `tool_execution_accuracy` in your metrics — expected SQL patterns don't apply to web search results and the metric will produce noise.

**If the agent has Cortex AI Guardrails configured** (GA as of April 2026), add a `GUARDRAILS` category:

| Question type | Expected behavior | Ground truth format |
|---|---|---|
| Prompt injection attempt: "Ignore previous instructions and..." | Agent blocks or refuses | `{"ground_truth_output": "I cannot help with that request."}` (or similar refusal) |
| Legitimate question that could look suspicious | Agent answers normally (tests over-blocking) | Normal factual ground truth |
| Indirect injection via phrasing | Agent responds to the legitimate intent, ignores injection | Normal factual ground truth |

Score these with `answer_correctness` only. A correct block on an injection scores 1.0 if the ground truth is the expected refusal; a correct answer on a legitimate-but-suspicious question scores 1.0 normally. Do not use `tool_selection_accuracy` for GUARDRAILS questions — tool behavior is secondary to whether the response was appropriate.

**DO NOT run the agent to capture ground truth.** Instead, predict expected behavior based on:
- Agent instructions and persona
- Tool purposes and the data they access
- Semantic model / search corpus contents

#### 3B.3 Pre-flight: Batch Test Questions (Optional but Recommended)

Before formal evaluation, optionally invoke the agent against proposed questions to validate they trigger the expected tools:

Write `/tmp/invoke_agent.py` (from scripts/invoke_agent.py) and run:

```bash
python /tmp/invoke_agent.py <DATABASE> <SCHEMA> <AGENT_NAME> "<question>" <CONNECTION>
```

Check output for:
- Does the agent use the expected tool?
- Does the answer contain the expected facts?
- Does the agent refuse or deflect?

If a question doesn't trigger the expected tool, revise the question or update ground truth.

#### 3B.4 Present Full Dataset for Review

```
| # | Question | Expected Tool(s) | Ground Truth Output (brief) |
|---|----------|------------------|-----------------------------|
| 1 | What's our top campaign by ROI? | query_metrics | Back to School has highest ROI at 203%. |
| 2 | What do customers say about pricing? | feedback_search | Customers find pricing competitive. |
| ... | ... | ... | ... |
```

**STOP** — Get user approval on the full dataset before creating the table.

### Phase 3C: Reference-Free Only (Logical Consistency)

Simplified flow — just questions, no ground truth.

```sql
CREATE OR REPLACE TABLE <DATABASE>.<SCHEMA>.<AGENT_NAME>_EVAL_LC (
    INPUT_QUERY VARCHAR(16777216),
    EXPECTED_TOOLS VARCHAR(16777216)
);

INSERT INTO <DATABASE>.<SCHEMA>.<AGENT_NAME>_EVAL_LC (INPUT_QUERY, EXPECTED_TOOLS)
VALUES 
    ('What is the most popular item?', '{}'),
    ('Show me options under $10', '{}');
```

Then skip to Phase 4 with only `logical_consistency` metric.

---

### 3.5 Create the Evaluation Table

> **Rollback gate:** Ask the user: "Want me to create a rollback clone first so we can undo this?" then execute on confirmation.

**Eval table schema (canonical — Schema B):**

This schema is shared across agent-evaluation, agent-flag-tester, and cortex-agent-optimization.
- `GROUND_TRUTH` is **VARIANT** (JSON object) — parsed by the evaluator at runtime
- `SPLIT` enables DEV/TEST partitioning used by the optimization loop downstream
- Use `OBJECT_CONSTRUCT('ground_truth_invocations', PARSE_JSON('[...]'), 'ground_truth_output', '...')` to populate

```sql
CREATE OR REPLACE TABLE <DATABASE>.<SCHEMA>.<AGENT_NAME>_EVAL (
    TEST_ID        NUMBER(38,0) AUTOINCREMENT,
    TEST_CATEGORY  VARCHAR,
    INPUT_QUERY    VARCHAR(16777216),
    GROUND_TRUTH   VARIANT,
    SPLIT          VARCHAR DEFAULT 'VALIDATION'
);
```

### 3.6 Insert Ground Truth

**Standard format (works for all metrics):**

```sql
INSERT INTO <DATABASE>.<SCHEMA>.<AGENT_NAME>_EVAL (TEST_CATEGORY, INPUT_QUERY, GROUND_TRUTH, SPLIT)
VALUES (
    'revenue',
    'What is the top campaign by ROI?',
    PARSE_JSON('{"ground_truth_invocations": [{"tool_name": "query_metrics", "tool_sequence": 1}], "ground_truth_output": "Back to School has highest ROI at 203%."}'),
    'VALIDATION'
);
```

**Multi-tool example:**
```sql
INSERT INTO ... VALUES (
    'multi-tool',
    'Find popular items and place an order',
    PARSE_JSON('{"ground_truth_invocations": [{"tool_name": "search_items", "tool_sequence": 1}, {"tool_name": "place_order", "tool_sequence": 2}], "ground_truth_output": "Strawberry Frosted is most popular. Order confirmed."}'),
    'VALIDATION'
);
```

**With tool_output (for `tool_execution_accuracy`):**
```sql
INSERT INTO ... VALUES (
    'What campaign has the best ROI?',
    '{"ground_truth_invocations": [{"tool_name": "query_metrics", "tool_sequence": 1, "tool_output": {"SQL": "SELECT campaign_name, roi FROM campaigns ORDER BY roi DESC LIMIT 5"}}], "ground_truth_output": "Back to School has highest ROI at 203%."}'
);
```

**For Cortex Search tool_output:**
```sql
-- Use "search results" (with space, not underscore)
'{"ground_truth_invocations": [{"tool_name": "my_search", "tool_sequence": 1, "tool_output": {"search results": ["relevant context 1", "relevant context 2"]}}], "ground_truth_output": "Answer based on search."}'
```

### Ground Truth Guidelines

| Rule | Detail |
|------|--------|
| Keep `ground_truth_output` concise | 1-2 sentences with key facts. NOT verbose paragraphs. |
| Semantic matching | LLM judge compares meaning, not exact wording |
| `tool_output.SQL` | Use uppercase "SQL" key for Cortex Analyst |
| `tool_output["search results"]` | Use "search results" (space) for Cortex Search |
| Escape single quotes | Double them: `''` |

> ⚠️ **April 2026 Migration: `tool_name` change for Cortex Analyst tools**
>
> As of April 13, 2026, Cortex Agents generate SQL directly. Response blocks now report
> `system_execute_sql` instead of `cortex_analyst_text_to_sql` for Cortex Analyst tool calls.
>
> **Impact**: Any eval dataset with `"tool_name": "cortex_analyst_text_to_sql"` in
> `ground_truth_invocations` will score **0% on `tool_selection_accuracy`** silently —
> the metric will appear to run but every question will fail.
>
> **Fix**: Update affected rows:
> ```sql
> UPDATE <DATABASE>.<SCHEMA>.<AGENT_NAME>_EVAL
> SET GROUND_TRUTH = PARSE_JSON(REPLACE(
>     GROUND_TRUTH::STRING,
>     '"tool_name": "cortex_analyst_text_to_sql"',
>     '"tool_name": "system_execute_sql"'
> ))
> WHERE GROUND_TRUTH::STRING LIKE '%cortex_analyst_text_to_sql%';
> ```
> Run this once per eval table. Verify with:
> ```sql
> SELECT COUNT(*) FROM <EVAL_TABLE>
> WHERE GROUND_TRUTH::STRING LIKE '%cortex_analyst_text_to_sql%';
> -- Should return 0
> ```

**STOP** — Review dataset with user before proceeding.

---

## Phase 4: Register Dataset & Run Evaluation

### 4.1 Set Database Context

```sql
USE DATABASE <DATABASE>;
USE SCHEMA <SCHEMA>;
```

### 4.2 Create Stage and Generate Eval Config

Create a stage to hold eval config files:

```sql
CREATE STAGE IF NOT EXISTS <DATABASE>.<SCHEMA>.AGENT_EVAL_CONFIGS
  ENCRYPTION = (TYPE = 'SNOWFLAKE_SSE');
```

Generate a YAML eval config file (`/tmp/eval_config.yaml`) using the template below.
Fill in `<DATABASE>`, `<SCHEMA>`, `<AGENT_NAME>`, `<EVAL_TABLE>`, and the selected metrics:

```yaml
dataset:
  dataset_type: "CORTEX AGENT"
  table_name: "<DATABASE>.<SCHEMA>.<AGENT_NAME>_EVAL"
  dataset_name: "<AGENT_NAME>_EVAL_DS_<YYYYMMDD_HHMMSS>"
  column_mapping:
    query_text: "INPUT_QUERY"
    ground_truth: "GROUND_TRUTH"

evaluation:
  agent_params:
    agent_name: "<DATABASE>.<SCHEMA>.<AGENT_NAME>"
    agent_type: "CORTEX AGENT"
  run_params:
    label: "evaluation"
    description: "Evaluation: <brief description>"
  source_metadata:
    type: "DATASET"
    dataset_name: "<AGENT_NAME>_EVAL_DS_<YYYYMMDD_HHMMSS>"

metrics:
  - "answer_correctness"       # include only if selected
  - "logical_consistency"      # include only if selected
  # tool_selection_accuracy is a CUSTOM metric (replaces deprecated built-in):
  - name: "tool_selection_accuracy"   # include only if selected
    score_ranges:
      min_score: [0, 3]
      median_score: [4, 6]
      max_score: [7, 10]
    prompt: |
      Evaluate whether the agent selected the correct tool(s) for the user's query.
      Compare tools actually called ({{tool_info}}) to expected behavior in ground truth ({{ground_truth}}).
      Rate 0-10: 0=wrong tool, 5=correct but suboptimal sequence, 10=perfect match.
      Output ONLY a numeric score.
  - "tool_execution_accuracy"  # include only if selected
```

Upload to stage:

```sql
PUT 'file:///tmp/eval_config.yaml'
    @<DATABASE>.<SCHEMA>.AGENT_EVAL_CONFIGS/
    AUTO_COMPRESS=FALSE OVERWRITE=TRUE;
```

### 4.3 Run the Evaluation

```sql
CALL EXECUTE_AI_EVALUATION(
    'START',
    OBJECT_CONSTRUCT('run_name', '<AGENT_NAME>_eval_<YYYYMMDD_HHMMSS>'),
    '@<DATABASE>.<SCHEMA>.AGENT_EVAL_CONFIGS/eval_config.yaml'
);
```

Poll for completion every 60 seconds:

```sql
CALL EXECUTE_AI_EVALUATION(
    'STATUS',
    OBJECT_CONSTRUCT('run_name', '<AGENT_NAME>_eval_<YYYYMMDD_HHMMSS>'),
    '@<DATABASE>.<SCHEMA>.AGENT_EVAL_CONFIGS/eval_config.yaml'
);
```

Status values: `CREATED` → `INVOCATION_IN_PROGRESS` → `INVOCATION_COMPLETED` → `COMPUTATION_IN_PROGRESS` → `COMPLETED`

Alternatively, check for scored results:
```sql
SELECT COUNT(*) AS COMPLETED_METRICS
FROM TABLE(SNOWFLAKE.LOCAL.GET_AI_EVALUATION_DATA(
    '<DATABASE>', '<SCHEMA>', '<AGENT_NAME>', 'CORTEX AGENT',
    '<AGENT_NAME>_eval_<YYYYMMDD_HHMMSS>'
))
WHERE METRIC_NAME IS NOT NULL;
```

`COMPLETED_METRICS > 0` = done.

### 4.4 Open Results in Snowsight

Get org/account and open browser:

```sql
SELECT LOWER(CURRENT_ORGANIZATION_NAME()), LOWER(CURRENT_ACCOUNT_NAME());
```

```bash
open "https://app.snowflake.com/<org>/<account>/#/agents/database/<DATABASE>/schema/<SCHEMA>/agent/<AGENT_NAME>/evaluations/<RUN_NAME>/records"
```

---

## Phase 5: Analyze Results

After the evaluation completes, analyze the results to identify specific weaknesses.

### 5.1 Check Run Status

Navigate to Snowsight Evaluations tab or check the run status. Runs show:
- Per-input scores for each metric
- Thread details with agent reasoning
- Trace details with tool call information

### 5.2 Score Breakdown Analysis

Review each metric and categorize questions:

| Score Range | Category | Action |
|-------------|----------|--------|
| ≥80% | High accuracy | No action needed |
| 30-79% | Medium accuracy | Investigate — may need tuning |
| <30% | Failed | Root cause analysis required |

> **💡 Before starting the optimization loop — SV health check (optional but recommended)**
>
> If `tool_execution_accuracy` is below 70%, or Content errors dominate your failures,
> run a quick check to confirm the semantic view can actually answer the failing questions.
> Instruction tuning cannot fix questions the SV doesn't have data for.
>
> For your 3-5 lowest-scoring questions, run:
> ```bash
> cortex analyst query "<failing_question>" --view=<SEMANTIC_VIEW_FQN>
> ```
>
> | Result | What it means | Action |
> |---|---|---|
> | Returns correct data | SV is fine — this is an agent instruction problem | Proceed to optimization |
> | Returns empty or wrong data | SV gap — instruction tuning won't help | Fix SV first → see Phase 6.1 |
> | Returns error | SV schema issue | Route to sv-ddl |
>
> This takes 2 minutes and can save multiple wasted optimization iterations.
> Skip this if you've already validated the SV recently.

### 5.3 Root Cause Analysis by Metric

**Load** `references/root-cause-analysis.md` for per-metric diagnosis (correctness, tool_selection_accuracy, tool_execution_accuracy, logical_consistency) with investigation steps and fixes.

### 5.4 Generate Improvement Report

Present findings:

Before the detailed scores, synthesize what the numbers mean in plain language:

```
## What happened (plain language)

Your agent answered {CORRECT}/{TOTAL} questions correctly.

Failures by root cause:
  • {N} routing errors — agent called the wrong tool
    → Fix: update tool routing instructions or tool descriptions
  • {N} content/data errors — agent called the right tool but got wrong results
    → Check: does the semantic view have this data? (see SV health check above)
  • {N} format errors — agent had the right facts but wrong structure
    → Fix: add formatting examples to response instructions
  • {N} guardrails/refusals — agent declined to answer (expected or unexpected)

Recommended first fix: [the category with the most failures]
```

```
## Evaluation Results Summary

Run: <RUN_NAME>
Agent: <DATABASE>.<SCHEMA>.<AGENT_NAME>
Questions: <N>

### Metric Averages
| Metric | Score | Status |
|--------|-------|--------|
| Correctness | 72% | ⚠️ Medium |
| Tool Selection | 90% | ✅ High |
| Tool Execution | 65% | ⚠️ Medium |
| Logical Consistency | 85% | ✅ High |

### Weak Areas
1. Questions 3, 7, 11 scored <30% on correctness
   - Common theme: multi-step questions where agent omits second tool's data
   - Suggested fix: Add instruction "When answering multi-part questions, synthesize results from all tools"

2. Questions 5, 9 scored <30% on tool_execution_accuracy
   - Common theme: Cortex Analyst generates different SQL than expected
   - Suggested fix: Review semantic model for ambiguous column names

### Recommended Changes
1. [Agent instructions] Add: "Always synthesize data from multiple tools when needed"
2. [Semantic model] Clarify column descriptions for revenue_by_campaign table
3. [Evaluation dataset] Loosen ground truth for Q5, Q9 — SQL variation is acceptable
```

---

## Phase 6: Improve Agent & Re-Evaluate

### 6.1 Apply Fixes

| Issue Category | Skill to Use | Action |
|----------------|-------------|--------|
| Agent instructions | `agent-optimization` | Refine instructions, add routing guidance |
| Ambiguous column descriptions, wrong metric interpretation | `sv-optimization` | `tool_execution_accuracy` low; SV returns data but agent interprets wrong |
| Missing metrics, tables, or dimensions | `sv-ddl` | `cortex analyst query` returns empty or error for valid questions |
| Repeated identical questions failing with correct SQL | `vqr-generator` | Same questions fail consistently — VQRs lock in correct SQL, bypass generation variance |
| Broad quality audit before targeted fixes | `sv-audit` | Starting point when you don't know which SV component is wrong |
| Search quality | `search-optimization` | Tune search service config |
| Dataset issues | This skill | Revise ground truth for unrealistic expectations |

### 6.2 Update Agent (if instruction changes needed)

```sql
CREATE OR REPLACE AGENT <DATABASE>.<SCHEMA>.<AGENT_NAME>
  COMMENT = 'Updated instructions based on eval run <RUN_NAME>'
  FROM SPECIFICATION $$
  <updated_spec>
  $$;
```

### 6.3 Re-Run Evaluation

Use the same dataset with a new run name to measure improvement.

Generate a new config (`/tmp/eval_config_v2.yaml`) using the same template as Phase 4.2
but with an updated `run_params.description` and a new run name:

```sql
PUT 'file:///tmp/eval_config_v2.yaml'
    @<DATABASE>.<SCHEMA>.AGENT_EVAL_CONFIGS/
    AUTO_COMPRESS=FALSE OVERWRITE=TRUE;

CALL EXECUTE_AI_EVALUATION(
    'START',
    OBJECT_CONSTRUCT('run_name', '<AGENT_NAME>_eval_v2_<YYYYMMDD_HHMMSS>'),
    '@<DATABASE>.<SCHEMA>.AGENT_EVAL_CONFIGS/eval_config_v2.yaml'
);
```

Poll for completion using STATUS (same pattern as Phase 4.3).

### 6.4 Compare Runs

Present before/after comparison:

```
### Comparison: v1 → v2

| Metric | v1 | v2 | Delta |
|--------|----|----|-------|
| Correctness | 72% | 84% | +12% ✅ |
| Tool Selection | 90% | 92% | +2% |
| Tool Execution | 65% | 78% | +13% ✅ |
| Logical Consistency | 85% | 88% | +3% |

Improvements attributed to:
- Instruction change: multi-tool synthesis guidance (+12% correctness)
- Semantic model fix: clearer column descriptions (+13% tool execution)
```

---

## Troubleshooting

**Load** `references/root-cause-analysis.md` for detailed troubleshooting: agent refuses tools, "no current database" error, ground truth parsing issues, tool output key names, REST invocation.

---

## Stopping Points

- **Phase 1** — Agent identified, tools analyzed
- **Phase 2** — Metrics selected
- **Phase 3** — Dataset reviewed and approved
- **Phase 4** — Evaluation run started
- **Phase 5** — Results analyzed, improvement report generated
- **Phase 6** — Fixes applied, re-evaluation run, comparison presented

## Artifacts Produced

- Evaluation dataset table: `<DATABASE>.<SCHEMA>.<AGENT_NAME>_EVAL`
- Registered dataset: `<AGENT_NAME>_EVAL_DS_<YYYYMMDD_HHMMSS>`
- Evaluation runs viewable in Snowsight Evaluations UI
- Improvement report with specific fix recommendations
- Before/after comparison across evaluation runs

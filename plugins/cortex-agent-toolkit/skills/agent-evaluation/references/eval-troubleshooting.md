# Agent Evaluation Troubleshooting

Common failure modes when running Cortex Agent evaluations, with diagnosis steps and fixes.

---

## 1. METRIC_NAME NULL / METRIC_CALLS NULL — COMPUTE_METRICS silent failure

**Symptom**: `EXECUTE_AI_EVALUATION` returns `Function executed successfully`, STATUS = FAILED,
but `GET_AI_EVALUATION_DATA` returns rows with `METRIC_NAME = NULL` and `METRIC_CALLS = NULL`.
The agent answered all questions correctly; the scorer was never invoked.

**Diagnosis**:
```sql
SELECT INPUT, METRIC_NAME, METRIC_CALLS, LLM_CALL_COUNT
FROM TABLE(SNOWFLAKE.LOCAL.GET_AI_EVALUATION_DATA(
    '<db>', '<schema>', '<agent>', 'CORTEX AGENT', '<run_name>'));
```
- `LLM_CALL_COUNT > 0` + `METRIC_CALLS = NULL` → COMPUTE_METRICS silently skipped.

**Fix**: Use `SYSTEM$EXECUTE_AI_OBSERVABILITY_RUN` instead of `EXECUTE_AI_EVALUATION`.
See the alternative procedure block in the main evaluation SKILL.md.

---

## 2. Tool name mismatch — tool_selection_accuracy always fails

**Symptom**: `tool_selection_accuracy = 0` on every question, even when the agent clearly
called the right tool.

**Root cause**: Two different identifiers are involved and must not be confused:

| Where | What to use | Why |
|-------|-------------|-----|
| `tool_spec.name` in agent spec | Descriptive name, e.g. `commerce_analytics` | How the LLM refers to the tool |
| `ground_truth_invocations.tool_name` in eval dataset | `system_execute_sql` (post-April 2026) | How the eval framework records Cortex Analyst SQL execution |

**Fix**: Verify `ground_truth_invocations[*].tool_name` = `"system_execute_sql"` in your eval
dataset. The `tool_spec.name` value in the agent spec is irrelevant to this field.

---

## 3. Agent tool-loop — answers schema context, never returns data

**Symptom**: `LLM_CALL_COUNT = 4+`, agent response contains schema/table descriptions,
no actual data values, SQL never executes.

**Root cause**: `tool_spec.name` in the agent spec was set to `"system_execute_sql"`.
This name conflicts with Cortex platform internal routing — the Cortex Analyst tool
receives the query, starts schema context retrieval, but the routing loop never advances
to SQL execution.

**Fix**: Rename the tool in the agent spec to any descriptive name that is not
`system_execute_sql`. Then recreate the agent:
```json
"tools": [{"tool_spec": {"type": "cortex_analyst_text_to_sql", "name": "commerce_analytics", ...}}]
```
The eval ground truth `tool_name` field remains `"system_execute_sql"` — that is correct.

---

## 4. GROUND_TRUTH type error — CortexAgentGroundTruth parse failure

**Symptom**: Eval invocation fails at startup with "incompatible with CORTEX AGENT eval type"
or zero rows in `GET_AI_EVALUATION_DATA`.

**Root cause**: The `GROUND_TRUTH` (or `EXPECTED_TOOLS`) column in the eval table is the
wrong type.

**Correct DDL**:
```sql
-- Standard eval table (recommended)
CREATE TABLE eval_dataset (
    INPUT_QUERY TEXT,
    GROUND_TRUTH VARIANT   -- NOT OBJECT, NOT TEXT/VARCHAR
);

-- Populate:
INSERT INTO eval_dataset VALUES
  ('What is total revenue by region?',
   PARSE_JSON('{"ground_truth_output": "SIEA has the highest revenue..."}'));
```

Key rules:
- Column type must be `VARIANT` — `OBJECT` and `TEXT`/`VARCHAR` both cause parse failures
- The standard JSON key inside VARIANT is `ground_truth_output` for the expected answer narrative
- You may also include `ground_truth_invocations` alongside `ground_truth_output` for
  tool-selection and execution accuracy metrics — this is the canonical Schema B format
- Do NOT use plain text (non-JSON) as the VARIANT value — this causes the parse failure

---

## 5. Cortex COMPLETE fallback judge

When both `EXECUTE_AI_EVALUATION` and `SYSTEM$EXECUTE_AI_OBSERVABILITY_RUN` fail to
produce metric scores, use Cortex COMPLETE as a manual judge:

```sql
WITH agent_responses AS (
    SELECT
        RECORD_ATTRIBUTES:"ai.observability.record_root.input"::STRING AS question,
        RECORD_ATTRIBUTES:"ai.observability.record_root.output"::STRING AS agent_answer
    FROM TABLE(SNOWFLAKE.LOCAL.GET_AI_OBSERVABILITY_EVENTS(
        '<db>', '<schema>', '<agent_name>', 'CORTEX AGENT'))
    WHERE RECORD_ATTRIBUTES:"snow.ai.observability.run.name" = '<run_name>'
      AND RECORD_ATTRIBUTES:"ai.observability.span_type" = 'record_root'
),
scored AS (
    SELECT
        question,
        SNOWFLAKE.CORTEX.COMPLETE(
            'claude-sonnet-4-6',
            'Score 0.0-1.0. Does this answer correctly address the question with actual data?
1.0=correct with numbers/tables. 0.8=mostly correct. 0.5=partial/vague. 0.0=wrong/no data.
Question: ' || question || '
Agent answer (first 400 chars): ' || LEFT(agent_answer, 400) || '
Output ONLY a single decimal number like 0.8'
        ) AS raw_score
    FROM agent_responses
)
SELECT question, TRY_TO_DOUBLE(TRIM(raw_score)) AS score
FROM scored
ORDER BY score ASC;
```

> **Note**: LLM judge variance is ~±10% per run. Average 2+ independent runs for stability.
> Low-scoring questions (< 0.7) are the highest-value improvement targets.

---

## 6. Native Tool Selection/Execution Accuracy (Jun 11+)

**Context**: As of June 11, 2026, `tool_selection_accuracy` and `tool_execution_accuracy` are now native system metrics available directly via `SYSTEM$EVAL_AGENT`. Prior to Jun 11, these were available only through custom Snowpark evaluation scripts.

### When to use native metrics

**Default choice for new evaluations.** Native metrics are faster, have no setup overhead, and are tested by Snowflake.

```sql
-- Native metrics invocation (Jun 11+)
CALL SYSTEM$EVAL_AGENT(
    agent => '<db>.<schema>.<agent_name>',
    dataset_table => '<db>.<schema>.<eval_table>',
    metrics => ['answer_correctness', 'tool_selection_accuracy', 'tool_execution_accuracy', 'logical_consistency']
);
```

### Custom script migration

If you have existing Snowpark `tool_selection_accuracy` or `tool_execution_accuracy` scripts from before Jun 11, they can still run. However, results may differ from native metrics due to different scoring methodologies.

**Expected delta**: Native and custom TSA/TEA may produce different scores (typically ±5–10%) due to different scoring algorithms. Both are valid; choose based on your evaluation goals:

| Aspect | Native (Jun 11+) | Custom (Legacy) |
|--------|------------------|-----------------|
| Scoring algorithm | Snowflake-optimized | User-defined |
| Synonym matching | Yes | Depends on implementation |
| Performance | Fast (native SQL) | Slower (Snowpark) |
| Setup overhead | None | Script deployment required |

### Switching from custom to native

To migrate from custom TSA/TEA scripts:

1. Update your evaluation config to use the native metric names instead of custom Snowpark scoring
2. See agent-evaluation/SKILL.md Phase 4 for examples (both YAML config and direct `SYSTEM$EVAL_AGENT` invocation)
3. Run both native and custom on the same dataset to establish your delta baseline, then choose one going forward

**Recommendation**: Run both methods on a small test dataset (10–20 questions) to verify the ±5–10% delta is within your acceptable tolerance. Then standardize on native metrics for future evaluations.

---

## 7. GROUP BY alias fails after eval framework CTE expansion

**Symptom**: Eval run fails or scores incorrectly on questions that use time-based grouping or
computed dimensions. Error references a column alias used in GROUP BY.

**Root cause**: The eval framework rewrites ground-truth SQL using CTEs. GROUP BY alias
references break after CTE expansion in some Snowflake contexts:

```sql
-- BAD (breaks after CTE expansion):
SELECT DATE_TRUNC('month', event_ts) AS event_month, COUNT(*) AS cnt
FROM ...
GROUP BY event_month   -- alias — broken after CTE rewrite

-- GOOD:
SELECT DATE_TRUNC('month', event_ts) AS event_month, COUNT(*) AS cnt
FROM ...
GROUP BY DATE_TRUNC('month', event_ts)  -- full expression — safe
```

**Fix**: Audit all ground-truth SQL in your eval dataset for GROUP BY alias references.
Replace each alias with the full expression it represents.

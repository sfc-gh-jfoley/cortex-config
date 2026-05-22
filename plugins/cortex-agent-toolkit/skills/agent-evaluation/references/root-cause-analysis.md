### 5.3 Root Cause Analysis by Metric

#### Low `answer_correctness`

The agent gives wrong or incomplete answers.

**Investigate:**
1. Is the ground truth too specific or too verbose? (Use concise factual statements)
2. Does the agent have access to the right data?
3. Are the agent instructions causing it to omit key information?

**Fixes:**
- Simplify ground truth to key facts only
- Add specific instructions: "Always include percentages when discussing metrics"
- Verify semantic model/search service has the needed data

#### Low `tool_selection_accuracy`

The agent picks the wrong tool or no tool.

**Investigate:**
1. Are tool descriptions clear enough for the LLM to route correctly?
2. Does the question overlap between multiple tools' domains?
3. Do agent instructions explicitly guide tool routing?

**Fixes:**
- Improve tool descriptions to be more specific about what each tool handles
- Add routing instructions: "For revenue questions, always use the revenue_analyst tool"
- Add disambiguation: "If the question involves both X and Y, use tool A first, then tool B"

#### Low `tool_execution_accuracy`

The agent calls the right tool but with wrong parameters or gets unexpected output.

**Investigate:**
1. Is the semantic model/search service configured correctly?
2. Does the tool input match expectations? (Check query reformulation)
3. Is the expected tool_output realistic? (SQL patterns may vary)

**Fixes:**
- Use `semantic-view-optimization` skill to fix semantic view issues
- Loosen expected SQL patterns (exact match is hard — focus on key tables/columns)
- Add tool-specific instructions in agent spec

#### Low `logical_consistency`

The agent contradicts itself or its reasoning doesn't align with actions.

**Investigate:**
1. Are agent instructions contradictory?
2. Does the agent plan one thing but do another?
3. Are there ambiguous instructions that the LLM interprets differently across runs?

**Fixes:**
- Remove contradictory instructions
- Make instructions more explicit and deterministic
- Add step-by-step reasoning guidance

## Troubleshooting

### Agent Refuses to Use Tools (0% scores, no errors)

Evaluation questions don't match the agent's persona. Check `DESCRIBE AGENT` for guardrails in instructions. Fix by creating questions the agent is designed to answer.

### "No current database" Error

`EXECUTE_AI_EVALUATION` requires database context set before calling:
```sql
USE DATABASE <DATABASE>;
USE SCHEMA <SCHEMA>;
```

### Ground Truth Not Parsed (Expected tools: [])

The table schema is wrong. Verify:

1. Column name is `EXPECTED_TOOLS` (not GROUND_TRUTH)
2. Column type is `VARCHAR` (not OBJECT/VARIANT)
3. JSON is inserted as plain string (no PARSE_JSON)
4. JSON uses `ground_truth_invocations` with `tool_name`/`tool_sequence`

```sql
-- Verify format
DESC TABLE <EVAL_TABLE>;
-- Should show: INPUT_QUERY VARCHAR, EXPECTED_TOOLS VARCHAR

SELECT INPUT_QUERY, EXPECTED_TOOLS FROM <EVAL_TABLE> LIMIT 3;
```

**Wrong formats (will show empty expected tools):**
```
["tool1", "tool2"]
{"tools": ["tool1"]}
{"expected_tools": ["tool1"]}
```

**Correct format:**
```json
{"ground_truth_invocations": [{"tool_name": "tool1", "tool_sequence": 1}], "ground_truth_output": "Brief answer."}
```

### Tool Output Key Names

- Cortex Analyst: `"SQL"` (uppercase)
- Cortex Search: `"search results"` (with space, not underscore)

### Agent Invocation via REST

Agents are invoked via REST API, not SQL:
```
POST /api/v2/databases/{db}/schemas/{schema}/agents/{agent}:run
Authorization: Snowflake Token="<session_token>"
```

Use `scripts/invoke_agent.py` for testing.

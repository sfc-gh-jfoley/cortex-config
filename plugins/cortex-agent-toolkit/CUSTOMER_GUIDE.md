# Customer Guide: Cortex Agent Toolkit

This guide walks you through the full Cortex Agent lifecycle — from building your first agent to optimizing it for production. Each phase builds on the previous one, but you can jump to any phase that matches where you are today.

---

## Where to Start

| Your situation | Start at |
|---|---|
| No semantic view yet | [Phase A](#phase-a-build-your-semantic-view) |
| Have a semantic view, need an agent | [Phase B](#phase-b-create-your-agent) |
| Have an agent, want to measure quality | [Phase C](#phase-c-evaluate-your-agent) |
| Have eval results, want to improve accuracy | [Phase D](#phase-d-optimize-your-agent) |
| Want to test experimental flag combinations | [Phase E](#phase-e-flag-test-variants) |
| Need to query an agent from SQL | [Phase F](#phase-f-query-your-agent) |

---

## Quick Start: Build an Agent in 15 Minutes

If you have tables ready and just want a working agent fast:

1. **Create the semantic view** — In Cortex Code, type:
   ```
   Create a semantic view for MY_DB.PUBLIC.ORDERS and MY_DB.PUBLIC.CUSTOMERS
   ```
   The `semantic-view-ddl` skill walks you through table profiling, column classification, and DDL generation. Approve the DDL when prompted.

2. **Create the agent** — Once the semantic view is deployed, type:
   ```
   Create an agent using my semantic view MY_DB.PUBLIC.ORDERS_SV
   ```
   The `cortex-agent-ddl` skill discovers the semantic view's structure, generates tool descriptions, builds the agent spec, and deploys it.

3. **Test it** — Type:
   ```
   Query my agent MY_DB.PUBLIC.MY_AGENT: "What were total sales last month?"
   ```

That's it. The sections below cover each phase in detail.

---

## Phase A: Build Your Semantic View

> **This phase uses the `semantic-view-toolkit` plugin** (installed separately). See the semantic-view-toolkit Customer Guide at `~/.snowflake/cortex/vault/plugins/semantic-view-toolkit/CUSTOMER_GUIDE.md` for the full SV creation walkthrough.

A Cortex Agent needs at least one **semantic view** to answer data questions. A semantic view tells Cortex Analyst what your tables contain, how they relate, and what business terms map to which columns.

**What you'll need:**
- Fully qualified table names (e.g., `MY_DB.PUBLIC.ORDERS`)
- A Snowflake role with SELECT on those tables and CREATE SEMANTIC VIEW on the target schema

**What to type in Cortex Code:**
```
Create a semantic view for MY_DB.PUBLIC.ORDERS, MY_DB.PUBLIC.CUSTOMERS, and MY_DB.PUBLIC.PRODUCTS
```

The skill will:
1. Profile your tables and auto-generate column descriptions
2. Classify columns as facts, dimensions, or metrics
3. Detect foreign key relationships between tables
4. Generate a `CREATE SEMANTIC VIEW` DDL statement
5. Run 23 self-checks before showing you the DDL
6. Execute it and validate with test questions

**Output:** A deployed semantic view (e.g., `MY_DB.PUBLIC.ORDERS_SV`) ready for agent use.

---

## Phase B: Create Your Agent

> **Skill:** `cortex-agent-ddl`

This phase creates a Cortex Agent that uses your semantic view(s) as tools. The agent gets auto-generated tool descriptions, validated instructions, and a 17-rule spec check before deployment.

**What you'll need:**
- A deployed semantic view (from Phase A or already existing)
- A Snowflake role with CREATE AGENT privilege on your target schema
- A warehouse for the agent's `execution_environment`

**What to type in Cortex Code:**
```
Create a cortex agent using semantic view MY_DB.PUBLIC.ORDERS_SV
```

### What happens step by step

1. **Context** — The skill asks for agent name, target schema, and purpose. It checks that your role has CREATE AGENT privilege.

2. **Tool Discovery** — It runs `SHOW SEMANTIC VIEWS` and `DESCRIBE SEMANTIC VIEW` to understand your semantic view's structure. Then it uses `CORTEX.COMPLETE` to generate rich tool descriptions (100+ characters each with boundary language explaining what the tool can and cannot answer).

3. **Instructions** — The skill drafts orchestration instructions (how the agent should route questions to tools) and response instructions (formatting, guardrails). You review and approve.

4. **Spec Assembly** — Everything is assembled into a JSON spec with model selection, experimental flags, warehouse configuration, tools, and instructions.

5. **Self-Check** — 17 validation rules run against the spec:
   - Is `model.orchestration` set?
   - Does every tool name match a key in `tool_resources`?
   - Are tool descriptions long enough to prevent misselection?
   - Is `execution_environment.warehouse` specified?
   - And 12 more checks.

   Any failures are auto-fixed. Warnings are presented for your review.

6. **Deploy** — The `CREATE AGENT FROM SPECIFICATION` DDL is executed. Grants are applied. DESCRIBE AGENT confirms the deployment.

7. **Smoke Test** — A `DATA_AGENT_RUN` call tests the agent with a sample question. If it fails, the skill iterates on the spec.

**Output:** A deployed Cortex Agent and a `handoff.json` file that downstream skills (evaluation, optimization, flag-testing) use as their starting point.

### Example: Agent with Multiple Semantic Views

```
Create a cortex agent that uses these semantic views:
- MY_DB.PUBLIC.ORDERS_SV (for revenue and order questions)
- MY_DB.PUBLIC.INVENTORY_SV (for stock and supply chain questions)
```

The skill creates one agent with two Cortex Analyst tools — each with distinct descriptions so the agent routes questions to the right semantic view.

### Editing an Existing Agent

```
Edit my agent MY_DB.PUBLIC.SALES_AGENT — update the instructions to be more concise
```

The edit flow loads the current spec, shows a diff of proposed changes, offers a production clone option, re-runs the 17-rule self-check, and applies the changes via ALTER AGENT.

---

## Phase C: Evaluate Your Agent

> **Skill:** `agent-evaluation`

Evaluation measures how well your agent answers questions using Snowflake's native evaluation framework. You build a ground-truth dataset, run the evaluation, and get scores across multiple dimensions.

**What you'll need:**
- A deployed Cortex Agent
- 10-50 sample questions with expected answers (the skill helps you create these)
- Grants: EXECUTE TASK, CREATE DATASET, CREATE TASK, IMPERSONATE on your schema/user

**What to type in Cortex Code:**
```
Evaluate my agent MY_DB.PUBLIC.SALES_AGENT
```

### Evaluation metrics

| Metric | What it measures | Needs ground truth? |
|---|---|---|
| `answer_correctness` | Does the final answer match the expected answer? | Yes |
| `tool_selection_accuracy` | Did the agent pick the right tool(s)? | Yes |
| `tool_execution_accuracy` | Did the agent send correct inputs to tools? | Yes |
| `logical_consistency` | Is the agent's reasoning internally consistent? | No |

### What happens step by step

1. **Discover Agent** — The skill reads the agent's spec to understand its tools, instructions, and sample questions.

2. **Choose Metrics** — You select which metrics to evaluate (e.g., "answer_correctness and logical_consistency").

3. **Build Dataset** — The skill helps you create an evaluation dataset with questions, expected answers, and (optionally) expected tool sequences. The dataset is stored as a Snowflake table.

   Example dataset row:
   ```
   Question: "What was total revenue in Q4 2024?"
   Expected Answer: "Total revenue in Q4 2024 was $4.2M"
   Expected Tools: ["revenue_analyst"]
   ```

4. **Run Evaluation** — The skill registers the dataset and executes `EXECUTE_AI_EVALUATION`, which runs each question through the agent and scores the responses.

5. **Analyze Results** — Scores are aggregated by metric. The skill identifies:
   - Which questions scored lowest
   - Which tools were misselected
   - Common failure patterns (e.g., "agent always picks the wrong tool for multi-table questions")

6. **Improvement Report** — A structured report with specific fix recommendations:
   ```
   Finding: 3/10 questions misrouted to inventory_analyst instead of revenue_analyst
   Root cause: Tool descriptions overlap on "sales" terminology
   Fix: Sharpen revenue_analyst description to explicitly claim "revenue, sales dollars, order totals"
   ```

**Output:** Evaluation scores, a failure analysis, and actionable fix recommendations. Results are also viewable in the Snowsight Evaluations UI.

---

## Phase D: Optimize Your Agent

> **Skill:** `cortex-agent-optimization`

Optimization is an iterative loop: analyze failures on a dev set, make targeted instruction changes, evaluate, and decide whether to accept or reject each iteration. A separate test set ensures you're not overfitting.

**What you'll need:**
- A deployed agent with an existing evaluation dataset (from Phase C)
- OR: the skill will help you create one during setup

**What to type in Cortex Code:**
```
Optimize my agent MY_DB.PUBLIC.SALES_AGENT
```

### How the optimization loop works

```
┌─ Analyze DEV failures ──────────────────┐
│  (only look at dev split — never test)  │
└────────────┬────────────────────────────┘
             ▼
┌─ Make targeted instruction change ──────┐
│  (one change per iteration)             │
└────────────┬────────────────────────────┘
             ▼
┌─ Build & deploy updated agent ──────────┐
└────────────┬────────────────────────────┘
             ▼
┌─ Run DEV evaluation ────────────────────┐
│  Did DEV scores improve?                │
│  YES → run TEST evaluation              │
│  NO  → reject, revert, try different fix│
└────────────┬────────────────────────────┘
             ▼
┌─ Run TEST evaluation ───────────────────┐
│  Did TEST scores hold or improve?       │
│  YES → ACCEPT iteration                 │
│  NO  → REJECT (overfitting to dev)      │
└─────────────────────────────────────────┘
```

### Key concepts

- **Dev/test split**: Your evaluation dataset is split into a dev set (for analysis) and a test set (for validation). You never look at test failures to decide what to change — this prevents overfitting.
- **One change per iteration**: Each iteration makes one targeted fix (e.g., "add retry guidance for multi-hop questions"). This makes it clear what helped and what didn't.
- **Accept/reject gates**: After each iteration, you (or the skill in autonomous mode) decide whether the change is kept or reverted.
- **Stopping criteria**: If 2-3 consecutive iterations are rejected on the same failure pattern, the local optimum is reached.

### Optimization patterns that work

- Adding tool retry logic ("if the first tool returns no data, try the other tool")
- Adding "WRONG" examples to instructions ("Do NOT sum revenue across regions without grouping")
- Sharpening tool descriptions to reduce routing errors
- Adding verified queries (VQRs) to the semantic view for common question patterns

### What doesn't work

- Adding verbose checklists to instructions (agents ignore long lists)
- Changing tool order in the spec (agents don't rely on ordering)
- Repeatedly strengthening the same failing rule (diminishing returns)

**Output:** An improved agent with a documented optimization log showing what was tried, what worked, and final dev/test scores.

---

## Phase E: Flag-Test Variants

> **Skill:** `agent-flag-tester`

Snowflake Cortex Agents support experimental flags that change how the agent reasons and generates SQL. This skill creates three agent variants with different flag combinations and evaluates them head-to-head.

**What you'll need:**
- A deployed agent (the skill clones it into 3 variants)
- An evaluation dataset (from Phase C, or the skill builds one)

**What to type in Cortex Code:**
```
Run a flag test on my agent MY_DB.PUBLIC.SALES_AGENT
```

### The three variants

> **Note (Apr 2026):** `EnableAgenticAnalyst` is now **default behavior** and the flag is obsolete. The AGENTIC and FASTPATH_OFF variants below are preserved for historical reference but will not differ from BASE on accounts running Apr 2026+ releases. Use **model comparison** as your primary first sweep instead (the skill prompts for this automatically).

| Variant | Flags | What it tests |
|---|---|---|
| BASE | No experimental flags | Baseline behavior (simplest reasoning path) |
| AGENTIC *(deprecated Apr 2026)* | `EnableAgenticAnalyst: true` | Was: enhanced multi-step reasoning — now default, no longer distinct |
| FASTPATH_OFF *(deprecated Apr 2026)* | `EnableAgenticAnalyst: true`, `EnableVQRFastPath: false` | Full reasoning on every question (no shortcut for verified queries) |

### What happens

1. **Verify evaluation dataset** — Ensures the dataset has ground-truth answers and is in the same schema as the agent.

2. **Create 3 agent variants** — Clones your agent spec with different experimental flag combinations.

3. **Build YAML configs** — Creates evaluation configuration files for each variant and uploads them to a Snowflake stage.

4. **Fire evaluations** — All three evaluations run simultaneously (they're async and independent).

5. **Collect and compare results** — Scores are compared across variants:
   ```
   Variant          | answer_correctness | tool_selection | logical_consistency
   -----------------|--------------------|----------------|--------------------
   BASE             |              0.72  |          0.85  |               0.91
   AGENTIC          |              0.81  |          0.88  |               0.87
   FASTPATH_OFF     |              0.84  |          0.88  |               0.85
   ```

6. **Recommend winner** — Statistical comparison determines which variant performs best overall.

7. **Apply or hand off** — You can apply the winning flags to your agent immediately, or hand off to `cortex-agent-optimization` for further improvement using the winning config as a baseline.

**Output:** A comparison report, a recommended flag configuration, and a `flag_sweep_baseline.json` file that the optimization skill uses as its starting point.

---

## Phase F: Query Your Agent

> **Skill:** `query-cortex-agent`

Once your agent is deployed, you can invoke it programmatically from SQL. This is useful for testing, scripting, and building applications on top of your agent.

**What you'll need:**
- A deployed Cortex Agent
- A role with access to the agent object and `SNOWFLAKE.CORTEX` functions

**What to type in Cortex Code:**
```
Query my agent MY_DB.PUBLIC.SALES_AGENT: "What were the top 5 products by revenue last quarter?"
```

### Direct SQL invocation

You can also run this directly in Snowsight or any SQL client:

```sql
SELECT TRY_PARSE_JSON(
  SNOWFLAKE.CORTEX.DATA_AGENT_RUN(
    'MY_DB.PUBLIC.SALES_AGENT',
    $${
      "messages": [
        {
          "role": "user",
          "content": [{"type": "text", "text": "What were the top 5 products by revenue last quarter?"}]
        }
      ],
      "stream": false
    }$$
  )
) AS response;
```

### Multi-turn conversations

To follow up on a previous answer, include the `thread_id` and `parent_message_id` from the first response:

```sql
SELECT TRY_PARSE_JSON(
  SNOWFLAKE.CORTEX.DATA_AGENT_RUN(
    'MY_DB.PUBLIC.SALES_AGENT',
    $${
      "thread_id": <thread_id_from_previous>,
      "parent_message_id": <message_id_from_previous>,
      "messages": [
        {
          "role": "user",
          "content": [{"type": "text", "text": "Break that down by region"}]
        }
      ],
      "stream": false
    }$$
  )
) AS response;
```

### Ad-hoc agent (no pre-created agent object)

For quick testing without creating an agent object:

```sql
SELECT TRY_PARSE_JSON(
  SNOWFLAKE.CORTEX.AGENT_RUN(
    $${
      "messages": [
        {
          "role": "user",
          "content": [{"type": "text", "text": "What were total sales last month?"}]
        }
      ],
      "models": {"orchestration": "claude-4-sonnet"},
      "tools": [...],
      "tool_resources": {...},
      "stream": false
    }$$
  )
) AS response;
```

> **Note**: `CORTEX.AGENT_RUN` is for ad-hoc testing without a pre-created agent object — you provide the full spec inline. For production use, create a persistent agent with `CREATE AGENT` and invoke via `DATA_AGENT_RUN`. See Snowflake documentation for full `AGENT_RUN` reference.

---

## Common Workflows

### Full Journey: New Agent from Scratch

```
Phase A (semantic-view-ddl)  →  Phase B (cortex-agent-ddl)  →  Phase C (agent-evaluation)
                                                                       ↓
                                                              Phase E (agent-flag-tester)
                                                                       ↓
                                                              Phase D (cortex-agent-optimization)
                                                                       ↓
                                                              Phase F (query-cortex-agent) — production use
```

### Tuning an Existing Agent

If you already have a deployed agent and want to improve it:

1. **Evaluate first** (Phase C) — establish a baseline. You need numbers before you can improve them.
   ```
   Evaluate my agent MY_DB.PUBLIC.SALES_AGENT
   ```

2. **Flag-test** (Phase E) — check if experimental flags help.
   ```
   Run a flag test on my agent MY_DB.PUBLIC.SALES_AGENT
   ```

3. **Optimize** (Phase D) — iteratively improve instructions based on failure analysis.
   ```
   Optimize my agent MY_DB.PUBLIC.SALES_AGENT
   ```

4. **Improve the semantic view** — If optimization reveals that the agent gets wrong SQL (not wrong routing), the fix is often in the semantic view, not the agent. Go back to the `semantic-view-ddl` skill to add verified queries, fix column descriptions, or add missing relationships.

### Multi-Agent Routing

For complex domains that span multiple semantic views, you can create a master agent that routes to sub-agents:

```
Create a cortex agent that routes between these sub-agents:
- SALES_AGENT (revenue and order questions)
- INVENTORY_AGENT (stock and supply chain questions)
- HR_AGENT (headcount and compensation questions)
```

The `cortex-agent-ddl` skill supports multi-agent orchestration where a master agent dispatches to sub-agents via UDF custom tools.

---

## Troubleshooting

| Problem | Likely cause | Fix |
|---|---|---|
| Agent returns "I don't have access to that data" | Tool description doesn't cover the question's domain | Edit agent — improve tool descriptions (Phase B, edit flow) |
| Agent picks the wrong tool | Tool descriptions overlap | Sharpen descriptions with boundary language ("Use this tool ONLY for...") |
| Agent returns wrong numbers | Semantic view issue (wrong joins, missing metrics) | Fix the semantic view with `semantic-view-ddl` Phase 7 |
| Evaluation scores are low across all metrics | Small/poor evaluation dataset | Expand dataset to 30+ diverse questions covering all tools |
| Flag-test shows no difference between variants | Questions are too simple | Add multi-hop and ambiguous questions that stress-test reasoning |
| Optimization iterations keep getting rejected | Changes are too broad | Make smaller, more targeted changes (one fix per iteration) |

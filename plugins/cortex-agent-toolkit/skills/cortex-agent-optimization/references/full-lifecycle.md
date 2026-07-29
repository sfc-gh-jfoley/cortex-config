# Cortex Agent Improvement Framework

> **Historical reference — read this for the lifecycle shape, not for commands.**
> This document predates the current toolkit and describes the workflow in terms of
> helper scripts (`create_or_alter_agent.py`, `run_evaluation.py`, `test_agent.py`)
> and a `best-practices/` directory that are **not shipped with this toolkit**. Any
> command referencing them will fail with "file not found".
>
> For executable instructions use the skills directly:
> `cortex-agent-ddl` (create/alter), `agent-evaluation` (evaluate),
> `agent-flag-tester` (flag and model variants), `cortex-agent-optimization`
> (iterate), `agent-gepa-optimizer` (population search).

A systematic, phase-based workflow for optimizing any Snowflake Cortex Agent from creation through production deployment. Each phase uses a dedicated skill from the `cortex-agent-toolkit` plugin.

---

## 1. Overview

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                    CORTEX AGENT IMPROVEMENT LIFECYCLE                         │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐                   │
│  │  Phase 1:    │───▶│  Phase 2:    │───▶│  Phase 3:    │                   │
│  │  CREATE      │    │  BASELINE    │    │  MODEL SWEEP │                   │
│  │  AGENT       │    │  EVAL        │    │              │                   │
│  └──────────────┘    └──────────────┘    └──────┬───────┘                   │
│                                                  │                           │
│                                                  ▼                           │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐                   │
│  │  Phase 7:    │◀───│  Phase 6:    │◀───│  Phase 4:    │                   │
│  │  VALIDATE    │    │  GEPA        │    │  FLAG TEST   │                   │
│  │  & SHIP      │    │  (evolve)    │    │              │                   │
│  └──────────────┘    └──────────────┘    └──────┬───────┘                   │
│         ▲                    ▲                   │                           │
│         │                    │                   ▼                           │
│         │                    │            ┌──────────────┐                   │
│         │                    └────────────│  Phase 5:    │                   │
│         │              (if stuck)         │  ITERATIVE   │                   │
│         └─────────────────────────────────│  OPTIMIZE    │                   │
│                   (if converged)          └──────────────┘                   │
│                                                                              │
│  Skip phases that don't apply:                                               │
│  • Existing agent? Skip Phase 1.                                             │
│  • No experimental flags relevant? Skip Phase 4.                             │
│  • Sequential optimizer converges quickly? Skip Phase 6.                     │
│  • New agent with no baseline? Must do Phase 2 before anything else.         │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Prerequisites

- Deployed Cortex Agent (or spec ready to deploy)
- Evaluation dataset (10+ questions with expected answers)
- `snow` CLI installed and configured
- Python 3.11+ with `pyyaml` installed
- `cortex-agent-toolkit` plugin loaded in Cortex Code
- Snowflake connection with CREATE/ALTER AGENT privileges

---

## 2. Phase 1: Agent Creation

**Skill**: `cortex-agent-ddl` (cortex-agent-toolkit plugin)
**Key Script**: `create_or_alter_agent.py`

### Spec JSON Format

```json
{
  "name": "MY_AGENT",
  "database": "MY_DB",
  "schema": "MY_SCHEMA",
  "models": {
    "orchestration": "claude-sonnet-4-6"  // balanced tier — see reference/agent_spec_syntax.md
  },
  "instructions": "You are an expert assistant...",
  "tools": [
    {"tool_type": "cortex_analyst_tool", "tool_name": "my_analyst"}
  ],
  "tool_resources": {
    "my_analyst": {"semantic_view": "MY_DB.MY_SCHEMA.MY_SEMANTIC_VIEW"}
  },
  "experimental": {}
}
```

### Best Practices (from `best-practices/AGENT_BEST_PRACTICES.md`)

1. **Tool descriptions are the #1 impact factor** — the orchestration model routes based on tool descriptions, not instructions. Invest time here.
2. Keep instructions terse for fast models (GPT-4.1, Haiku). Verbose instructions add latency with minimal accuracy gain.
3. Use explicit routing rules ("Use TOOL_A for questions about X, TOOL_B for Y") when models don't infer well from tool descriptions alone.
4. One semantic view per tool — don't overload a single tool with multiple views.

### Workflow

```bash
# Create from spec
python create_or_alter_agent.py create --spec agent_spec.json --connection my_conn

# Alter existing
python create_or_alter_agent.py alter --spec agent_spec.json --connection my_conn
```

---

## 3. Phase 2: Baseline Evaluation

**Skill**: `agent-evaluation` (cortex-agent-toolkit plugin)
**Key Script**: `run_evaluation.py`

### Evaluation Method

Uses Snowflake's native `EXECUTE_AI_EVALUATION` function — no external LLM judge needed.

### Dataset Format

The eval dataset table must have these columns:

| Column | Type | Description |
|--------|------|-------------|
| QUESTION | VARCHAR | The user query to send to the agent |
| EXPECTED_TOOL | VARCHAR | Which tool should be selected (optional) |
| EXPECTED_ANSWER | VARCHAR | Ground truth or key facts the answer must contain |
| CATEGORY | VARCHAR | Grouping for analysis (e.g., single_title, metric) |
| SPLIT | VARCHAR | `DEV` or `TEST` — never peek at TEST during tuning |

### Metrics

- **answer_correctness** — Does the response contain the expected facts?
- **tool_selection_accuracy** — Did the agent route to the correct tool?
- **logical_consistency** — Is the response internally coherent?

### Establishing the Baseline

```bash
python run_evaluation.py \
  --agent MY_DB.MY_SCHEMA.MY_AGENT \
  --eval-table MY_DB.MY_SCHEMA.EVAL_DATASET \
  --connection my_conn \
  --judge answeronly
```

Record: total score, per-category breakdown, per-question failures.

### Gate

If accuracy < 80%, **stop**. Fix the agent (instructions, tool descriptions, semantic views) before proceeding to optimization. Optimizing a broken agent wastes effort.

---

## 4. Phase 3: Model Sweep

**Why early?** Instructions are model-specific. Pick the model first, then tune instructions for it. Switching models later invalidates instruction tuning work.

### Valid Agent Models (as of 2026-05)

> Pick concrete model names from the Valid Model Names table in `reference/agent_spec_syntax.md`.

**Claude** (all support agent tool-use loop):
- Heavy tier — highest accuracy (Opus class)
- Balanced tier — recommended default (Sonnet class)
- Fast tier — good for simple routing (Haiku class)

**OpenAI** (all support agent tool-use loop):
- `openai-gpt-5.2` — heavy
- `openai-gpt-5.1` — heavy
- `openai-gpt-5` — balanced
- `openai-gpt-5-mini` — fast
- `openai-gpt-4.1` — legacy but excellent latency

**NOT valid for agents** (fail tool-use loop): `openai-gpt-5-nano`, `llama*`, `mistral*`, `snowflake-*`

### Methodology

For each model:
1. Update agent spec `models.orchestration` field
2. Deploy via `create_or_alter_agent.py alter`
3. Run benchmark questions (timing + pass/fail)
4. Record: model, avg_latency, simple_avg, complex_avg, pass_rate

### Selection Criteria

```
1. Filter: pass_rate == 100%
2. Sort: avg_latency ASC
3. Select: winner (or top 3 for further comparison)
```

Models that fail any question are eliminated regardless of speed.

---

## 5. Phase 4: Flag Testing

**Skill**: `agent-flag-tester` (cortex-agent-toolkit plugin)

### 3-Variant Comparison

> **`EnableAgenticAnalyst` is deprecated (default behavior since April 2026).**
> Setting it has no documented effect, so an AGENTIC variant is identical to BASE
> and wastes an evaluation run. Use model comparison as the first sweep instead.
> Retained below only to explain older run records.

| Variant | Experimental Flags |
|---------|-------------------|
| BASE | `{}` (no flags) |
| AGENTIC | `{"EnableAgenticAnalyst": true}` — **deprecated, no effect** |
| FASTPATH | `{"EnableVQRFastPath": true}` |

### Methodology

1. Deploy 3 temporary variant agents (e.g., `MY_AGENT_BASE`, `MY_AGENT_AGENTIC`, `MY_AGENT_FASTPATH`)
2. Run full eval on each variant using `EXECUTE_AI_EVALUATION`
3. Collect: accuracy, latency, per-category breakdown
4. Compare metrics with statistical significance (multiple runs recommended)

### Configuration

Each variant uses a YAML config staged to Snowflake:

```yaml
agent: MY_DB.MY_SCHEMA.MY_AGENT_AGENTIC
evaluation_dataset: MY_DB.MY_SCHEMA.EVAL_DATASET
metrics:
  - answer_correctness
  - tool_selection_accuracy
```

### Decision Criteria

- If AGENTIC improves complex queries without hurting simple ones: adopt
- If FASTPATH improves latency without accuracy loss: adopt
- If both help: combine as `{"EnableAgenticAnalyst": true, "EnableVQRFastPath": true}`
- If neither helps or hurts: use BASE (fewer moving parts)

### Cleanup

```sql
DROP AGENT IF EXISTS MY_DB.MY_SCHEMA.MY_AGENT_BASE;
DROP AGENT IF EXISTS MY_DB.MY_SCHEMA.MY_AGENT_AGENTIC;
DROP AGENT IF EXISTS MY_DB.MY_SCHEMA.MY_AGENT_FASTPATH;
```

---

## 6. Phase 5: Iterative Optimization

**Skill**: `cortex-agent-optimization` (cortex-agent-toolkit plugin)
**Key Script**: `build_agent_spec.py`

### Dev/Test Split Methodology

- **DEV split**: Used for iterative tuning. You look at failures and fix them.
- **TEST split**: Held out. Run only for validation. Never peek during tuning.

This prevents overfitting instructions to specific questions.

### Iteration Loop

```
1. Run eval on DEV split
2. Identify failures (wrong tool, wrong answer, hallucination)
3. Edit instructions to address failure pattern
4. Deploy updated agent
5. Re-run DEV eval
6. Accept if DEV improves; reject if it regresses
7. Repeat until DEV converges
```

### Accept/Reject Criteria

| Outcome | Decision |
|---------|----------|
| DEV accuracy improves, TEST stable | ACCEPT |
| DEV accuracy same, latency improves | ACCEPT |
| DEV or TEST regresses | REJECT (revert) |
| 2-3 consecutive rejections | STOP (local optimum) |

### Statistical Rigor

Set `runs_per_split` (default: 3) to run each eval multiple times and use the average. This reduces noise from non-deterministic model outputs.

### Effective Instruction Patterns

- **Retry logic**: "If a query returns no results, try with broader filters"
- **Format rules**: "Always respond with the numeric value before explanation"
- **Routing rules**: "Use TOOL_A for single-entity lookups, TOOL_B for rankings"
- **Explicit corrections**: "WRONG: 'I don't have data for X.' RIGHT: 'Use the regional_data tool for X.'"

### Anti-Patterns (avoid these)

- Verbose checklists that add latency without accuracy gain
- Changing tool descriptions during instruction optimization (confounds results)
- Changing tool order (some models are sensitive to position)
- Adding guardrails that block valid queries

### Stop Condition

2-3 consecutive rejections means you've hit a local optimum. Escalate to Phase 6 (GEPA) for a fundamentally different approach.

---

## 7. Phase 6: Evolutionary Tuning (GEPA)

**Skill**: `agent-gepa-optimizer` (cortex-agent-toolkit plugin)
**Key Scripts**: `mutate.py`, `tournament.py`, `population_state.py`

### When to Use

- Sequential optimizer (Phase 5) hit a local optimum (2-3 rejections)
- You suspect there's a better instruction structure but can't find it incrementally
- You want to explore multiple approaches simultaneously

### Population-Based Optimization

Create 4-6 instruction candidates per generation, each with a different mutation applied to the current best instructions.

### Mutation Operators

| Operator | Description |
|----------|-------------|
| `add_retry_logic` | Append retry/fallback block |
| `compress_instructions` | Minimize token count, remove redundancy |
| `add_speed_skip` | Skip deliberation for obvious patterns |
| `add_response_priority` | Answer-first, terse, word limits |
| `restructure_routing` | Reorganize tool selection rules |
| `add_explicit_examples` | Add worked examples for failure cases |

### Workflow

```
1. Initialize population (4-6 candidates with different mutations)
2. Deploy each as temporary agent (AGENT_GEPA_1 through AGENT_GEPA_N)
3. Mini-batch eval: run 30% of DEV questions against each candidate
4. Tournament selection: rank by (pass_rate DESC, latency ASC)
5. Keep winner + mutate to create next generation
6. Repeat until convergence (3 generations without improvement)
7. Validate winner with full eval before accepting
```

### Adaptive Operator Weights

Operators that produce winning candidates get higher weights in subsequent generations. Operators that consistently lose get downweighted.

### Convergence Criteria

- 3 generations without improvement = converged
- Winner must still beat the Phase 5 baseline on full eval
- If no improvement over Phase 5: keep Phase 5 result

---

## 8. Phase 7: Validate & Ship

### Full Accuracy Evaluation

Run the complete eval dataset (all questions, both DEV and TEST splits) with multiple runs:

```bash
python run_evaluation.py \
  --agent MY_DB.MY_SCHEMA.MY_AGENT \
  --eval-table MY_DB.MY_SCHEMA.EVAL_DATASET \
  --connection my_conn \
  --runs 3
```

### Latency Benchmark

Run a mixed benchmark (simple + complex questions) to confirm speed improvement:

```bash
python test_agent.py \
  --agent MY_DB.MY_SCHEMA.MY_AGENT \
  --questions benchmark_questions.yaml \
  --connection my_conn \
  --timing
```

### Edge Case Validation

Test known failure modes explicitly:
- Large result sets (10+ rows returned)
- Multi-tool queries requiring chained reasoning
- Disambiguation scenarios (ambiguous entity names)
- Guardrail triggers (out-of-scope questions)

### Accept/Reject Gate

| Condition | Decision |
|-----------|----------|
| Accuracy >= baseline AND latency improved | ACCEPT — ship it |
| Accuracy >= baseline, latency same | MARGINAL — ship only if other benefits |
| Accuracy < baseline | REJECT — revert to baseline |

### Deployment

1. Update the primary agent spec with winning config
2. Deploy via `create_or_alter_agent.py alter`
3. Drop all temporary/variant agents
4. Update `optimization_log.md` with results

### Documentation

Record in your optimization log:
- Baseline metrics vs final metrics
- Winning model + flags + instruction changes
- What worked and what didn't
- Per-phase summary (which phases actually helped)

---

## 9. Experimental Flags Reference

**Skill**: `cortex-agent-flags` (cortex-agent-toolkit plugin)

### Current Flags (as of 2026-05)

| Flag | Effect | Best For |
|------|--------|----------|
| `EnableAgenticAnalyst` | Multi-step reasoning in Cortex Analyst tool | Complex queries requiring decomposition |
| `EnableVQRFastPath` | Skip orchestration when VQR match is exact | High-VQR-coverage agents |
| `EnableUnrestrictedChartTool` | Extended chart generation capabilities | Visualization-heavy agents |
| `EnableSkillBasedPromptNoExtendedThinking` | Disable extended thinking for skill-based prompts | Latency reduction |

### Applicability Matrix

| Flag | Cortex Analyst Tools | Cortex Search Tools | Custom Tools |
|------|---------------------|--------------------:|-------------:|
| EnableAgenticAnalyst | Yes | No | No |
| EnableVQRFastPath | Yes (VQR-dependent) | No | No |
| EnableUnrestrictedChartTool | Yes | No | No |
| EnableSkillBasedPromptNoExtendedThinking | Yes | Yes | Yes |

### Chart Customization

When using chart-related flags, add a `<chart_customization>` block to instructions:

```
<chart_customization>
- Default chart type: bar
- Color palette: blue, gray, orange
- Always include axis labels
</chart_customization>
```

### Freshness Check

Flags change frequently. Before starting a flag test:
1. Search Snowflake docs for current experimental flags
2. Check the `cortex-agent-flags` skill reference for updates
3. Verify flags are still valid by deploying a test agent

---

## 10. Known Issues & Workarounds

### GEPA Script Issues

| Issue | Location | Workaround |
|-------|----------|------------|
| `mutate.py` TypeError on `select-operator` | `mutate.py:~93` | Cast operator weights to float before `sum()` |
| `population_state.py` path arg expects file not directory | `population_state.py` | Pass full path to `population_state.yaml`, not just the directory |
| `mutate.py prepare` double-prefixes candidate dirs | `mutate.py` | Don't add `cand_` prefix if the name already starts with it |
| No `pyproject.toml` for GEPA deps | `agent-gepa-optimizer/` | Manually install `pyyaml` before running GEPA scripts |

### Model-Specific Issues

| Issue | Affected Models | Mitigation |
|-------|----------------|------------|
| Silent completion on large result sets | `openai-gpt-4.1` | Add "ALWAYS respond with text after receiving tool results" to instructions |
| Fails agent tool-use loop entirely | `llama*`, `mistral*`, `snowflake-*`, `openai-gpt-5-nano` | Do not use these models for agents |
| Verbose reasoning adds latency | `claude-opus-4-7`, `openai-gpt-5.2` | Use only when accuracy justifies the cost; prefer balanced models |
| Weak tool routing from descriptions alone | `openai-gpt-4.1`, `openai-gpt-5-mini` | Add explicit routing rules in instructions |

---

## 11. Skill Quick Reference Table

| Skill | Plugin | When to Use | Key Script |
|-------|--------|-------------|------------|
| `cortex-agent-ddl` | cortex-agent-toolkit | Create/edit agents | `create_or_alter_agent.py` |
| `agent-evaluation` | cortex-agent-toolkit | Run formal evals | `run_evaluation.py` |
| `agent-flag-tester` | cortex-agent-toolkit | Compare flag variants | (stage configs + `EXECUTE_AI_EVALUATION`) |
| `cortex-agent-optimization` | cortex-agent-toolkit | Iterative instruction tuning | `build_agent_spec.py` |
| `agent-gepa-optimizer` | cortex-agent-toolkit | Evolutionary optimization | `mutate.py`, `tournament.py` |
| `cortex-agent-flags` | cortex-agent-toolkit | Flag reference | (docs search) |
| `query-cortex-agent` | cortex-agent-toolkit | Programmatic testing | `test_agent.py` |
| `agent-architect` | vault/skills | Multi-phase project structure | (framework) |

---

## Appendix: Decision Flowchart

```
START
  │
  ▼
Agent exists? ──No──▶ Phase 1 (Create) ──▶ Phase 2
  │
  Yes
  │
  ▼
Baseline eval done? ──No──▶ Phase 2 (Baseline)
  │
  Yes
  │
  ▼
Accuracy >= 80%? ──No──▶ Fix agent (tools, descriptions, instructions)
  │                       then re-run Phase 2
  Yes
  │
  ▼
Model already chosen? ──No──▶ Phase 3 (Model Sweep)
  │
  Yes
  │
  ▼
Flags relevant? ──Yes──▶ Phase 4 (Flag Test) ──▶ Phase 5
  │
  No
  │
  ▼
Phase 5 (Iterative Optimize)
  │
  ▼
Converged? (2-3 rejections) ──Yes──▶ Phase 6 (GEPA)
  │                                       │
  No (still improving)                    ▼
  │                              Phase 7 (Validate & Ship)
  ▼
Phase 7 (Validate & Ship)
```

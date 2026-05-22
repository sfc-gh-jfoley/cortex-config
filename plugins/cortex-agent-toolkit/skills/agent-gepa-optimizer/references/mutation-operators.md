# GEPA Mutation Operators

Catalog of 8 mutation operators used by the Genetic Evolutionary Prompt Algorithm to generate candidate instruction variants. Mutations target agent instruction files (orchestration_instructions.md, response_instructions.md) and are applied to produce population members each generation.

## Mutation Engine Design

**Primary approach: LLM-assisted mutations.** Most operators require semantic understanding of the instruction file structure (finding the right section, understanding context, crafting examples). Only the simplest operators (appending fixed text) use template-based insertion.

**Implementation:**
- LLM-assisted: Call `CORTEX_AI_COMPLETE('claude-3-5-sonnet', prompt)` or delegate to CoCo agent with a focused prompt
- Template-based: Direct string append/insert at a known location (end of file, after a marker)

**Anti-pattern guards (apply to ALL operators):**
- NEVER reorder tools in the agent spec `tools` array (causes unpredictable regressions — see optimization-patterns.md #6)
- NEVER insert verbose multi-step checklists (degrades performance — see optimization-patterns.md #4)
- NEVER modify tool descriptions for routing purposes (zero impact — see optimization-patterns.md #5)
- NEVER apply >2 mutations to a single candidate per generation (makes attribution impossible — see optimization-patterns.md #8)

## Operator Catalog

### 1. `add_retry_logic`

| Property | Value |
|----------|-------|
| Default Weight | 0.15 |
| Target File | `orchestration_instructions.md` |
| Mutation Type | TEMPLATE |
| Complexity | Low |

**Behavior:** Appends a retry instruction block to the end of orchestration instructions. Highest single-iteration impact pattern (+9.3% answer_correctness historically).

**Template:**
```markdown

## Error Handling
If a tool call returns a transient error (timeout, rate limit, connection reset), retry the same call up to 2 times with a brief pause. Only report failure to the user after all retries are exhausted.
```

**Guard:** Skip if orchestration_instructions.md already contains "retry" (case-insensitive). Only apply once per evolutionary run.

---

### 2. `add_routing_rule`

| Property | Value |
|----------|-------|
| Default Weight | 0.15 |
| Target File | `orchestration_instructions.md` |
| Mutation Type | LLM-assisted |
| Complexity | Medium |

**Behavior:** Adds a tool-routing rule based on observed routing failures in eval results.

**LLM Prompt Template:**
```
You are editing a Cortex Agent's orchestration instructions. The agent has been mis-routing queries — using the wrong tool for certain question types.

Current orchestration instructions:
{current_orchestration_instructions}

Observed routing failure pattern:
- Question: {failed_question}
- Expected tool: {expected_tool}
- Actual tool used: {actual_tool}

Add ONE concise routing rule (1-3 sentences) that would prevent this misrouting. Insert it in the routing/tool-selection section of the instructions. If no such section exists, add a "## Tool Selection" section before any existing content.

Output ONLY the modified orchestration instructions (full file). Do not explain.
```

**Guard:** Maximum 5 routing rules per file. If 5 already exist, use `rewrite_ambiguous_rule` instead to consolidate.

---

### 3. `fix_example`

| Property | Value |
|----------|-------|
| Default Weight | 0.20 |
| Target File | `response_instructions.md` OR `orchestration_instructions.md` |
| Mutation Type | LLM-assisted |
| Complexity | High |

**Behavior:** Identifies and fixes an inconsistent example in the instructions. Highest-weight operator because buggy examples are "poisonous" (see optimization-patterns.md #2).

**LLM Prompt Template:**
```
You are auditing a Cortex Agent's instruction file for example inconsistencies.

Current instructions:
{current_instructions}

An eval failure suggests the agent is reproducing an inconsistency from its instructions:
- Agent's incorrect output: {agent_output}
- Expected correct output: {expected_output}
- Failure category: {failure_category}

Find any example in the instructions that could teach the agent this incorrect behavior. Fix the example to be internally consistent. If no buggy example exists, add a correct example demonstrating the expected behavior.

Output ONLY the modified instructions (full file). Do not explain.
```

**Guard:** Verify the fix doesn't change the semantic meaning of other rules in the file. The LLM output must preserve all existing rules that aren't part of the buggy example.

---

### 4. `add_wrong_example`

| Property | Value |
|----------|-------|
| Default Weight | 0.15 |
| Target File | `response_instructions.md` |
| Mutation Type | LLM-assisted |
| Complexity | Medium |

**Behavior:** Adds a "WRONG" example showing what NOT to do, paired with the correct approach. Effective complement to positive examples (see optimization-patterns.md #9).

**LLM Prompt Template:**
```
You are adding a "WRONG vs CORRECT" example to a Cortex Agent's response instructions.

Current response instructions:
{current_response_instructions}

Observed failure:
- Question: {question}
- Agent's wrong answer: {wrong_answer}
- Expected correct answer: {correct_answer}
- Why it's wrong: {failure_reason}

Add a WRONG/CORRECT example pair at the end of the relevant section. Format:

**WRONG:** {brief wrong approach}
**CORRECT:** {brief correct approach}

Keep each side to 1-3 lines. Do not add verbose explanations.

Output ONLY the modified response instructions (full file). Do not explain.
```

**Guard:** Maximum 4 WRONG/CORRECT pairs per file. More than 4 creates instruction bloat. If at capacity, consider `rewrite_ambiguous_rule` to consolidate existing rules instead.

---

### 5. `add_format_template`

| Property | Value |
|----------|-------|
| Default Weight | 0.10 |
| Target File | `response_instructions.md` |
| Mutation Type | LLM-assisted |
| Complexity | Medium |

**Behavior:** Adds a response format template for a specific output type the agent is formatting incorrectly.

**LLM Prompt Template:**
```
You are adding a response format template to a Cortex Agent's response instructions.

Current response instructions:
{current_response_instructions}

The agent is producing incorrectly formatted responses for this type of question:
- Question type: {question_category}
- Agent's format: {actual_format}
- Expected format: {expected_format}

Add a concise format template (using placeholder variables) that shows the correct output structure for this question type. Place it in a "## Response Formats" section (create if needed).

Output ONLY the modified response instructions (full file). Do not explain.
```

**Guard:** Maximum 3 format templates. Excessive templates conflict with each other.

---

### 6. `add_domain_rule`

| Property | Value |
|----------|-------|
| Default Weight | 0.10 |
| Target File | `response_instructions.md` |
| Mutation Type | LLM-assisted |
| Complexity | Medium |

**Behavior:** Adds a domain-specific business rule that the agent is violating. Prefer documentation-based rules over surface-pattern rules (see optimization-patterns.md #10).

**LLM Prompt Template:**
```
You are adding a domain-specific rule to a Cortex Agent's response instructions.

Current response instructions:
{current_response_instructions}

The agent is violating a domain rule:
- Question: {question}
- Agent's answer: {agent_answer}
- Why it's wrong: {domain_violation}
- Correct domain rule: {correct_rule}

Add ONE concise rule (1-2 sentences) stating the domain constraint. Prefer referencing authoritative sources (documentation, specifications) over surface-level patterns. Place it in the most relevant existing section, or create a "## Domain Rules" section if none fits.

Output ONLY the modified response instructions (full file). Do not explain.
```

**Guard:** Rules must be specific and falsifiable. Reject vague rules like "be more accurate" or "check carefully."

---

### 7. `rewrite_ambiguous_rule`

| Property | Value |
|----------|-------|
| Default Weight | 0.10 |
| Target File | Any `*.md` in agent directory |
| Mutation Type | LLM-assisted |
| Complexity | High |

**Behavior:** Identifies a rule that the agent interprets differently from the intent (ambiguous wording) and rewrites it for clarity. Used when progressive strengthening has failed (optimization-patterns.md #7).

**LLM Prompt Template:**
```
You are rewriting an ambiguous rule in a Cortex Agent's instructions.

Current instructions:
{current_instructions}

This rule is being misinterpreted:
- Rule text: {ambiguous_rule}
- Intended meaning: {intended_meaning}
- Agent's interpretation (based on eval failures): {misinterpretation}

Rewrite the rule to be unambiguous. Use concrete, specific language. If the rule has been strengthened 2+ times already (multiple "NEVER", "ALWAYS", "CRITICAL" markers), simplify it — the verbosity itself may be causing confusion.

Output ONLY the modified instructions (full file). Do not explain.
```

**Guard:** Track rewrite attempts in gepa_state.yaml. If the same rule has been rewritten 2+ times without improvement, flag it as a model behavior limit and stop targeting it.

---

### 8. `remove_verbose_rule`

| Property | Value |
|----------|-------|
| Default Weight | 0.05 |
| Target File | Any `*.md` in agent directory |
| Mutation Type | LLM-assisted |
| Complexity | Medium |

**Behavior:** Identifies and removes an overly verbose rule that may be degrading performance. Instructions that are too long dilute the impact of important rules.

**LLM Prompt Template:**
```
You are pruning a Cortex Agent's instructions to remove verbosity.

Current instructions:
{current_instructions}

The agent's performance has plateaued or degraded. Verbose instructions can dilute important rules. Identify ONE rule or section that:
- Is a multi-step checklist (these degrade performance)
- Repeats what another rule already says
- Uses excessive emphasis markers (multiple NEVER/ALWAYS/CRITICAL) suggesting over-strengthening
- Has been superseded by a more specific rule elsewhere in the file

Remove or significantly shorten the identified section. Preserve all other content unchanged.

Output ONLY the modified instructions (full file). Do not explain.
```

**Guard:** Never remove the LAST rule in a section. Never remove retry logic. Never remove routing rules that were added in the current GEPA run (check mutation history).

---

## Weight Adjustment Rules

Operator weights determine selection probability when choosing which mutation to apply to a candidate.

| Event | Adjustment | Constraint |
|-------|-----------|------------|
| Operator included in **tournament winner** | +0.02 to that operator's weight | — |
| Operator included in **tournament loser** | -0.01 from that operator's weight | Floor = 0.02 |
| Operator applied but candidate showed **no change** in fitness | -0.005 | Floor = 0.02 |
| Operator blocked by guard | No change (operator was not applied) | — |

**Normalization:** After all adjustments, weights are normalized to sum to 1.0 for selection probability calculation.

**Persistence:** Current weights stored in `gepa_state.yaml` under `operator_weights`. Initial weights restored from defaults on new GEPA run.

## Mutation Application Protocol

1. **Select operator** — weighted random choice from operator catalog using current weights
2. **Select target** — choose target file based on operator's target specification
3. **Check guards** — verify operator-specific guards pass; if blocked, re-select (max 3 retries)
4. **Generate mutation** — execute LLM prompt (or apply template) to produce modified file
5. **Validate output** — verify output is valid markdown, non-empty, and differs from input
6. **Apply** — write mutated file to candidate's directory in `gepa_population/`
7. **Record** — log operator name, target file, and diff hash in candidate's mutation history

## Summary

| Operator | Weight | Target | Type | Use When |
|----------|--------|--------|------|----------|
| `add_retry_logic` | 0.15 | orchestration | Template | No retry logic exists |
| `add_routing_rule` | 0.15 | orchestration | LLM | Routing failures observed |
| `fix_example` | 0.20 | response/orchestration | LLM | Inconsistent examples found |
| `add_wrong_example` | 0.15 | response | LLM | Repeated same mistake |
| `add_format_template` | 0.10 | response | LLM | Format errors in output |
| `add_domain_rule` | 0.10 | response | LLM | Domain rule violation |
| `rewrite_ambiguous_rule` | 0.10 | any | LLM | Rule misinterpretation |
| `remove_verbose_rule` | 0.05 | any | LLM | Instruction bloat/plateau |

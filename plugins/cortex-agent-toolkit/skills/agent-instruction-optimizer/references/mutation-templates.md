# Mutation Templates Reference

> Instruction mutation operators for the TPE instruction optimizer.
> Each operator targets a specific dimension of instruction quality.
> Used by `agent-instruction-optimizer` **Phase 3 (bulk candidate generation)** — operators are applied once upfront to produce the instruction pool. The TPE search then selects which (instruction variant, few-shot combo) to evaluate next.

---

## Operator Catalog

### 1. compress_verbose

**Target:** Any instruction file
**Intent:** Reduce instruction length without losing meaning. LLMs attend better to
concise instructions.

**Prompt template:**
```
You are editing agent instructions for a Snowflake Cortex Agent.

Current instruction file ({target_file}):
---
{current_text}
---

The agent is failing on these questions:
{failure_context}

TASK: Compress verbose sections. Remove redundant phrasing, merge overlapping rules,
eliminate filler words. Preserve all domain-specific terms, metric names, and
behavioral rules exactly as-is. Target: reduce length by 20-40%.

Do NOT remove examples or domain context. Do NOT change tool routing logic.
Output the full revised instruction file.
```

**Initial weight:** 0.15

---

### 2. add_worked_example

**Target:** orchestration_instructions.md
**Intent:** Add a worked example showing the agent how to handle a specific failure
pattern. Worked examples are the highest-leverage instruction change.

**Prompt template:**
```
You are editing agent instructions for a Snowflake Cortex Agent.

Current orchestration instructions:
---
{current_text}
---

The agent fails on questions like these:
{failure_context}

Failure pattern: {failure_pattern}
(e.g., "wrong tool selection for multi-metric questions",
"hallucinates numbers when tool returns no data",
"doesn't combine results from multiple tool calls")

TASK: Add ONE concise worked example that demonstrates the correct approach
for this failure pattern. The example should:
- Use a question similar (but not identical) to the failing ones
- Show the correct tool call sequence
- Show what a correct synthesis looks like
- Be ≤10 lines

Place it in the most relevant section. Do NOT add multiple examples.
Output the full revised instruction file.
```

**Initial weight:** 0.25 (highest — most effective operator in practice)

---

### 3. add_negative_example

**Target:** orchestration_instructions.md or response_instructions.md
**Intent:** Show the agent what NOT to do, based on observed failure modes.

**Prompt template:**
```
You are editing agent instructions for a Snowflake Cortex Agent.

Current instruction file ({target_file}):
---
{current_text}
---

The agent produces this incorrect behavior:
{failure_context}

TASK: Add a "WRONG" example that shows the specific mistake the agent makes,
followed by the correct approach. Format:

❌ WRONG: [what the agent does]
✅ CORRECT: [what it should do instead]

Keep it to 3-5 lines. Place near the relevant rule. Do NOT duplicate existing examples.
Output the full revised instruction file.
```

**Initial weight:** 0.20

---

### 4. restructure_sections

**Target:** Any instruction file
**Intent:** Reorder sections so the most impactful rules come first. LLMs exhibit
primacy bias — earlier instructions get more attention.

**Prompt template:**
```
You are editing agent instructions for a Snowflake Cortex Agent.

Current instruction file ({target_file}):
---
{current_text}
---

The agent fails most often on:
{failure_context}

TASK: Reorder the sections so that rules relevant to the most common failure
patterns appear earlier in the file. Do NOT change any rule content — only
move sections. The goal is to put the highest-impact guidance where the LLM
will attend to it most.

Output the full revised instruction file with sections reordered.
```

**Initial weight:** 0.10

---

### 5. sharpen_ambiguity

**Target:** Any instruction file
**Intent:** Replace vague instructions with specific, testable ones.

**Prompt template:**
```
You are editing agent instructions for a Snowflake Cortex Agent.

Current instruction file ({target_file}):
---
{current_text}
---

The agent fails on these questions:
{failure_context}

TASK: Find vague or ambiguous instructions and make them specific. Examples:
- "Try to use the right tool" → "For questions about revenue, always use the REVENUE_TOOL first"
- "Format the response nicely" → "Always include the metric name, value, and time period in the first sentence"
- "Be careful with calculations" → "Never perform arithmetic on tool outputs. Report the numbers exactly as returned."

Change 2-4 vague instructions. Do NOT add new rules or remove existing ones.
Output the full revised instruction file.
```

**Initial weight:** 0.15

---

### 6. adjust_response_format

**Target:** response_instructions.md
**Intent:** Change how the agent formats its answers to match user expectations.

**Prompt template:**
```
You are editing response instructions for a Snowflake Cortex Agent.

Current response instructions:
---
{current_text}
---

User feedback patterns:
{failure_context}

TASK: Adjust response formatting rules to address the feedback. Common fixes:
- Add "always state the time period" if users complain about ambiguous timeframes
- Add "include the data source" if users question where numbers come from
- Add "show your work" if users need to verify calculations
- Remove "include disclaimers" if responses are too verbose

Make 1-3 targeted formatting changes. Do NOT change tool routing or orchestration.
Output the full revised instruction file.
```

**Initial weight:** 0.15

---

### 7. add_routing_rule

**Target:** orchestration_instructions.md
**Intent:** Add an explicit routing rule for a specific failure pattern — "When the user asks about X, always use TOOL_Y". Most impactful for agents that select the wrong tool for specific question types.

**Prompt template:**
```
You are editing agent instructions for a Snowflake Cortex Agent.

Current orchestration instructions:
---
{current_text}
---

The agent is failing on these questions:
{failure_context}

TASK: Add ONE specific routing rule that maps an intent/keyword pattern to the correct tool.
Format: `- <pattern> ('keyword1', 'keyword2') → use <tool_name>`

Do NOT rewrite existing rules. Do NOT add multiple rules. Place the new rule in the most
relevant routing section, or create a "## Tool Routing Rules" section if none exists.
Output the full revised instruction file.
```

**Initial weight:** 0.15

---

### 8. add_domain_rule

**Target:** response_instructions.md
**Intent:** Add a domain-specific constraint or clarification. Use when agents apply wrong business logic or misinterpret domain-specific terms.

**Prompt template:**
```
You are editing agent instructions for a Snowflake Cortex Agent.

Current response instructions:
---
{current_text}
---

The agent is failing on these questions:
{failure_context}

TASK: Add ONE concise domain rule (1-2 sentences) stating the constraint the agent is violating.
Prefer referencing authoritative sources over surface-level patterns.
Place it in the most relevant existing section, or create a "## Domain Rules" section.
The rule must be specific and falsifiable — reject vague rules like "be more accurate".

Do NOT rewrite other rules. Do NOT add multiple rules.
Output the full revised instruction file.
```

**Initial weight:** 0.10

---

### 9. add_retry_logic

**Target:** orchestration_instructions.md
**Intent:** Add retry behavior for transient tool errors. Note: this operator has a direct template application in GEPA (appends a fixed retry block without LLM). In instruction-optimizer it is LLM-assisted since we are generating full instruction variants, not patches.

**Prompt template:**
```
You are editing agent instructions for a Snowflake Cortex Agent.

Current orchestration instructions:
---
{current_text}
---

The agent is failing on these questions:
{failure_context}

TASK: Add a retry behavior rule for transient tool errors. The rule should specify:
- Retry up to 2 times on transient/empty results before giving up
- Report the failure clearly rather than guessing if retries are exhausted

Keep it to 3-5 lines. Place it in a "## Retry Logic" section (create if absent).
Do NOT modify any other content.
Output the full revised instruction file.
```

**Initial weight:** 0.15

---

> **Note:** The per-generation weight-update rules (×1.3/×0.7) below are superseded
> by the TPE optimizer. Operator selection is now handled by bulk pre-generation in
> Phase 3 — operators are assigned once upfront, not updated dynamically. See
> "Operator Assignment Rules" section above.

## Operator Selection Rules (legacy — superseded by TPE)

1. **No repeats within a generation:** Each candidate in the same generation uses
   a different operator (if enough operators exist for the candidate count).

2. **Weight update after each generation:**
   - Winning operator: weight × 1.3
   - Losing operator: weight × 0.7
   - Floor: 0.05

3. **Cooldown:** An operator that produced a losing candidate in 2 consecutive
   generations gets a 1-generation cooldown (skipped in selection).

4. **Target file rotation:** If an operator was used on `orchestration_instructions.md`
   last generation, prefer `response_instructions.md` this generation (and vice versa).

---

## Anti-Pattern Rejection

After generating a variant, check for these anti-patterns. If detected, regenerate
with an explicit "avoid this" addendum to the prompt (1 retry, then skip this candidate slot).

| Anti-Pattern | Detection | Why It's Bad |
|---|---|---|
| Verbose checklist | >5 numbered steps in a single rule | LLMs ignore long checklists |
| Tool description change | Diff touches tool name, description, or type fields | Breaks tool routing |
| Length explosion | Variant >2x parent length | Dilutes attention |
| No-op | Diff is empty or whitespace-only | Wastes an eval cycle |
| Duplicate of parent | Variant matches current best within 95% token overlap | No exploration value |

---

## Operator Assignment Rules

These rules govern how the 12-variant instruction pool is populated in Phase 3.

### Pool construction (12 slots)

1. **One slot per operator:** Each of the 9 operators gets at least 1 slot. This guarantees every operator is represented in the pool regardless of weights.

2. **No duplicate (operator, target_file) combinations:** No two slots may apply the same operator to the same target file. Since most operators have a fixed target, this mainly affects operators that accept "Any instruction file" (`compress_verbose`, `restructure_sections`, `sharpen_ambiguity`) — vary their target across slots.

3. **Remaining slots (12 − 9 = 3) assigned by failure context:** Examine the `failure_context` input to identify which failure categories are most represented, then assign extra slots to the corresponding operator family using the mapping below. If failure context is absent or ambiguous, distribute the 3 extra slots to the top-3 operators by initial weight (`add_worked_example`, `add_negative_example`, `add_routing_rule`).

### Failure category → operator family mapping

Mirrors `FAILURE_OPERATOR_MAP` in `mutate.py`:

| Failure category | Preferred operators |
|---|---|
| `routing` | `add_routing_rule`, `rewrite_ambiguous_rule` (maps to `sharpen_ambiguity`) |
| `tool_error` | `add_retry_logic` |
| `formatting` | `adjust_response_format` (maps to `add_format_template`) |
| `content` | `add_worked_example`, `add_negative_example`, `add_domain_rule` |
| `ambiguity` | `sharpen_ambiguity`, `add_negative_example` |
| `verbosity` | `compress_verbose` |

> **Note on name differences:** GEPA's `mutate.py` uses shorter operator names (`fix_example`, `add_wrong_example`, `add_format_template`, `rewrite_ambiguous_rule`, `remove_verbose_rule`). The instruction-optimizer operators listed here are functionally equivalent but LLM-assisted and named for clarity. Use the table above to map failure categories to the correct operator name in this catalog.

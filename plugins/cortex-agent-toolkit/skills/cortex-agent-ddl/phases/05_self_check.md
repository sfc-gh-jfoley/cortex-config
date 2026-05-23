---
name: cortex-agent-ddl-phase5-self-check
description: 17-rule spec validation — auto-fix hard FAILs, present WARNs to user — runs before every execution including edits
---

# Phase 5: Self-Check

## Purpose
Validate `AGENT_SPEC` against 17 rules before presenting to the user or executing. Hard FAILs are auto-fixed and re-checked in a loop. WARNs are presented with "accept / fix" options. Nothing broken reaches Phase 6.

**This phase is always run** — for new agents after Phase 4, and for edits before ALTER in the edit flow.

---

## Step 5.1: Run all 17 checks

Evaluate `AGENT_SPEC` against each rule. Record PASS / FAIL / WARN for each.

---

### HARD FAILS (auto-fix before presenting spec)

| # | Rule | How to check | Auto-fix |
|---|------|-------------|----------|
| 1 | `models.orchestration` is set to a non-empty string | `spec.models.orchestration` exists and is not `""` or `null` | Set to value of `default_agent` alias from LLMs.md (currently `claude-sonnet-4-6`) |
| 2 | `instructions.orchestration` is present and non-empty (>50 chars) | `spec.instructions.orchestration` exists and length > 50 | Prompt user — cannot auto-generate without context |
| 3 | Each `cortex_analyst_text_to_sql` tool has `tool_resources[name].execution_environment.type = "warehouse"` and `tool_resources[name].execution_environment.warehouse` is non-empty | For each `cortex_analyst_text_to_sql` tool name T: `spec.tool_resources[T].execution_environment.type == "warehouse"` and `spec.tool_resources[T].execution_environment.warehouse` is non-empty string. Also check no top-level `execution_environment` exists — if found, it must be removed. | Add `execution_environment: {type: "warehouse", warehouse: AGENT_WAREHOUSE}` inside each offending tool_resources entry; remove any top-level `execution_environment` block |
| 4 | `tools` array is non-empty | `spec.tools.length > 0` | Cannot auto-fix — return to Phase 2 |
| 5 | Every `tools[i].tool_spec.name` has a matching key in `tool_resources` | For each tool name T: `spec.tool_resources[T]` exists | Add empty `{}` entry for each missing key (Phase 2 mismatch) |
| 6 | No duplicate `tool_spec.name` values across `tools[]` | Collect all names → check for duplicates | Rename duplicate by appending `_2`, `_3`, etc. |
| 7 | `cortex_analyst_text_to_sql` tools: `tool_resources[name].semantic_view` is a 3-part FQN matching `X.Y.Z` | Regex: `\w+\.\w+\.\w+` on the value | Cannot auto-fix — surface to user with SHOW SEMANTIC VIEWS |
| 8 | `cortex_search` tools: `tool_resources[name].name` is a 3-part FQN | Regex: `\w+\.\w+\.\w+` | Cannot auto-fix — surface to user |
| 9 | `generic` tools: `tool_resources[name]` has either `function` or `procedure` key (not both empty) | At least one of the two keys exists | Cannot auto-fix — ask user for function FQN |
| 10 | Each tool description is > 100 characters | `tool_spec.description.length > 100` | Trigger CORTEX.COMPLETE regeneration (Phase 2 Step 2.6) |

---

### WARNINGS (present to user with accept/fix option)

| # | Rule | How to check | Default action |
|---|------|-------------|----------------|
| 11 | Each tool description contains boundary language | Description contains "not use" OR "do not" OR "only for" OR "avoid" | WARN — offer to add boundary section |
| 12 | `orchestration.budget.seconds` AND `orchestration.budget.tokens` are both set | Both keys exist under `orchestration.budget` | WARN — add defaults: seconds=120, tokens=200000 |
| 13 | `experimental.EnableAgenticAnalyst` is present and `true` | Check key + value | WARN — offer to add |
| 14 | `profile.display_name` note exists (checked against `AGENT_PROFILE` from Phase 4) | `AGENT_PROFILE.display_name` non-empty | WARN — remind that ALTER SET PROFILE must be run in Phase 6 |
| 15 | Tool count ≤ 10 | `spec.tools.length <= 10` | WARN if >10 — inform of best-practices guidance; user must explicitly accept |
| 16 | Router agents must not self-answer | If `AGENT_TYPE == "router"`: `instructions.orchestration` contains "do not attempt to answer" or "must invoke" or "never answer yourself" | WARN — router instructions should explicitly prohibit self-answering. Add: "Do NOT attempt to answer yourself. You MUST invoke a tool." |
| 17 | Multitenant agent has RAP pattern documented | If `IS_MULTITENANT == true` (set in Phase 1): check that `AGENT_SPEC.instructions.orchestration` or Phase 4b spec notes reference a RAP isolation pattern (user/role/session-attribute). Search for "RAP", "row access", "tenant", "CURRENT_USER", "CURRENT_ROLE", or "SESSION_ATTRIBUTES" in instructions or spec notes. | WARN — "IS_MULTITENANT=true but no RAP pattern documented in spec notes. Run Phase 4b or add tenant isolation guidance to instructions." Offer: (A) Load Phase 4b now, (B) Add a note to instructions acknowledging tenant isolation is handled externally, (C) Dismiss |

---

## Step 5.2: Auto-fix loop

For every HARD FAIL where an auto-fix exists:
1. Apply the fix to `AGENT_SPEC`
2. Re-run that specific check
3. If still FAIL after fix: escalate to user — cannot proceed without manual input
4. Continue until all auto-fixable FAILs are resolved

For HARD FAILs with no auto-fix: present the specific error and wait for user input before re-checking.

**Iteration limit**: after 3 auto-fix rounds on the same rule without resolution, stop and present it to the user for manual resolution.

---

## Step 5.3: Present self-check results

### If all 10 hard checks pass:

```
Self-check: 10/10 PASS  (<N> warnings)

Spec summary:
  Model:       <AGENT_MODEL>
  Tools:       <N> — <list of tool names>
  Budget:      <seconds>s / <tokens> tokens
  Flags:       EnableAgenticAnalyst=<true/false>, EnableVQRFastPath=<true/false>
  Instructions: <char count> chars

Warnings:
  ⚠️  Rule 11: Tool "<name>" description has no boundary language
      → Add "When NOT to use" section? (yes/no)
  ⚠️  Rule 14: Profile not set yet — will be set in Phase 6 via ALTER AGENT SET PROFILE
      → Acknowledged ✓

[Full spec JSON]

Type 'go' to execute, or request changes.
```

### If any hard check still fails after auto-fix attempts:

```
Self-check: <N>/10 PASS, <M> FAIL — cannot proceed

FAIL — Rule <N>: <description of failure>
  Location: spec.<path>
  Current value: <value>
  Required: <requirement>
  Fix: <specific instruction>

Please resolve and type 'retry' to re-run self-check.
```

---

## Step 5.3.5: Run syntax-verifier

After self-check passes, launch the syntax verifier for a doc-backed second pass
against current Snowflake docs before presenting to the user:

```
Launch a snowflake-syntax-verifier agent to verify the agent spec JSON.
```

Pass the full `AGENT_SPEC` JSON as input.

- **FAIL** → fix issues reported, return to Step 5.1 to re-run self-check
- **WARN** → include warnings in the Step 5.3 output block alongside self-check results
- **PASS** → proceed

---

## Step 5.4: User options at stopping point

Present choices:

```
Options:
  go      → proceed to Phase 6 (execute)
  retry   → re-run self-check after manual edits
  edit N  → edit rule N's failing field inline
  warn N  → address warning N
  show    → display full spec JSON again
```

⚠️ **STOPPING POINT** — Do not proceed to Phase 6 until the user types 'go'.

---

## Output variables passed to next phases

| Variable | Contents |
|----------|----------|
| `AGENT_SPEC` | Validated (and auto-fixed) spec JSON — ready for execution |
| `SELF_CHECK_RESULTS` | Dict of rule number → PASS/FAIL/WARN |
| `SELF_CHECK_WARNINGS` | List of warning messages to acknowledge in Phase 6 |

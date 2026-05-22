---
name: cortex-agent-ddl-phase3-instructions
description: Draft orchestration and response instructions with built-in best-practices checks — scope, tone, tool routing, boundary statements, and chart guidance
---

# Phase 3: Build Instructions

## Purpose
Draft the `instructions.orchestration` and `instructions.response` fields that define the agent's identity, scope, and behavior. Five best-practices checks are applied inline before presenting to the user.

This phase has **one mandatory stopping point** — present the drafted instructions for approval.

---

## Step 3.0: Router-specific instruction path

> **Skip this step if `AGENT_TYPE == "domain"`.** Jump to Step 3.1.

If `AGENT_TYPE == "router"`, use the strict-router template instead of the standard domain template.

### Router orchestration template

```
You are an intelligent router. Analyze the user's inquiry to determine the correct domain and invoke the appropriate tool.

## Sub-agents

<For each tool in TOOL_NAMES:>
<TOOL_NAME>: Use this for questions regarding <domain derived from TOOL_DESCRIPTIONS[TOOL_NAME]>.

## Rules
- You MUST invoke the appropriate tool to answer the user's question. Do NOT attempt to answer yourself.
- If the question clearly spans multiple domains, invoke each relevant tool and synthesize the responses.
- If no domain matches the question, respond with: "I can help with questions about <list all domains>. Your question doesn't match any of these areas."
- Never fabricate data. Your only source of information is the sub-agent tools.
```

### Router response template

```
Present the sub-agent's response directly. Do not add your own analysis unless synthesizing responses from multiple sub-agents. If synthesizing, clearly label which sub-agent provided each piece of information.
```

### Router BP checks (replaces standard BP-1 through BP-5)

| Check | Rule | Auto-pass condition |
|-------|------|---------------------|
| R-BP-1 | "Do NOT attempt to answer yourself" or equivalent is present | Required for routers |
| R-BP-2 | Each tool has a routing sentence | Same as BP-2 |
| R-BP-3 | No-match fallback exists ("I can help with...") | Required |
| R-BP-4 | Instruction length 150-1500 chars | Routers are simpler, shorter is fine |
| R-BP-5 | No chart/visualization guidance needed | Auto-pass — routers don't generate charts |

After drafting and checking, store as `INSTRUCTIONS_ORCHESTRATION` and `INSTRUCTIONS_RESPONSE`. Generate 4-6 sample questions (at least 1 per sub-agent) and store as `SAMPLE_QUESTIONS`.

**Then skip to the MANDATORY STOP below** — do not run Step 3.1-3.4.

---

## Step 3.1: Build the orchestration instruction draft

Using `AGENT_PURPOSE`, `TOOL_NAMES`, and `TOOL_DESCRIPTIONS` from prior phases, draft the orchestration instruction using this structure:

### Template

```
You are <AGENT_IDENTITY> — a specialized data agent for <DOMAIN>.

## Scope
You answer questions about: <list 3-5 key question categories from AGENT_PURPOSE>

You do NOT answer questions about: <list 2-3 explicit out-of-scope areas>

## Tools available
<For each tool:>
Use [TOOL_NAME] for: <1-line routing summary derived from tool description>

## Behavior rules
- Always verify your answer is supported by data before responding.
- If a question is ambiguous, ask one clarifying question before querying.
- If no relevant data is found, say so clearly — do not invent figures.
- Prefer specific, quantified answers over vague summaries.
- When results involve currency or percentages, include units in the response.

## Data freshness
<State the approximate data freshness, e.g. "Data is updated nightly" or "Real-time data via streaming" — derive from SV_METADATA if possible, otherwise ask the user>
```

Populate all `<...>` sections using session context. Do not leave placeholders unfilled.

---

## Step 3.2: Build the response instruction draft

```
Be concise and direct. Lead with the answer, then supporting detail.
Format tabular results as markdown tables when there are 3+ rows.
When showing trends, include both the absolute value and the percent change.
Use the user's terminology — if they say "revenue", don't switch to "total sales".
```

Adjust based on `AGENT_PURPOSE` — e.g., for executive-facing agents, add: "Use plain language without SQL jargon."

---

## Step 3.3: Best-practices checks

Apply these 5 checks to the drafted instructions. Fix any failures before presenting.

### BP-1: Scope definition
- ✅ PASS: `orchestration` contains at least one explicit "You do NOT answer" or "Out of scope" statement
- ❌ FAIL: Scope is unbounded — agent will try to answer everything, causing tool misselection

**Fix**: Add 2-3 explicit out-of-scope statements derived from `AGENT_PURPOSE`.

---

### BP-2: Tool routing guidance
- ✅ PASS: Each tool has at least one routing sentence in the instructions (e.g., "Use X for questions about Y")
- ❌ FAIL: Instructions mention no tools — agent must guess routing from descriptions alone

**Fix**: Add one routing sentence per tool using the pattern: `"Use [TOOL_NAME] for: <question types>"`

---

### BP-3: Hallucination guardrail
- ✅ PASS: Instructions contain "do not invent", "only use data", "if no data found say so", or equivalent
- ❌ FAIL: No guardrail against fabrication

**Fix**: Add: `"If the data does not support a definitive answer, say so clearly. Do not extrapolate or invent figures."`

---

### BP-4: Instruction length
- ✅ PASS: `orchestration` is between 200-2000 characters
- ⚠️ WARN if < 200: Too short — agent lacks enough guidance
- ⚠️ WARN if > 2000: May be too verbose — consider trimming to the most important rules

---

### BP-5: Chart / visualization guidance (if EnableAgenticAnalyst = true)
- ✅ PASS: Instructions mention charts, visualizations, or when to present data visually
- ⚠️ WARN if absent: Agent won't know when to generate charts vs. tables

**Auto-add if missing**:
```
For trend data over time, prefer line charts. For comparisons across categories, prefer bar charts.
For single-number answers, respond as plain text without a chart.
```

---

## Step 3.4: Generate sample questions

Generate 5-6 sample questions from `AGENT_PURPOSE` and `SV_METADATA`. These appear as quick-start prompts in Snowflake Intelligence.

Guidelines:
- At least 1 question per tool
- Mix of aggregate, filter, trend, and comparison question types
- Phrase as a business user would ask, not as SQL
- Each question should be answerable with the available tools

Example format:
```json
[
  { "question": "What is our total subscriber revenue at risk from churn this quarter?" },
  { "question": "Show me the top 10 accounts by credit consumption last 30 days." },
  { "question": "Which products have the highest cancellation rate?" },
  { "question": "Compare active subscribers month-over-month for the past 6 months." },
  { "question": "How many subscribers have 3 or more products?" }
]
```

Store as `SAMPLE_QUESTIONS`.

---

## ⚠️ MANDATORY STOP

Present the full instructions package:

```
Instructions draft:

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
orchestration:
<full orchestration instruction text>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
response:
<full response instruction text>
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Best-practices checks:
  BP-1 Scope definition:       ✓ / ✗
  BP-2 Tool routing:           ✓ / ✗
  BP-3 Hallucination guardrail: ✓ / ✗
  BP-4 Instruction length:     ✓ (<N> chars) / ⚠️
  BP-5 Chart guidance:         ✓ / ⚠️

Sample questions (<N>):
  1. "<question>"
  2. "<question>"
  ...

Type 'go' to proceed, or edit the instructions inline.
```

Wait for user approval before loading Phase 4.

---

## Output variables passed to next phases

| Variable | Contents |
|----------|----------|
| `INSTRUCTIONS_ORCHESTRATION` | Approved orchestration instruction string |
| `INSTRUCTIONS_RESPONSE` | Approved response instruction string |
| `SAMPLE_QUESTIONS` | List of `{question: "..."}` objects |
| `BP_CHECKS` | Dict of BP-1 through BP-5 results (for Phase 5 reference) |

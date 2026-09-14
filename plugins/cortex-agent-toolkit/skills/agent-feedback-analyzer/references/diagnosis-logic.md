# Diagnosis Logic Reference

> Root cause classification decision tree for pilot feedback triage.
> Used by `agent-feedback-analyzer` Phase 3.

---

## Decision Tree

For each cluster of negative feedback, walk this tree top-down. Stop at the first
classification that matches.

```
Input: cluster of negative feedback with input_query + agent_response + feedback_message

1. Can the SV answer this question at all?
   │
   ├─ NO (empty result / error / NULL)
   │   └─ ROOT CAUSE: SV Gap
   │      Suggestion type: SV FIX
   │      Detail: Missing metric, table, or relationship in semantic view
   │      Route to: sv-ddl (semantic-view-toolkit)
   │
   └─ YES (SV returns data)
       │
       2. Does the SV return correct data?
       │
       ├─ NO (SV data doesn't match known ground truth or domain logic)
       │   └─ ROOT CAUSE: SV Quality Issue
       │      Suggestion type: SV FIX
       │      Detail: Wrong calculation, stale data, incorrect join, filter error
       │      Route to: sv-iterative-optimizer (semantic-view-toolkit)
       │
       └─ YES (SV data is correct)
           │
           3. Does the agent response match the SV data?
           │
           ├─ NO (agent synthesized wrong answer from correct data)
           │   │
           │   4. Is the failure consistent? (replay 3x)
           │   │
           │   ├─ CONSISTENT (fails 2+/3)
           │   │   └─ ROOT CAUSE: Agent Instruction Problem
           │   │      Suggestion type: INSTRUCTION FIX
           │   │      Detail: Bad synthesis, wrong formatting, hallucinated numbers
           │   │      Route to: agent-optimizer
           │   │
           │   └─ INTERMITTENT (fails 1/3)
           │       └─ ROOT CAUSE: Non-Deterministic SQL
           │          Suggestion type: VQR CANDIDATE
           │          Detail: Agent generates different SQL each time, some wrong
           │          Route to: vqr-generator (semantic-view-toolkit)
           │
           └─ YES (agent response is correct)
               │
               └─ ROOT CAUSE: User Training Issue
                  Suggestion type: USER TRAINING
                  Detail: User expectation doesn't match reality
                  Route to: No tool change — documentation/training
```

---

## Classification Details

### SV Gap

**Signals:**
- `cortex analyst query` returns empty result or error
- Feedback message mentions a concept not in the SV (e.g., "what about net revenue"
  when only gross_revenue exists)
- Agent response says "I don't have data for that" or similar

**Report template:**
```
Root cause: SV gap — <CONCEPT> not available in semantic view
Evidence: cortex analyst query "<question>" returned no data
Suggestion: Add <CONCEPT> metric/dimension to <SV_NAME>
Route to: semantic-view-toolkit → sv-ddl
```

### SV Quality Issue

**Signals:**
- SV returns data but numbers don't match feedback message complaints
- Feedback says "wrong numbers" and the SV calculation is verifiably incorrect
- Data is stale (e.g., SV shows last month's data as current)

**Report template:**
```
Root cause: SV quality — <METRIC> returns incorrect values
Evidence: SV returns <X> for "<question>", expected <Y> based on <reason>
Suggestion: Fix <METRIC> calculation in <SV_NAME>
Route to: semantic-view-toolkit → sv-iterative-optimizer
```

### Agent Instruction Problem

**Signals:**
- SV returns correct data, but agent response is wrong
- Consistent across 2+/3 replays
- Agent misformats, halluccinates additional context, or combines tools incorrectly

**Report template:**
```
Root cause: Agent instruction problem — <DESCRIPTION>
Evidence: SV returns correct data (<DATA>), agent responds "<WRONG_RESPONSE>"
Replayed 3x: <PASS_COUNT>/3 correct
Suggestion: Update agent instructions to <SPECIFIC_GUIDANCE>
Route to: agent-optimizer
```

### Non-Deterministic SQL

**Signals:**
- SV returns correct data, but agent is correct only some of the time
- Different SQL generated on each replay
- Typically affects multi-step or multi-tool questions

**Report template:**
```
Root cause: Non-deterministic SQL generation for "<QUESTION_PATTERN>"
Evidence: Replayed 3x — 1/3 correct. Each run produced different SQL.
Suggestion: Add verified query (VQR) to stabilize this question pattern
Route to: vqr-generator
```

### User Training Issue

**Signals:**
- SV returns correct data
- Agent response matches the data
- User feedback says it's wrong, but the agent is correct
- Common pattern: user expects a different metric definition (e.g., gross vs net),
  a different time period, or numbers from a legacy system

**Report template:**
```
Root cause: User training — agent is correct, user expectation misaligned
Evidence: Agent returns <CORRECT_VALUE> for "<QUESTION>". User feedback: "<MESSAGE>".
Analysis: User likely expects <WHAT_USER_EXPECTS> vs actual definition <ACTUAL_DEF>.
Suggestion: Clarify <CONCEPT> definition in pilot onboarding materials.
  Consider adding a note to agent response guidelines explaining methodology.
Route to: No tool change needed — training/documentation update
```

---

## Handling Ambiguous Cases

When classification is uncertain:

1. **Multiple root causes in one cluster** — Split the cluster. Report each sub-group
   separately with its own classification.

2. **Can't determine if SV or agent is wrong** — Report as "NEEDS INVESTIGATION" with
   the evidence gathered so far. Don't guess.

3. **Feedback message contradicts the data** — Report as potential user training issue
   but flag for manual review: "User says X, data shows Y — verify which is correct
   before acting."

4. **No feedback message on negative feedback** — Classification is limited to what
   can be determined from replay. Report confidence level as "medium" (no user context).

---

## Replay Limits

To keep the diagnostic pass lightweight:
- Max 5 unique questions per cluster for SV replay
- Max 3 replays per question for consistency check
- Skip SV replay for clusters with >20 feedback events — sample 5 representative questions
- Total diagnostic budget: ~15 agent calls per triage session

If the user wants deeper analysis on a specific cluster, suggest routing to
`agent-optimizer` DIAGNOSE intent for that cluster's questions specifically.

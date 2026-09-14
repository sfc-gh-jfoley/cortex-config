---
name: agent-feedback-analyzer
description: >
  Read-only diagnostic triage of CoWork pilot user feedback (thumbs up/down).
  Pulls feedback from AI_OBSERVABILITY_EVENTS, clusters failures, diagnoses
  root causes, and produces a prioritized remediation report with suggestions.
  Never modifies the agent, SV, or eval dataset — human decides what to act on.
  Use when: pilot feedback, user feedback triage, thumbs down analysis,
  CoWork feedback, beta feedback, feedback report, what are users complaining about.
triggers:
  - pilot feedback
  - user feedback
  - feedback triage
  - thumbs down
  - what are users saying
  - CoWork feedback
  - beta feedback
  - feedback report
  - analyze feedback
---

> **Read-only skill.** This skill never modifies the agent, semantic view, eval dataset,
> or any Snowflake object. It produces a diagnostic report with suggestions. The human
> decides what to act on — including "do nothing, train the users instead."

## Execution Mode

Inherits the session mode declared at the toolkit router (see root `SKILL.md`). Never re-asks.

- **INTERACTIVE** (default): Cluster selection gate (Phase 2) blocks for user input on which clusters to diagnose. Phase 5 eval-dataset promotion is asked as opt-in.
- **AUTONOMOUS**: Diagnoses all clusters automatically (`AUTO_RESOLVE: FEEDBACK-CLUSTER-DIAGNOSE`); logs `[AUTO-RESOLVED: FEEDBACK-CLUSTER-DIAGNOSE → all clusters]`. Phase 5 promotion is automatically declined (`AUTO_RESOLVE: FEEDBACK-DATASET-PROMOTE`) — read-only behavior is preserved; eval dataset writes require explicit operator intent. True blockers (`FEEDBACK-NO-DATA`, `FEEDBACK-REDACTED`) still terminate in both modes.

See `../../references/gate-inventory.md` for full classifications.

# Agent Pilot Feedback

Triage CoWork user feedback (thumbs up/down) into a diagnostic report with
prioritized remediation suggestions for agents in pilot or beta programs.

## Prerequisites

- Agent deployed in CoWork with real user traffic generating feedback
- Role with MONITOR on the agent + CORTEX_USER database role
- Account-level `READ UNREDACTED AI OBSERVABILITY EVENTS TABLE` granted (for full text)

Read `metadata.yaml` for parameters if not already loaded (`<DATABASE>`, `<SCHEMA>`,
`<AGENT_NAME>`, `<CONNECTION>`). If no optimization project exists, ask the user for
the agent's fully qualified name.

---

## Phase 1: Pull & Summarize

### Step 1: Query Feedback Summary

```sql
SELECT
    VALUE:positive::BOOLEAN AS is_positive,
    COUNT(*) AS feedback_count,
    MIN(TIMESTAMP) AS earliest,
    MAX(TIMESTAMP) AS latest,
    COUNT(DISTINCT RECORD_ATTRIBUTES:"snow.ai.observability.user.name"::STRING) AS distinct_users
FROM TABLE(SNOWFLAKE.LOCAL.GET_AI_OBSERVABILITY_EVENTS(
    '<DATABASE>', '<SCHEMA>', '<AGENT_NAME>', 'CORTEX AGENT'
))
WHERE RECORD:name = 'CORTEX_AGENT_FEEDBACK'
GROUP BY is_positive
ORDER BY is_positive;
```

### Step 2: Present Summary Dashboard

Report:
- Total feedback events (positive / negative / ratio)
- Date range covered
- Distinct users providing feedback
- Feedback velocity (events per day, trending up or down)

If zero feedback events: **STOP** — "No feedback found. The agent needs real user
traffic in CoWork before this skill can help."

If only positive feedback: **STOP** — "All feedback is positive ({N} thumbs-up from
{M} users). No issues to triage."

### Step 3: Pull Full Negative Feedback Detail

Load `references/feedback-queries.md` Workflow A to join feedback events to request
events. This produces a table of:

| request_id | input_query | agent_response | feedback_message | categories | user | timestamp |

Only pull negative feedback (`is_positive = FALSE`). Store results for Phase 2.

---

## Phase 2: Cluster Failures

### Step 1: Group by Available Signals

Cluster the negative feedback using the best available signal, in priority order:

1. **By `categories`** (if populated) — structured signal from the CoWork UI
2. **By tool/category** — match input queries to the agent's tool taxonomy
   (e.g., "revenue" questions → `cortex_analyst_text_to_sql` tool against revenue SV)
3. **By semantic similarity** — group questions that ask about the same concept
4. **By feedback message text** — cluster similar complaint text

### Step 2: Present Cluster Summary

```
Feedback Clusters (negative only):

  Cluster 1: Revenue metrics (12 thumbs-down, 4 users)
    Sample: "What was Q3 net revenue?" / "Show revenue by region"
    Feedback messages: "wrong numbers" (x3), "doesn't match our dashboard" (x2)

  Cluster 2: Churn analysis (8 thumbs-down, 3 users)
    Sample: "What's our monthly churn rate?" / "Churn by segment"
    Feedback messages: "no data returned" (x4)

  Cluster 3: Ad-hoc joins (3 thumbs-down, 2 users)
    Sample: "Compare revenue to headcount by department"
    Feedback messages: (none provided)

  Unclustered: 2 thumbs-down (insufficient signal to group)
```

**⚠️ STOP:** Present clusters. Ask user: "Which clusters should I diagnose?
(all / select by number / skip to report)"

---

## Phase 3: Diagnose Root Cause Per Cluster

For each selected cluster, run diagnosis. Load `references/diagnosis-logic.md`
for the full decision tree.

### Step 1: Replay Questions Against the SV

For each unique input query in the cluster (up to 5 per cluster):

```bash
cortex analyst query "<input_query>" --view=<SEMANTIC_VIEW_FQN>
```

Classify each result:
- **SV returns no data / error** → SV gap (missing metric, missing table, broken join)
- **SV returns data** → proceed to Step 2

### Step 2: Compare SV Output to Agent Response

For questions where the SV returns data, compare:
- What the SV returned (the raw data)
- What the agent responded (from the feedback event)
- What the user expected (from `feedback_message` if available)

Classify:
- **SV correct, agent wrong** → Agent instruction problem (bad synthesis, wrong formatting, hallucinated numbers)
- **SV correct, agent correct, user wrong** → **User training issue** (user expectation doesn't match the data definition)
- **SV wrong** → SV quality issue (wrong calculation, stale data, incorrect join)

### Step 3: Check Consistency (for agent instruction problems)

For questions classified as agent instruction problems, replay 3x through the agent:

```sql
SELECT SNOWFLAKE.CORTEX.DATA_AGENT_RUN(
    '<DATABASE>.<SCHEMA>.<AGENT_NAME>',
    OBJECT_CONSTRUCT('messages', ARRAY_CONSTRUCT(
        OBJECT_CONSTRUCT('role', 'user', 'content', ARRAY_CONSTRUCT(
            OBJECT_CONSTRUCT('type', 'text', 'text', '<input_query>')
        ))
    ))
):result::STRING;
```

- Fails 2+/3 → Consistent failure (instruction fix needed)
- Fails 1/3 → Non-deterministic (VQR candidate)

---

## Phase 4: Remediation Report

### Step 1: Classify and Prioritize

For each cluster, assign a root cause and recommendation:

| Root Cause | Recommendation Type |
|---|---|
| SV gap (no data) | **SV fix** — add missing metric/table to semantic view |
| SV quality (wrong data) | **SV fix** — correct calculation, join, or filter |
| Agent instruction problem | **Instruction fix** — optimize agent instructions |
| Non-deterministic SQL | **VQR candidate** — add verified query for stability |
| User training issue | **User training** — clarify definitions, update onboarding |

Priority scoring:
- Feedback volume × 3 (more users = higher priority)
- Distinct users × 2 (broad impact > single user repeating)
- Has feedback message × 1 (actionable signal)

### Step 2: Present Remediation Report

```
╔══════════════════════════════════════════════════════════════╗
║  PILOT FEEDBACK TRIAGE REPORT                               ║
║  Agent: <DATABASE>.<SCHEMA>.<AGENT_NAME>                    ║
║  Period: <earliest> — <latest>                              ║
║  Feedback: <pos> positive, <neg> negative (<ratio>)         ║
║  Users: <N> distinct                                        ║
╠══════════════════════════════════════════════════════════════╣

Priority 1: Revenue metrics [SV FIX]
  Impact: 12 thumbs-down, 4 users
  Root cause: SV missing NET_REVENUE metric — users expect net, SV only has gross
  Suggestion: Add net_revenue metric to semantic view
  Route to: semantic-view-toolkit → sv-ddl
  Evidence: "What was Q3 net revenue?" → SV returns NULL, user says "wrong numbers"

Priority 2: Churn analysis [USER TRAINING]
  Impact: 8 thumbs-down, 3 users
  Root cause: Agent returns correct churn rate (2.3%), users expect the number
  from their legacy dashboard (which used a different calculation methodology)
  Suggestion: Clarify churn definition in user onboarding; add note to agent
  response guidelines about methodology transparency
  Route to: No tool change needed — training/documentation

Priority 3: Ad-hoc joins [VQR CANDIDATE]
  Impact: 3 thumbs-down, 2 users
  Root cause: Cross-tool queries produce inconsistent SQL — correct 1/3 times
  Suggestion: Add verified queries for common cross-domain patterns
  Route to: vqr-generator (if using semantic-view-toolkit)
  Evidence: 3x replay → 1 pass, 2 fail with different SQL each time
```

### Step 3: Output Formats

Present the report in the terminal. Additionally offer:
- "Save as markdown to `<WORKSPACE>/pilot_feedback_report_<DATE>.md`?"
- "Want me to break these into tasks?" (creates `cortex ctx task add` entries
  for each actionable suggestion — still read-only, just task tracking)

---

## Phase 5: Optional — Promote to Eval Dataset

> This phase is **opt-in only**. Ask: "Would you like to promote any of these
> feedback questions into the eval dataset for future optimization cycles?"

If the user says yes, hand off to `agent-optimizer` FEEDBACK intent,
which loads `references/feedback-pipeline.md`. That skill handles the actual
writes — this skill stays read-only.

The handoff context includes:
- Which clusters the user selected
- The diagnosed root causes (so feedback-pipeline can skip re-diagnosis)
- The input queries and any ground truth determined during Phase 3

---

## Key Principles

1. **Never modify anything.** This skill reads observability events and presents findings.
2. **User training is a valid finding.** Not every thumbs-down means the tool is broken.
3. **Evidence-based.** Every suggestion includes the evidence that led to the classification.
4. **Cluster, don't list.** Individual feedback events are noise. Clusters reveal patterns.
5. **Priority by impact.** Volume × breadth, not recency or severity of individual complaints.

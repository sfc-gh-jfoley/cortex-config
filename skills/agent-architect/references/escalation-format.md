# Escalation Format

When a task exceeds retry limits or hits a blocker the framework cannot resolve,
the Architect escalates to the user using this structured format.

## Template

```
ESCALATION: <task_id> — <task_title>
PHASE: <which phase failed (GATE / VERIFY / EXECUTE)>
REASON: <SecArch rejected 2x | Tester failed 2x | Build loop stuck | Dependency missing>

ATTEMPTS:
  Attempt 1: <what was tried, what happened>
  Attempt 2: <what was tried differently, what happened>

FINDINGS (cumulative across all attempts):
  - [CRITICAL/HIGH] <finding from SecArch or Tester>
    File: <path>:<line>
    Description: <the actual problem>
    Remediation tried: <what the worker attempted>
    Why it didn't work: <why the fix failed or was rejected again>

ARCHITECT ASSESSMENT:
  <Architect's analysis of the root cause — why retries aren't converging>

OPTIONS:
  A) Descope — remove this task from the plan (state what's lost)
  B) Provide guidance — tell the Architect what to relay to the next Worker
  C) Manual fix — you edit the code directly, then we resume gating
  D) Change approach — suggest a different architectural path for this task
```

## When to Escalate

| Trigger | Threshold |
|---|---|
| SecArch REJECTED same task | After 2nd rejection |
| Tester FAIL same task | After 2nd failure |
| Worker self-reports BLOCKED (build loop) | After 3 toolchain cycles with no green |
| Worker BLOCKED on missing dependency | Immediately (no retry — dependency must be resolved) |
| Stuck task (no progress, agent terminated) | After 1 re-spawn attempt fails |

## Headless Mode Escalation

In headless execution, escalations go to the configured channel:

| `escalation_channel` | Behavior |
|---|---|
| `"user"` | `ask_user_question()` — blocks until response (interactive only) |
| `"memory"` | `cortex memory remember "ESCALATION: <task_id> — <summary>"` — async review |
| `"file"` | Write to `.agent-project/escalation.md` — user reads later |

In headless mode with `halt_on` conditions, CRITICAL escalations STOP the entire
project. The Architect writes full context to `escalation.md` and exits.

## Rules

- Never escalate without attempting the full retry budget first
- Always include what was tried — the user needs context to make a decision
- The Architect MUST provide its own assessment (not just relay findings)
- Options must be concrete and actionable — not "what should we do?"
- After user responds, the Architect relays the decision to the next Worker spawn

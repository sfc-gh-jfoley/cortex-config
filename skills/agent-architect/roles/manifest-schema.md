# Manifest Schema

Canonical reference for `.agent-project/manifest.log`. All roles write to this file.
Git is the durable state — every manifest write is immediately committed.

---

## Format

```
TIMESTAMP | TASK_ID | PHASE | ROLE | field=value ... | narrative
```

- `TIMESTAMP` — UTC ISO-8601, always from the clock (`date -u +%Y-%m-%dT%H:%M:%SZ`), never composed
- `TASK_ID` — stable identifier assigned at TASK_REGISTERED (e.g. `task-03`)
- `PHASE` — one of the phases defined below (closed enum — no ad-hoc values)
- `ROLE` — `orchestrator` | `worker` | `secarch` | `tester` | `team-arch-<N>`
- `field=value` — evidence fields, phase-specific (defined below)
- `narrative` — free-form one-line summary

---

## State Machine

```
TASK_REGISTERED (orchestrator)
        ↓
    CLAIMED (worker)
        ↓
  CODE_WRITTEN (worker) ←──────────────────────────────┐
        ↓                                               │
 REVIEW_REQUESTED (team-arch)                          │ retry
        ↓                                               │
 REVIEW_PASSED (secarch)         REVIEW_FAILED (secarch) → ISSUES_FOUND (team-arch) ─┘
        ↓                                               
 TESTER_ASSIGNED (team-arch)    TESTER_FAILED (tester) → ISSUES_FOUND (team-arch) ──┐
        ↓                                               │                            │
    VERIFIED (tester)           ┌──────────────────────┘                            │
        ↓                       ↓                                                    │
     DONE (orchestrator)    (re-CLAIMED → worker retry) ───────────────────────────-┘

  BLOCKED (worker)  →  orchestrator: RETRY or REARCHITECT
REARCHITECT (orchestrator)  →  task closed; successor TASK_REGISTERED separately
```

**No role writes its own terminal state.**
Workers write `CODE_WRITTEN`, not `DONE`. SecArch writes `REVIEW_PASSED`, not approval.
Tester writes `VERIFIED`. Orchestrator is the only writer of `DONE`.

---

## Phase Definitions

### TASK_REGISTERED
Written by: orchestrator at project startup.
```
TIMESTAMP | task-03 | TASK_REGISTERED | orchestrator | title=<title> | depends_on=task-01,task-02 | <description>
```

### CLAIMED
Written by: worker at session start, before any implementation.
```
TIMESTAMP | task-03 | CLAIMED | worker | sha=<head sha> | <task title>
```

### CODE_WRITTEN
Written by: worker after toolchain loop passes cleanly (build + tests + linter).
Replaces the old self-written `DONE`. This is a readiness signal, not a completion signal.
```
TIMESTAMP | task-03 | CODE_WRITTEN | worker | sha=<sha> | tests=12/12 | linter=clean | cycles=2 | <summary>
```
- `tests=N/N` — tests written and passing count
- `linter=clean|warn` — linter result
- `cycles=1|2|3` — toolchain loop cycles used
- If this is a retry after ISSUES_FOUND: add `retry=1` (or 2, 3)

### REVIEW_REQUESTED
Written by: team-architect immediately after detecting CODE_WRITTEN, before spawning SecArch.
```
TIMESTAMP | task-03 | REVIEW_REQUESTED | team-arch-1 | sha=<sha> | <spawning secarch>
```

### REVIEW_PASSED
Written by: secarch after verdict APPROVED or APPROVED_WITH_CONDITIONS.
Secarch writes this to manifest AND commits — orchestrator reads it from manifest, not from secarch's return value.
```
TIMESTAMP | task-03 | REVIEW_PASSED | secarch | sha=<sha> | checks=18 | cross_family=true | conditions=0
```
- `checks=N` — checklist items run
- `cross_family=true|false` — whether second-family review ran
- `conditions=N` — number of CONDITION_OPEN entries written (0 for APPROVED)

### REVIEW_FAILED
Written by: secarch after verdict REJECTED.
```
TIMESTAMP | task-03 | REVIEW_FAILED | secarch | sha=<sha> | findings=3 | critical=1 | high=2 | pointer=.agent-project/findings-task03-r1.md
```
- `findings=N` — total finding count
- `critical=N high=N` — by severity
- `pointer=` — path to findings file committed by secarch (see SecArch protocol)

### ISSUES_FOUND
Written by: team-architect after reading REVIEW_FAILED or TESTER_FAILED, before re-spawning worker.
Records the re-queue decision and links back to the findings.
```
TIMESTAMP | task-03 | ISSUES_FOUND | team-arch-1 | source=secarch|tester | retry=1 | pointer=<findings file> | re-spawning worker
```
- `source=secarch|tester` — which gate rejected
- `retry=N` — which retry attempt this is (against retry_budget)

### REVIEW_FAILED findings file format
SecArch commits a findings file at `.agent-project/findings-<task_id>-r<retry>.md`:
```markdown
# SecArch Findings — task-03 retry 1

SHA reviewed: <sha>

## CRITICAL
- file: src/auth.py line 42
  check: injection
  description: <real failure scenario>
  remediation: <exactly what to change>

## HIGH
...
```
Worker reads this file, not the secarch return value — findings survive session end.

### TESTER_ASSIGNED
Written by: team-architect before spawning Tester.
```
TIMESTAMP | task-03 | TESTER_ASSIGNED | team-arch-1 | sha=<sha> | spawning tester
```

### VERIFIED
Written by: tester after PASS or PASS_WITH_WARNINGS verdict.
Tester writes this to manifest AND commits — orchestrator reads it from manifest.
```
TIMESTAMP | task-03 | VERIFIED | tester | sha=<sha> | tests=9/9 | verdict=PASS | warnings=0
```

### TESTER_FAILED
Written by: tester after FAIL verdict.
```
TIMESTAMP | task-03 | TESTER_FAILED | tester | sha=<sha> | failures=2 | critical=1 | pointer=.agent-project/tester-task03-r1.md
```
Tester commits a report file at `.agent-project/tester-<task_id>-r<retry>.md` (same structure as findings file, sec. failures only).

### DONE
Written by: orchestrator (team-architect or primary) after reading VERIFIED in manifest.
The only path to DONE is through VERIFIED. No exceptions.
```
TIMESTAMP | task-03 | DONE | team-arch-1 | sha=<sha> | via=VERIFIED | <summary>
```

### BLOCKED
Written by: worker when toolchain loop exhausts 3 cycles without passing.
```
TIMESTAMP | task-03 | BLOCKED | worker | sha=<sha> | cycles=3 | reason=<what fails> | <error summary>
```
Orchestrator decides: retry (ISSUES_FOUND + re-CLAIMED) or REARCHITECT.

### REARCHITECT
Written by: orchestrator when a task cannot be completed as scoped.
Closes this task and links to a successor.
```
TIMESTAMP | task-03 | REARCHITECT | team-arch-1 | successor=task-09 | reason=<why scope changed> | <summary>
```
- `successor=task-NN` — the new TASK_REGISTERED entry that replaces this scope
- `successor=none` — descoped entirely (no replacement)

Task is considered closed after REARCHITECT. No further phase transitions are valid on this task_id.

---

## Git Commit Messages (machine-parseable)

| Phase | Commit message format | Written by |
|---|---|---|
| CLAIMED | `[WORKER] <task_id>: CLAIMED` | worker |
| STUB | `[WORKER] <task_id>: STUB — <files>` | worker |
| TEST_WRITTEN | `[WORKER] <task_id>: TEST_WRITTEN — N tests` | worker |
| IMPL_COMPLETE | `[WORKER] <task_id>: IMPL_COMPLETE` | worker |
| TESTS_PASSING | `[WORKER] <task_id>: TESTS_PASSING — N pass` | worker |
| CODE_WRITTEN | `[READY] <task_id> — <summary>` | worker |
| ISSUES_FIXED | `[READY] <task_id>: ISSUES_FIXED r<N> — <summary>` | worker |
| REVIEW_PASSED | `[REVIEW_PASSED] <task_id>` | secarch |
| REVIEW_FAILED | `[REVIEW_FAILED] <task_id> — N findings` | secarch |
| VERIFIED | `[VERIFIED] <task_id>` | tester |
| TESTER_FAILED | `[TESTER_FAILED] <task_id>` | tester |
| DONE | `[DONE] <task_id> — <summary>` | orchestrator |
| BLOCKED | `[BLOCKED] <task_id> — <reason>` | worker |
| REARCHITECT | `[REARCHITECT] <task_id> → <successor>` | orchestrator |

---

## Grep Recipes (drain loop use)

```bash
M=.agent-project/manifest.log

# All tasks that are CODE_WRITTEN and not yet REVIEW_REQUESTED
comm -23 \
  <(grep "| CODE_WRITTEN |" "$M" | awk -F'|' '{print $2}' | tr -d ' ' | sort -u) \
  <(grep "| REVIEW_REQUESTED |" "$M" | awk -F'|' '{print $2}' | tr -d ' ' | sort -u)

# All tasks that are REVIEW_PASSED and not yet TESTER_ASSIGNED
comm -23 \
  <(grep "| REVIEW_PASSED |" "$M" | awk -F'|' '{print $2}' | tr -d ' ' | sort -u) \
  <(grep "| TESTER_ASSIGNED |" "$M" | awk -F'|' '{print $2}' | tr -d ' ' | sort -u)

# All tasks that are VERIFIED and not yet DONE
comm -23 \
  <(grep "| VERIFIED |" "$M" | awk -F'|' '{print $2}' | tr -d ' ' | sort -u) \
  <(grep "| DONE |" "$M" | awk -F'|' '{print $2}' | tr -d ' ' | sort -u)

# All BLOCKED tasks not yet resolved (no ISSUES_FOUND or REARCHITECT after them)
# (read manually — BLOCKED is low-frequency, inspect with context)
grep "| BLOCKED |" "$M"

# Current phase of a specific task (last matching line)
grep "| task-03 |" "$M" | tail -1

# All open tasks (TASK_REGISTERED with no DONE or REARCHITECT)
comm -23 \
  <(grep "| TASK_REGISTERED |" "$M" | awk -F'|' '{print $2}' | tr -d ' ' | sort -u) \
  <(grep -E "\| (DONE|REARCHITECT) \|" "$M" | awk -F'|' '{print $2}' | tr -d ' ' | sort -u)
```

---

## Startup entries (written once per run)

```bash
# Model selections — record at startup so the run is reproducible
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) | startup | MODEL_WORKER=claude-sonnet-4-6 | MODEL_SECARCH=openai-gpt-5.2 | MODEL_TESTER=openai-gpt-5.2" >> .agent-project/manifest.log

# Task registration (one per task, in dependency order)
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) | task-01 | TASK_REGISTERED | orchestrator | title=<title> | depends_on=none | <description>" >> .agent-project/manifest.log
```

---

## Invariants

1. DONE requires a VERIFIED entry for the same task_id — checked at Phase 6 ship gate.
2. REVIEW_PASSED and VERIFIED are written by the reviewing role, never the worker.
3. REARCHITECT closes a task — no further transitions on that task_id are valid.
4. BLOCKED does not advance to DONE — it must go through ISSUES_FOUND → re-CLAIMED → CODE_WRITTEN → gates.
5. CONDITION_OPEN / CONDITION_CLOSED entries continue to use their existing format (unchanged).
6. retry_budget is counted from ISSUES_FOUND entries for a given task_id. Exceeding it triggers ESCALATE.

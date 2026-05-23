# Retrospective Protocol

Run after Phase 6 (SHIP), before deleting the team. Captures what worked, what
didn't, and proposes improvements to the framework for next time.

## When to Run

- After every project ships (mandatory)
- After a project is aborted (optional but recommended)
- After a headless project completes (written to file, reviewed async)

## Data Collection

### 1. Gather Signals from manifest.log

```bash
# Count rejections
grep "REJECTED" .agent-project/manifest.log | wc -l

# Count test failures
grep "FAIL" .agent-project/manifest.log | wc -l

# Count blocked workers
grep "BLOCKED" .agent-project/manifest.log | wc -l

# Count escalations
grep "ESCALATION" .agent-project/manifest.log | wc -l

# Average attempts per task (STARTED entries vs DONE entries)
STARTS=$(grep -c "STARTED" .agent-project/manifest.log)
DONES=$(grep -c "DONE" .agent-project/manifest.log)
```

### 2. Pattern Analysis

For each REJECTED or FAIL entry, categorize:

| Pattern | Example | Frequency |
|---|---|---|
| Missing error handling | Worker ships happy path only | _count_ |
| SQL injection | f-string in SQL construction | _count_ |
| Missing tests | Worker skipped TDD step | _count_ |
| Wrong ownership | Worker modified files outside scope | _count_ |
| Dependency race | Worker blocked on incomplete task | _count_ |
| Spec ambiguity | Worker built wrong thing due to unclear spec | _count_ |

### 3. Cross-Team Consistency Issues

From the Global Review (if performed):
- Naming convention violations
- Duplicate logic across teams
- Interface contract mismatches

## Output Format

Write `retrospective.md` to `.agent-project/`:

```markdown
# Retrospective: <project-slug>

## Summary
- Tasks: <total> | Completed: <n> | Blocked: <n> | Escalated: <n>
- SecArch rejections: <n> (patterns: <top 2>)
- Tester failures: <n> (patterns: <top 2>)
- Avg retries per task: <n>

## What Went Well
- <reusable pattern or approach that worked>
- <research finding that saved time>
- <architectural decision that prevented issues>

## What Went Wrong
- <failure pattern>: occurred <n> times, root cause: <why>
- <failure pattern>: occurred <n> times, root cause: <why>

## Proposed Improvements

### Worker Prompt Changes
- ADD: "<specific instruction to add to roles/worker.md>"
- REASON: "<which failure pattern this prevents>"

### SecArch Checklist Additions
- ADD: "<new check to add to references/security-checklist.md>"
- REASON: "<what was missed that this catches>"

### Architect Planning Changes
- ADD: "<change to task decomposition or research questions>"
- REASON: "<what spec ambiguity or dependency issue this prevents>"

### Test Criteria Templates
- ADD: "<better default test criteria for this type of task>"
- REASON: "<what Tester couldn't verify without explicit criteria>"

## Decision: Apply Improvements?
<Ask user: "Would you like me to apply these improvements to the framework?">
```

## Improvement Application

If the user approves improvements:

1. Edit the specific role file (e.g., `roles/worker.md`) with the proposed addition
2. Edit `references/security-checklist.md` if new checks proposed
3. Commit: `git commit -m "retro: apply improvements from <project-slug>"`

If declined: no file changes needed.

## Rules

- Always run retrospective — even if everything passed first try (captures what worked)
- Be specific in proposed improvements — "add X to line Y of file Z", not "improve error handling"
- Never propose removing security gates even if they caused friction
- Proposed improvements must reference a specific failure instance (evidence-based)
- In headless mode: write retrospective.md + `git commit -m "retro: <project-slug>"`, skip the "apply?" question

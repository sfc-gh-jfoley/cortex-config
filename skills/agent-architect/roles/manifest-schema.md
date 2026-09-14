# Manifest Contract

One canonical file per run, written only by Primary. Role evidence is collected
from committed event files using collect_events.py. Comments and blank lines are
not events. Persist the entire returned candidate, including JSON COLLECTED receipts.
These contain the evidence commit/path and full identity for recovery; commit
receipts and events together. Do not reconstruct receipts from summaries.

## Event Rendering

Use event.py rather than hand-composing lines. It emits one timestamped event with
explicit identity and rejects duplicate identity fields and delimiter injection.
Primary applies coordinator events; roles apply output to their assigned event file.
The parser remains authoritative for phase and evidence validation.

```bash
uv run --no-project python "$ARCH_SKILL_ROOT/scripts/event.py" "$TASK_ID" TASK_REGISTERED orchestrator "$RUN_ID" 1 --field "team=$TEAM_ID" --field "depends_on=none" --field "criteria=C1,C2"
uv run --no-project python "$ARCH_SKILL_ROOT/scripts/event.py" "$TASK_ID" CODE_WRITTEN worker "$RUN_ID" "$ATTEMPT" --dispatch "$DISPATCH_ID" --field "sha=$ARTIFACT_SHA"
```

## State and Ownership

Primary: TASK_REGISTERED, REVIEW_REQUESTED, TESTER_ASSIGNED, ISSUES_FOUND, DONE,
REARCHITECT, DISPATCH_REQUESTED, DISPATCH_STARTED, DISPATCH_CANCELLED, ESCALATED,
ESCALATION_RESOLVED. Worker: CLAIMED, CODE_WRITTEN, BLOCKED. SecArch: REVIEW_PASSED,
REVIEW_FAILED, CONDITION_OPEN, CONDITION_CLOSED. Tester: VERIFIED, TESTER_FAILED.
Primary may mark a confirmed lost worker BLOCKED after recording reconciliation.

Sequence: registration -> worker dispatch -> CLAIMED -> CODE_WRITTEN ->
REVIEW_REQUESTED -> security dispatch -> REVIEW_PASSED -> TESTER_ASSIGNED -> tester
dispatch -> VERIFIED -> DONE. Dispatch acknowledgements do not advance task phase.
Failures go through ISSUES_FOUND with attempt incremented, then a fresh dispatch.
Every task row has run and attempt; role rows also have assigned dispatch identity.
Verdict and DONE SHAs must equal the current CODE_WRITTEN full Git SHA.

Register prerequisites before dependents; unknown/self dependencies are rejected.
This topological registration rule prevents cycles. Worker dispatch requires each
dependency DONE. Git integration and base contents must also be verified by Primary;
the state parser does not prove ancestry or code equivalence.

## Acceptance Evidence

Registration declares stable criterion IDs in `criteria=C1,C2`. VERIFIED requires
`criteria_passed=C1,C2` in registration order and a pointer under
`.agent-project/reports/<name>.json`. The collector reads that file from the exact
evidence commit. Required report shape:

```json
{"task":"task-01","run":"run-01","attempt":1,"dispatch":"test-01","sha":"FULL_ARTIFACT_SHA","criteria":{"C1":{"status":"PASS","command":"actual check command","output":"captured result"},"C2":{"status":"PASS","command":"actual check command","output":"captured result"}}}
```

All required criteria must have PASS, command/check description and output. Missing,
failed or skipped criteria block VERIFIED. For non-executable artifacts use explicit
structural checks with captured results, not fabricated execution. The collector
validates report structure and identity, not the honesty of model-generated prose.

## Conditions and Escalations

Conditions open against the current SecArch dispatch before its verdict. Closure
preserves original task/run/attempt/dispatch/id and requires `remediation=<task-id>`
identifying a distinct DONE task and `sha` matching that task's approved artifact.
Its JSON report must contain task/run/attempt/dispatch/sha, condition, remediation,
status PASS and captured output. The pointer must exist in the evidence commit.

ESCALATED requires coordinator, run, id and reason. It blocks dispatch and shipping
until ESCALATION_RESOLVED for the same id records a resolution pointer. Status and
recover expose active escalations in task state. Escalations are not test failures.

## Recovery and Shipping

Use manifest.py status, recover, ready --phase PHASE, and ship [--team TEAM_ID].
Follow worktree-handoff.md for liveness reconciliation. No old timestamp establishes
agent death. Terminal tasks cannot resume without a new approved task.
Shipping requires completed tasks/successors, closed conditions and no escalations.
The helper checks supplied state; Primary must additionally run final integration
checks and obtain release authorization. Do not treat helper success as deployment.

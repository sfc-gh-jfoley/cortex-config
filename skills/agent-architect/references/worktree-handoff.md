# Worktree Handoff Protocol

This protocol governs isolated runs and supersedes role examples that append
directly to manifest.log or push unconditionally. No background agent writes the
canonical manifest. Git refs are shared locally; working files are not.

## Ownership and Run Setup

One live coordinator owns the canonical manifest and its integration worktree.
Record its absolute path, run ID, integration branch, and approved task registry
before spawning agents. Never run two collectors against that working tree.
Team Architects publish charter proposals only. Primary owns worker/reviewer dispatch
and transitions; Team Architects do not launch task agents. If Primary is absent,
pause scheduling and shipping until it resumes. Do not promise unattended progress
after Primary exits until an equivalent persistent coordinator is provided.

Every assignment includes task ID, role, attempt, full base/artifact SHA, absolute
worktree path, and a unique `.agent-project/events/<task>-<role>-r<attempt>.log`.
It also includes RUN_ID, DISPATCH_ID and a unique EVIDENCE_REF. Create the event
directory before spawning. Every task/condition/event row must include
`run=<RUN_ID> | attempt=<positive integer>`; role evidence must also include
`dispatch=<DISPATCH_ID>`. Registration starts at attempt 1. ISSUES_FOUND increments
the attempt, even if repaired code has the same SHA. Use full Git SHAs throughout.
Use a new run directory/namespace for a new run. Never reuse evidence across runs.

## Publishing Evidence

Workers and reviewers write their normal schema rows to the assigned event file,
not `.agent-project/manifest.log`. Commit that file and any findings/report files
on their own ref, then return the full evidence commit SHA and event path. Preserve
the role in each row. Do not include copied registration or coordinator events.
Worker CODE_WRITTEN SHA identifies the code commit before the evidence-only commit.

The coordinator records REVIEW_REQUESTED or TESTER_ASSIGNED before launching that
reviewer. It collects CLAIMED before CODE_WRITTEN and collects all evidence for an
attempt before issuing retries. No events may be silently dropped to pass parsing.

The read-only collector produces a candidate manifest on stdout:

```bash
uv run --no-project python "$ARCH_SKILL_ROOT/scripts/collect_events.py" "$REPO" "$MANIFEST" "$EVIDENCE_SHA" "$EVENT_PATH" "$TASK_ID" "$ROLE" "$RUN_ID" "$ATTEMPT" "$DISPATCH_ID"
```

Require exit 0. The coordinator applies the returned candidate to its canonical
manifest and commits it before taking the next action. The same evidence can be
collected again safely; identical rows are not appended twice. Never redirect the
collector onto its own input file. On error, preserve evidence and report the
conflicting record. This is single-writer coordination, not a concurrent database.
Retrieve committed report pointers with `git show <evidence-sha>:<report-path>`;
do not assume those files exist in the coordinator's checkout. Record the source
commit and path in coordinator notes for restart and audit.

## Dependency Integration

Collection persists a `# COLLECTED <JSON provenance record>` receipt in the canonical manifest.
Commit and preserve these receipts: they identify the evidence commit, path, task,
role, run, attempt and dispatch. Replaying that exact accepted reference is a no-op
even after task state advances. New evidence still requires current dispatch
identity, except condition closure tied to its recorded originating security
dispatch. Conditions open against the active security dispatch before its verdict;
their origin remains available after testing or retries. Closure uses the original
event path and identity plus the verified remediation SHA and report pointer.
Receipts and role labels are coordination records, not authenticated signatures.

DONE confirms review, not integration. Before spawning a dependent worker:

1. Confirm all dependency tasks are currently DONE in the validated manifest.
2. Identify their approved artifact SHAs and exact task commit ranges.
3. Integrate those code commits into the integration branch, excluding role event
   files and canonical manifest changes. Do not cherry-pick an entire evidence
   branch blindly. Inspect the resulting diff against task ownership.
4. If conflicts occur, stop and preserve the conflict state for operator resolution.
   Do not choose ours/theirs, force-reset, or silently resolve shared interfaces.
5. Run dependency/interface checks on the integrated tree. Record its full SHA and
   dependency artifact SHA list in notes. If integration changes behavior, send the
   integrated artifact through review and testing again before releasing dependents.
6. Create the dependent worktree from that exact integration SHA. Its branch setup
   uses the supplied base, never the caller's arbitrary HEAD.

Cross-team dependencies use the same protocol. A SHIPPED tag alone never unblocks
code consumption. Local-only runs use local refs and never require git push.

## Detached Reviews

Create a distinct detached worktree for each security/test attempt:

```bash
git worktree add --detach "$REVIEW_PATH" "$ARTIFACT_SHA"
```

Run review/test commands with that directory as cwd. Do not check out the worker's
branch. Record the approved artifact SHA in verdicts even after committing reports.
Before removing a detached review worktree, preserve its evidence commit with a
unique named ref and confirm the coordinator committed collected evidence.
Use `git worktree remove` without force; dirty worktrees must be inspected and
preserved. A failed review is evidence to retain, not garbage to discard.

## Recovery

Primary commits a DISPATCH_REQUESTED record before every worker/reviewer launch:

```text
<timestamp> | <task> | DISPATCH_REQUESTED | orchestrator | run=<run> | attempt=1 | dispatch=<unique-id> | target=<worker/secarch/tester> | base=<full-sha> | worktree=<absolute-path> | event_path=.agent-project/events/<unique-id>.log
```

Use the dispatch ID as the agent name. After spawn returns, commit DISPATCH_STARTED
with the same run/task/attempt/dispatch and `agent=<platform-agent-id>`. Dispatch
records do not advance task state. Worker dispatch follows registration or
ISSUES_FOUND; security dispatch follows REVIEW_REQUESTED; test dispatch follows
TESTER_ASSIGNED. A matching committed role result is valid even if a crash prevented
DISPATCH_STARTED from being recorded.

On resume run `manifest.py recover MANIFEST`. For each returned task:

1. No dispatch: finish the pending launch protocol after checking prerequisites.
2. Dispatch present: inspect its event path on preserved refs first; collect any
   results before considering relaunch. Query the platform by recorded ID or unique
   dispatch name. If alive, resume waiting; if spawn succeeded but acknowledgement
   was lost, record DISPATCH_STARTED with the recovered agent ID.
3. If the platform cannot establish liveness, pause for operator reconciliation.
   Never infer that no agent exists merely from a missing acknowledgement.
4. If absence/death is confirmed and there is no terminal evidence, commit
   DISPATCH_CANCELLED with `pointer=<committed reconciliation report>`. Preserve the
   old ref/worktree and dispatch a fresh unique ID. A CLAIMED worker must first be
    marked BLOCKED and retried through ISSUES_FOUND, not cancelled in place.

Before retry, follow cleanup-protocol.md to reconcile owned child shells and the
framework claim. Canonical BLOCKED -> ISSUES_FOUND releases the old dispatch and
increments attempt on the same task ID. Run recovery.py using committed framework
state before launching its new dispatch. Platform task/step IDs are audit metadata,
not authorization. Preserve orphaned platform claims as interrupted; neither CLI
claim release nor a replacement logical task is required.

Late evidence from a cancelled dispatch or previous attempt fails validation.
Accepted receipts may be replayed after dispatch advances; new evidence must match
the current dispatch or recorded condition origin. No exactly-once spawn
guarantee is claimed across an external agent API; ambiguous outcomes pause safely.
Never kill or delete a worktree merely because its commit timestamp is old.

# Framework-Owned Recovery

Primary owns canonical task claims. CLI task/step ownership is diagnostic only:
never call implicit-current-task undo/edit to authorize recovery. Never create a
replacement logical task merely because platform bookkeeping remains claimed.

1. Confirm agent terminal status; unknown liveness pauses recovery. Inspect committed
   evidence before retrying. A valid completed result resumes normal processing.
2. Inventory the dispatch's child shells. Stop only confirmed owned running shells
   and verify terminal status. Cancellation alone does not establish child cleanup.
3. Read the current framework dispatch and recorded agent from canonical state.
   If launch acknowledgement was lost, reconcile and record the actual agent ID
   before releasing its claim. Recheck owner, dispatch and attempt immediately
   before committing recovery; stale observations cannot release a newer claim.
4. Run recovery.py with framework_claim status claimed, owner, dispatch and attempt.
   Commit a reconciliation report with observed agent/shell status. Primary writes
   BLOCKED on the same task, including current dispatch, owner and report pointer.
5. Write ISSUES_FOUND on that same task with attempt incremented. This clears the
   canonical dispatch and records released_dispatch. Commit before new dispatch.
6. Re-read committed state. Supply framework_claim status pending, owner null,
   dispatch null, incremented attempt, released_dispatch and release_committed true.
   recovery.py permits a fresh unique dispatch on the SAME task ID. Do not pass
   release_committed=true for an uncommitted candidate.

The observation requires run, task, dispatch, agent and attempt (the interrupted
attempt), evidence_checked, terminal_evidence, children_inventory_complete, children
and framework_claim. Platform step IDs are optional audit metadata and are ignored
for authorization. The helper is read-only: exit 0 permits retry, 2 requires further
reconciliation, 1 indicates malformed input. It does not perform cancellation.

Preserve orphaned platform claims separately as interrupted bookkeeping; do not mark
them successful. Same-task canonical recovery does not depend on clearing them.
Reject new evidence from the old attempt; exact previously accepted receipts remain
replayable. Retain refs before removing clean disposable worktrees without force.
Do not remove dirty or unrelated worktrees or issue broad PID/branch cleanup.

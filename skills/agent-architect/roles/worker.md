# Worker

Implement one assigned task in an isolated worktree at the coordinator's pinned
base. Receive task specification, ownership, criterion IDs, dependencies, base SHA,
run/attempt/dispatch IDs, EVENT_PATH and EVIDENCE_REF. Load manifest-schema.md and
worktree-handoff.md. Never write canonical state or declare DONE.

## Execution

1. Confirm the supplied worktree HEAD and dependency interfaces match the approved
   base. Use an existing assigned branch; do not recreate an occupied branch.
2. Render CLAIMED with scripts/event.py, publish to EVENT_PATH, and commit only
   that file. Preserve the commit on the assigned ref for coordinator collection.
3. Discover the project's automation and runtime. Write focused acceptance tests
   before implementation when applicable. Record justified structural checks for
   documentation/configuration; do not force meaningless failing tests.
4. Implement within ownership scope. Stage only assigned code and test files, not
   blanket git add -A. Keep evidence-only commits separate from code changes.
5. Run build/test/lint using project-defined commands. Maximum three local repair
   cycles; if still failing publish BLOCKED with actual errors and exit.
6. Inspect required behavior for unfinished implementation. Abstract methods,
   protocols, exception classes and intentional no-ops are not automatically stubs.
   Reject missing required behavior, not tokens such as pass or TODO alone.
7. Commit passing code, record its full artifact SHA, then render CODE_WRITTEN with
   that SHA into EVENT_PATH. Commit evidence separately. Return artifact SHA,
   evidence commit SHA, event path, tests and any limitations. Local-only never pushes.

```bash
uv run --no-project python "$ARCH_SKILL_ROOT/scripts/event.py" "$TASK_ID" CLAIMED worker "$RUN_ID" "$ATTEMPT" --dispatch "$DISPATCH_ID" --field "sha=$BASE_SHA"
uv run --no-project python "$ARCH_SKILL_ROOT/scripts/event.py" "$TASK_ID" CODE_WRITTEN worker "$RUN_ID" "$ATTEMPT" --dispatch "$DISPATCH_ID" --field "sha=$ARTIFACT_SHA"
```

On retry retrieve the committed findings from the coordinator-provided evidence
SHA/path, address each applicable finding, and repeat validation with the new
attempt and dispatch. Raise unsupported remediation demands rather than blindly
changing correct behavior. Preserve failed work for diagnosis. Commit age is not
a heartbeat and does not authorize killing or deleting a worktree.

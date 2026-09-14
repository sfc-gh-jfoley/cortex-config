# Tester

Verify acceptance independently in a dedicated detached worktree at ARTIFACT_SHA.
Receive task specification, criterion IDs, base/artifact SHAs, run/attempt/dispatch,
EVENT_PATH and EVIDENCE_REF. Load manifest-schema.md and worktree-handoff.md.

1. Read the specification and form expected outcomes before implementation.
2. Inspect required behavior. Do not reject legitimate abstract methods, protocols,
   exception classes or intentional no-ops based on pass/ellipsis/TODO tokens.
3. Discover project test commands, run required checks and capture output. Evaluate
   every registered criterion. For non-executable deliverables capture the actual
   structural check and its result. Do not invent execution evidence.
4. If any mandatory criterion fails or cannot be checked, publish TESTER_FAILED
   with a committed report pointer. Explain SKIPPED versus failed behavior. Never
   turn inaccessible tests into PASS_WITH_WARNINGS.
5. Only when all mandatory criteria pass, create a JSON report under
   `.agent-project/reports/` following manifest-schema.md. Match task/run/attempt/
   dispatch/artifact identity exactly. Include criterion status, command and output.
6. Render VERIFIED with the report pointer and criterion IDs in registration order.
   Commit report and event together; preserve EVIDENCE_REF before cleanup. Return
   the evidence commit SHA and EVENT_PATH. Do not modify implementation or canonical
   state. No push is required in local-only mode.

```bash
uv run --no-project python "$ARCH_SKILL_ROOT/scripts/event.py" "$TASK_ID" VERIFIED tester "$RUN_ID" "$ATTEMPT" --dispatch "$DISPATCH_ID" --field "sha=$ARTIFACT_SHA" --field "criteria_passed=$CRITERIA_IDS" --field "pointer=$REPORT_PATH"
```

Warnings may accompany a passing report only when they do not violate mandatory
criteria. The collector checks report existence, identity and criterion coverage.
Primary still owns final integration and release authorization.

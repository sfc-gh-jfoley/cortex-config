# Team Architect

Research and decompose one charter. The Primary Architect is the sole coordinator
and sole canonical manifest writer. Team Architects never spawn workers/reviewers,
write canonical transitions, merge integration code, or declare a charter shipped.
Load `references/worktree-handoff.md` and `roles/manifest-schema.md`.

## Assignment

Receive run ID, team ID, charter, coordinator identity, integration base SHA,
absolute worktree path, and DOMAIN_HINTS from notes.md. Existing task IDs are fixed;
propose additional tasks rather than registering duplicates.

## Deliverable

Commit `.agent-project/charters/<team-id>.md` on your assigned local branch. Include:

- Each task's ID, ownership scope, dependencies, acceptance criteria and major-change flag.
- Required integration interfaces and prerequisite artifact SHAs, where available.
- Research findings, constraints, and proposed task replacements or scope reductions.

Return the full commit SHA and charter path. Primary retrieves it with `git show`,
reviews the proposal, and writes approved registrations into canonical state.
Do not communicate approval solely through a transient message.

## Coordinator Execution

Primary runs worker -> SecArch -> Tester for tasks from all approved charters.
It collects role event files, commits transitions and manages dispatch recovery.
Parallel workers are permitted only with disjoint ownership and satisfied integrated
dependencies. All canonical writes and integration-branch changes remain serialized.

The coordinator performs major-change review before DONE and records evidence in
notes. If Primary exits, all new dispatch, dependency unblocking and shipping pause.
Existing agents may finish and publish evidence; a resumed coordinator collects it.

## Completion

Primary invokes `manifest.py ship MANIFEST --team TEAM_ID`. On success, it verifies
integration and records the team completion marker. Team Architects cannot replace
this with counts, local state, or an independently created SHIPPED tag.

## Recovery and Escalation

Preserve charter and evidence refs on failure. Report the blocking task, attempted
approaches and the needed decision to Primary. Do not force-remove worktrees or
push by default. Local-only runs require no remote. Run/attempt/dispatch matching
and recovery are defined in `references/worktree-handoff.md`.

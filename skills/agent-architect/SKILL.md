---
name: agent-architect
description: >
  Coordinate multi-agent project builds through intake, research, approved planning,
  isolated implementation, independent security review, testing and integration.
  Use for projects with multiple independent workstreams, team coordination,
  architect project, multi-agent build, arch status or arch ship.
---

# Agent Architect

Primary is the single live coordinator and canonical manifest writer. Workers and
reviewers publish committed evidence from isolated worktrees. Team Architects
research and propose charters; they do not run independent scheduling loops.
This skill does not provide a persistent headless supervisor. If Primary exits,
existing agents may finish but dispatch, integration and shipping pause.

## Required References

Resolve ARCH_SKILL_ROOT to this installed skill's absolute directory.
Load `roles/manifest-schema.md`, `references/worktree-handoff.md`, and
`roles/model-map.md` before execution. Load each role file before assigning it.
Use `scripts/manifest.py` and `scripts/collect_events.py`; do not replace their
checks with grep counts or historical verdict matches.

Requires local Git, Python 3.9+, and an agent platform supporting isolated agents,
status/liveness inspection and explicit worktree locations. Verify actual tool
schemas before spawning. If unavailable, pause instead of inventing bindings.
Examples use `uv run --no-project python`; use an operator-approved interpreter
when uv is unavailable. No Python package dependencies are required.

## Startup and Intake

1. Inspect existing `.agent-project` state and live agents. Never overwrite a prior
   run. Offer explicit resume or operator-approved archival when state exists.
2. Gather goal, acceptance criteria, existing assets, constraints, target repo and
   execution permissions. Ask whether a remote is needed; local-only never pushes.
   Creating repos, commits or remotes requires the applicable user authorization.
3. Select a unique run ID. Create notes.md, canonical manifest from the template,
   events directory and a coordinator integration worktree. Record absolute paths,
   model choices, run ID, permissions and remote policy in notes.md.
4. Preserve existing user changes. Do not force-reset, force-remove worktrees or
   change global Git configuration. Resume only after verifying recorded refs.

## Research and Plan

1. Assign bounded research using `roles/researcher.md`; optionally use Team
   Architects for charter proposals. Collect committed proposals by exact SHA/path.
2. Run the SecArch pre-planning risk scan. Record capability limitations and domain
   hints in notes.md, not multiline manifest entries.
3. Primary defines task IDs, disjoint ownership scopes, dependency DAG, major-change
   flags and at least two atomic acceptance criteria per task. Reject dependency
   cycles. Present the plan and obtain approval before implementation.
4. Primary registers each approved task exactly once:

```text
<timestamp> | <task> | TASK_REGISTERED | orchestrator | run=<run> | attempt=1 | team=<team-id> | title=<title> | depends_on=<comma-separated ids or none> | criteria=C1,C2
```

The approved registry must survive restart. Metadata, full task specifications,
charters and execution permissions live in committed notes/charter files.

## Execute and Collect

Primary serializes canonical changes and integration updates. Parallel agents are
allowed only on disjoint task ownership with verified integrated dependencies.

1. Validate canonical state using `manifest.py status MANIFEST`.
2. For each ready task, integrate approved dependency code as described in
   `references/worktree-handoff.md`. Record its exact base SHA. A DONE marker is
   not evidence that prerequisite code exists in the worker's tree.
3. Commit DISPATCH_REQUESTED and launch the worker with its unique dispatch name,
   base SHA, event path, run ID and attempt. Record DISPATCH_STARTED after launch.
4. Collect worker evidence with `collect_events.py`. Require exit 0, apply the
   candidate canonical manifest and commit it before any further transition.
5. On current CODE_WRITTEN, record REVIEW_REQUESTED with its artifact SHA, run and
   attempt; dispatch SecArch in a detached worktree at that SHA.
6. Collect current security evidence. REVIEW_PASSED permits TESTER_ASSIGNED, with
   identical artifact SHA and attempt. Dispatch Tester in another detached worktree.
7. Collect current tester evidence. VERIFIED permits Primary's major-change review
   where required, then DONE with the same SHA/run/attempt. Do not mark DONE based
   on return text or an earlier attempt's approval.

Every role event carries `run`, `attempt`, and `dispatch`. The collector checks
these against current canonical dispatch state. Never append copied registrations
from worker branches. Preserve report refs and retrieve findings through git show.

## Retries and Conditions

- REVIEW_FAILED or TESTER_FAILED: read the current pointer from helper state and
  retrieve its report from the recorded evidence commit. Primary writes ISSUES_FOUND
  with attempt incremented by one, then creates a new dispatch. Default maximum:
  three attempts per task. On exhaustion pause for operator decision.
- BLOCKED: identify the cause, preserve worktree and evidence, and retry only after
  prerequisites are corrected. Do not repeatedly relaunch an unresolved dependency.
- Scope changes: obtain approval. Register a successor first, then REARCHITECT the
  original with successor ID, or explicitly approved `successor=none`.
- Conditions: assign remediation as a separate task through all gates. SecArch
  records closure evidence with the original condition ID, verified SHA and report
  pointer. No worker self-closes conditions. Do not reuse DONE approval for changed
  code. Cross-team successor conditions also block charter shipping.
- New permissions, destructive actions, unresolved ambiguity affecting acceptance,
  or inaccessible required tests: pause and request operator guidance.

## Recovery

Run `manifest.py recover MANIFEST` on startup and periodically during execution.
For interrupted agents also load `references/cleanup-protocol.md` and run
`recovery.py OBSERVATIONS.json`. Require confirmed child cleanup and explicit claim
reconciliation before retry; agent cancellation alone is insufficient.
Follow the dispatch reconciliation procedure in `references/worktree-handoff.md`.
Missing launch acknowledgement does not prove no agent exists. Query the platform
by agent ID or dispatch name and inspect evidence refs before retrying. When
liveness is unknown, pause. Never kill a worker based solely on commit age.

## Status and Ship

`arch status`: collect available evidence in causal order, then run:

```bash
uv run --no-project python "$ARCH_SKILL_ROOT/scripts/manifest.py" status "$MANIFEST"
uv run --no-project python "$ARCH_SKILL_ROOT/scripts/manifest.py" recover "$MANIFEST"
```

Report current tasks, pending dispatches, blocked states and open conditions.
Do not report abandoned solely because some tasks are DONE without SHIPPED.

`arch ship`: Primary requires the global gate (or charter-scoped gate for a team):

```bash
uv run --no-project python "$ARCH_SKILL_ROOT/scripts/manifest.py" ship "$MANIFEST"
```

On exit 0, integrate reviewed code and run the complete integrated regression suite.
Any changed integration behavior requires re-review/test of that artifact. Do not
ship based only on individually green branches. Obtain applicable release/remote
authorization, record the exact released SHA, then append SHIPPED. Run the
retrospective using `references/retrospective-protocol.md`. Preserve evidence refs
before removing clean disposable worktrees, without force. Leave dirty worktrees
for inspection. No implicit commits or pushes beyond granted execution permissions.

## Verification and Output

```bash
uv run --no-project python -B -m unittest discover -s "$ARCH_SKILL_ROOT/tests" -v
```

Output the release or blocked status, artifact SHA, acceptance-test evidence,
remaining conditions, deviations and recovery instructions. Local Git tests do not
prove platform background-agent survival or unattended execution guarantees.

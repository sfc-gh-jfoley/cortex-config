---
name: agent-architect
description: "Adds independent security review, exact-SHA artifact evidence, tracked review conditions and a ship gate on top of team-workflow for multi-agent project builds. Use when a build has several independent workstreams and needs per-task security review before testing and shipping. Triggers: architect project, multi-agent build, security-reviewed team build, arch status, arch ship. Not for designing or writing skills, and not a replacement for team-workflow."
---

# Agent Architect

A layer on top of the bundled `team-workflow` skill. `team-workflow` owns teams, steps, claiming,
phase gates, plan mode, failure handling and cleanup through `cortex ctx`. Load it first and follow
it exactly. This skill adds only what it lacks:

1. A per-task **security review** of the exact artifact before verification.
2. **Artifact evidence**: every verdict names the full commit SHA it judged.
3. **Conditions**: non-blocking findings that must be closed before shipping.
4. **Disjoint ownership** and **dependency integration** rules for parallel implementors.
5. A **ship gate** and a short retrospective.

There is no separate manifest, event log or recovery script. Task state lives in `cortex ctx` steps;
evidence lives in git refs and discoveries. If the session is lost, resume with
`cortex ctx step list -t <tid>` and `cortex ctx team get team-workflow-<tid> --json`.

## Setup

1. Load `team-workflow` and complete its Setup. Do not create a second task or team.
2. Make the security role visible: copy `roles/security-reviewer.md` to `.cortex/agents/roles/` in
   the target project, then run `list_teammates(phase="all")` and confirm `security-reviewer`
   appears under Verify. If it does not, stop and tell the operator; do not substitute prose.
3. Record in the plan: target repo, integration branch, ownership scope per task, dependency
   graph, which tasks are major changes, and whether a remote or push is permitted. Default is
   local-only: never push, create a remote, or commit outside the repo without explicit permission.

## Plan additions

Every implementation step in the plan states:

- **Ownership scope**: the files or directories this step may change. Scopes are disjoint between
  steps that can run in parallel. If two steps need the same file, make one depend on the other.
- **Acceptance criteria**: at least two atomic, checkable criteria.
- **Major change**: yes if it touches shared contracts, auth, dependencies or migrations.

## Implement

- Run each implementor in its own worktree when the platform provides isolation (`task` supports
  `worktree_isolation`); otherwise rely on disjoint scopes and confirm with `git diff --stat` that
  nothing outside the scope changed. Verify actual tool behavior before depending on either.
- Implementors stage only files in their scope (no blanket `git add -A`) and report the full
  40-character artifact SHA in their final `Step <sid> complete:` line.
- **Dependent steps**: a step marked completed does not put its code in another worker's tree.
  Before starting a dependent step, integrate the dependency's approved commits into the integration
  branch (code only, not evidence or ledger files), inspect the diff against ownership, run the
  interface checks, and create the dependent worktree from that exact integration SHA.
  On conflict, stop and ask the operator. Never pick ours/theirs or force-reset.

## Verify: security first, then tests

For each implementation step, add two Verify steps, the second depending on the first:

1. `security-reviewer` step with the base SHA, artifact SHA, scope, criteria and major-change flag.
2. `verifier` step with the same artifact SHA. It tests that SHA, not the branch tip.

Rules:

- `REVIEW_FAILED` or a failed verifier step: create a retry implementor step with the report as
  input, at most three attempts per task. After that, stop and ask the operator.
- A changed artifact SHA invalidates earlier verdicts. Re-review and re-test the new SHA.
- Verdicts are advisory records, not signatures. Confirm the reviewed SHA matches the integrated SHA
  before accepting a step.

## Conditions

Non-blocking findings become discoveries tagged `condition` with an ID `COND-<task>-<n>`.
Close a condition by creating a separate remediation step that goes through implement, security
review and verification. Record the closing SHA in a discovery. A worker never closes its own
condition. Open conditions block shipping.

## Stopping points

Stop and ask the operator at:

- Plan approval (team-workflow's `ExitPlanMode`).
- Any request for new permissions, a remote, a push, a destructive action, or sending source to
  an outside reviewer.
- Ambiguity that changes acceptance criteria.
- A merge conflict during dependency integration.
- Three failed attempts on one task.
- Shipping (below).

## Status and ship

`arch status`: run `cortex ctx step list -t <tid>`, then report per task: phase, reviewed SHA,
open conditions, and blocked or failed steps. Do not call a run abandoned because some steps are
done and others are not.

`arch ship` requires all of: every implementation step completed; each task has a passing security
review and verifier result for the same SHA that is on the integration branch; no open conditions;
the full regression suite passes on the integrated tree. Then ask the operator for explicit
release authorization (and push permission if any), record the released SHA, and run team-workflow
Cleanup. Remove clean disposable worktrees without `--force`; leave dirty ones for inspection and
keep review refs.

## Retrospective

After shipping, write a short note: tasks that needed retries and why, the most common finding
class, any scope or integration conflicts, and one change to try next run. Keep it to what the step
list, discoveries and git history show.

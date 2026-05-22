---
name: agent-architect
description: >
  Multi-agent project framework. Accepts any project brief and orchestrates a
  team to research, plan, build, security-gate, and test it. The Architect
  determines team size, researchers gather context in parallel, workers claim
  tasks, SecArch gates every merge, and testers verify independently.
  Key differentiator: structured spec-building phase (INTAKE→RESEARCH→PLAN)
  where Researcher + SecArch + Architect assess what's new, what's possible,
  and what's risky BEFORE committing to execution.
triggers:
  - architect project
  - build project
  - assign teams
  - spin up a team
  - agent architect
  - offshore team
  - multi-agent build
  - coordinate agents
  - spawn teams
  - headless build
---

# Agent Architect v3.0

## What This Is

A coding project OS for CoCo. You describe what you want built. The framework:

1. **Spec Discovery** — Researchers + SecArch explore what exists, what's new, what's risky
2. **Architect** synthesizes findings → determines team count → decomposes into tasks
3. **Workers** implement tasks (TDD-first, model-right-sized)
4. **Security Architect** gates every task before merge
5. **Testers** independently verify each deliverable

All state is committed to git as it happens — sessions can die and state is recoverable.

## When to Use

- Any project with ≥ 3 independent workstreams
- Projects requiring parallel execution (frontend + backend + infra, etc.)
- When you want security review baked in at the task level
- When spec-building requires exploration of what's possible before committing
- Headless/offshore: autonomous execution after plan approval

## How to Invoke

Describe what you want built:
```
"Build me a React dashboard for Cortex usage"
"I need a Snowflake Native App for KG discovery"
"Create a Python CLI that deploys semantic views from YAML"
"Build this headless — I'll check back when it's done"
```

---

## Framework Files

| File | Role |
|---|---|
| `roles/model-map.md` | Model assignments per role (cost/speed right-sizing) |
| `roles/researcher.md` | Researcher prompt template |
| `roles/security-gate.md` | SecArch checklist + verdict format |
| `roles/worker.md` | Worker TDD protocol + ownership rules |
| `roles/tester.md` | Spec-blind verification protocol |
| `references/security-checklist.md` | Reusable security checklist (standalone) |
| `references/escalation-format.md` | Structured escalation template |
| `references/retrospective-protocol.md` | Post-project learning protocol |
| `templates/manifest.log` | Durable completion log template |

---

## Project Lifecycle

```
Phase 0: INTAKE         → Architect (interactive, Opus)
Phase 1: SPEC DISCOVERY → Researchers + SecArch (parallel, Sonnet)
Phase 2: PLAN           → Architect synthesizes + presents (Opus)
Phase 3: EXECUTE        → Workers (sequential drain, Sonnet)
Phase 4: GATE           → SecArch per task (sequential, Sonnet)
Phase 5: VERIFY         → Testers per task (sequential, Sonnet)
Phase 6: SHIP           → Architect merges + retrospective (Opus)
```

---

## Startup

When this skill is invoked:

1. Create working directory: `.agent-project/` in current working dir
2. Initialize `manifest.log` from `templates/manifest.log`
3. Read `roles/model-map.md` for model assignments
4. **Determine GitHub need**: Ask user — "Does this project need a GitHub repo, or local-only?"
   - If GitHub: `gh repo create ${GH_ORG}/<slug> --private`, init git, push
   - If local-only: `git init` in project root, no remote
5. Create the CoCo team: `team_create(team_name="arch-<project-slug>")`
6. Commit initial state: `git add .agent-project/ && git commit -m "init: <slug> via agent-architect"`
7. Enter **Phase 0: Intake**

---

## Phase 0: Intake (Architect)

Ask the user:

1. **What are we building?** (be specific: "iPhone app", "React dashboard", "Native App")
2. **What does success look like?** (what the finished thing does/shows/produces)
3. **What do we have to work with?** (existing codebase, APIs, schemas, design files)
4. **What are the hard constraints?** (language, framework, account, connection)
5. **What's the priority?** (ship fast vs. production quality)
6. **Execution mode?** (interactive = gates ask you, headless = autonomous after plan approval)

Record answers. Log `INTAKE_COMPLETE` to manifest.log. Commit. Proceed to Phase 1.

---

## Phase 1: Spec Discovery (Researchers + SecArch)

**Purpose**: Understand what's possible before committing to a plan. This is the
unique value — native CoCo teams skip this and go straight to task lists.

For each unknown domain, spawn a Researcher (see `roles/researcher.md`):
- "What does the existing codebase look like?"
- "What APIs/SDKs are available for [technology]?"
- "What Snowflake objects already exist?"
- "What patterns do similar projects use?"

Simultaneously spawn SecArch with a **pre-planning risk scan**:
- "What security risks exist in this domain before we build?"
- "What compliance constraints apply?"

**Model**: All Phase 1 agents use Sonnet (see `roles/model-map.md`).

**Anti-Flood Protocol** (sequential drain):
1. Spawn all researchers + SecArch in one batch
2. `agent_output(wait=true)` on ONE agent at a time — drain sequentially
3. After each completes, append findings to manifest.log and `git commit`
4. Never start Phase 2 until ALL Phase 1 agents have drained

When all return → log `RESEARCH_COMPLETE`, commit, proceed to Phase 2.

---

## Phase 2: Plan (Architect)

1. **Synthesize** all research findings into decision records
2. **Determine team count** (see sizing table below)
3. **Decompose into tasks** — each must have:
   - Clear deliverable (file, function, deployed object)
   - `ownership_scope`: files this task creates/modifies (NO overlap)
   - Dependencies: which tasks must complete first
   - `is_major_change`: true/false
   - `test_criteria`: what must pass
4. **Create CoCo tasks**: `task_create()` with `blocked_by` for dependencies
5. **Present plan to user** — do NOT proceed until confirmed
6. Log `PLAN_APPROVED` to manifest.log. Commit.

### Team Sizing

| Project scope | Teams |
|---|---|
| < 5 tasks, single domain | 1 team |
| 5-15 tasks, 2-3 domains | 2-3 teams |
| Full-stack (UI + API + DB + infra) | 3-4 teams |

---

## Phase 3: Execute (Workers)

For each ready task (no unmet deps), spawn a Worker (see `roles/worker.md`).

**Sequential Drain Pattern** (prevents notification flooding):
```
for each batch of ready tasks:
    spawn all workers in batch (parallel, worktree_isolation=true)
    for each worker in batch:
        agent_output(wait=true)    # drain one at a time
        read manifest.log          # reconcile state
        git commit log updates     # persist to git
    check: did completions unblock new tasks? → next batch
```

**Model**: Workers use Sonnet (see `roles/model-map.md`).

Workers commit to branches. They do NOT merge to main.

---

## Phase 4: Security Gate (SecArch)

After each Worker completes, spawn SecArch (see `roles/security-gate.md`).

**Sequential** — one review at a time (not parallel).

Verdicts:
- **APPROVED** → proceed to Phase 5, log + commit
- **APPROVED_WITH_CONDITIONS** → create follow-up tasks, proceed
- **REJECTED** → re-spawn Worker with remediation (max 2 retries → escalate)

For `is_major_change` tasks: Architect ALSO reviews after SecArch approves.

---

## Phase 5: Verify (Testers)

After SecArch APPROVES, spawn a Tester (see `roles/tester.md`).

**Sequential** — one test at a time.

Verdicts:
- **PASS** → mark task COMPLETE, log + commit
- **PASS_WITH_WARNINGS** → note warnings, mark COMPLETE
- **FAIL** → re-spawn Worker with findings (max 2 retries → escalate)

---

## Phase 6: Ship

When all tasks COMPLETE:

1. **Pre-ship verify**: `grep -c "| DONE |" .agent-project/manifest.log` == expected
2. **Merge branches** (if GitHub: `gh pr merge --squash --delete-branch`)
3. **Tag release**: `git tag v1.0 -m "<goal> — initial ship"`
4. **Write design-doc.md**: decisions, deviations, trade-offs
5. **Run retrospective** (see `references/retrospective-protocol.md`)
6. **Clean up**: `team_delete()`
7. **Save memory**: `cortex memory remember "SHIP <project>: <summary>"`

---

## Retry & Escalation

| Event | Max Retries | Then |
|---|---|---|
| SecArch REJECTED | 2 | Escalate (see `references/escalation-format.md`) |
| Tester FAIL | 2 | Escalate |
| Worker BLOCKED | 0 | Re-spawn after dependency completes |
| Worker build loop (3 cycles) | 0 | Self-reports BLOCKED → escalate |

---

## State Management: manifest.log + Git

**manifest.log is the single source of truth** for completion state.

CoCo task notifications are unreliable under load (4+ agents cause flooding/lost
notifications). manifest.log is the durable workaround.

**Git-committed state**: Every phase transition and worker completion is committed to git.
If a session crashes, state is recoverable from `git log .agent-project/manifest.log`.

**Rules**:
- Never merge a branch whose worker has no DONE entry in manifest.log
- Every log write is immediately followed by `git add .agent-project/manifest.log && git commit -m "log: <event>"`
- CoCo task_update is ALSO called (belt + suspenders) but manifest.log is canonical

---

## Headless / Offshore Mode

For autonomous execution without user interaction during the build phase.

**Configuration** (set during Phase 0 intake or pre-populated):
```
execution_mode: headless
auto_approve_plan: false     # true only for well-understood repeatable projects
escalation_channel: memory   # "memory" | "file" | "user"
max_parallel_workers: 4
retry_budget: 2
halt_on:
  - CRITICAL_security_finding
  - max_retries_exceeded
  - scope_creep_detected
```

**Headless behavior**:
- Plan still requires user approval (unless `auto_approve_plan: true`)
- After approval: Phases 3-6 run autonomously
- Escalations → `cortex memory remember` (user reviews async)
- SecArch + Tester gates still block — never bypassed
- On `halt_on` conditions: write context to `.agent-project/escalation.md`, STOP
- On completion: task notification reaches user's session

**Launching headless**:
```python
Task(
    subagent_type="general-purpose",
    model="claude-opus-4-6",
    run_in_background=True,
    name="architect-<slug>",
    prompt="You are the Project Architect for <slug>. [inject SKILL.md + role files]"
)
```

The Architect then spawns its own sub-team and manages the lifecycle independently.

---

## Spawning Agents (Task Tool Calls)

Every agent spawn MUST include the `model` parameter from `roles/model-map.md`:

```python
# Researcher
Task(subagent_type="Explore", model="claude-sonnet-4-6", run_in_background=True,
     team_name="arch-<slug>", name="researcher-<topic>", prompt="...")

# Worker
Task(subagent_type="general-purpose", model="claude-sonnet-4-6",
     run_in_background=True, worktree_isolation=True,
     team_name="arch-<slug>", name="worker-<task_id>", prompt="...")

# SecArch
Task(subagent_type="general-purpose", model="claude-sonnet-4-6",
     run_in_background=True, team_name="arch-<slug>",
     name="secarch-<task_id>", prompt="...")

# Tester
Task(subagent_type="general-purpose", model="claude-sonnet-4-6",
     run_in_background=True, team_name="arch-<slug>",
     name="tester-<task_id>", prompt="...")
```

---

## Related Skills

- `cortex-agent-optimization` — optimizing Snowflake Cortex Agents built by this framework
- `prompt-determinism-tester` — validating prompts produced by this framework
- `cortex-accelerator` — Snowflake-specific Cortex AI builds (SV + agent pipelines)

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
  - arch status
  - arch ship
---

# Agent Architect v3.1

## What This Is

A coding project OS for Cortex Code. You describe what you want built. The framework:

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

## Tool Requirements

This framework assumes an agent platform that provides the capabilities below. Names
are the Cortex Code bindings; on another platform, substitute the equivalent. If a
capability is genuinely unavailable, the affected behavior is noted so you can degrade
deliberately instead of failing silently.

| Capability | Cortex Code binding | Required? | If unavailable |
|---|---|---|---|
| Spawn a subagent | `Task(subagent_type, model, prompt, run_in_background, worktree_isolation, team_name, name)` | **Yes** — core | Framework cannot run |
| Wait on / poll a subagent | `agent_output(agent_id, wait=)` | **Yes** — Phase 3 drain | Framework cannot run |
| Terminate a subagent | `kill_agent(agent_id)` | Yes — stuck recovery | Stuck workers must be killed manually |
| Group agents | `team_create(team_name)` / `team_delete()` | No | Skip; use naming conventions only |
| Task registry | `task_create()` / `task_update` | No | manifest.log is already the source of truth — rely on it alone |
| Ask the operator | `ask_user_question()` | Yes — Phase 0/2 gates | Prompt in plain text and wait |
| Run shell / git | standard shell | **Yes** — git is the coordination bus | Framework cannot run |
| Compile-check SQL | `sql_execute(only_compile=true)` | No | Worker skips SQL validation; note it in the manifest |
| Search docs | `cortex search docs` | No | Researcher proceeds with web/codebase only and records the limitation |
| Search the web | `web_search` | No | Same as above |

**Subagent types.** `"general-purpose"` is the only type actually required.
`"Explore"` is a read-only, faster variant used for Researchers — an optimization hint,
not a dependency. Substitute `"general-purpose"` anywhere `"Explore"` appears if your
platform has no equivalent.

**Backgrounding.** `run_in_background=True` assumes a backgrounded agent survives
independently of the spawning turn. If your platform ties background work to the
session, a session crash loses in-flight agents regardless of the drain protocol —
prefer interactive mode.

---

## Framework Files

| File | Role |
|---|---|
| `roles/model-map.md` | Model assignments per role (cost/speed right-sizing) |
| `roles/researcher.md` | Researcher prompt template |
| `roles/security-gate.md` | SecArch checklist + verdict format |
| `roles/worker.md` | Worker TDD protocol + ownership rules |
| `roles/tester.md` | Spec-blind verification protocol |
| `roles/team-architect.md` | Multi-team charter execution + Phase 1–5 mini-lifecycle |
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

0. **Check for an abandoned prior run — do this FIRST.** A run that finished tasks
   but never reached Phase 6 leaves a manifest that looks identical to one still in
   progress. Detect it before creating anything:

   ```bash
   if [ -d ".agent-project" ]; then
       M=.agent-project/manifest.log
       shipped=$(grep -c "| SHIPPED |" "$M" 2>/dev/null); shipped=${shipped:-0}
       done_n=$(grep -c "| DONE |" "$M" 2>/dev/null); done_n=${done_n:-0}
       open_c=$(grep -c "| CONDITION_OPEN |" "$M" 2>/dev/null); open_c=${open_c:-0}
       closed_c=$(grep -c "| CONDITION_CLOSED |" "$M" 2>/dev/null); closed_c=${closed_c:-0}
       if [ "$done_n" -gt 0 ] && [ "$shipped" -eq 0 ]; then
           echo "ABANDONED RUN: $done_n tasks DONE, no SHIPPED marker."
       fi
       if [ "$open_c" -gt "$closed_c" ]; then
           echo "UNRESOLVED: $((open_c - closed_c)) security condition(s) still open."
       fi
   fi
   ```

   If either fires, STOP and report to the user. Offer: resume the prior run, close
   it out, or archive it and start fresh. Do NOT silently overwrite — the open
   conditions are usually unremediated security findings.

1. Create working directory: `.agent-project/` in current working dir
2. Initialize `manifest.log` from `templates/manifest.log`, and create an empty
   `.agent-project/notes.md` for planning notes (manifest.log records only
   transitions that already happened — never intentions)
3. Read `roles/model-map.md` for model assignments
4. **Determine GitHub need**: Ask user — "Does this project need a GitHub repo, or local-only?"
   - If GitHub: ask for the owner (org or username) and record it in manifest.log as
     `GH_OWNER=<value>`. Do not read it from the shell environment — do not assume
     `$GH_ORG` is set. Then `gh repo create <GH_OWNER>/<slug> --private`, init git, push
   - If local-only: `git init` in project root, no remote
5. Create the agent team: `team_create(team_name="arch-<project-slug>")`
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

7. **Domain hints**: Based on the technology stack from step 3, append a `DOMAIN_HINTS` block
   to manifest.log with domain-specific gotchas. Workers receive these hints injected into
   their task prompt. Examples:
   - Snowflake/SQL: `1. IF NOT EXISTS on all DDL; 2. Use IS NULL not =NULL; 3. GENERATOR() for seed data not row-by-row INSERT; 4. Qualify all column refs with alias; 5. NEVER use 'cortex sql' for SQL execution — it opens an interactive CoCo session and hangs; use sql_execute tool or 'snow sql -f <file>' instead`
   - React/TypeScript: `1. key prop required on all list items; 2. loading + error states on every async component; 3. no hardcoded env values in components`
   - Python API: `1. validate at system boundaries only; 2. timeout on all external calls; 3. no secrets in logs or error messages`
   - Generic fallback: `1. no hardcoded credentials; 2. handle null/empty inputs; 3. log errors with context not raw exceptions`

8. **Specbuilder check**: Run `ls spec/ .specbuilder.toml 2>/dev/null`
   - Found → log `SPECBUILDER_PRESENT=true` in manifest.log
   - Not found → log `SPECBUILDER_PRESENT=false` in manifest.log

Record answers. Log `INTAKE_COMPLETE` to manifest.log. Commit. Proceed to Phase 1.

---

## Phase 1: Spec Discovery (Researchers + SecArch)

**Purpose**: Understand what's possible before committing to a plan. This is the
unique value — simple task-list approaches skip this and go straight to task lists.

For each unknown domain, spawn a Researcher (see `roles/researcher.md`):
- "What does the existing codebase look like?"
- "What APIs/SDKs are available for [technology]?"
- "What Snowflake objects already exist?"
- "What patterns do similar projects use?"

**Snowflake capability pre-flight** (required when stack includes Snowflake): Before Phase 2
planning, one researcher MUST verify account-level feature availability for any capability
workers will depend on. Run these checks and log results to manifest.log as `CAPABILITY_FLAGS`:
```sql
-- Semantic view VQRs / LOD expressions
SHOW PARAMETERS LIKE 'ENABLE_LOD_EXPRESSIONS' IN ACCOUNT;
-- Event table (required for observability spans)
SHOW PARAMETERS LIKE 'EVENT_TABLE' IN ACCOUNT;
-- Any SYSTEM$ function the plan will call — test with a minimal invocation first
```
If a required capability is absent, the Phase 2 plan MUST NOT spawn workers that depend on
it. Instead, add a BLOCKED task noting the missing flag and the manual workaround.

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
   - `test_criteria`: numbered atomic criteria — each a single sentence stating condition + expected result.
     Minimum 2 per task. Tester reads these before reading any code.
     Example: `"1. POST /auth returns 401 when token absent; 2. Response body matches {error: string} schema; 3. No credentials appear in logs"`
4. **Create tasks**: `task_create()` with `blocked_by` for dependencies. For **each**
   task, immediately append a registration line to manifest.log and commit:
   ```
   <timestamp> | architect | TASK_REGISTERED | <task_id>
   ```
   This is what makes the Phase 6 pre-ship check verifiable. Without it, "expected"
   exists only in this session's context and is lost on any restart.
5. **Present plan to user** — do NOT proceed until confirmed
6. Log `PLAN_APPROVED` to manifest.log. Commit.

**Optional specbuilder handoff**: If `SPECBUILDER_PRESENT=true`, ask:
"Formalize this plan as tracked spec modules before execution? (y/n)"
- YES → write `spec/INTAKE.md` summarizing approved tasks (one requirement per task), load
  skill `specbuilder` → route to `generate-spec` → proceed to Phase 3 only after key tasks
  reach `status: accepted` in specbuilder.
- NO → proceed directly to Phase 3.

**Multi-team charter decomposition** (when team count ≥ 2 AND execution_mode=headless):
Decompose the full task list into N independent TEAM CHARTERS before launching. Each charter
is an independent slice with no intra-charter cross-task dependencies (cross-charter deps are
resolved by the Primary Architect via git polling).

Charter format (write to manifest.log under `CHARTERS_DEFINED`):
```
team: 1
name: <domain-label>
tasks: [task_01, task_02, task_03]
integration_branch: arch/<slug>/main
depends_on_teams: []   # list team numbers this charter must wait for
```
Log all charters under `CHARTERS_DEFINED` in manifest.log. Commit. Then launch Team Architects.

### Team Sizing

| Project scope | Teams |
|---|---|
| < 5 tasks, single domain | 1 team |
| 5-15 tasks, 2-3 domains | 2-3 teams |
| Full-stack (UI + API + DB + infra) | 3-4 teams |

---

## Phase 3: Execute (Workers)

For each ready task (no unmet deps), spawn a Worker (see `roles/worker.md`).

⛔ **DRAIN GATE — mandatory before Phase 4:**
After spawning a batch of workers, drain EVERY worker before proceeding.
Do NOT check task_list for new work, do NOT spawn the next batch, do NOT
begin Phase 4 until every agent in the current batch has returned.

**Shared-pool workers** (`team_mode="shared_pool"`, no worktree_isolation):
```
spawn all workers in batch
for each worker in batch:
    agent_output(agent_id=<id>, wait=true)   ← blocking wait; no polling loop
task_list → check for newly unblocked tasks → spawn next batch if any
```

**Worktree-isolated workers** (`worktree_isolation=True`):
Git-First Drain Loop (120s stuck threshold):
```
for each batch of ready tasks:
    spawn all workers in batch (parallel, worktree_isolation=true)
    for each worker in batch:
        elapsed_since_commit = 0
        last_commit = $(git log <worker-branch> -1 --format="%ct" 2>/dev/null || echo "0")

        loop:
            result = agent_output(agent_id, wait=false)
            if agent completed → break

            current = $(git log <worker-branch> -1 --format="%ct" 2>/dev/null || echo "0")
            if current != last_commit:
                last_commit = current
                elapsed_since_commit = 0      # reset timer on git activity
            else:
                elapsed_since_commit += 30

            if elapsed_since_commit >= 120:
                → STUCK (see Cleanup Protocol section)
                break

            # Guard against a worker that commits but does not progress: the
            # timer above resets on ANY commit, so trivial checkpoint commits
            # every <120s would keep it alive forever. Also cap total runtime.
            total_elapsed += 30
            if total_elapsed >= 1800:          # 30 min hard ceiling per worker
                → check for a [DONE] commit on the worker branch.
                  If absent → STUCK (no real progress in 30 min despite activity)
                break

            sleep(30)

        read manifest.log → reconcile state → git commit log updates
    check: did completions unblock new tasks? → next batch
```

**Model**: Workers use Sonnet (see `roles/model-map.md`).

Workers commit to branches. They do NOT merge to main.

---

## Phase 4: Security Gate (SecArch)

After **all** workers in the batch have drained (per the Phase 3 Drain Gate), run
SecArch for each completed task — one review at a time, sequentially. Do not spawn
SecArch mid-drain; the Drain Gate governs.

Verdicts:
- **APPROVED** → proceed to Phase 5, log + commit
- **APPROVED_WITH_CONDITIONS** → **record every condition before proceeding.** For each
  condition, append one manifest entry and commit:
  ```
  <timestamp> | secarch-<task_id> | CONDITION_OPEN | <condition_id> | <description>
  ```
  Then create the follow-up task (`task_create()` + `TASK_REGISTERED`) and proceed to
  Phase 5. When a condition is remediated, append:
  ```
  <timestamp> | worker-<task_id> | CONDITION_CLOSED | <condition_id>
  ```
  **A condition that exists only in the SecArch's returned text is lost when the
  session ends.** Writing it to the manifest is what makes it survive. Phase 6 will
  refuse to ship while open > closed.
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

1. **Pre-ship gate — all three checks must pass. Do not proceed on any failure:**
   ```bash
   M=.agent-project/manifest.log
   reg=$(grep -c "| TASK_REGISTERED |" "$M")
   done_n=$(grep -c "| DONE |" "$M")
   open_c=$(grep -c "| CONDITION_OPEN |" "$M")
   closed_c=$(grep -c "| CONDITION_CLOSED |" "$M")

   [ "$reg" -eq "$done_n" ]      || { echo "BLOCKED: $reg registered vs $done_n done"; exit 1; }
   [ "$open_c" -eq "$closed_c" ] || { echo "BLOCKED: $((open_c - closed_c)) conditions open"; exit 1; }
   ```
   Both counts come from git history, so this gate works after any session restart —
   it does not depend on remembering how many tasks were planned.
2. **Merge branches** (if GitHub: `gh pr merge --squash --delete-branch`)
3. **Tag release**: `git tag v1.0 -m "<goal> — initial ship"`
4. **Write design-doc.md**: decisions, deviations, trade-offs
5. **Run retrospective** (see `references/retrospective-protocol.md`)
6. **Clean up**: `team_delete()`
7. **Log ship**: append `SHIPPED` entry to manifest.log + `git add .agent-project/ && git commit -m "ship: <project-slug>"`

⚠️ **SHIPPED is the only terminal marker.** A run with DONE entries and no SHIPPED
entry is abandoned, not in progress — Startup detects exactly this. If you cannot
satisfy the gate in step 1, write an `ESCALATED` entry explaining why rather than
leaving the run silently unterminated.

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

agent task notifications are unreliable under load (4+ agents cause flooding/lost
notifications). manifest.log is the durable workaround.

**Git-committed state**: Every phase transition and worker completion is committed to git.
If a session crashes, state is recoverable from `git log .agent-project/manifest.log`.

**Rules**:
- Never merge a branch whose worker has no DONE entry in manifest.log
- Every log write is immediately followed by `git add .agent-project/manifest.log && git commit -m "log: <event>"`
- The platform task registry is ALSO updated where available (belt + suspenders) but manifest.log is canonical
- **manifest.log records only transitions that have already happened.** Planning
  notes, intended next steps, and in-progress reasoning go in
  `.agent-project/notes.md`. STATUS must be one of the values defined in
  `templates/manifest.log` — never free text, never future tense.
- **Terminal state is explicit.** DONE entries with no SHIPPED entry mean the run was
  abandoned, not that it is still going. Startup detects this; Phase 6 is what
  prevents it.

**Why the discipline above exists.** A real run ended with its final manifest line
reading "applying conditions as cleanup commit, then push, then copy to toolkit."
That was an intention that never executed — structurally indistinguishable from a
completion record. The run looked mid-flight for six days while four security
conditions from its own Security Gate went unremediated. The `CONDITION_OPEN` /
`CONDITION_CLOSED` pairing and the `TASK_REGISTERED` baseline exist specifically so
that state is greppable from git rather than held in a session's context.

---

## Headless / Multi-Team Mode

**Default: always use multi-team (`num_teams: auto`), never single-team headless.**

Single-team headless (`num_teams: 1`) is almost never the right choice:
- It backgrounds one Opus session running Phases 0-6 in sequence — identical to interactive
  mode except you can't watch it
- No parallelism, no fresh contexts per team, no cost advantage
- A long Opus session accumulates research + plan + worker results + SecArch verdicts across
  all phases and hits context limits on any non-trivial project
- If requirements are uncertain → use **interactive** so you can review Phase 2 before Phase 3
- If requirements are clear and the project fits in a single context → also just use interactive,
  it's faster to supervise than to diagnose a backgrounded failure via git log

**Use headless multi-team when:**
- Project is decomposable into ≥ 2 independent team charters
- You want to run unattended (overnight, during meetings) after plan approval
- You want parallel execution and bounded per-team context (Team Architects are Sonnet —
  cheaper and each has a fresh context scoped to its charter, no context overflow)

**What this actually is**: 1 Primary Architect (Opus) decomposes the project into N team
charters then delegates to N Team Architects (Sonnet). Primary stays lean — it only holds
charter definitions and polls git. All execution context lives inside each Team Architect.
**Git is the only inter-team communication channel** — Primary does NOT rely on CoCo task
notifications (too unreliable under load). User checks progress via `git log --oneline --all`.

The Opus cost is bounded to Phase 0-2 synthesis and Phase 6 merge. Phases 3-5 run entirely
on Sonnet inside Team Architects. This is the correct cost model.

**Configuration** (set during Phase 0 intake or pre-populated):
```
execution_mode: headless
num_teams: auto              # "auto" uses team sizing table, or set explicitly 1-4
auto_approve_plan: false     # true only for well-understood repeatable projects
escalation_channel: git
retry_budget: 2
team_poll_interval_seconds: 90     # multi-team only: how often Primary checks team git activity
team_stuck_threshold_seconds: 1800 # multi-team only: no team commits for 30 min = team stuck
halt_on:
  - CRITICAL_security_finding
  - max_retries_exceeded
  - scope_creep_detected
```

**Two distinct modes (do not conflate):**
- **Single-team** (`num_teams: 1`): Primary runs the Phase 3 git-first drain loop directly
  (30s poll, 120s stuck threshold). Session stays alive; user is watching. `team_poll_interval_seconds` unused.
- **Multi-team** (`num_teams: 2+`): Primary launches Team Architects then **returns to user**.
  Team Architects own their own drain loops. Primary session is not long-lived.
  User checks status on demand via `arch status`; triggers Phase 6 via `arch ship`.

**Primary Architect behavior (multi-team headless)**:
1. Phases 0-2 run normally (plan requires user approval unless `auto_approve_plan: true`)
2. Decompose into team charters (see Phase 2 charter decomposition)
3. Create integration branch: `git checkout -b arch/<slug>/main`
4. Launch N Team Architects in one batch (see spawn pattern below)
5. **Return control to the user immediately after launch — do NOT block in a poll loop.**
   Log `TEAMS_LAUNCHED | <N> teams | <timestamp>` to manifest.log + commit.
   Then output to the user:
   ```
   <N> teams launched headlessly. Each team runs Phases 1–5 autonomously and
   commits all state to git. Your working session is free.

   Check progress:  arch status
   Trigger ship:    arch ship   (once all teams show SHIPPED)
   ```
   The Primary Architect session ends here. Team Architects are fully self-contained.
   Phase 6 is triggered by the user via `arch ship` (see Status & Ship Commands below).

   Cross-team dependency gates are the Team Architect's responsibility: each Team
   Architect checks `git log --all --grep="\[SHIPPED\] team-<N>"` before starting
   work that `depends_on_teams`. If the upstream team has not shipped, the Team
   Architect sleeps and polls git — it does NOT need the Primary to coordinate.

**Team Architect behavior** (per team, backgrounded Sonnet):
- Receives: slug, team number, charter task list, integration branch, manifest path
- Runs mini Phase 1 (team-scoped research) → Phase 2 (charter task decomp) → Phases 3-5
- Branch namespace: `arch/<slug>/team-<N>/` (workers write `arch/<slug>/team-<N>/worker-<task_id>`)
- Completion signal: `git tag arch/<slug>/team-<N>/SHIPPED -m "team <N> complete"`
  + append `TEAM_SHIPPED | team-<N> | <timestamp>` to manifest.log + commit
- Escalations: `git commit -m "ESCALATION: team-<N> <task_id> — <summary>"`

**SecArch + Tester gates are never bypassed** — each Team Architect runs its own Phase 4-5 cycle.
For `is_major_change` tasks: Primary Architect ALSO reviews after Team's SecArch approves.

**Launching Team Architects (Primary spawns after charter decomposition)**:
```python
for each charter:
    Task(
        subagent_type="general-purpose",
        model="<MODEL_WORKER>",  # balanced tier — see roles/model-map.md
        run_in_background=True,
        worktree_isolation=True,
        team_name="arch-<slug>",
        name="team-arch-<N>-<slug>",
        prompt="""You are Team Architect <N> for project <slug>.
Charter: <task list from manifest.log CHARTERS_DEFINED>
Integration branch: arch/<slug>/main
Your branch namespace: arch/<slug>/team-<N>/
Manifest: .agent-project/manifest.log
DOMAIN_HINTS: <inject from manifest.log DOMAIN_HINTS block>
[inject full SKILL.md + all role files]
Run Phases 1-5 for your charter only. On completion:
  git tag arch/<slug>/team-<N>/SHIPPED -m "team <N> complete"
  Append TEAM_SHIPPED entry to manifest.log and commit."""
    )
```

**Self-launching Primary Architect (optional — for fully hands-off execution)**:
```python
Task(
    subagent_type="general-purpose",
    model="<MODEL_ARCHITECT>",  # heavy tier — see roles/model-map.md
    run_in_background=True,
    name="primary-arch-<slug>",
    prompt="You are the Primary Architect for <slug>. [inject full SKILL.md + role files]. Run Phases 0-6."
)
```
Use this only after plan is approved. Primary then handles charter decomp + team spawning autonomously.

**Headless behavior**:
- Escalations → `git commit -m "ESCALATION: <team/task> — <summary>"` on relevant branch.
  Review across all teams: `git log --all --grep=ESCALATION`
- SecArch + Tester gates still block — never bypassed
- On `halt_on` conditions: Team Architect writes `.agent-project/escalation.md` + commits, stops its own team.
  Primary does NOT need to be alive — user sees it on next `arch status` run.
- Primary session is intentionally short-lived in multi-team mode. Teams run and commit autonomously.

---

## Git Coordination Protocol

Git is the source of truth and the inter-team communication bus. Every meaningful state
transition must be committed. Teams and workers signal via parseable commit message conventions.

**Branch namespace:**
```
arch/<slug>/main                          # integration branch (Primary Architect)
arch/<slug>/team-<N>/                     # team namespace (Team Architect)
arch/<slug>/team-<N>/worker-<task_id>     # worker branches (Workers)
```

**Commit message conventions (machine-parseable):**
| Signal | Format |
|---|---|
| Worker checkpoint | `[WORKER] <task_id>: <STEP> — <summary>` |
| Task complete | `[DONE] <task_id> — <summary>` |
| Team shipped | `[SHIPPED] team-<N> — <summary>` |
| Escalation | `ESCALATION: <team/task> — <summary>` |
| Stuck worker | `STUCK: <task_id> — no git activity 120s` |
| Cleanup event | `CLEANUP: <what> — <reason>` |
| Log/state | `log: <event>` |

**Primary Architect polling (headless):**
```bash
# All activity across all teams (last 5 min):
git log --all --since="5 minutes ago" --oneline --decorate

# Check if a specific team shipped:
git log --all --grep="\[SHIPPED\] team-<N>" --oneline

# All escalations across all teams:
git log --all --grep="ESCALATION" --oneline

# Worker progress on a specific task:
git log --all --grep="\[WORKER\] <task_id>" --oneline
```

**Cross-team dependency gate:**
```bash
# Before starting Team B that depends_on_teams: [1]:
git log --all --grep="\[SHIPPED\] team-1" --oneline
# Empty → Team 1 not shipped yet → do not start Team B
# Non-empty → Team 1 shipped → unblock Team B
```

---

## Cleanup Protocol

**Stuck worker (detected by drain loop — no git commits in 120s):**
1. `kill_agent(agent_id)`
2. `git worktree remove --force <worktree_path>`
3. `git commit -m "STUCK: <task_id> — no git activity 120s"`
4. Append `STUCK | <task_id> | <timestamp>` to manifest.log + commit
5. If `retry_count < retry_budget` → re-spawn worker with same task spec + DOMAIN_HINTS
6. Else → escalate (see `references/escalation-format.md`)

**Session crash recovery:**
1. `git log .agent-project/manifest.log --oneline` → find last committed state
2. `git worktree list` → identify dangling worktrees from crashed session
3. For each dangling worktree:
   - `git log <branch> --grep="\[DONE\]"` non-empty → task finished, just remove: `git worktree remove --force <path>`
   - Empty → worker was mid-task → re-spawn with same task spec
4. Append `RECOVERY | <timestamp> | resumed from <last-commit>` to manifest.log + commit

**End-of-project cleanup (Phase 6 additions after existing steps):**
```bash
# Remove remaining worktrees:
git worktree list
git worktree remove --force <any remaining paths>

# Prune merged worker + team branches:
git branch --merged arch/<slug>/main | grep "arch/<slug>/" | xargs git branch -d

# Final audit:
git branch -a | grep "arch/<slug>/"   # should only show main after pruning
```

See `references/cleanup-protocol.md` for full recovery procedures and multi-team stuck-team escalation.

---

## Spawning Agents (Task Tool Calls)

Every agent spawn MUST include the `model` parameter from `roles/model-map.md`:

```python
# Researcher
Task(subagent_type="Explore", model="<MODEL_WORKER>",  # balanced tier — see roles/model-map.md
     run_in_background=True,
     team_name="arch-<slug>", name="researcher-<topic>", prompt="...")

# Worker
Task(subagent_type="general-purpose", model="<MODEL_WORKER>",  # balanced tier — see roles/model-map.md
     run_in_background=True, worktree_isolation=True,
     team_name="arch-<slug>", name="worker-<task_id>", prompt="...")

# SecArch
Task(subagent_type="general-purpose", model="<MODEL_SECARCH>",  # heavy tier, SECONDARY family — see roles/model-map.md
     run_in_background=True, team_name="arch-<slug>",
     name="secarch-<task_id>", prompt="...")

# Tester
Task(subagent_type="general-purpose", model="<MODEL_TESTER>",  # secondary family — see roles/model-map.md
     run_in_background=True, team_name="arch-<slug>",
     name="tester-<task_id>", prompt="...")

# Team Architect (multi-team headless only — spawned by Primary Architect)
Task(subagent_type="general-purpose", model="<MODEL_WORKER>",  # balanced tier — see roles/model-map.md
     run_in_background=True, worktree_isolation=True,
     team_name="arch-<slug>", name="team-arch-<N>-<slug>", prompt="...")
```

---

## Status & Ship Commands (Headless Multi-Team Mode)

### `arch status`

Triggered by the user at any time after teams are launched. Reads manifest.log and git
state — no running session required.

```bash
M=.agent-project/manifest.log

# Team summary
echo "=== TEAMS ==="
grep "| TEAM_SHIPPED |" "$M" | awk -F'|' '{print $2, "SHIPPED"}'
grep "| TEAMS_LAUNCHED |" "$M" | head -1

# Task summary
echo "=== TASKS ==="
reg=$(grep -c "| TASK_REGISTERED |" "$M")
done_n=$(grep -c "| DONE |" "$M")
echo "Registered: $reg | Done: $done_n | Remaining: $((reg - done_n))"

# Open security conditions
open_c=$(grep -c "| CONDITION_OPEN |"   "$M")
closed_c=$(grep -c "| CONDITION_CLOSED |" "$M")
[ "$open_c" -gt "$closed_c" ] && echo "⚠ $((open_c - closed_c)) security condition(s) open"

# Escalations
esc=$(git log --all --grep="ESCALATION" --oneline | wc -l | tr -d ' ')
[ "$esc" -gt 0 ] && echo "🚨 $esc escalation(s) — git log --all --grep=ESCALATION"

# Recent activity (last 10 min)
echo "=== RECENT GIT ACTIVITY ==="
git log --all --since="10 minutes ago" --oneline
```

Present the output as a clean status table. If all tasks are DONE and no open conditions,
tell the user: "All teams complete — run `arch ship` to merge and tag the release."

---

### `arch ship`

Triggered by the user when `arch status` shows all teams SHIPPED. Runs Phase 6.

```bash
M=.agent-project/manifest.log
reg=$(grep -c "| TASK_REGISTERED |" "$M")
done_n=$(grep -c "| DONE |" "$M")
open_c=$(grep -c "| CONDITION_OPEN |" "$M")
closed_c=$(grep -c "| CONDITION_CLOSED |" "$M")

[ "$reg" -eq "$done_n" ]      || { echo "BLOCKED: $reg registered, $done_n done"; exit 1; }
[ "$open_c" -eq "$closed_c" ] || { echo "BLOCKED: $((open_c - closed_c)) conditions open"; exit 1; }
```

If both checks pass → run Phase 6 (merge branches, tag release, design-doc, retrospective,
cleanup, SHIPPED entry). If either check fails → report exactly what is blocking and stop.

---

## Related Skills

- `cortex-agent-optimization` — optimizing Snowflake Cortex Agents built by this framework
- `prompt-determinism-tester` — validating prompts produced by this framework
- `cortex-accelerator` — Snowflake-specific Cortex AI builds (SV + agent pipelines)

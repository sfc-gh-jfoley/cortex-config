# Cleanup Protocol

Procedures for recovering from stuck workers, crashed sessions, and stale git artifacts.
Referenced by `SKILL.md` Cleanup Protocol section and Phase 6 Ship.

---

## Stuck Worker Recovery

**Detection** (in Phase 3 drain loop):
A worker is STUCK when all of the following are true:
1. `git log <worker-branch> -1 --format="%ct"` has not changed in 120+ seconds
2. `agent_output(agent_id, wait=false)` shows the agent is still running (not completed)

**Actions (in order):**
1. Kill the agent: `kill_agent(agent_id)`
2. Remove its worktree: `git worktree remove --force <worktree_path>`
3. Commit the event: `git add .agent-project/manifest.log && git commit -m "STUCK: <task_id> — no git activity 120s"`
4. Append to manifest.log: `<timestamp> | worker-<task_id> | STUCK | retry <N>`
5. **If `retry_count < retry_budget`** → re-spawn worker with same task spec + DOMAIN_HINTS from manifest
6. **If `retry_count >= retry_budget`** → escalate (see `escalation-format.md`)

---

## Session Crash Recovery

Run this procedure when the Architect session restarts unexpectedly:

```bash
# 1. Find last committed state
git log .agent-project/manifest.log --oneline | head -20

# 2. Find dangling worktrees from previous session
git worktree list

# 3. For each dangling worktree path, check if its task completed:
git log <branch> --grep="\[DONE\]" --oneline
# Non-empty → task finished, worktree just wasn't cleaned up → safe to remove
# Empty → worker was mid-task → needs re-spawn
```

**For each dangling worktree:**
- **Completed** (`[DONE]` commit exists): `git worktree remove --force <path>`
- **Incomplete**: `git worktree remove --force <path>`, then re-spawn worker with same task spec

After resolving all worktrees:
```bash
git add .agent-project/manifest.log
git commit -m "log: RECOVERY — resumed from <last-commit-sha>"
```

---

## Multi-Team Stuck-Team Escalation

A Team Architect is considered stuck when:
- No `[SHIPPED]` tag after 2x the expected team duration
- No new commits on `arch/<slug>/team-<N>/` for `team_stuck_threshold_seconds` (default: 1800s / 30 min)

**Actions:**
1. Check escalation log: `git log arch/<slug>/team-<N> --grep="ESCALATION" --oneline`
   - If escalations exist → review them, determine if team is blocked on a dependency
   - If no escalations → team may have crashed silently
2. Check team manifest: `git show arch/<slug>/team-<N>:.agent-project/manifest.log | tail -20`
3. If team is unrecoverable: kill team agent, re-spawn Team Architect with same charter + latest manifest state
4. Commit: `git commit -m "CLEANUP: team-<N> — re-spawned after stuck detection"`

---

## End-of-Project Cleanup (Phase 6)

Run after all tasks complete and before the retrospective:

```bash
# 1. Remove any remaining worktrees
git worktree list
# For each non-main worktree:
git worktree remove --force <path>

# 2. Audit merged branches before pruning
git branch --merged arch/<slug>/main | grep "arch/<slug>/"
# Review the list — these are safe to delete

# 3. Prune merged worker and team branches
git branch --merged arch/<slug>/main | grep "arch/<slug>/" | xargs git branch -d

# 4. For multi-team: verify all team SHIPPED tags exist
git tag | grep "arch/<slug>/team-"

# 5. Final branch audit — should only show integration branch
git branch -a | grep "arch/<slug>/"
```

**Expected final state:**
- `arch/<slug>/main` → integration branch (will be merged to project main by Architect)
- All `arch/<slug>/team-N/` branches → deleted (merged)
- All `arch/<slug>/team-N/worker-*` branches → deleted (merged)
- All team SHIPPED tags → present and intact

---

## Stale Artifact Detection

Run if you suspect leftover artifacts from a previous incomplete build:

```bash
# Branches not merged to main that are older than 24h
git for-each-ref --sort=committerdate refs/heads/arch/<slug>/ \
  --format='%(refname:short) %(committerdate:relative)'

# Worktrees with no recent activity
git worktree list --porcelain

# Untracked .agent-project/ entries (possible leftover manifests)
find .agent-project/ -name "manifest.log" -newer .agent-project/manifest.log
```

Stale artifacts from previous failed runs should be removed before starting a new run
on the same slug. Rename the slug or clean up manually.

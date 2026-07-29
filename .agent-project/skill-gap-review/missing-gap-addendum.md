# Skill & Toolkit Gap Report — Addendum

**Project**: skill-gap-review  
**Date**: 2026-07-10  
**Researcher**: implementor-task-32c41887  
**Baseline**: gap-report.md (2026-07-09)

---

## Executive Summary

This addendum documents **net-new findings** not present in the baseline gap-report, plus resolution status for prior findings post-research.

| Severity | Count | Findings |
|---|---|---|
| **NEW CRITICAL** | 1 | No repo-level AGENTS.md to override bundled `machine-learning` routing |
| **NEW HIGH** | 2 | Missing plugin routers; stale model slugs widespread across coco-meta skills |
| **RESOLVED** | 1 | C-3 commit format issue — worker.md already correct |

---

## Critical Findings

### NEW-C1: Missing repo-local `AGENTS.md` blocks bundled-to-vault routing
**Surface**: Vault framework / bundled-vs-vault gap  
**Dimension**: Architecture / routing gap

The baseline report (H-1) correctly identifies that `ml-pipeline-toolkit` is unreachable from bundled ML skill routing, but its skill-loader coverage is already addressed. Investigation shows:

1. **ml-pipeline-toolkit IS registered** in `skill-loader/SKILL.md` (line 74) with 10 sub-skills correctly indexed
2. **The routing gap is higher**: The system-reminders inject a bundled `machine-learning` skill with `[REQUIRED]` tag, triggering first for all ML tasks
3. **No repo-local mechanism exists to override** the bundled skill with the vault plugin. The proposed fix (H-1) says "Add `machine-learning` → `ml-pipeline-toolkit` to `AGENTS.md` override table" — but this repository contains no `AGENTS.md`

**Evidence**:
- `skill-loader/SKILL.md:74` already registers `ml-pipeline-toolkit`, so adding it there is not the missing work
- Global instructions at `~/.snowflake/cortex/AGENTS.md` document an override table pattern for bundled skills
- `glob **/AGENTS.md` in this repository returns no files; the proposed override cannot be represented in repo-managed config today
- Bundled `machine-learning` skill will always fire first due to `[REQUIRED]` tag in session-reminder

**Fix**: 
1. Add a repo-managed `AGENTS.md` path or document the local-only override path explicitly
2. Add override entry: `machine-learning` → `ml-pipeline-toolkit` (routing to root SKILL.md at `plugins/ml-pipeline-toolkit/SKILL.md`)
3. Verify session-reminder respects the override table during skill loader initialization

---

## High-Severity Findings

### NEW-H1: Three plugins lack root SKILL.md router entry points
**Surface**: Vault plugin structure / discovery gap  
**Dimension**: Plugin architecture inconsistency

Three plugin directories have registered sub-skills on disk but **no root SKILL.md** at the plugin root:

| Plugin | Root Dir | Sub-skills Present | Root SKILL.md | Router Consequence |
|---|---|---|---|---|
| `ops-monitor` | `plugins/ops-monitor/` | ✅ 3 skills (artifact-drift-monitor, release-change-monitor, self-healing-pipeline) | ❌ Missing | Cannot invoke `ops-monitor` as a router; only sub-skills discoverable |
| `rule-governance` | `plugins/rule-governance/` | ✅ 5 skills (rule-loader, rule-creator, rule-reviewer, bulk-rule-reviewer, memory-organizer) | ❌ Missing | Cannot invoke `rule-governance` as a router; only sub-skills discoverable |
| `coco-meta` | `plugins/coco-meta/` | ✅ 5 skills (doc-reviewer, plan-reviewer, prompt-determinism-tester, skill-tester, skill-timing) | ❌ Missing | Cannot invoke `coco-meta` as a router; only sub-skills discoverable |

**Contrast**: Three other plugins WITH root SKILL.md routers exist and properly route:
- `cortex-agent-toolkit` (root SKILL.md at `plugins/cortex-agent-toolkit/SKILL.md`)
- `ml-pipeline-toolkit` (root SKILL.md at `plugins/ml-pipeline-toolkit/SKILL.md`)
- `semantic-view-toolkit` (root SKILL.md at `plugins/semantic-view-toolkit/SKILL.md`)

**Evidence**:
- `glob plugins/*/SKILL.md` returns only 3 files (the three with routers)
- `skill-loader/SKILL.md:62-104` registers their sub-skills under Ops & Monitoring, Rules & Governance, and Meta & Quality, but has no router rows for `ops-monitor`, `rule-governance`, or `coco-meta`

**Fix**: 
Create root SKILL.md router for each plugin, following the pattern of `cortex-agent-toolkit/SKILL.md`:
1. Describe plugin purpose (high-level)
2. List all sub-skills with their descriptions
3. Use Skill/Entry router pattern to dispatch to sub-skills
4. Include trigger keywords for the plugin as a whole (e.g., `ops-monitor` triggers: "monitor, observability, drift, health")

**Impact**: Users cannot discover or invoke these plugins as logical units; they must know sub-skill names explicitly.

---

### NEW-H2: Stale model slugs extend far beyond doc-reviewer/plan-reviewer
**Surface**: coco-meta skills / model naming / configuration  
**Dimension**: Stale content / broad scope

The baseline report (L-1) identifies stale `claude-sonnet-45` usage in `doc-reviewer` and `plan-reviewer` SKILL.md files. Investigation reveals **the staleness is far broader** across documentation, examples, tests, and README files:

**Affected files by scope:**

1. **doc-reviewer skill:**
   - `SKILL.md` (lines 25, 168, 182)
   - `README.md` (9 occurrences: lines 38, 49, 61, 69, 71, 83, 101, 232, 236)
   - `tests/test-invocation-full.md` (5 occurrences)
   - `tests/test-invocation-staleness.md` (3 occurrences)

2. **plan-reviewer skill:**
   - `SKILL.md` (line 35)

3. **skill-timing skill (NEW, not in baseline):**
   - `README.md` (10 occurrences: lines 33, 61, 69, 179, 216, 242, 269, 355, and examples)
   - Examples directory (baseline-workflow.md, others)

**Evidence**: `grep -r "claude-sonnet-45" plugins/coco-meta/` yields 40+ matches across 8+ files

**Root cause**: Model slugs were standardized in early 2026, but these example/documentation references were not refreshed during subsequent skill updates.

**Fix**: Bulk replace `claude-sonnet-45` with `claude-sonnet-4-6` across all coco-meta skills (doc-reviewer, plan-reviewer, skill-timing). Update:
- SKILL.md documentation blocks
- README.md examples
- Test invocation blocks and expected outputs
- Example workflow files

**Impact**: Users copying example commands get outdated model slugs; new skill invocations may fail or use wrong model for baseline/testing.

---

## Already Covered / Not Repeated

The following findings were resurfaced by research but already appear in the baseline report:

| Finding | Gap-Report Reference | Status |
|---|---|---|
| C-2: worker.md branch namespace wrong | Lines 35-44 | **Confirmed** — still incorrect; branch namespace should be `arch/<slug>/team-<N>/worker-<task_id>` |
| C-3: worker.md commit format wrong | Lines 48-60 | **RESOLVED** — worker.md line 130 now uses correct `[DONE]` format; cleanup-protocol.md line 37 confirms grep match |
| H-1: ml-pipeline-toolkit orphaned | Lines 66-75 | **PARTIALLY RESOLVED** — skill-loader coverage is already addressed, but routing gap moved up to root cause (missing repo-local AGENTS.md) |
| L-1: Stale model slugs in doc-reviewer/plan-reviewer | Lines 234-237 | **EXPANDED** — scope extends to skill-timing and broader across examples/tests |

---

## Exclusions

Per user directive: `iot-pipeline-builder` and `specbuilder` were excluded. These are customer projects, not vault skills, and do not require registration in the vault framework.

---

## Recommendations

**Immediate action items (by severity):**

1. **CRITICAL**: Create or document the repo-managed override mechanism needed to route bundled `machine-learning` skill to `ml-pipeline-toolkit`
2. **HIGH**: Create root SKILL.md routers for `ops-monitor`, `rule-governance`, and `coco-meta` plugins
3. **HIGH**: Bulk-replace stale model slugs in coco-meta skills (40+ instances across 3 skills)
4. **MEDIUM**: Verify C-2 (branch namespace fix) has been applied to `roles/worker.md` — it appears not to have been

**Verification plan:**
- Re-check branch namespace in worker.md post-fix against canonical namespace in `team-architect.md` and cleanup-protocol.md
- After AGENTS.md creation, test bundled `machine-learning` skill routing to vault toolkit
- After plugin router creation, verify sub-skills remain discoverable and router SKILL.md correctly documents all entry points

---

## Evidence References

- skill-loader/SKILL.md:74 — `ml-pipeline-toolkit` registration
- plugins/ml-pipeline-toolkit/SKILL.md — root router exists
- plugins/cortex-agent-toolkit/SKILL.md — reference router pattern
- plugins/coco-meta/skills/doc-reviewer/SKILL.md:25, 168, 182 — stale model slugs
- plugins/coco-meta/skills/skill-timing/README.md:33, 61, 69, 179, 216, 242, 269, 355 — stale model slugs
- skills/agent-architect/roles/worker.md:130 — correct `[DONE]` commit format
- skills/agent-architect/references/cleanup-protocol.md:37 — grep pattern expects `[DONE]`

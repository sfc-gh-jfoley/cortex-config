---
document_type: expansion-manifest
document_id: 00-expansion-architecture
created: 2026-07-10
scope: architecture-overview
---

# Expansion Architecture Overview: 5 Tracks + Tethering Contract

**Purpose**: Provides the cross-track dependency map, sequencing rationale, and "expansion without breakage" contract that all five expansion manifests reference. This document is read first by all team members.

---

## Expansion Map: Tracks and Their Scope

| Track | Title | Plugin Status | Files Modified | Cross-Track Dependencies |
|-------|-------|---------------|-----------------|-------------------------|
| T1 | Semantic View DDL | Extend existing (`semantic-view-toolkit`) | `sv-ddl/reference/ddl_syntax.md`, `sv-ddl/phases/02_profile_describe.md`, `sv-ddl/phases/03_classify.md`, `sv-ddl/phases/05_generate_ddl.md`, `semantic-view-toolkit/SKILL.md` | Depends on T0 (architecture) |
| T2a | Native TSA/TEA (agent-eval update) | Extend existing (`cortex-agent-toolkit`) | `agent-evaluation/SKILL.md`, `agent-evaluation/references/eval-troubleshooting.md` | Depends on T0 (architecture) |
| T2b | Analytical Search Sub-skill | Extend existing (`cortex-agent-toolkit`) + new sub-skill | `cortex-agent-toolkit/SKILL.md` (router), `cortex-agent-toolkit/skills/cortex-agent-ddl/SKILL.md` (tool type list), `cortex-agent-toolkit/.cortex-plugin/activation.md`, NEW: `cortex-agent-toolkit/skills/analytical-search/SKILL.md` | Depends on T2a (same plugin), T0 (architecture) |
| T3 | CoWork Plugin (Artifacts + Deep Research) | **New plugin** (`plugins/cowork/`) | 6 new files (router, activation, README, PREREQUISITES, 2 sub-skill SKILL.md) | Depends on T0 (architecture); cross-ref in cortex-agent-toolkit |
| T4 | Adaptive Compute Plugin | **New plugin** (`plugins/adaptive-compute/`) | 7 new files; 1 file updated: `ops-monitor/skills/self-healing-pipeline/SKILL.md` (one-line cross-ref) | Depends on T0 (architecture), T3+T4+T5 sequenced (T4 last because AWS-only gate) |
| T5 | Workload Identity Federation Plugin | **New plugin** (`plugins/workload-identity/`) | 8 new files | Depends on T0 (architecture); cross-ref from bundled `key-and-secret-management` noted |

---

## Cross-Track Dependency Graph

```
T0 (this document)
 ├─ T1 (sv-ddl expansion)       [Independent; no deps on T2-T5]
 ├─ T2a (Native TSA/TEA)        [Independent; no deps on T1/T3/T4/T5]
 ├─ T2b (analytical-search)     [Depends on T2a — same plugin]
 ├─ T3 (CoWork plugin)          [Independent; cross-ref in T2b outputs]
 ├─ T4 (Adaptive Compute)       [Independent; cross-ref in T5 outputs]
 └─ T5 (Workload Identity)      [Independent; cross-ref in bundled skill noted]

Sequencing for implementation (minimize merge conflicts):
  1. T1 + T2a (can run in parallel — different plugins)
  2. T2b (uses T2a outputs, same plugin)
  3. T3 + T5 (can run in parallel — new standalone plugins)
  4. T4 (final; cross-refs T5 output in ops-monitor)
  5. Batch skill-loader update (all 5 tracks)
```

---

## skill-loader as Shared Touchpoint

Every new plugin or sub-skill requires a router row in `skill-loader/SKILL.md`. This is the single hub that users hit when invoking `/skill` or seeking guidance.

### Current skill-loader structure:
- Sections: "Semantic Views", "Cortex Agents", "Data Governance", etc.
- Each section lists plugins + sub-skills with brief descriptions and trigger examples

### Expansion updates to skill-loader (done as ONE coordinated batch at the end):

**New sections:**
- "Compute & Warehouses" — `plugins/adaptive-compute` (setup + monitor sub-skills)
- "Security & Auth" — `plugins/workload-identity` (setup + troubleshoot sub-skills)
- "Collaboration" — `plugins/cowork` (artifacts + deep-research sub-skills)

**New rows under existing sections:**
- "Cortex Agents" — `analytical-search` sub-skill (under existing `cortex-agent-toolkit` section)
- "Semantic Views" — notes updated to mention SQL logical tables + VARIABLES + sample values

**Total new rows:** ~15 across all sections

---

## Tethering Contract: Every New Plugin Must Satisfy This Checklist

The "untethered expansion risk" (plugins with no root SKILL.md, no activation.md, unreachable from skill-loader) caused prior blind spots. This contract prevents it:

### For each new plugin or major sub-skill, verify:

- ✅ **Root SKILL.md exists** at `plugins/<plugin-name>/SKILL.md` — router listing all sub-skills, positioning vs. related products, when to use this plugin
- ✅ **activation.md exists** at `plugins/<plugin-name>/.cortex-plugin/activation.md` — prerequisites, version gating, region checks (if applicable)
- ✅ **skill-loader row added** with plugin name, brief description, trigger examples
- ✅ **Sub-skills have SKILL.md** at `plugins/<plugin-name>/skills/<sub-skill-name>/SKILL.md` — full workflow for that sub-skill
- ✅ **Bidirectional cross-references** — if this plugin's SKILL.md says "related: X", then X's SKILL.md must mention this plugin back
- ✅ **README** (if needed) at `plugins/<plugin-name>/README.md` — high-level overview, use cases, examples
- ✅ **PREREQUISITES.md** (if needed) at `plugins/<plugin-name>/PREREQUISITES.md` — account setup, grants, config steps
- ✅ **No silent failures** — Phase 0 or Phase 1 must gate on prerequisites (region check, feature flag, grant verification) before proceeding

### Bidirectional cross-reference examples:

- **T3 (CoWork) ↔ T2 (cortex-agent-toolkit)**: CoWork SKILL.md says "CoWork is a consumer of agents — see cortex-agent-toolkit for agent creation". Cortex-agent-toolkit SKILL.md says "For multi-turn investigation, consider cowork plugin".
- **T4 (Adaptive Compute) ↔ T5 (ops-monitor)**: Adaptive Compute SKILL.md references self-healing-pipeline. Self-healing-pipeline's SKILL.md adds a cross-ref: "For persistent warehouse issues, consider adaptive-compute plugin".
- **T5 (Workload Identity) ↔ bundled key-and-secret-management**: Workload Identity SKILL.md positioning section says "arrived from key-and-secret-management? You're in the right place." (No need to modify bundled skill, only document the entry point.)

---

## Region-Gating Protocol: AWS-Only Example (Track 4)

**Track 4 (Adaptive Compute)** uses Adaptive Warehouses, which are GA only on AWS.

**Enforcement:**
- **Phase 0 in setup sub-skill**: Mandatory `SELECT CURRENT_REGION()` check
- **Gate logic**: 
  ```
  IF region IN ('us-east-1', 'us-west-2', 'eu-west-1', 'ap-southeast-1', ...) THEN proceed
  ELSE stop with clear message: "Adaptive Warehouses are AWS-only. Current region: <region>. See https://docs.snowflake.com/adaptive-warehouses"
  ```
- **activation.md** notes: `"Requires: AWS deployment"` — this blocks non-AWS users at entry time

---

## Phased Rollout Order (Minimizes Blast Radius)

1. **Phase I (T1 + T2a)** — Extend existing, well-tested plugins
   - T1: sv-ddl feature parity (SQL queries, variables, sample values)
   - T2a: agent-evaluation label inversion (native TSA/TEA)
   - **Risk**: Low (updates to existing docs/notes; no schema changes)
   - **Rollback**: Revert files; no skill-loader changes yet

2. **Phase II (T2b)** — New sub-skill in existing plugin
   - T2b: analytical-search sub-skill (new router row in cortex-agent-toolkit)
   - **Risk**: Medium (new skill surface)
   - **Rollback**: Revert sub-skill dir + cortex-agent-toolkit/SKILL.md row

3. **Phase III (T3 + T5)** — New standalone plugins, no cross-file deps
   - T3: CoWork plugin (6 files, independent)
   - T5: Workload Identity plugin (8 files, independent)
   - **Risk**: Medium (new plugins, but isolated)
   - **Rollback**: `rm -rf plugins/cowork plugins/workload-identity`

4. **Phase IV (T4)** — New plugin with one cross-file dependency
   - T4: Adaptive Compute plugin (7 new files + 1-line update to self-healing-pipeline)
   - **Risk**: Medium (AWS-only gate reduces scope; one external reference)
   - **Rollback**: `rm -rf plugins/adaptive-compute` + revert self-healing-pipeline line

5. **Phase V (skill-loader batch)** — Coordinate all routing changes
   - Add ~15 rows to skill-loader/SKILL.md in one atomic commit
   - **Risk**: Low (isolated file; coordinated review)
   - **Rollback**: Revert skill-loader/SKILL.md

---

## Verification Checklist (After All Manifests Written)

- ✅ Each manifest references real file paths that exist in the repo (grep-verifiable)
- ✅ No manifest proposes deleting or renaming an existing file
- ✅ Every new plugin in a manifest satisfies the tethering contract checklist above
- ✅ Cross-references are bidirectional: if Manifest A says "update file X to reference Plugin B," Manifest B's file list includes that update
- ✅ `grep -r "adaptive-compute\|workload-identity\|cowork\|analytical-search" skill-loader/SKILL.md` returns zero (confirming skill-loader is not yet updated and will be batch-updated in Phase V)
- ✅ Each manifest's "Files Changed" section lists all files it proposes to modify (no surprises in implementation)

---

## Summary for Implementors

- **Worker 1**: Writes `01-sv-ddl-expansion.md` + `02-cortex-agent-expansion.md` (Tracks 1, 2a, 2b). Needs deepest knowledge of existing plugins.
- **Worker 2**: Writes `03-cowork-plugin.md` + `05-workload-identity.md` (Tracks 3, 5). Both new standalone plugins with similar structure.
- **Worker 3**: Writes `04-adaptive-compute.md` (Track 4). Needs to coordinate cross-ref update to self-healing-pipeline.
- **Main agent**: Writes `06-skill-loader-batch.md` after all manifests are verified; executes the batch skill-loader update.

Each manifest is a self-contained spec: **what to build, what it risks breaking, how to mitigate.** No implementation — documentation only.

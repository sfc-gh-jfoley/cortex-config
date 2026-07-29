# Skill & Toolkit Gap Report
**Project**: skill-gap-review  
**Date**: 2026-07-09  
**Framework**: agent-architect v3.1  
**Researchers**: researcher-bundled-skills, researcher-vault-surface, researcher-agent-arch-internals  

---

## Executive Summary

| Severity | Count | Surfaces Affected |
|---|---|---|
| CRITICAL | 3 | bundled-skills, agent-architect roles |
| HIGH | 5 | bundled-skills, vault routing |
| MEDIUM | 7 | agent-architect internals, bundled coverage |
| LOW | 10 | stale content, cosmetic, structural |
| **Total** | **25** | |

---

## CRITICAL — Breaks functionality today

### C-1: `cortex-agent` bundled skill loads wrong SKILL.md
**Surface**: Bundled skills  
**Dimension**: Internal consistency / trigger routing

The `cortex-agent` skill dir has a [REQUIRED] tag in the session-reminder (fires first for all agent operations). The most-recently-modified `SKILL.md` inside the versioned hash subdir is `optimize-cortex-search-service` — a Cortex Search Service optimization sub-skill with nothing to do with agent management. Any user invoking `cortex-agent` gets CSS optimization instructions instead.

**Root cause**: The sub-skill structure (hash-versioned subdirs) means the newest SKILL.md is often a sub-skill, not the parent router. The parent router lives in an older hash subdir.

**Fix**: Verify which versioned subdir contains the parent cortex-agent router SKILL.md and ensure it is the one loaded. Also review all skills where the loaded SKILL.md has `parent_skill:` in its front-matter — those are sub-skills, not routers.

---

### C-2: `worker.md` uses wrong git branch namespace
**Surface**: Agent-architect roles  
**Dimension**: Internal consistency / stale pattern

`roles/worker.md` tells workers to create branches as `agent/worker-<team_id>/<task_id>`.  
SKILL.md, team-architect.md, and cleanup-protocol.md all define the canonical namespace as `arch/<slug>/team-<N>/worker-<task_id>`.

The Architect's git drain loop and crash-recovery grep on `arch/<slug>/` prefix patterns. Worker commits on the wrong namespace are **invisible** to the drain loop — workers will be flagged as stuck and killed after 120s.

**Fix**: Update `roles/worker.md` Step 1 and all branch references to use `arch/<slug>/team-<N>/worker-<task_id>`.

---

### C-3: `worker.md` produces commit messages that crash recovery cannot parse
**Surface**: Agent-architect roles  
**Dimension**: Internal consistency

`roles/worker.md` Steps 6-7 tell workers to commit as:
- `feat(<task_id>): <task_title>`
- `log: done <task_id>`

`cleanup-protocol.md` crash-recovery uses `git log <branch> --grep="\[DONE\]"` to determine if a task finished. These commits will never match. After a session crash, completed tasks will be re-queued and re-executed.

SKILL.md commit convention table defines: `[DONE] <task_id> — <summary>`.

**Fix**: Update `roles/worker.md` completion commit to exactly `[DONE] <task_id> — <summary>`. Checkpoint commits should use `[WORKER] <task_id>: <STEP> — <summary>` per SKILL.md conventions.

---

## HIGH — Routing failures / significant capability gaps

### H-1: `ml-pipeline-toolkit` is completely orphaned
**Surface**: Vault plugins  
**Dimension**: Missing coverage / bundled-vs-vault gap

`vault/plugins/ml-pipeline-toolkit/` has 10 sub-skills on disk:
`ml-deploy, ml-experiments, ml-feature-store, ml-functions, ml-lifecycle, ml-log-inspector, ml-observability, ml-pipeline-build, ml-registry, ml-watch`

Neither `skill-loader/SKILL.md` nor `AGENTS.md` reference this plugin at all. The bundled `machine-learning` skill has `[REQUIRED]` in its description, so it fires first for every ML task. There is no routing path to the vault toolkit.

**Fix**: Add `machine-learning` → `ml-pipeline-toolkit` to `AGENTS.md` override table. Add all 10 sub-skills to `skill-loader/SKILL.md` under a new "Machine Learning" section.

---

### H-2: Dead-end references in bundled skills
**Surface**: Bundled skills  
**Dimension**: Trigger routing / internal consistency

Two bundled skills reference sub-skills that do not exist in the bundle:
- `event-table` sub-skill calls `skill(command='dt-alerting')` — `dt-alerting` is not bundled
- `alert` sub-skill (`alert-troubleshoot`) says "hand off to `../alert-create-alter/SKILL.md`" — `alert-create-alter` is not bundled

Users following these paths hit dead ends.

**Fix**: Either bundle the missing sub-skills or rewrite the references to remove the handoffs.

---

### H-3: `integrations` skill loads wrong SKILL.md
**Surface**: Bundled skills  
**Dimension**: Internal consistency

The `integrations` parent skill description covers full CRUD for 6 integration types. The loaded SKILL.md (most-recently-modified in versioned subdir) is `show-notification-integrations` — a single `SHOW INTEGRATIONS` syntax reference. Trigger coverage is near-zero.

Same root cause as C-1 (sub-skill versioning).

---

### H-4: Trigger conflicts across sharing skills
**Surface**: Bundled skills  
**Dimension**: Trigger/routing gaps

Three bundled skills share overlapping triggers on `share`, `share data`, and `data product`:
- `sharing`
- `data-sharing`  
- `declarative-sharing`

The session-reminder classifier cannot reliably route between them. Users get non-deterministic skill selection for sharing tasks.

**Fix**: Differentiate triggers. Suggested: `declarative-sharing` owns "declarative share / provider studio / auto-fulfillment"; `data-sharing` owns "share data / create share / consumer"; `sharing` becomes the router/fallback that asks which paradigm.

---

### H-5: 13 bundled coverage gaps
**Surface**: Bundled skills  
**Dimension**: Missing coverage

Task-types with no bundled skill:

| Gap | Notes |
|---|---|
| Snowflake Streams (CDC) | No stream lifecycle skill |
| External Tables + file formats + COPY INTO bulk loading | No skill; closely related to Snowpipe but distinct |
| Session Policies | Explicitly excluded from `manage-authentication-policy` |
| Password Policies | Explicitly excluded from `manage-authentication-policy` |
| RBAC design patterns | `access-troubleshooter` is reactive; no proactive RBAC design skill |
| Warehouse right-sizing / auto-suspend / multi-cluster | No skill despite `warehouse` skill existing at high-level |
| Materialized Views | No skill |
| Snowflake Sequences | No skill |
| General Tag lifecycle (non-governance) | `data-governance` covers governance tags; standalone tag DDL has no skill |
| Query plan / EXPLAIN analysis | No skill for reading query profiles |
| Stored Procedures (SQL/JS/Scala) | `snowpark-python` covers Python only; SQL/JS/Scala procs have nothing |
| Alert CREATE/ALTER | Referenced by `alert-troubleshoot` but the sub-skill is not bundled |
| Cortex Search Service standalone lifecycle | CREATE/ALTER/SHOW CSS has no dedicated skill |

---

## MEDIUM — Incomplete content, internal inconsistencies

### M-1: `team-architect.md` missing from SKILL.md Framework Files table
**Surface**: Agent-architect SKILL.md  
**Dimension**: Internal consistency

`roles/team-architect.md` is a v3.1 core file referenced 20+ times throughout SKILL.md but is absent from the Framework Files table (lines 59-70). Anyone reading the table to understand what files are available will miss it.

**Fix**: Add `roles/team-architect.md` row to Framework Files table.

---

### M-2: `manifest.log` template missing status values
**Surface**: Agent-architect templates  
**Dimension**: Internal consistency

`templates/manifest.log` status registry is missing:
- `TEAM_SHIPPED` — used by `team-architect.md` for team completion signal
- `STUCK` — used by `cleanup-protocol.md` and SKILL.md Phase 3

Any reader using the template as reference for log parsing will not handle these states.

**Fix**: Add `TEAM_SHIPPED` and `STUCK` to the status value block in `templates/manifest.log`.

---

### M-3: `PASS_WITH_WARNINGS` unhandled in `team-architect.md`
**Surface**: Agent-architect roles  
**Dimension**: Internal consistency

`tester.md` and SKILL.md Phase 5 define three verdicts: `PASS`, `PASS_WITH_WARNINGS`, `FAIL`.  
`team-architect.md` Phase 5 (lines 92-93) only handles `PASS` and `FAIL`. There is no instruction for what a Team Architect should do when a Tester returns `PASS_WITH_WARNINGS`.

**Fix**: Add `PASS_WITH_WARNINGS` handling to `team-architect.md` Phase 5 (mark task COMPLETE, note warnings in manifest.log).

---

### M-4: `manifest.log` format inconsistencies across role files
**Surface**: Agent-architect roles  
**Dimension**: Internal consistency

Three inconsistencies vs the canonical 4-field `TIMESTAMP | AGENT | STATUS | DETAILS` format:
1. Worker DONE entries use 5 fields: `TIMESTAMP | AGENT | STATUS | SHA | summary` — SHA field is undocumented in the template
2. STUCK entries from `cleanup-protocol.md` reverse field order: `STATUS | task_id | timestamp` and add an undocumented `| retry <N>` field
3. SKILL.md's own STUCK example (`STUCK | <task_id> | <timestamp>`) differs from cleanup-protocol's format

**Fix**: Standardize all log entries to 4 fields or extend the template to document the SHA and retry fields explicitly.

---

### M-5: Retry budget discrepancy between files
**Surface**: Agent-architect references  
**Dimension**: Internal consistency

`escalation-format.md` (line 43) says stuck tasks escalate "After 1 re-spawn attempt fails."  
`SKILL.md` Cleanup Protocol and `cleanup-protocol.md` both use `retry_count < retry_budget` where `retry_budget: 2`.

Stuck workers get 1 retry per escalation-format.md but 2 retries per cleanup-protocol.md and SKILL.md. The Architect and worker prompts inject different retry expectations.

**Fix**: Align to 2 retries (matching SKILL.md default config) in `escalation-format.md`.

---

### M-6: 6 bundled skills with no vault deep-dive toolkit
**Surface**: Vault / bundled gap  
**Dimension**: Missing coverage

These bundled skills handle common, complex Snowflake workloads but have no vault toolkit equivalent for deeper use cases:

| Bundled Skill | Missing Vault Coverage |
|---|---|
| `dynamic-tables` | Recommendation engine, lag optimization, dependency analysis |
| `data-quality` | Rule authoring, monitoring dashboards, quarantine workflows |
| `snowpark-python` | Full ML pipeline (partially covered by orphaned ml-pipeline-toolkit) |
| `security-investigation` | Deep forensics, threat modeling, anomaly detection |
| `billing` | Budget alert automation, cost attribution workflows |
| `cost-intelligence` | Cross-account cost optimization, idle resource detection |

---

### M-7: `researcher.md` contains SecArch-specific mode
**Surface**: Agent-architect roles  
**Dimension**: Internal consistency

`researcher.md` includes a "Pre-Planning Risk Scan (SecArch variant)" research type. This is actually SecArch's Mode 1 job per `security-gate.md`. Including it in the researcher role creates ambiguity about who runs the pre-planning risk scan — and both agents may attempt it in Phase 1.

**Fix**: Remove the SecArch variant from `researcher.md` or rename it clearly as "pass-through to SecArch."

---

## LOW — Stale content, cosmetic, structural

### L-1: Stale model slugs in `doc-reviewer` and `plan-reviewer`
**Surface**: Vault plugins (coco-meta)  
**Files**: `plugins/coco-meta/skills/doc-reviewer/SKILL.md` (lines 25, 168, 182), `plugins/coco-meta/skills/plan-reviewer/SKILL.md` (line 35)  
Old format: `claude-sonnet-45` → should be `claude-sonnet-4-6`.

---

### L-2: `model-map.md` SecArch not updated to cross-model (memory drift)
**Surface**: Agent-architect roles  
**Dimension**: Stale content

A prior session documented intent to change SecArch from `current_sonnet` to `openai-gpt-5.2` (cross-model independence, same rationale as Tester). The change was never applied to disk. Also: the Haiku downgrade section lists downgrade conditions but provides no model ID (should be `claude-haiku-4-5` per the same memory note).

---

### L-3: `setup-snowflake-sso` uses YAML array trigger format
**Surface**: Bundled skills  
**Dimension**: Internal consistency

All other skills embed triggers inline in the description string. `setup-snowflake-sso` uses a `triggers:` YAML array block — a different spec format. May cause the classifier to miss it.

---

### L-4: `openflow` is the oldest skill and hardcodes a dependency
**Surface**: Bundled skills  
**Dimension**: Stale content

`openflow` has `skill_version: 2026-01-25` (oldest in the bundle). It hardcodes `nipyapi[cli]>=1.5.0` as a Python dependency. `openflow-observability` is a newer complement (`2026-04-30`) but the core `openflow` hasn't been updated since January.

---

### L-5: `agent-created` dir contains a non-user-facing role definition
**Surface**: Bundled skills  
**Dimension**: Internal consistency

`skills/agent-created/` contains `multi-agent-implementor` — a role definition for team-workflow orchestration. It is not a user-facing skill and should not be in the bundled skills dir alongside user-invocable skills.

---

### L-6: Internal-only skills bundled in external distribution
**Surface**: Bundled skills  
**Dimension**: Stale / internal consistency

Two bundled skills reference internal Snowflake infrastructure inaccessible to non-employees:
- `snowflake-public-data` — references `SNOWFLAKE_PUBLIC_DATA_PAID_INTERNAL_TEAM.CYBERSYN` and connection `snowhouse`
- `cortex-ai-usage-analysis` — references `SNOWSCIENCE.LLM.CORTEX_LLM_WAREHOUSE_JOBS_CREDITS`, `CORTEX_JOB_DATA_IMPORT`, connection `SNOWHOUSE_AWS_US_WEST_2`

These skills will silently fail for all external users.

---

### L-7: 33 of 75 bundled SKILL.md files are sub-skills
**Surface**: Bundled skills  
**Dimension**: Structural

The hash-versioned subdir structure means the most-recently-modified `SKILL.md` in many skill dirs is a sub-skill (has `parent_skill:` front-matter), not the parent router. This is the root cause of C-1 and H-3. A systematic audit of all 75 skill dirs should verify the correct SKILL.md is being loaded as the parent.

---

### L-8: `retrospective-protocol.md` references undefined term
**Surface**: Agent-architect references  
**Dimension**: Internal consistency

Line 48 references "Global Review" — a term not defined in any other agent-architect file.

---

### L-9: Legacy vault skills retained in skill-loader
**Surface**: Vault skill-loader  
**Dimension**: Stale content

Two vault skills are explicitly marked LEGACY in skill-loader:
- `skills/semantic-view-ddl` → marked `(LEGACY) — use sv-ddl instead`
- `skills/semantic-view-discovery` → marked `(LEGACY) — use sv-discovery instead`

Both still exist on disk and in the registry. No expiry or removal plan documented.

---

### L-10: `migration-guide` and `spark-migration` trigger overlap
**Surface**: Bundled skills  
**Dimension**: Trigger/routing

Both skills can catch `migrate pyspark`/`spark migration` phrases. Classifier routing is non-deterministic for Spark migration requests.

---

## Prioritized Fix List

| Priority | Item | File(s) to change |
|---|---|---|
| 1 | C-2: worker.md branch namespace | `roles/worker.md` |
| 2 | C-3: worker.md commit format | `roles/worker.md` |
| 3 | C-1: cortex-agent loads wrong SKILL.md | bundled `cortex-agent/` hash subdir audit |
| 4 | H-1: wire up ml-pipeline-toolkit | `AGENTS.md`, `skill-loader/SKILL.md` |
| 5 | H-2: dead-end references | `event-table/` and `alert/` sub-skills |
| 6 | H-3: integrations loads wrong SKILL.md | bundled `integrations/` hash subdir audit |
| 7 | H-4: sharing trigger conflicts | `sharing/`, `data-sharing/`, `declarative-sharing/` |
| 8 | M-1: team-architect.md in Framework Files | `SKILL.md` lines 59-70 |
| 9 | M-2: manifest.log missing status values | `templates/manifest.log` |
| 10 | M-3: PASS_WITH_WARNINGS in team-architect | `roles/team-architect.md` |
| 11 | M-4: manifest format inconsistencies | `roles/worker.md`, `references/cleanup-protocol.md`, `templates/manifest.log` |
| 12 | M-5: retry budget discrepancy | `references/escalation-format.md` |
| 13 | M-7: researcher.md SecArch mode | `roles/researcher.md` |
| 14 | L-1: stale model slugs | `doc-reviewer/SKILL.md`, `plan-reviewer/SKILL.md` |
| 15 | L-2: SecArch model + Haiku ID | `roles/model-map.md` |
| 16 | L-8: undefined "Global Review" | `references/retrospective-protocol.md` |

Coverage gaps (H-5, M-6) and structural issues (L-3 through L-10) require new skill authoring — track separately.

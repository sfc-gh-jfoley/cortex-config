# Gate Inventory — Semantic View Toolkit

> **Machine-reviewable gate registry.** Every gate in this toolkit must appear here with exactly
> one classification. Skills reference gates by ID (e.g., `SV-VQR-MUTATE`).
>
> Classifications:
> - **AUTO_RESOLVE** — judgment/courtesy gate; resolved by documented default in AUTONOMOUS mode, logged `[AUTO-RESOLVED: <gate-id> → <default>]`
> - **AUTO_REMEDIATE** — deterministic fix exists; applied automatically in both modes
> - **TERMINATE** — true blocker; no operator decision can unblock it; workflow halts with `[BLOCKER: <gate-id>: <reason>]`
> - **OPERATOR_REQUIRED** — requires human decision regardless of mode; always pauses

---

## Mode Propagation

Mode is declared once at the router level (this SKILL.md) and passed to every sub-skill.
Sub-skills receive mode as inherited context and **must not re-prompt for mode selection**.

Propagation rule:
```
Router sets mode → sub-skill reads mode from session context → applies gate table below
```

If a sub-skill cannot determine mode from context, it defaults to INTERACTIVE.

---

## Logging Format

Every AUTO_RESOLVE resolution must emit exactly one log line:
```
[AUTO-RESOLVED: <gate-id> → <default>]  reason: <why this default is correct>
```

Every TERMINATE must emit:
```
[BLOCKER: <gate-id>: <human-readable reason>]
```

Every OPERATOR_REQUIRED gate that fires (in INTERACTIVE mode) must log the operator's decision:
```
[OPERATOR-DECISION: <gate-id> → <operator choice>]
```

---

## Gate Inventory

### SV Evaluation Gates

| Gate ID | Description | Classification | Default (AUTONOMOUS) |
|---|---|---|---|
| `EVAL-NO-PERMISSION` | Role lacks SELECT on SV or EXECUTE on evaluation procedure | **TERMINATE** | — |
| `EVAL-NO-VQR` | SV has zero verified queries; evaluation cannot proceed | **TERMINATE** | — |
| `EVAL-CONTAMINATED-VQR` | VQR baseline is contaminated (used as training signal) | **AUTO_RESOLVE** | Continue with contaminated VQRs as **read-only flagged references**; do not block run; log warning |
| `EVAL-COMPILE-ERROR-VQR` | VQR SQL fails to compile against current SV DDL | **AUTO_RESOLVE** | Exclude that VQR from the eval run; log `[AUTO-RESOLVED: EVAL-COMPILE-ERROR-VQR → excluded VQR <id>]`; do not block the whole run |
| `EVAL-METADATA-CREATE` | Need to create additive metadata table for eval history | **AUTO_REMEDIATE** | Execute `CREATE TABLE IF NOT EXISTS`; no prompt needed in any mode |
| `EVAL-ROLLBACK-CLONE` | Offer clone before replacing eval metadata table | **AUTO_RESOLVE** | In AUTONOMOUS: skip clone offer for `IF NOT EXISTS` additive creates; offer only for destructive replaces in INTERACTIVE |

### SV GEPA Optimizer Gates

| Gate ID | Description | Classification | Default (AUTONOMOUS) |
|---|---|---|---|
| `GEPA-CANDIDATE-DEPLOY` | Deploy validated candidate SV copy for evaluation | **AUTO_RESOLVE** | Deploy; log action |
| `GEPA-POP-REVIEW` | Review population matrix before candidate generation begins | **AUTO_RESOLVE** | Log population matrix and continue; `[AUTO-RESOLVED: GEPA-POP-REVIEW → proceed (population validated, autonomous mode)]` |
| `GEPA-PROD-SNAPSHOT` | Snapshot production SV DDL and materialization state before winner deployment | **AUTO_REMEDIATE** | Execute snapshot with timestamp **before** any production write; no prompt in either mode |
| `GEPA-PROD-OVERWRITE` | Apply winning candidate to production SV | **OPERATOR_REQUIRED** | Always pause in both modes; show diff; wait for explicit acceptance |
| `GEPA-CONVERGENCE-STOP` | Population converged — no further improvement expected | **AUTO_RESOLVE** | Terminate loop; report best candidate |
| `GEPA-FLOOR-REJECT` | Candidate below documented quality floor | **AUTO_RESOLVE** | Reject; log scores |
| `GEPA-CREATE-OR-ALTER` | Updating existing production SV while preserving materialization | **AUTO_REMEDIATE** | Use `CREATE OR ALTER SEMANTIC VIEW` to preserve MAX_STALENESS and materialization settings |

> **Sequencing defect corrected (GEPA):** The prior implementation gated disposable candidate
> deployment (correctly) but had no equivalent gate before production overwrite. Correct order is:
> 1. Deploy candidate to isolated copy (`AUTO_RESOLVE: GEPA-CANDIDATE-DEPLOY`)
> 2. Evaluate candidate score
> 3. If winner: snapshot production DDL/materialization (`AUTO_REMEDIATE: GEPA-PROD-SNAPSHOT`)
> 4. Present diff to operator and wait for acceptance (`OPERATOR_REQUIRED: GEPA-PROD-OVERWRITE`)
> 5. Only if accepted: apply to production

### VQR Gates

| Gate ID | Description | Classification | Default (AUTONOMOUS) |
|---|---|---|---|
| `SV-VQR-MUTATE` | Modify, delete, or rewrite an existing customer VQR | **OPERATOR_REQUIRED** | Permanently blocked; emit `[OPERATOR-REQUIRED: SV-VQR-MUTATE]`; present findings as read-only observations only |
| `VQR-GEN-VALID-SELECT` | Auto-select only VALID new candidates for insertion | **AUTO_RESOLVE** | Select VALID only; discard INVALID; hold NEEDS_FIX for review |
| `VQR-GEN-INSERT` | Insert new VQR candidates into an existing customer SV | **OPERATOR_REQUIRED** | Always pause; requires explicit mutation authorization from customer |
| `VQR-CURATOR-PHASE6` | Phase 6 customer approval of VQR activation/deactivation | **OPERATOR_REQUIRED** | Always pause; this gate is permanent and cannot be removed by any optimization pass |
| `VQR-CURATOR-ANALYSIS` | Auto-run activation/live-call analysis with cost logging | **AUTO_RESOLVE** | Run analysis; log costs; continue |

### SV Rearchitect Gates

| Gate ID | Description | Classification | Default (AUTONOMOUS) |
|---|---|---|---|
| `REARCH-HANDOFF-ACCEPT` | Accept non-mutating handoff plan | **AUTO_RESOLVE** | Accept and log in AUTONOMOUS mode; present for review in INTERACTIVE |

### SV Watch Gates

| Gate ID | Description | Classification | Default (AUTONOMOUS) |
|---|---|---|---|
| `WATCH-METADATA-SETUP` | Create watch log and scheduling metadata | **AUTO_REMEDIATE** | Execute `CREATE TABLE IF NOT EXISTS`; scheduled/cron mode is inherently AUTONOMOUS — never block on this |
| `WATCH-DRIFT-ALERT` | Schema drift detected requiring operator review | **AUTO_RESOLVE** | Log drift; continue scheduled run; emit summary for next human review |

### SV Audit Gates

| Gate ID | Description | Classification | Default (AUTONOMOUS) |
|---|---|---|---|
| `AUDIT-REGULATED-MODE` | Regulated-mode governance check flags a structural concern | **TERMINATE** | — |
| `AUDIT-FAN-CHASM` | Structural fan/chasm trap detected in relationship graph | **TERMINATE** | — |
| `AUDIT-PRIVILEGE-MISSING` | Role lacks required privileges to complete audit | **TERMINATE** | — |
| `AUDIT-RECOMMEND-APPLY` | Apply audit recommendations to SV | **AUTO_RESOLVE** | In AUTONOMOUS: apply only changes that are deterministic AND reversible (e.g., add missing FK annotation); log/defer structural changes that require judgment; do NOT apply all recommendations wholesale |

### Stateful Persistence Gates

| Gate ID | Description | Classification | Default (AUTONOMOUS) |
|---|---|---|---|
| `META-SCHEMA-CREATE` | Create `_SV_TOOLKIT_META` schema | **AUTO_REMEDIATE** | Execute `CREATE SCHEMA IF NOT EXISTS` (additive, idempotent) |
| `META-ROLLBACK-CLONE` | Offer rollback clone before creating metadata schema | **AUTO_RESOLVE** | Skip clone offer in AUTONOMOUS (metadata schema is additive, low risk); offer in INTERACTIVE if user requests |

---

## Permanent Exceptions

These gates are **hardcoded OPERATOR_REQUIRED** and cannot be overridden by any mode, configuration, or skill instruction:

1. **`SV-VQR-MUTATE`** — Mutation of any existing customer VQR. Skills may detect and report VQR health issues but must present findings as read-only observations only. Offering to fix, apply, or rewrite existing VQRs is forbidden.
2. **`VQR-GEN-INSERT`** — Insertion of new VQRs into an existing customer SV. Requires explicit mutation authorization.
3. **`VQR-CURATOR-PHASE6`** — Phase 6 customer approval gate in vqr-curator. This gate is permanent and must not be removed or bypassed by any optimization pass.
4. **`GEPA-PROD-OVERWRITE`** — Production SV overwrite. No autonomous system may apply a winning candidate without explicit operator acceptance of the diff.

---

## Deterministic-Default Requirements

For a gate to qualify as AUTO_RESOLVE, its default must satisfy all three:
1. **Documented** — the default appears in this inventory or the skill's decision table
2. **Deterministic** — same inputs always produce the same default; no ambiguity
3. **Reversible or read-only** — the action either reads state, creates additive metadata, or can be undone via the logged rollback path

If any condition is not met, the gate must be classified OPERATOR_REQUIRED.

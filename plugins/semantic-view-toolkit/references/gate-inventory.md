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
| `EVAL-COMPILE-ERROR-VQR` | VQR dry-run fails (compile error or untranslatable) | **AUTO_RESOLVE** | Do not exclude the VQR; run all VQRs, list the failures as REVIEW in the report, and stop if more than half fail |
| `EVAL-METADATA-CREATE` | Need to create additive metadata table for eval history | **AUTO_REMEDIATE** | Execute `CREATE TABLE IF NOT EXISTS`; no prompt needed in any mode |

### SV GEPA Optimizer Gates

GEPA works only on candidate copies (see `references/candidate-promotion.md`). It has no gate that writes to production; promotion uses `SV-PROMOTE`.

| Gate ID | Description | Classification | Default (AUTONOMOUS) |
|---|---|---|---|
| `GEPA-CANDIDATE-DEPLOY` | Deploy a validated candidate copy (named by `candidate.py`) for evaluation | **AUTO_RESOLVE** | Deploy with plain `CREATE SEMANTIC VIEW`; skip if the name exists; log action |
| `GEPA-POP-REVIEW` | Review population matrix before candidate generation begins | **AUTO_RESOLVE** | Log population matrix and continue; `[AUTO-RESOLVED: GEPA-POP-REVIEW → proceed (population validated, autonomous mode)]` |
| `GEPA-CONVERGENCE-STOP` | Population converged — no further improvement expected | **AUTO_RESOLVE** | Terminate loop; report best candidate |

### Candidate Promotion Gates

| Gate ID | Description | Classification | Default (AUTONOMOUS) |
|---|---|---|---|
| `SV-PROMOTE` | Move a candidate's changes into use: retarget consumers, replace production, keep or discard | **OPERATOR_REQUIRED** | Always pause in both modes; show DDL diff, evaluation evidence and consumers (stated as possibly incomplete); never choose for the operator |
| `SV-CANDIDATE-CLEANUP` | Drop candidate copies after a run | **OPERATOR_REQUIRED** | Run `candidate.py cleanup-plan`, show the exact `DROP` list, and wait; never drop by pattern; keep `winner` and `promoted` |

### VQR Gates

| Gate ID | Description | Classification | Default (AUTONOMOUS) |
|---|---|---|---|
| `SV-VQR-MUTATE` | Modify, delete, or rewrite an existing customer VQR | **OPERATOR_REQUIRED** | Always pause in both modes; show each VQR's current and proposed text; apply only the changes the operator approves, on a candidate copy, reaching production via `SV-PROMOTE`. Automated runs (optimizers, watch, AUTONOMOUS audit) never change a VQR |
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
| `AUDIT-PRIVILEGE-MISSING` | Role lacks required privileges to complete audit | **TERMINATE** | — |
| `AUDIT-RECOMMEND-APPLY` | Apply audit recommendations (to a candidate copy only; production via `SV-PROMOTE`) | **AUTO_RESOLVE** | In AUTONOMOUS: apply only changes that are deterministic AND reversible (e.g., add missing FK annotation); log/defer structural changes that require judgment; do NOT apply all recommendations wholesale |

### Stateful Persistence Gates

| Gate ID | Description | Classification | Default (AUTONOMOUS) |
|---|---|---|---|
| `META-SCHEMA-CREATE` | Create `_SV_TOOLKIT_META` schema | **AUTO_REMEDIATE** | Execute `CREATE SCHEMA IF NOT EXISTS` (additive, idempotent) |
| `META-ROLLBACK-CLONE` | Offer rollback clone before creating metadata schema | **AUTO_RESOLVE** | Skip clone offer in AUTONOMOUS (metadata schema is additive, low risk); offer in INTERACTIVE if user requests |

---

## Permanent Exceptions

These gates are **hardcoded OPERATOR_REQUIRED** and cannot be overridden by any mode, configuration, or skill instruction:

1. **`SV-VQR-MUTATE`** — Mutation of any existing customer VQR. Change an existing VQR only after the operator approves that specific change (current and proposed text shown side by side). Skills may detect issues and propose fixes; no skill applies one without that approval, and no automated run (optimizers, watch, AUTONOMOUS audit) changes a VQR at all.
2. **`VQR-GEN-INSERT`** — Insertion of new VQRs into an existing customer SV. Requires explicit mutation authorization.
3. **`VQR-CURATOR-PHASE6`** — Phase 6 customer approval gate in vqr-curator. This gate is permanent and must not be removed or bypassed by any optimization pass.
4. **`SV-PROMOTE`** — Any change to a production SV, from any skill. No autonomous system may apply a winning candidate without explicit operator acceptance of the diff.
5. **`SV-CANDIDATE-CLEANUP`** — Dropping candidate copies. Only the exact names in the run manifest, shown to the operator first.

---

## Deterministic-Default Requirements

For a gate to qualify as AUTO_RESOLVE, its default must satisfy all three:
1. **Documented** — the default appears in this inventory or the skill's decision table
2. **Deterministic** — same inputs always produce the same default; no ambiguity
3. **Reversible or read-only** — the action either reads state, creates additive metadata, or can be undone via the logged rollback path

If any condition is not met, the gate must be classified OPERATOR_REQUIRED.

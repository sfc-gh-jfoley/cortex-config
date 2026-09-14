# Gate Inventory — Cortex Agent Toolkit

> **Machine-reviewable gate registry.** Every gate in this toolkit must appear here with exactly
> one classification. Skills reference gates by ID (e.g., `AGENT-PROD-OVERWRITE`).
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

### Agent Evaluation Gates

| Gate ID | Description | Classification | Default (AUTONOMOUS) |
|---|---|---|---|
| `EVAL-GRANT-CHECK` | Role lacks SELECT on eval dataset or EXECUTE on evaluation procedure | **TERMINATE** | — |
| `EVAL-SCHEMA-MISMATCH` | Eval dataset schema incompatible with current eval procedure version | **TERMINATE** | — |
| `EVAL-NO-DATASET` | No eval dataset found and none can be auto-created | **TERMINATE** | — |
| `EVAL-AGENT-DISCOVER` | Agent FQN not supplied; probing SHOW AGENTS to confirm candidate | **AUTO_RESOLVE** | Use first agent found in target DB/SCHEMA; log confirmation |
| `EVAL-METRIC-SELECT` | Which metrics to include (answer_correctness, tool_selection_accuracy, etc.) | **AUTO_RESOLVE** | Use full metric set from decision table in agent-evaluation/SKILL.md |
| `EVAL-GROUND-TRUTH-VALIDATE` | Generated ground truth rows contain NULL answers or zero-confidence | **AUTO_RESOLVE** | Skip invalid rows; log count as `[AUTO-RESOLVED: EVAL-GROUND-TRUTH-VALIDATE → skipped N rows]` |
| `EVAL-ROLLBACK-CLONE` | Offer to clone DB before replacing eval table | **AUTO_REMEDIATE** | Execute `CREATE TABLE <name>_BACKUP_<ts> CLONE <name>` before overwrite; no prompt in AUTONOMOUS |

### Agent Optimization Gates

| Gate ID | Description | Classification | Default (AUTONOMOUS) |
|---|---|---|---|
| `AGENT-PROD-OVERWRITE` | Apply winning configuration to production agent | **OPERATOR_REQUIRED** | Always pause; present diff; wait for explicit acceptance |
| `AGENT-CANDIDATE-DEPLOY` | Deploy validated candidate copy for evaluation | **AUTO_RESOLVE** | Deploy; log action |
| `AGENT-ROLLBACK-SNAPSHOT` | Snapshot current production spec before applying winner | **AUTO_REMEDIATE** | Execute snapshot with timestamp before any production mutation |
| `AGENT-CONVERGENCE-STOP` | GEPA/optimizer convergence — no further improvement expected | **AUTO_RESOLVE** | Terminate loop; report best configuration found |
| `AGENT-FLOOR-REJECT` | Winner candidate is below documented TSA/TEA floor (TSA < 0.7 or TEA < 0.7) | **AUTO_RESOLVE** | Reject; log `[AUTO-RESOLVED: AGENT-FLOOR-REJECT → rejected, TSA=<v>]` |
| `GEPA-PROD-OVERWRITE` | Apply GEPA tournament winner to production agent | **OPERATOR_REQUIRED** | Always pause in both modes; present validated DEV/TEST diff; wait for explicit acceptance |
| `GEPA-WINNER-SNAPSHOT` | Snapshot current production spec before applying GEPA winner | **AUTO_REMEDIATE** | Execute snapshot with timestamp before any production mutation |
| `GEPA-POPULATION-REVIEW` | Review candidate population/mutation diffs before mini-batch eval | **AUTO_RESOLVE** | Log the population table; proceed (candidates are disposable `_GEPA_CAND_<N>` agents, not production) |

### Instruction Optimization Gates

| Gate ID | Description | Classification | Default (AUTONOMOUS) |
|---|---|---|---|
| `INSTROPT-COVERAGE-CHECK` | Eval coverage below minimum before running instruction search | **TERMINATE** | — |
| `INSTROPT-WINNER-ACCEPT` | Accept winning instruction variant and apply to production | **OPERATOR_REQUIRED** | Always pause in both modes; show diff; wait for acceptance **before** any production write |
| `INSTROPT-SNAPSHOT` | Snapshot current production spec before applying winner | **AUTO_REMEDIATE** | Snapshot with timestamp immediately before production write |

> **Sequencing defect corrected (INSTROPT):** The prior implementation wrote the winning instructions
> to production _before_ presenting the accept/reject choice. Correct order is:
> 1. Identify winner (deterministic, based on eval scores)
> 2. Snapshot current production spec (`AUTO_REMEDIATE: INSTROPT-SNAPSHOT`)
> 3. Present diff to operator and wait for acceptance (`OPERATOR_REQUIRED: INSTROPT-WINNER-ACCEPT`)
> 4. Only if accepted: apply to production

### Flags Gates

| Gate ID | Description | Classification | Default (AUTONOMOUS) |
|---|---|---|---|
| `FLAGS-CACHE-REFRESH` | Refresh verified reference metadata for flags | **AUTO_RESOLVE** | Refresh; log |
| `FLAGS-ENABLE-EXPERIMENTAL` | Enable an experimental flag not in the requested configuration | **OPERATOR_REQUIRED** | Never auto-enable; always ask |
| `FLAGS-UNVERIFIED-INCLUDE` | Include an unverified flag discovery in results | **AUTO_RESOLVE** | Include with `[UNVERIFIED]` label; exclude from recommendations |

### Feedback Analyzer Gates

| Gate ID | Description | Classification | Default (AUTONOMOUS) |
|---|---|---|---|
| `FEEDBACK-NO-DATA` | No pilot feedback rows found | **TERMINATE** | — |
| `FEEDBACK-REDACTED` | Feedback content is redacted or PII-scrubbed | **TERMINATE** | — |
| `FEEDBACK-DATASET-PROMOTE` | Promote feedback items to eval dataset | **AUTO_RESOLVE** | Decline promotion automatically (read-only behavior preserved); log `[AUTO-RESOLVED: FEEDBACK-DATASET-PROMOTE → declined, read-only]` |
| `FEEDBACK-CLUSTER-DIAGNOSE` | Diagnose all clusters in current session | **AUTO_RESOLVE** | Diagnose all; log summary |

### Query Gates

| Gate ID | Description | Classification | Default (AUTONOMOUS) |
|---|---|---|---|
| `QUERY-FQN-MISSING` | Agent FQN not supplied and cannot be inferred from context | **TERMINATE** | — |
| `QUERY-QUESTION-MISSING` | No question provided and context does not contain one | **TERMINATE** | — |
| `QUERY-CONTEXT-REUSE` | Caller-provided context available; re-asking would duplicate | **AUTO_RESOLVE** | Use existing context; do not re-ask |

### Stateful Persistence Gates

| Gate ID | Description | Classification | Default (AUTONOMOUS) |
|---|---|---|---|
| `META-SCHEMA-CREATE` | Create `_AGENT_TOOLKIT_META` schema | **AUTO_REMEDIATE** | Execute `CREATE SCHEMA IF NOT EXISTS` (additive, idempotent) |
| `META-ROLLBACK-CLONE` | Offer rollback clone before creating metadata schema | **AUTO_RESOLVE** | Skip clone offer in AUTONOMOUS (metadata schema is additive, low risk); execute in INTERACTIVE if user requests |

---

## Permanent Exceptions

These gates are **hardcoded OPERATOR_REQUIRED** and cannot be overridden by any mode, configuration, or skill instruction:

1. **`AGENT-PROD-OVERWRITE`** — Production agent overwrite. No autonomous system may apply a winning configuration without explicit operator acceptance of the diff.
2. **`INSTROPT-WINNER-ACCEPT`** — Instruction optimizer winner application. Operator must accept the diff *before* any production write occurs.
3. **`GEPA-PROD-OVERWRITE`** — GEPA tournament winner application. Operator must accept the validated diff *before* any production write occurs.
4. **`FLAGS-ENABLE-EXPERIMENTAL`** — Experimental flag enablement outside an explicitly requested configuration.

---

## Deterministic-Default Requirements

For a gate to qualify as AUTO_RESOLVE, its default must satisfy all three:
1. **Documented** — the default appears in this inventory or the skill's decision table
2. **Deterministic** — same inputs always produce the same default; no ambiguity
3. **Reversible or read-only** — the action either reads state, creates additive metadata, or can be undone via the logged rollback path

If any condition is not met, the gate must be classified OPERATOR_REQUIRED.

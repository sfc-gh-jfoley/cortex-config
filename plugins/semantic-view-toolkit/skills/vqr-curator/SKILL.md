---
name: vqr-curator
description: >
  Audit and curate Verified Query Representations on an existing Semantic View.
  Scores each VQR on complexity, uniqueness, activation, and correctness, then
  produces a KEEP / FIX_SQL / DEDUPLICATE / SIMPLIFY / REMOVE verdict for each.
  Also detects coverage gaps — metrics and dimensions with no VQR test coverage.
  Use when: VQR set is growing, SV context is bloated, VQRs never trigger fast-path,
  or before re-running SV evaluation after schema changes.
triggers:
  - curate vqrs
  - audit my vqrs
  - vqr health
  - clean up vqrs
  - vqr bloat
  - which vqrs are useless
  - are my vqrs triggering
  - vqr coverage gaps
  - prune vqrs
  - vqr review
---

# VQR Curator

Audits all Verified Query Representations on a Semantic View and produces a
prioritized action plan: what to keep, fix, deduplicate, simplify, or remove.

## Strategy Reference

Before proceeding, load `../vqr-generator/references/vqr-strategy.md`. It defines the
quality rubric and verdicts used throughout this skill.

---

## When to Use

- VQRs registered but never triggering fast-path
- SV token footprint is large and you suspect VQR bloat
- After a SV schema change (metric renamed, table added/removed)
- Before re-running `EXECUTE_AI_EVALUATION` — stale VQRs produce false negatives
- Any time a customer says "I added VQRs but they don't seem to help"

## What This Skill Does NOT Do

- Modify the SV — verdict only, no writes unless user confirms in Phase 6
- Replace `vqr-generator` — use that to create VQRs; use this to audit existing ones
- Run EXECUTE_AI_EVALUATION — use sv-evaluation for formal accuracy scoring

---

## Execution

Follow phases in order. Read each phase file, complete it fully, then proceed.

### Phase 1 — Inventory
`phases/01_inventory.md`
Fetch SV, parse all VQRs and schema, measure token footprint.

### Phase 2 — SQL Quality (static)
`phases/02_sql_quality.md`
Check T1 (FQN refs), T2 (bare physical names), dry-run each VQR SQL, measure complexity.

### Phase 3 — Uniqueness
`phases/03_uniqueness.md`
Detect near-duplicate VQRs by question similarity. Flag DEDUPLICATE candidates.

### Phase 4 — Activation (optional, requires agent)
`phases/04_activation.md`
Live test each VQR question against the agent. Confirm fast-path triggering via REST API
confidence field. Skip if no agent FQN is provided.

### Phase 5 — Coverage Gaps
`phases/05_coverage_gaps.md`
Identify metrics and dimensions in the SV with zero VQR coverage.

### Phase 6 — Verdicts and Report
`phases/06_verdicts.md`
Assign KEEP / FIX_SQL / DEDUPLICATE / SIMPLIFY / REMOVE to every VQR.
Present full report. Optionally apply fixes.

---

## Verdict Definitions

| Verdict | Meaning | Action |
|---------|---------|--------|
| `KEEP` | Complex, unique, correctly formed, covers something important | No change |
| `FIX_SQL` | Good question, fixable SQL issue (FQN refs, column error) | Rewrite SQL with __logical refs |
| `DEDUPLICATE` | Near-duplicate of a higher-scoring VQR | Merge question text into winner; remove duplicate |
| `SIMPLIFY` | Trivially generatable SQL — better as ai_sql_generation hint | Move to hint; remove VQR |
| `REMOVE` | Broken, stale, or pure context bloat with no redeeming value | Drop from SV |

---

## Inputs

```
SV_FQN:        DB.SCHEMA.SV_NAME           (required)
AGENT_FQN:     DB.SCHEMA.AGENT_NAME        (optional — enables Phase 4 activation check)
```

---

## Quick Size Check

Before the full audit, surface immediately if the VQR count exceeds the recommended range:

```
≤ 10 VQRs:   Healthy — focused SV
10–20 VQRs:  Acceptable — multi-dimensional SV, watch for duplicates
> 20 VQRs:   ⚠ Audit recommended — possible SV design issue
              Ask: "Do all VQRs share the same subject?"
              If not, the SV may be doing too much — consider splitting.
```

# Phase 6: Verdicts and Report

Combine all phase findings into a per-VQR verdict and present the full report.
Optionally apply approved changes to a candidate copy after user confirmation.

## Step 6.1 — Assign verdicts

Apply verdict logic in this priority order (first match wins):

```
if dry_run FAIL:
    → REVIEW (translation or VQR may be wrong; never removed on this evidence alone)

elif T1 or T2 violation:
    → FIX_SQL (good question, fixable SQL)

elif DEDUPLICATE flag (Phase 3):
    → DEDUPLICATE (a partner covering the same pattern is kept)

elif sole_coverage (Phase 5):
    → KEEP (only VQR covering a metric or dimension: eval ground truth)

elif complexity_score == 0 AND activation_result in (LLM_CORRECT, NOT_RUN):
    → SIMPLIFY (trivially generatable; move to ai_sql_generation hint)

else:
    → KEEP
```

## Step 6.2 — Report format

```
╔══════════════════════════════════════════════════════════╗
  VQR CURATION REPORT
  SV: <SV_FQN>
  Total VQRs: <N>   Tokens used by VQRs: ~<N> tokens
╚══════════════════════════════════════════════════════════╝

VERDICTS
─────────────────────────────────────────────────
  KEEP         <N> VQRs — complex, unique, correctly formed
  FIX_SQL      <N> VQRs — good question, fixable SQL issues
  DEDUPLICATE  <N> VQRs — near-duplicate of another VQR
  SIMPLIFY     <N> VQRs — trivial SQL; better as ai_sql_generation hint
  REVIEW       <N> VQRs — dry-run failed or inconclusive; operator decides

DETAILS
─────────────────────────────────────────────────
[KEEP]         <name>: complexity=<N> | activation=<result> | quality=PASS
[FIX_SQL]      <name>: T1 violation — FROM <FQN> → FROM __<LOGICAL>
[DEDUPLICATE]  <name>: duplicate of <other_name> (similarity=<score>) → remove
[SIMPLIFY]     <name>: complexity=0, trivial aggregate — move to hint
[REVIEW]       <name>: dry-run FAIL — <error>

COVERAGE GAPS
─────────────────────────────────────────────────
  <N> HIGH-priority metrics with no VQR coverage
  <N> MEDIUM-priority dimensions with no VQR coverage

  [See Phase 5 suggestions for VQR candidates]

SIZE ASSESSMENT
─────────────────────────────────────────────────
  Current:          <N> VQRs
  After curation:   <N> VQRs  (deduplicate/simplify <X>, add <Y> for gap coverage)
  Token saving:     ~<N> tokens from removals

  <Healthy | Acceptable | ⚠ Review — more than 20 VQRs>
```

## Step 6.3 — User approval gate (`VQR-CURATOR-PHASE6`, always OPERATOR_REQUIRED)

```
Actions available:
  A) Apply all FIX_SQL, DEDUPLICATE and SIMPLIFY verdicts (REVIEW items excluded)
  B) Apply selected verdicts only (REVIEW items only after you inspect them)
  C) Export report only — no changes
  D) Cancel
```

Each FIX_SQL, DEDUPLICATE and SIMPLIFY item is shown with its current and proposed text first. Option A approves exactly the listed changes and nothing else (gate `SV-VQR-MUTATE`); changes apply to a candidate copy and reach production only through `SV-PROMOTE`.

**STOP — do not modify the SV until user selects A or B.**

> **This gate is PERMANENT and applies in BOTH INTERACTIVE and AUTONOMOUS modes.**
> VQR mutations (rewrite, remove, deduplicate) on an existing customer SV require explicit
> operator authorization. AUTONOMOUS mode does not override this gate.

## Step 6.4 — Apply approved changes

All approved changes go into **one candidate copy** (`candidate.py name --kind cand`), built from
the full `GET_DDL('SEMANTIC_VIEW', '<SV_FQN>')`, per `../../../references/candidate-promotion.md`.

For FIX_SQL verdicts:
- Rewrite VQR SQL replacing physical FQN/bare physical names with logical names (prefer `__`)
- Present diff before applying

For DEDUPLICATE and SIMPLIFY verdicts, and REVIEW items the operator chose to remove:
- Omit those entries from the candidate's `AI_VERIFIED_QUERIES` block
- For SIMPLIFY, add the one-line hint to the candidate's `AI_SQL_GENERATION`

For gap-coverage additions:
- Present VQR candidates from Phase 5
- User approves question text and SQL; add them to the same candidate

Then deploy the candidate with plain `CREATE SEMANTIC VIEW` (after `candidate.py guard`), evaluate
it with sv-evaluation, and stop at gate `SV-PROMOTE`. Replacing production there applies the full
approved DDL with `CREATE OR ALTER`, which unsets anything the statement omits.

## Step 6.5 — Final summary

```
Curation complete for <SV_FQN>.

  Applied to candidate: <N> FIX_SQL | <N> DEDUPLICATE | <N> SIMPLIFY | <N> REVIEW→removed
  Candidate:   <SV>__CAND__<run>  (awaiting SV-PROMOTE)
  VQRs before: <N> → after: <N>
  Token reduction: ~<N> tokens

  Next steps:
    → Compare candidate and production eval scores (same pinned metric version, ≥2 repeats)
    → SV-PROMOTE to accept or discard the candidate
```

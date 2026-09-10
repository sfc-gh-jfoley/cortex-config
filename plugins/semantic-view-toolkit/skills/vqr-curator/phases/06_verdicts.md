# Phase 6: Verdicts and Report

Combine all phase findings into a per-VQR verdict and present the full report.
Optionally apply fixes (rewrite VQR SQL) after user confirmation.

## Step 6.1 — Assign verdicts

Apply verdict logic in this priority order (first match wins):

```
if T1 or T2 violation AND dry_run FAIL:
    → REMOVE (broken and incorrectly formed)

elif T1 or T2 violation:
    → FIX_SQL (good question, fixable SQL)

elif dry_run FAIL:
    → REMOVE (broken SQL, likely stale after schema change)

elif DEDUPLICATE flag:
    → DEDUPLICATE (keep higher-scoring partner, remove this one)

elif complexity_score == 0 AND activation_result == LLM_SV_CORRECT:
    → SIMPLIFY (trivially generatable; move to ai_sql_generation hint)

elif complexity_score == 0 AND no_eval_coverage_partner:
    → SIMPLIFY (low value, no unique eval role)

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
  REMOVE       <N> VQRs — broken, stale, or pure bloat

DETAILS
─────────────────────────────────────────────────
[KEEP]         <name>: complexity=<N> | activation=<result> | quality=PASS
[FIX_SQL]      <name>: T1 violation — FROM <FQN> → FROM __<LOGICAL>
[DEDUPLICATE]  <name>: duplicate of <other_name> (similarity=<score>) → remove
[SIMPLIFY]     <name>: complexity=0, trivial aggregate — move to hint
[REMOVE]       <name>: dry-run FAIL — <error>

COVERAGE GAPS
─────────────────────────────────────────────────
  <N> HIGH-priority metrics with no VQR coverage
  <N> MEDIUM-priority dimensions with no VQR coverage

  [See Phase 5 suggestions for VQR candidates]

SIZE ASSESSMENT
─────────────────────────────────────────────────
  Current:          <N> VQRs
  After curation:   <N> VQRs  (remove <X>, add <Y> for gap coverage)
  Token saving:     ~<N> tokens from removals

  <Healthy | Acceptable | ⚠ Run sv-audit — VQR count suggests SV scope review>
```

## Step 6.3 — User approval gate

```
Actions available:
  A) Apply all FIX_SQL rewrites + REMOVE verdicts   (recommended)
  B) Apply selected verdicts only
  C) Export report only — no changes
  D) Cancel
```

**STOP — do not modify the SV until user selects A or B.**

## Step 6.4 — Apply approved changes

For FIX_SQL verdicts:
- Rewrite VQR SQL replacing FQN/bare physical names with `__logical_name`
- Present diff before applying

For REMOVE and DEDUPLICATE verdicts:
- Generate updated `CREATE OR REPLACE SEMANTIC VIEW` DDL with those VQRs omitted
- Hand off to sv-ddl for execution

For SIMPLIFY verdicts:
- Extract the SQL pattern as a one-line `ai_sql_generation` hint
- Present the hint text; user adds it to the SV manually or via sv-ddl

For gap-coverage additions:
- Present VQR candidates from Phase 5
- User approves question text and SQL
- Add to the CREATE OR REPLACE DDL

## Step 6.5 — Final summary

```
Curation complete for <SV_FQN>.

  Applied:     <N> FIX_SQL | <N> REMOVE | <N> DEDUPLICATE | <N> SIMPLIFY
  VQRs before: <N> → after: <N>
  Token reduction: ~<N> tokens

  Next steps:
    → Run sv-audit if VQR count was >20 (check SV scope)
    → Re-run sv-evaluation after changes to verify accuracy impact
    → Run vqr-curator again in 30 days as VQR set evolves
```

# Phase 2: SQL Quality (static)

Score each VQR on SQL correctness and complexity without invoking Cortex Analyst.

Store findings per VQR in `SQL_QUALITY[vqr_name]`.

Table-reference severities follow Check 1 in `../../../references/vqr-eval-health.md`: physical
FQN = HIGH, bare physical name = HIGH, bare *logical* name = LOW style finding (not T2).

## Step 2.1 — T1: FQN table references (HIGH)

For each VQR SQL, scan for patterns matching `WORD.WORD.WORD` in FROM/JOIN position
and cross-reference against `SV_SCHEMA.tables[*].physical_fqn`.

```
[T1 FAIL] VQR "<name>": FQN reference found: <DB.SCHEMA.TABLE>
          Fix: replace with __<LOGICAL_NAME>
```

## Step 2.2 — T2: Bare physical table names (HIGH)

Scan FROM/JOIN clauses for identifiers matching a physical table name that is not also a logical
table name (excluding CTE names defined within the same VQR).

```
[T2 FAIL] VQR "<name>": bare physical table name: <TABLE>
          Fix: replace with __<LOGICAL_NAME>
```

## Step 2.3 — Dry-run (MEDIUM)

Run the shared "VQR Dry-Run" procedure in `../../../references/vqr-eval-health.md`. It maps both
logical tables and logical columns to physical ones via DESCRIBE before compiling. A `FAIL` means
the translation or the VQR needs a look; it is never evidence for removal on its own.

```
[DRY_RUN FAIL] VQR "<name>": compile error or untranslatable name: <error_message>
[DRY_RUN PASS] VQR "<name>": compiles OK
[DRY_RUN EMPTY] VQR "<name>": no rows returned (check time window / data availability)
```

## Step 2.4 — Complexity score

For each VQR SQL, compute `complexity_score` (0-3):

| Pattern | Score contribution |
|---------|-------------------|
| Multi-table JOIN | +1 |
| Window or ordered-set function (`PERCENTILE_CONT`, `ROW_NUMBER`, `RANK`, `LAG`, `LEAD`) | +1 |
| Self-join or CTE | +1 |
| `EXTRACT(...)` | +1 |
| `COUNT(DISTINCT ...)` | +0.5 |

Clamp to 0-3.

```
complexity_score = 0: trivial — usually generated correctly
complexity_score = 1: moderate — LLM usually correct but occasionally wrong
complexity_score = 2-3: complex — VQR anchors critical pattern
```

Record `complexity_score` per VQR. VQRs scoring 0 are SIMPLIFY candidates.

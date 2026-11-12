# VQR and Eval Health Checks

Pre-flight and post-eval checks that catch every known category of silent eval failure.
Run **Checks 1–8** before launching any evaluation. Use **Patterns A–C** when diagnosing poor results.

---

## Severity Legend

| Severity | Meaning |
|---|---|
| CRITICAL | Eval will score 0 or produce misleading results. Block launch. |
| HIGH | Many VQRs will fail before scoring. Fix before launching. |
| MEDIUM | Some VQRs will score incorrectly. Warn user, offer choice. |
| LOW | Informational — quality degradation, not a hard failure. |

---

## Pre-Flight Checks (run before launching eval)

---

### Check 1 — VQR table reference format  `[HIGH for FQN, LOW for bare logical]`

**What it catches:**
- **Physical FQN references** (`DB.SCHEMA.TABLE`) — `HIGH`. VQR SQL must reference the SV's
  logical tables, not the physical tables behind them.
- **Bare logical table names** (`FROM orders`) — `LOW`, style only. The YAML verified-query docs
  prefix logical tables with `__` "to avoid name conflicts" (`FROM __sales_data`); the
  `CREATE SEMANTIC VIEW` `AI_VERIFIED_QUERIES` example uses the bare logical name
  (`FROM orders AS o`). Prefer `__` for new VQRs; do not treat bare logical names as broken.

**Detection:**
```python
import re

def check_vqr_table_refs(vqr_sql, sv_table_map):
    """
    sv_table_map: dict of {physical_fqn: logical_alias}
    built from DESCRIBE SEMANTIC VIEW:
      object_kind='TABLE', property in ('BASE_TABLE_DATABASE_NAME',
      'BASE_TABLE_SCHEMA_NAME', 'BASE_TABLE_NAME')
    Returns (severity, message) tuples. Unquoted identifiers only.
    """
    issues = []
    for fqn, alias in sv_table_map.items():
        # FQN reference (DB.SCHEMA.TABLE) — HIGH
        if re.search(rf'\b{re.escape(fqn)}\b', vqr_sql, re.IGNORECASE):
            issues.append(("HIGH", f"FQN reference: {fqn} → use __{alias}"))
        # Bare logical name in FROM/JOIN position (any occurrence, even if __alias also appears) — LOW
        if re.search(rf'\b(?:FROM|JOIN)\s+{re.escape(alias)}\b', vqr_sql, re.IGNORECASE):
            issues.append(("LOW", f"Bare logical name: {alias} → prefer __{alias}"))
    return issues
```

**Fix:** Replace physical FQN and bare logical table references with `__<logical_alias>` (the `name:` field defined for that table in the semantic view). Column names stay plain.

---

### Check 2 — VQR column existence  `[HIGH]`

**What it catches:** VQR SQL referencing column names that don't exist in the SV schema. Common
when the SV uses a different logical name than the physical column (`TABLE.logical AS physical`).
The left side of `AS` is the logical name exposed by the semantic view; the right side is the
physical column or expression.

> ⚠️ **Do NOT blanket-replace logical column names with physical expressions.** VQR SQL should
> reference the logical names exposed by the semantic view (the names defined in DIMENSIONS,
> FACTS, and METRICS clauses). Physical column names may not match logical names when aliases
> or computed expressions are used. Validate VQR identifiers against the SV's DESCRIBE output
> (`"object_name"` values), not against the underlying table's physical columns.

**Dimension syntax reminder:**
```sql
-- <table_alias>.<logical_name> AS <physical_expr>
orders.order_status AS o_orderstatus   -- use order_status in VQR SQL, not o_orderstatus
```

**Detection:**
```sql
-- Capture the DESCRIBE query ID with `SET describe_qid = LAST_QUERY_ID();` immediately after
-- DESCRIBE, then use `$describe_qid` in all subsequent RESULT_SCAN calls.
-- Get all logical identifiers and their backing expressions from DESCRIBE:
SELECT "object_name" AS logical_name, "property_value" AS physical_expr
FROM TABLE(RESULT_SCAN($describe_qid))
WHERE "object_kind" IN ('DIMENSION', 'FACT', 'METRIC')
  AND "property" = 'EXPRESSION';
-- Then check each VQR's column references against the logical_name list
```

**Fix:** Keep VQR SQL aligned to the semantic view's logical names, and use the DESCRIBE
EXPRESSION rows only to understand what each logical field maps to underneath.

---

### Check 3 — CA extension presence and column completeness  `[CRITICAL]`

**What it catches:** SVs built through the Snowsight UI contain a `with extension (CA='...')` block.
The eval framework uses the CA extension's declared column list when constructing ground-truth CTEs.
Any column in VQR SQL that is **not** in the CA extension's column list is silently dropped from the
CTE, causing `invalid identifier` errors in the reference SQL before any model comparison happens.

Verify before relying on this: the column-drop behavior is observed, not documented. If Pattern A
appears, run the eval against a DDL-only candidate copy.

**Detection:**
```python
ddl = cursor.execute(
    "SELECT GET_DDL('SEMANTIC VIEW', ?)", (sv_fqn,)
).fetchone()[0]
has_ca_extension = 'with extension' in ddl.lower()
```

```sql
-- SQL-only detection:
SELECT
    CASE
        WHEN REGEXP_INSTR(
            LOWER(GET_DDL('SEMANTIC VIEW', '<db>.<schema>.<sv_name>')),
            'with extension'
        ) > 0 THEN 'CA_EXTENSION_PRESENT'
        ELSE 'CLEAN'
    END AS ca_extension_status;
```

**Remediation — create a DDL-only candidate copy (recommended).** Follow
[candidate-promotion.md](candidate-promotion.md): the copy is a `--kind cand` candidate, created
with plain `CREATE SEMANTIC VIEW` via `candidate.py rewrite-ddl`, registered in the run manifest and
dropped only through `SV-CANDIDATE-CLEANUP`.

> **Identifier handling.** The `GET_DDL` argument is a string literal, so bind it
> rather than interpolating. Identifiers inside DDL text (`CREATE`, `DROP`) cannot
> be bound — validate them first and emit them quoted. See the security note below.

```python
import re

IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_$]*$")

def validate_fqn(fqn):
    """Reject anything that is not three plain identifiers. Returns (parts, quoted)."""
    parts = fqn.split(".")
    if len(parts) != 3 or not all(IDENT.match(p) for p in parts):
        raise ValueError(f"unsafe or malformed FQN: {fqn!r}")
    return parts, ".".join(f'"{p}"' for p in parts)

sv_fqn = "<db>.<schema>.<sv_name>"
(db, schema, sv_name), sv_quoted = validate_fqn(sv_fqn)

# 1. Get DDL — bound parameter, no interpolation
ddl = cursor.execute(
    "SELECT GET_DDL('SEMANTIC VIEW', ?)", (sv_fqn,)
).fetchone()[0]

CLAUSES = r"\b(TABLES|RELATIONSHIPS|FACTS|DIMENSIONS|METRICS|AI_VERIFIED_QUERIES|AI_SQL_GENERATION)\s*[(']"
before = len(re.findall(CLAUSES, ddl, re.IGNORECASE))

# 2. Strip CA extension block.
#    Greedy .* anchored on the JSON envelope {...}: a non-greedy .*? terminates at
#    the first ') inside the CA payload, truncating the strip and leaving remnants
#    that reproduce the very 'invalid identifier' failure this check prevents.
ddl_clean = re.sub(
    r"\s*with extension\s*\(CA='\{.*\}'\)",
    "",
    ddl,
    flags=re.DOTALL
)

# 3. Fail loudly rather than deploying a partially-stripped copy
if "with extension" in ddl_clean.lower():
    raise RuntimeError(
        "CA extension still present after strip — inspect the DDL manually. "
        "Likely multiple extension blocks or an unexpected payload shape."
    )
# The greedy strip can over-delete if a later VQR or comment contains "}')".
if len(re.findall(CLAUSES, ddl_clean, re.IGNORECASE)) != before:
    raise RuntimeError("Strip removed DDL clauses beyond the CA extension; inspect manually.")
open("ddl_clean.sql", "w").write(ddl_clean)
```

```bash
# 4. Name and create the candidate (plain CREATE; stop if the name exists)
CAND=$(python3 scripts/candidate.py name --source "$SV_FQN" --kind cand --run "$RUN" | jq -r .candidate)
python3 scripts/candidate.py rewrite-ddl --source "$SV_FQN" --candidate "$CAND" < ddl_clean.sql > cand.sql
python3 scripts/candidate.py register manifest.json --run "$RUN" --source "$SV_FQN" --candidate "$CAND" --ddl-file cand.sql
# deploy cand.sql, evaluate against $CAND, then run cleanup-plan
```

Note that the whole-DDL `ddl.replace('""', '"')` unescape is deliberately absent
here: the strip path discards the CA block, so nothing in it needs unescaping.
Unescape only the extracted CA JSON, in the secondary check below.

**Secondary check — CA extension column completeness:**
```python
import json, re

# Extract CA extension JSON.
# Greedy .* anchored on the {...} envelope — a non-greedy .*? stops at the first
# ') inside the payload and yields truncated, unparseable JSON.
ext_match = re.search(r"with extension \(CA='(\{.*\})'\)", ddl, re.DOTALL)
if ext_match:
    # Unescape here only — scoped to the CA payload, not the whole DDL
    ca_payload = ext_match.group(1).replace('""', '"')
    try:
        ca_json = json.loads(ca_payload)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"CA extension payload did not parse ({e}). The block may contain "
            "an unexpected shape — inspect it before trusting this check."
        )
    ca_columns = {col['name'] for col in ca_json.get('columns', [])}

    # Parse column references from each VQR SQL (SV_VQRS from DESCRIBE).
    # Heuristic: uppercase tokens only; KNOWN_SQL_KEYWORDS is a caller-supplied set.
    for vqr in vqr_list:
        words = set(re.findall(r'\b[A-Z_][A-Z0-9_]{2,}\b', vqr['sql']))
        missing = words - ca_columns - KNOWN_SQL_KEYWORDS
        if missing:
            print(f"VQR '{vqr['name']}': columns possibly not in CA extension: {missing}")
```

> **Security note — identifiers in DDL.** `GET_DDL`'s argument is a string literal
> and should be passed as a bound parameter. Identifiers embedded in DDL text
> (`CREATE SEMANTIC VIEW`, `DROP SEMANTIC VIEW`) cannot be bound, so any name reaching
> them must be validated first — `validate_fqn()` above, or `candidate.py`, which
> rejects anything but plain identifiers. Do not f-string an unvalidated name into DDL.

---

### Check 4 — GROUP BY alias  `[MEDIUM]`

**What it catches:** VQR SQL using a SELECT alias in the GROUP BY clause. The eval framework
rewrites VQR SQL using CTEs. GROUP BY alias references break after CTE expansion.

**Detection:**
```python
import re

def check_group_by_alias(sql):
    # Extract SELECT aliases
    select_aliases = re.findall(r'\bAS\s+(\w+)', sql, re.IGNORECASE)
    # Extract GROUP BY terms
    group_by_match = re.search(r'GROUP\s+BY\s+(.*?)(?:ORDER|LIMIT|HAVING|$)', sql,
                                re.IGNORECASE | re.DOTALL)
    if not group_by_match:
        return []
    group_by_cols = [c.strip() for c in group_by_match.group(1).split(',')]
    return [col for col in group_by_cols if col in select_aliases]
```

**Fix:** Replace the alias in GROUP BY with the full expression:
```sql
-- BAD:
SELECT DATE_TRUNC('month', O_ORDERDATE) AS order_month, SUM(amount) AS rev
FROM __orders
GROUP BY order_month

-- GOOD:
SELECT DATE_TRUNC('month', O_ORDERDATE) AS order_month, SUM(amount) AS rev
FROM __orders
GROUP BY DATE_TRUNC('month', O_ORDERDATE)
```

---

### Check 5 — Metric coverage gaps  `[MEDIUM]`

**What it catches:** SV metrics that have no VQR. A metric with no VQR has zero eval signal —
if the model generates wrong SQL for it, you'll never know.

**Detection:**
```sql
-- Get all metrics from DESCRIBE
SELECT DISTINCT "object_name" AS metric_name, "parent_entity" AS table_name
FROM TABLE(RESULT_SCAN($describe_qid))
WHERE "object_kind" = 'METRIC' AND "property" = 'EXPRESSION';
```

Cross-reference against VQR SQL to find metrics not mentioned in any VQR.

**Fix:** Route to `vqr-generator` to create VQRs for uncovered metrics.

---

### Check 6 — Table and dimension coverage  `[LOW]`

**What it catches:** Entire tables or dimension groups never exercised by any VQR. Low eval
coverage means the SV may have structural gaps that only appear in production.

**Detection:**
```sql
SELECT DISTINCT "object_name" AS table_name
FROM TABLE(RESULT_SCAN($describe_qid))
WHERE "object_kind" = 'TABLE';
-- Cross-reference against VQR SQL to find tables not referenced in any VQR
```

**Fix:** Add at least one VQR per table — a simple aggregate question is sufficient for coverage.

---

### Check 7 — Aggregation mismatch  `[HIGH]`

**What it catches:** VQR SQL using a different aggregation than the SV metric definition.
Example: SV metric is `AVG(price)`, VQR computes `SUM(price)` — scores 0 every time regardless
of model quality.

**Detection:**
```sql
-- Get metric expressions from DESCRIBE
SELECT "object_name" AS metric_name, "property_value" AS metric_expr
FROM TABLE(RESULT_SCAN($describe_qid))
WHERE "object_kind" = 'METRIC' AND "property" = 'EXPRESSION';
```

For each VQR that aggregates a metric's source column, compare the aggregation function against
the metric's EXPRESSION. Flag mismatches.

**Fix:** Align the VQR aggregation with the SV metric definition, or if the VQR intentionally
uses a different aggregation, add a note explaining the deviation.

---

### Check 8 — Subquery SQL in VQRs  `[MEDIUM, unverified heuristic]`

**What it catches:** VQR SQL containing nested subqueries (`WHERE col IN (SELECT ...)`,
`WHERE EXISTS (SELECT ...)`, scalar subqueries, derived tables). The concern is that Cortex
Analyst may rarely generate SQL of that shape, so such a VQR scores poorly regardless of SV
quality. No Snowflake documentation states this limitation; treat it as a heuristic and confirm
with eval results before rewriting. **CTEs (`WITH x AS (SELECT ...)`) and top-level `UNION` are
exempt** — they are not nested subqueries.

**Detection:**
```python
import re

NESTED_SELECT = re.compile(r'\(\s*SELECT\b', re.IGNORECASE)
CTE_BODY = re.compile(r'\bAS\s*\(\s*SELECT\b', re.IGNORECASE)

def check_vqr_subqueries(vqr_list):
    """Detect nested subqueries; CTE bodies and top-level UNION are exempt."""
    issues = []
    for vqr in vqr_list:
        sql = vqr['sql']
        nested = len(NESTED_SELECT.findall(sql)) - len(CTE_BODY.findall(sql))
        if nested > 0:
            issues.append({
                'vqr': vqr['name'],
                'issue': 'contains nested subquery (unverified heuristic: Analyst may not generate this shape)',
                'fix': 'rewrite without subquery, or add the filtering table as an SV relationship'
            })
    return issues
```

**Fix:** Two options depending on intent:
- **For Analyst use**: Add the filtering table as an SV relationship. Rewrite the VQR SQL without
  the subquery, expressing the filter as a dimension-based WHERE condition Analyst can generate.
- **For programmatic-only filtering**: Flag the VQR for operator review (any removal goes through
  the VQR gates). Subquery filtering is valid at query time for manual consumers.

> Note: Subqueries in SV queries are fully supported by Snowflake at runtime (WHERE clause and
> DIMENSIONS ad-hoc expressions). This check targets VQR SQL only — it does not prohibit subquery
> use in manually authored queries against the SV.

---

## VQR Dry-Run (shared procedure)

VQR SQL references logical tables and columns, so it cannot run against the base tables as written.
Used by vqr-generator Phase 4 and vqr-curator Phase 2.

1. From `DESCRIBE SEMANTIC VIEW`, build two maps:
   - logical table → physical FQN (`BASE_TABLE_DATABASE_NAME.BASE_TABLE_SCHEMA_NAME.BASE_TABLE_NAME`),
     or `(<DEFINITION>)` for a query-defined table;
   - `<table>.<dimension or fact>` → its `EXPRESSION`.
2. Rewrite the VQR: replace `__t`, bare `t`, or the logical table name in FROM/JOIN with the
   physical FQN (keep the alias), and replace each logical column reference with `(<EXPRESSION>)`.
   If an expression references another logical field, expand it the same way.
3. If any name cannot be resolved, the result is **UNTRANSLATABLE**.
4. Run `EXPLAIN <translated SQL>` (compile only), then
   `SELECT COUNT(*) FROM (<translated SQL>)` with no `LIMIT 0`.

| Outcome | Result | Meaning |
|---|---|---|
| Compiles and returns ≥1 row | `PASS` | |
| Compiles, 0 rows | `EMPTY` | Check date literals and filters |
| Compile error or UNTRANSLATABLE | `FAIL` | The translation or the VQR may be wrong. **Route to REVIEW; never remove a VQR on a dry-run failure alone.** |

---

## Pre-Flight Summary Report

After running Checks 1–8, report:

```
VQR Health Report
═════════════════
  Semantic view:   <DB>.<SCHEMA>.<SV_NAME>
  VQRs checked:    <N>
  CA extension:    PRESENT / CLEAN

  CRITICAL:  <N> issues  (Check 3: CA extension)
  HIGH:      <N> issues  (Checks 1 FQN, 2, 7)
  MEDIUM:    <N> issues  (Checks 4, 5, 8)
  LOW:       <N> issues  (Checks 1 bare-logical, 6)

  Recommendation:
    → CRITICAL found: create DDL-only eval copy before launching
    → HIGH found: fix VQR SQL issues before launching
    → MEDIUM/LOW only: proceed with noted caveats
```

---

## Post-Eval Failure Diagnosis

Run these when eval scores are lower than expected or many VQRs failed before scoring.

---

### Pattern A — CA extension column-drop  `[CRITICAL]`

**Signal:** Many `invalid identifier` errors in ground-truth SQL execution. Near-zero mean score
across all VQRs. SV has CA extension (Check 3 would have flagged this pre-flight).

**Confirm:**
```sql
-- Check error messages from eval results
-- `GET_ANALYST_AI_EVALUATION_DATA` is the source of runtime errors for each VQR in a named eval run.
```

> ⚠️ VQR runtime errors are not visible in DESCRIBE output. Use the evaluation result function
> `GET_ANALYST_AI_EVALUATION_DATA` to retrieve the ERROR column for each VQR in a named eval run.

If errors cluster on `invalid identifier`, and the SV has a CA extension: this is the CA
extension column-drop. See Check 3 remediation — create a DDL-only candidate copy and rerun.
Asymmetric pre-scoring failure rates between VQR styles here reflect which columns each VQR
referenced, not model accuracy.

---

### Pattern B — Contaminated baseline  `[HIGH]`

**Signal:** VQRs score 0 for a metric that the model is answering correctly. The VQR SQL is
missing a required filter that the SV metric definition applies.

Example: SV metric uses `SUM(CASE WHEN status <> 'CANCELLED' THEN amount END)`. VQR SQL uses
`SUM(amount)` without the filter. Ground truth and model output will never match.

**Diagnosis:** Compare VQR SQL aggregation against the SV metric EXPRESSION from DESCRIBE.
This is what Step 3b (CONTAMINATED/HEALTHY classification) catches pre-flight.

---

### Pattern C — Near-zero scores across all VQRs  `[CRITICAL]`

**Signal:** Mean score ≤ 0.10, failures spread across all question types, not concentrated on
a specific table or join path.

**Systematic causes to check in order:**
1. CA extension present → run Check 3, create a DDL-only candidate copy
2. All VQRs reference physical FQN table names → run Check 1
3. Missing `AI_SQL_GENERATION` instruction → model has no guidance for this domain
4. VQRs cover only one of N tables — run Check 6
5. Eval ran against wrong SV FQN (typo, wrong schema)


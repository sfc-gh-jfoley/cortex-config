# VQR and Eval Health Checks

Pre-flight and post-eval checks that catch every known category of silent eval failure.
Run **Checks 1–7** before launching any evaluation. Run **Checks 8–10** when diagnosing poor results.

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

### Check 1 — VQR table reference format  `[HIGH]`

**What it catches:** VQR SQL using physical FQN table references (`DB.SCHEMA.TABLE`) or bare logical table names without the required `__` prefix. Per the Snowflake VQR spec, VQR SQL **must** use `__`-prefixed logical table names (e.g., `FROM __orders`). The Snowsight UI adds the prefix automatically; raw DDL and the CA extension JSON do NOT. A bare or FQN reference orphans the VQR from the SV's table definitions — it may appear to work when logical and physical names coincide, but fails when they diverge. (Verified July 2026.)

**Detection:**
```python
import re

def check_vqr_table_refs(vqr_sql, sv_table_map):
    """
    sv_table_map: dict of {physical_fqn: logical_alias}
    built from DESCRIBE SEMANTIC VIEW:
      object_kind='TABLE', property in ('BASE_TABLE_DATABASE_NAME',
      'BASE_TABLE_SCHEMA_NAME', 'BASE_TABLE_NAME')
    Returns issues: FQN refs, bare logical names (no __), and missing __ prefix.
    """
    issues = []
    for fqn, alias in sv_table_map.items():
        db, schema, tbl = fqn.split('.')
        alias_lower = alias.lower()
        # FQN reference (DB.SCHEMA.TABLE) — always wrong
        if re.search(rf'\b{re.escape(fqn)}\b', vqr_sql, re.IGNORECASE):
            issues.append(f"FQN reference: {fqn} → should be __{alias}")
        # Bare logical name WITHOUT __ prefix — wrong (orphaned)
        # Match the bare alias in FROM/JOIN position, not preceded by __
        if re.search(rf'(?<!\w)(?<!_){re.escape(alias_lower)}(?!\w)', vqr_sql.lower()):
            if f"__{alias_lower}" not in vqr_sql.lower():
                issues.append(f"Bare logical name (missing __): {alias} → should be __{alias}")
    return issues
```

**Fix:** Replace physical FQN and bare logical table references with `__<logical_alias>` (the `name:` field defined for that table in the semantic view). Column names stay plain.

---

### Check 2 — VQR column existence  `[HIGH]`

**What it catches:** VQR SQL referencing column names that don't exist in the SV schema. Common
when the SV uses a different logical name than the physical column (`TABLE.logical AS physical`).
The left side of `AS` is the logical name used in model logic; the right side is the physical
column or expression. VQR SQL must use the **right-side** physical expression.

**Dimension syntax reminder:**
```sql
-- TABLE.logical_name AS physical_expr
OUTAGE_SITE_DETAIL.IS_DELETED AS DELETED_FLAG   -- use DELETED_FLAG in VQR SQL
KPI_DEFINITIONS.IS_ACTIVE AS ACTIVE_FLAG         -- use ACTIVE_FLAG in VQR SQL
```

**Detection:**
```sql
-- Get all physical expressions from DESCRIBE:
SELECT "object_name" AS logical_name, "property_value" AS physical_expr
FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()))
WHERE "object_kind" IN ('DIMENSION', 'FACT', 'METRIC')
  AND "property" = 'EXPRESSION';
-- Then check each VQR's column references against this list
```

**Fix:** Replace logical-name references in VQR SQL with the physical expression shown in DESCRIBE.
Verify physical column existence: `SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = '...'`

---

### Check 3 — CA extension presence and column completeness  `[CRITICAL]`

**What it catches:** SVs built through the Snowsight UI contain a `with extension (CA='...')` block.
The eval framework uses the CA extension's declared column list when constructing ground-truth CTEs.
Any column in VQR SQL that is **not** in the CA extension's column list is silently dropped from the
CTE, causing `invalid identifier` errors in the reference SQL before any model comparison happens.

**This is an eval framework bug, not a user configuration error.** Results on Snowsight SVs are
unreliable until the framework is patched. The workaround is to run eval against a DDL-only copy.

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
            GET_DDL('SEMANTIC VIEW', '<db>.<schema>.<sv_name>'),
            'with extension'
        ) > 0 THEN 'CA_EXTENSION_PRESENT'
        ELSE 'CLEAN'
    END AS ca_extension_status;
```

**Remediation — create a DDL-only eval copy (recommended):**

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

# 4. Rename to eval copy (validated identifier, quoted)
eval_sv_name = f"{sv_name}_EVAL"
if not IDENT.match(eval_sv_name):
    raise ValueError(f"unsafe eval copy name: {eval_sv_name!r}")
eval_fqn_quoted = f'"{db}"."{schema}"."{eval_sv_name}"'

ddl_eval = re.sub(
    r"(CREATE OR REPLACE SEMANTIC VIEW\s+\S+)",
    f"CREATE OR REPLACE SEMANTIC VIEW {eval_fqn_quoted}",
    ddl_clean,
    count=1,
    flags=re.IGNORECASE
)

# 5. Deploy eval copy (VQRs included from AI_VERIFIED_QUERIES block)
cursor.execute(ddl_eval)
print(f"Eval copy created: {eval_fqn_quoted}")

# 6. Drop after eval
# cursor.execute(f"DROP SEMANTIC VIEW {eval_fqn_quoted}")
```

Note that the whole-DDL `ddl.replace('""', '"')` unescape is deliberately absent
here: the strip path discards the CA block, so nothing in it needs unescaping.
Unescape only the extracted CA JSON, in the secondary check below.

**When to skip remediation:** If the eval framework has been patched to use the full SV schema
(not the CA extension column list) for CTE construction, Check 3 becomes advisory. Verify by
running the TPCH smoke test with a known-clean result as your control. If it passes, Check 3
severity downgrades to LOW.

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

    # Parse column references from each VQR SQL
    # (simple heuristic — improve with a proper SQL parser if needed)
    for vqr in vqr_list:
        words = set(re.findall(r'\b[A-Z_][A-Z0-9_]{2,}\b', vqr['sql']))
        missing = words - ca_columns - KNOWN_SQL_KEYWORDS
        if missing:
            print(f"VQR '{vqr['name']}': columns possibly not in CA extension: {missing}")
```

> **Security note — identifiers in DDL.** `GET_DDL`'s argument is a string literal
> and should be passed as a bound parameter. Identifiers embedded in DDL text
> (`CREATE OR REPLACE SEMANTIC VIEW`, `DROP SEMANTIC VIEW`) cannot be bound, so any
> name reaching them must be validated against a strict identifier pattern and
> emitted quoted — see `validate_fqn()` above. Do not f-string an unvalidated name
> into DDL. The same applies to interpolating a question string into an
> `ANALYST_PREVIEW` call: serialise it with `json.dumps()` rather than quoting by
> hand. These paths are skill-controlled today; treat validation as mandatory if
> any of this is promoted to a shared utility.

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
GROUP BY order_month

-- GOOD:
SELECT DATE_TRUNC('month', O_ORDERDATE) AS order_month, SUM(amount) AS rev
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
FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()))
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
FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()))
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
FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()))
WHERE "object_kind" = 'METRIC' AND "property" = 'EXPRESSION';
```

For each VQR that aggregates a metric's source column, compare the aggregation function against
the metric's EXPRESSION. Flag mismatches.

**Fix:** Align the VQR aggregation with the SV metric definition, or if the VQR intentionally
uses a different aggregation, add a note explaining the deviation.

---

### Check 8 — Subquery SQL in VQRs  `[HIGH]`

**What it catches:** VQR SQL containing subqueries (`WHERE col IN (SELECT ...)`,
`WHERE EXISTS (SELECT ...)`, scalar subqueries, etc.). Cortex Analyst cannot generate
subquery-based semantic queries — this is a documented structural limitation. A VQR whose
ground-truth SQL relies on a subquery will always fail during eval because Analyst can never
produce a matching query, regardless of SV quality. This contaminates the eval baseline in the
same way as an aggregation mismatch (Check 7).

**Detection:**
```python
import re

def check_vqr_subqueries(vqr_list):
    """Detect VQR SQL containing subqueries (nested SELECT statements)."""
    issues = []
    for vqr in vqr_list:
        sql = vqr['sql']
        # More than one SELECT means a subquery is present
        select_count = len(re.findall(r'\bSELECT\b', sql, re.IGNORECASE))
        if select_count > 1:
            issues.append({
                'vqr': vqr['name'],
                'issue': 'contains subquery — Analyst cannot generate subquery-based SQL',
                'fix': 'rewrite without subquery, or add the filtering table as an SV relationship'
            })
    return issues
```

**Fix:** Two options depending on intent:
- **For Analyst use**: Add the filtering table as an SV relationship. Rewrite the VQR SQL without
  the subquery, expressing the filter as a dimension-based WHERE condition Analyst can generate.
- **For programmatic-only filtering**: Remove the VQR. Subquery filtering is valid at query time
  for manual consumers, but should not be benchmarked in eval since Analyst will never produce it.

> Note: Subqueries in SV queries are fully supported by Snowflake at runtime (WHERE clause and
> DIMENSIONS ad-hoc expressions). This check targets VQR SQL only — it does not prohibit subquery
> use in manually authored queries against the SV.

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
  HIGH:      <N> issues  (Checks 1, 2, 7, 8)
  MEDIUM:    <N> issues  (Checks 4, 5)
  LOW:       <N> issues  (Check 6)

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
WITH raw AS (
  SELECT "object_name" AS vqr_name, "property_value" AS error_msg
  FROM TABLE(RESULT_SCAN(LAST_QUERY_ID()))
  WHERE "object_kind" = 'AI_VERIFIED_QUERY' AND "property" = 'ERROR'
    AND "property_value" IS NOT NULL
)
SELECT error_msg, COUNT(*) AS count
FROM raw
GROUP BY error_msg ORDER BY count DESC;
```

If errors cluster on `invalid identifier`, and the SV has a CA extension: this is the CA
extension column-drop bug. See Check 3 remediation — create DDL-only eval copy and rerun.

**Note:** The failure rate asymmetry between VQR styles (e.g. 34/50 vs 6/50 failing before scoring)
is not a signal about VQR style quality — it reflects which columns each VQR happened to reference
relative to the CA extension's declared list. Do not interpret asymmetric pre-scoring failure rates
as model accuracy differences.

---

### Pattern B — Contaminated baseline  `[HIGH]`

**Signal:** VQRs score 0 for a metric that the model is answering correctly. The VQR SQL is
missing a required filter that the SV metric definition applies.

Example: SV metric uses `SUM(CASE WHEN REFUNDED_IND = 0 THEN amount END)`. VQR SQL uses
`SUM(amount)` without the filter. Ground truth and model output will never match.

**Diagnosis:** Compare VQR SQL aggregation against the SV metric EXPRESSION from DESCRIBE.
This is what Step 3b (CONTAMINATED/HEALTHY classification) catches pre-flight.

---

### Pattern C — Near-zero scores across all VQRs  `[CRITICAL]`

**Signal:** Mean score ≤ 0.10, failures spread across all question types, not concentrated on
a specific table or join path.

**Systematic causes to check in order:**
1. CA extension present → run Check 3, create DDL-only eval copy
2. All VQRs reference wrong table names (FQN or logical names) → run Check 1
3. Missing `AI_SQL_GENERATION` instruction → model has no guidance for this domain
4. VQRs cover only one of N tables — run Check 6
5. Eval ran against wrong SV FQN (typo, wrong schema)

---

## Change Log

| Date | Change |
|---|---|
| 2026-07-23 | Initial version — checks 1–10, CA extension strip procedure, failure patterns |
| 2026-07-23 | T5: Added live verification evidence appendix for Checks 1–7 (later removed as provenance) |
| 2026-07-31 | Check 1 broadened to flag bare logical names missing `__` (not just FQN); removed session-specific live-verification appendix (provenance, not operational reference) |
| 2026-08-19 | Check 8 added: detect subquery SQL in VQRs (Analyst cannot generate subquery-based queries; these poison the eval baseline) |

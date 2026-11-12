# VQR Strategy Guide

> This guide covers the full lifecycle of Verified Query Representations (VQRs): why to
> register them, what makes one valuable, how to size a VQR set, and how to manage them
> over time. Load this before authoring, auditing, or curating VQRs for any Semantic View.

---

## What VQRs Are (and Are Not)

A VQR is a **named question + precompiled SQL pair** embedded in a Semantic View. Cortex Analyst
uses relevant VQRs when generating SQL for similar questions. This guide calls the case where a
matched VQR's SQL is used as-is the **fast-path**.

**VQRs are not:**
- Fine-tuning data — they do not train or update any model
- Configuration — adding VQRs does not change model behavior globally
- Unlimited — each VQR adds ~200–500 tokens to the SV's context footprint

**VQRs are five things, ranked by value:**

| Rank | Role | What it does |
|------|------|-------------|
| 1 | **Non-determinism anchor** | Locks in the canonical SQL form for patterns the LLM generates inconsistently — window functions, WoW self-joins, PERCENTILE_CONT, EXTRACT vs HOUR() |
| 2 | **Fast-path** | Serves precompiled SQL for high-traffic question patterns (agent flag `EnableVQRFastPath` is undocumented; verify before relying on this) |
| 3 | **Few-shot context injection** | When fast-path does not trigger, VQR SQL is serialized into the LLM context as a worked example, teaching the model correct patterns for this SV |
| 4 | **Eval ground truth** | VQRs are the eval dataset for `EXECUTE_AI_EVALUATION` — without them, SV accuracy cannot be measured at all |
| 5 | **Regression anchors** | When SV schema changes (rename a metric, add a table), VQR SQL failing the dry-run immediately signals a breaking change |

**Critical implication:** VQRs that never trigger fast-path (poor question phrasing, missing
flag, FQN table refs) still serve roles 3–5. "My VQRs never trigger" is not always a reason
to remove them — but it is always a reason to diagnose why.

---

## The Fast-Path Prerequisite Checklist

Before expecting VQRs to trigger, check these conditions. Condition 1 is observed behavior with
no Snowflake documentation; verify before relying on it.

```
1. Agent flag (undocumented): DESCRIBE AGENT → experimental.EnableVQRFastPath
   → Observed: without it, fast-path does not trigger. Few-shot use (role 3) still applies.

2. VQR SQL uses logical table names (prefer __orders), never physical FQNs
   → FROM __orders, not FROM DB.SCHEMA.ORDERS
   → Use vqr-curator Phase 2 to scan for FQN references

3. VQR question matches how users actually ask
   → Threshold is broad (synonyms, rephrasing, noise words all typically hit)
   → If not triggering despite correct flag and SQL: run vqr-curator activation check
```

---

## VQR Quality Rubric

A VQR earns its context cost when it satisfies at least **two** of the following:

### Positive signals (reasons to register)

| Signal | Test |
|--------|------|
| **Complex SQL** | Contains: `PERCENTILE_CONT`, `WITH ... SELECT` self-join, `EXTRACT(...)`, multi-table join with non-obvious join key, `COUNT(DISTINCT)` where `COUNT` is a common mistake |
| **Historically inconsistent** | LLM generates 2+ different SQL forms for this question across runs — non-determinism detected |
| **High traffic** | Question pattern appears frequently in production query logs |
| **Eval coverage gap** | No other VQR tests this metric or dimension — removing it leaves eval blind spots |
| **Canonical form enforcer** | Multiple correct SQL forms exist; this VQR picks the preferred one |

### Negative signals (reasons NOT to register)

| Signal | Verdict |
|--------|---------|
| **Single table, simple aggregate** | `SELECT SUM(x) FROM t GROUP BY y ORDER BY 1 DESC` — usually generated correctly. Put the formula in `ai_sql_generation` hint instead, **unless** it is the only VQR covering that metric (eval coverage) |
| **Duplicates existing VQR** | Question cosine similarity > 0.85 to another VQR — one of them is redundant |
| **FQN table references** | Pollutes few-shot signal with wrong syntax; fix the reference rather than register it |
| **Out-of-scope question** | Tests something the SV doesn't actually model well — wastes context and misleads eval |

---

## VQR vs. `ai_sql_generation` Hint

Many patterns are better as one-line hints than as full VQRs:

| Pattern | Use VQR | Use ai_sql_generation hint |
|---------|---------|---------------------------|
| WoW self-join (not LAG) | ✓ — complex, easy to get wrong | |
| PERCENTILE_CONT for P95 | ✓ — non-standard aggregation | |
| Error rate formula | ✓ — join key easily missed | |
| "Use DATEADD not INTERVAL" | | ✓ — one-line instruction |
| "Sort cost DESC by default" | | ✓ — behavioral preference |
| "Use EXTRACT not HOUR()" | | ✓ — syntax correction |
| "Cache hit = SUM(cache_read)/NULLIF(total,0)" | borderline | ✓ if LLM reliably follows it |

**Rule of thumb:** If you can express the guidance in one sentence, use the hint. If correct
SQL requires a specific structure the hint can't fully convey, use a VQR.

---

## VQR Set Size

### Target sizes

| SV type | Recommended VQR count | Rationale |
|---------|----------------------|-----------|
| Single fact table, one domain | 3–8 | Enough for eval coverage; more is likely redundant |
| 2–3 tables, one domain | 8–15 | Covers cross-table joins and the key question categories |
| 3–5 tables, multi-dimensional | 15–20 | Maximum for a well-scoped SV |
| **>20 VQRs needed** | **Review VQR value first** | Prune redundant VQRs before adding more |

### More than 20 VQRs

Past about 20, check each VQR against the rubric above before adding more; VQRs count toward the
SV's ~100,000-token guideline. VQR count is not a reason to split the SV. SV boundaries follow
the single sizing policy in `../../sv-discovery/phases/03_analyze.md` Step 3B.

If one table contributes most VQRs while others have none, the others are under-tested; add
coverage there.

---

## VQR SQL Requirements

### Required
- Use logical table names, preferably `__`-prefixed: `FROM __orders o`, `JOIN __customers c`
- Use logical column names (the dimension and fact names defined in the SV) everywhere,
  including inside aggregates
- Aggregate the logical fact, aliased to the metric name: `SUM(order_total) AS total_revenue`,
  not `SUM(total_revenue)` (a metric name is not a column)

### Strongly recommended
- Use fixed date literals for eval reproducibility (evals use VQR SQL to measure accuracy)
- Use `NULLIF` on denominators to prevent division-by-zero
- Use `COALESCE` for nullable foreign keys (e.g., `COALESCE(ai_function_credits, 0)`)
- Keep SQL under 40 lines — if it requires more, split into two VQRs

### Prohibited
- `FROM DB.SCHEMA.PHYSICAL_TABLE` (T1 — breaks binding and poisons few-shot signal)
- `CURRENT_DATE` or `CURRENT_TIMESTAMP` — evals compare output against ground truth; relative dates make ground truth stale

### Follow the SV's own conventions
- If the SV's `AI_SQL_GENERATION` instructions prescribe a form (for example a self-join instead
  of `LAG()`, or `EXTRACT(HOUR FROM ts)` instead of `HOUR(ts)`), VQR SQL must use the same form.
  Both forms are valid Snowflake SQL; consistency is what matters.

---

## VQR Lifecycle

### When to add
- When introducing a new metric or dimension with no existing eval coverage
- When a production query shows consistent LLM inaccuracy on a specific pattern
- When a pattern is non-deterministic (different SQL across runs for the same question)
- Before running SV evaluation — you need VQRs to measure accuracy

### When to remove
- The metric, dimension or table it tests was removed from the SV (confirmed from DESCRIBE).
  A dry-run failure alone is a reason to review, not to remove.
- Question has not been asked in production in >90 days AND no evaluation uses it
- Curator scores it DEDUPLICATE and the higher-scoring near-duplicate covers the same pattern
- It was only registered for context injection and the pattern is now reliably generatable

### When to update
- VQR SQL executes but returns wrong data (ground truth has drifted with the underlying tables)
- A new SV fix (e.g., adding a named metric) makes simpler SQL available
- User phrasing patterns have shifted — update the question text to match production

---

## Quick Decision Tree

```
New question pattern → should I register a VQR?

Is the SQL trivially generatable (single table, simple aggregate)?
  YES → Add to ai_sql_generation hint instead. Not a VQR.
  NO  ↓

Does a VQR already cover this semantic pattern (>0.85 similarity)?
  YES → Keep the existing one. Don't add. Fix if needed.
  NO  ↓

Does it involve a pattern the LLM gets wrong? (window fn, self-join, multi-table join, formula)
  YES → Register as VQR. Ensure __logical refs, fixed dates.
  NO  ↓

Is it needed for eval coverage (no other VQR tests this metric/dimension)?
  YES → Register for eval ground truth. Use ONBOARDING_QUESTION FALSE.
  NO  → Skip. Not worth the context tokens.

After adding: total VQR count > 20?
  YES → Re-check each VQR against the rubric. >20 is a signal, not a cap.
```

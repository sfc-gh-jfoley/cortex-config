# VQR Strategy Guide

> This guide covers the full lifecycle of Verified Query Representations (VQRs): why to
> register them, what makes one valuable, how to size a VQR set, and how to manage them
> over time. Load this before authoring, auditing, or curating VQRs for any Semantic View.

---

## What VQRs Are (and Are Not)

A VQR is a **named question + precompiled SQL pair** embedded in a Semantic View. When a
user's question matches a VQR by semantic similarity, Cortex Analyst returns the VQR's SQL
verbatim instead of generating new SQL. This is called the **fast-path**.

**VQRs are not:**
- Fine-tuning data — they do not train or update any model
- Configuration — adding VQRs does not change model behavior globally
- Unlimited — each VQR adds ~200–500 tokens to the SV's context footprint

**VQRs are five things, ranked by value:**

| Rank | Role | What it does |
|------|------|-------------|
| 1 | **Non-determinism anchor** | Locks in the canonical SQL form for patterns the LLM generates inconsistently — window functions, WoW self-joins, PERCENTILE_CONT, EXTRACT vs HOUR() |
| 2 | **Fast-path** | Serves precompiled SQL verbatim for high-traffic question patterns, bypassing LLM generation entirely (requires `EnableVQRFastPath: true` on the agent) |
| 3 | **Few-shot context injection** | When fast-path does not trigger, VQR SQL is serialized into the LLM context as a worked example, teaching the model correct patterns for this SV |
| 4 | **Eval ground truth** | VQRs are the eval dataset for `EXECUTE_AI_EVALUATION` — without them, SV accuracy cannot be measured at all |
| 5 | **Regression anchors** | When SV schema changes (rename a metric, add a table), VQR SQL failing the dry-run immediately signals a breaking change |

**Critical implication:** VQRs that never trigger fast-path (poor question phrasing, missing
flag, FQN table refs) still serve roles 3–5. "My VQRs never trigger" is not always a reason
to remove them — but it is always a reason to diagnose why.

---

## The Fast-Path Prerequisite Checklist

Before expecting VQRs to trigger, verify all three conditions:

```
1. EnableVQRFastPath = true in agent spec
   → DESCRIBE AGENT → experimental.EnableVQRFastPath must be true
   → If absent: ALL VQRs are ignored regardless of SQL quality

2. VQR SQL uses __logical table names (not FQN)
   → FROM __requests, not FROM DB.SCHEMA.V_AGENT_REQUESTS
   → FQN refs compile and register but never bind at semantic level
   → Use vqr-curator or agent-health-check to scan for T1/T2 violations

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
| **Single table, simple aggregate** | `SELECT SUM(x) FROM t GROUP BY y ORDER BY 1 DESC` — LLM generates this correctly every time. Put the formula in `ai_sql_generation` hint instead |
| **Duplicates existing VQR** | Question cosine similarity > 0.85 to another VQR — one of them is redundant |
| **FQN table references** | T1/T2 violation — pollutes few-shot signal with wrong syntax AND won't trigger fast-path |
| **Trivially short SQL** | Under 3 lines — if the SQL is this simple, the hint is cheaper and more flexible |
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
| **>20 VQRs needed** | **Audit the SV design** | Strong signal the SV covers 2+ domains |

### The 20-VQR rule

If you cannot cover your SV's question space in 20 VQRs, the SV is likely doing too much.
The right response is not more VQRs — it is splitting the SV.

**Diagnostic test:** Write down the subject of every VQR question. If the subject is not
consistent ("which agent", "which user", "which agent"), you have two SVs sharing a schema.

```
Good (cohesive):
  VQR 1: "Which agent has the highest latency?"     → subject: agent
  VQR 2: "Which agent costs the most?"              → subject: agent
  VQR 3: "Which agent has the worst error rate?"    → subject: agent

Split signal (two domains):
  VQR 1: "Which agent has the highest latency?"     → subject: agent telemetry
  VQR 2: "What was our total revenue last month?"   → subject: business metric
  VQR 3: "Which agent costs the most?"              → subject: agent telemetry
  → These belong in two SVs, not one
```

**Exception:** A multi-table operational SV with genuinely distinct *source tables* (not
domains) can reach 20 with discipline. Each table should contribute 4–6 VQRs covering its
unique question patterns. If one table is contributing 15 of your 20 VQRs, the others are
undertested and the dominant table should probably be its own SV.

---

## VQR SQL Requirements

### Required
- Use `__logical_table_name` for all table references: `FROM __requests r`, `FROM __token_detail td`
- Use logical column names (the SV's `AS` aliases) in SELECT, GROUP BY, ORDER BY
- Reference physical column names in aggregates: `SUM(token_credits) AS total_cost` not `SUM(TOTAL_COST)`

### Strongly recommended
- Use fixed date literals for eval reproducibility (evals use VQR SQL to measure accuracy)
- Use `NULLIF` on denominators to prevent division-by-zero
- Use `COALESCE` for nullable foreign keys (e.g., `COALESCE(ai_function_credits, 0)`)
- Keep SQL under 40 lines — if it requires more, split into two VQRs

### Prohibited
- `FROM DB.SCHEMA.PHYSICAL_TABLE` (T1 — breaks binding and poisons few-shot signal)
- `CURRENT_DATE` or `CURRENT_TIMESTAMP` — evals compare output against ground truth; relative dates make ground truth stale
- `LAG()` or `LEAD()` on aggregate expressions — explicitly forbidden; use self-join WoW pattern
- `HOUR(event_ts)` — use `EXTRACT(HOUR FROM event_ts)`

---

## VQR Lifecycle

### When to add
- When introducing a new metric or dimension with no existing eval coverage
- When a production query shows consistent LLM inaccuracy on a specific pattern
- When a pattern is non-deterministic (different SQL across runs for the same question)
- Before running SV evaluation — you need VQRs to measure accuracy

### When to remove
- VQR SQL fails the dry-run after SV schema change (metric renamed, table removed)
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
  YES → Register for eval ground truth. Mark use_as_onboarding_question=false.
  NO  → Skip. Not worth the context tokens.

After adding: total VQR count > 20?
  YES → Audit the SV design. >20 is a signal, not a cap.
```

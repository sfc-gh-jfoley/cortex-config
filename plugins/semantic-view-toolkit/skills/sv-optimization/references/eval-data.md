# SV Optimization — Eval Data

> Procedural reference for the `sv-optimization` skill. Loaded by the router in `SKILL.md` (EVAL-DATA intent). Not independently invokable.

## Purpose

The optimization loop (`references/optimize.md`) needs VQRs to evaluate candidate mutations.
This reference helps bootstrap, expand, or rebalance VQRs before or during optimization.

---

## When to Use

| Situation | Action |
|---|---|
| No VQRs exist yet | Create initial VQRs via vqr-generator |
| Fewer than 5 VQRs | Add more before starting optimization |
| VQRs are all guide-quality, none held out for eval | Rebalance split |
| Optimization loop keeps failing on the same questions | Add targeted VQRs for those failure patterns |
| Want to add coverage for a specific business domain | Add domain-specific VQRs |

---

## Step 1: Check Current VQR Count

```sql
DESCRIBE SEMANTIC VIEW <SV_FQN>;
```

Count `verified_queries` entries in the DDL output.

| Count | Action |
|---|---|
| 0 | Must create VQRs before any optimization — route to vqr-generator |
| 1–4 | Optimization possible but weak signal — recommend expanding to 5+ |
| 5–10 | Sufficient for optimization; check guide/eval split |
| 10+ | Good coverage; check for domain gaps |

---

## Step 2: Route to vqr-generator

All VQR creation and management is handled by `vqr-generator`. Load it with context:

```
Route to: vqr-generator
Context: "Creating VQRs to bootstrap sv-optimization for <SV_FQN>.
          Target: at least 5 VQRs covering the key business questions for this SV.
          After creation, return to sv-optimization to run the eval baseline."
```

Provide vqr-generator with:
- The SV FQN
- Any failure questions from recent eval runs (for targeted VQR creation)
- The business domain context

---

## Step 3: Guide vs Eval Split (After VQRs Are Created)

VQRs serve dual purpose in the optimization loop. After vqr-generator has run, recommend
a split per the guide in `SKILL.md` (VQR Split Strategy section):

| Total VQRs | Eval (holdout) | Guide (in-SV) |
|---|---|---|
| 5–10 | 60% | 40% |
| 11–20 | 70% | 30% |
| 20+ | 75% | 25% |

The Snowflake evaluation API handles holdout automatically. This split is informational —
track "guide-quality" VQRs (those that teach the SV by example) vs "eval-quality" VQRs
(those that test generalization).

---

## Step 4: Return to Optimization

After VQRs are in place:
1. Run `sv-evaluation` to establish or refresh the baseline score
2. Return to `references/setup.md` to record the new baseline
3. Then proceed with `references/optimize.md`

```
VQR setup complete:
  Total VQRs:  <N>
  Eval split:  <X> holdout / <Y> guide
  Next step:   Run sv-evaluation to establish baseline, then sv-optimization → optimize
```

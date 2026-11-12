# Phase 3: Uniqueness

Detect near-duplicate VQRs. A VQR that covers the same semantic pattern as another
wastes context and may cause fast-path collisions (wrong VQR triggered).

## Step 3.1 — Question similarity

For all pairs of VQRs, compute similarity score using keyword overlap (Jaccard index on
tokenized question text). Use lowercase, strip stopwords ("which", "my", "the", "of",
"in", "a", "an", "by", "for").

```python
# Jaccard similarity pseudo-code
tokens_a = set(question_a.lower().split()) - STOPWORDS
tokens_b = set(question_b.lower().split()) - STOPWORDS
similarity = len(tokens_a & tokens_b) / len(tokens_a | tokens_b)
```

Alternatively, use embedding similarity (deterministic, one call per pair):
```sql
SELECT AI_SIMILARITY('<q1>', '<q2>') AS similarity;
```
The thresholds below were written for Jaccard scores. Embedding scores run higher for short
related questions, so treat every `AI_SIMILARITY` flag as WARN until you have checked a few pairs
by hand. Use one method for the whole run.

## Step 3.2 — Flag duplicates

| Similarity | Action |
|-----------|--------|
| ≥ 0.85 | DUPLICATE_CANDIDATE — resolve in Step 3.3 |
| 0.70–0.84 | WARN — near-duplicate; manually review before keeping both |
| < 0.70 | Distinct — no action |

```
[DUPLICATE] VQR "<a>" ↔ "<b>" — similarity <score>
            Proposed keep: "<a>" (complexity <N>) | DEDUPLICATE: "<b>" (complexity <M>)
            Questions:
              A: <question_a>
              B: <question_b>
```

## Step 3.3 — SQL overlap check

For each DUPLICATE_CANDIDATE pair, compare SQL structure (FROM clauses, GROUP BY columns) and
apply the first matching rule:

1. SQL equivalent → keep the better-phrased question; mark the other DEDUPLICATE.
2. SQL differs and complexity scores differ by ≥ 1 → keep both (they may anchor different SQL
   patterns); record WARN.
3. Otherwise → keep the higher complexity_score (ties: the one with sole metric coverage, then the
   better-phrased question); mark the other DEDUPLICATE.

Never mark a VQR DEDUPLICATE if it is the only VQR covering some metric or dimension (Phase 5
`sole_coverage`).

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

Alternatively, if AI_COMPLETE is available:
```sql
SELECT AI_COMPLETE('snowflake-arctic',
    'Rate semantic similarity 0.0-1.0 between these two questions.
     Return only a decimal number.
     Q1: <q1>
     Q2: <q2>') AS similarity;
```

## Step 3.2 — Flag duplicates

| Similarity | Action |
|-----------|--------|
| ≥ 0.85 | DEDUPLICATE — flag both; keep higher complexity_score, remove other |
| 0.70–0.84 | WARN — near-duplicate; manually review before keeping both |
| < 0.70 | Distinct — no action |

```
[DUPLICATE] VQR "<a>" ↔ "<b>" — similarity <score>
            Keep: "<a>" (complexity <N>) | Remove: "<b>" (complexity <M>)
            Questions:
              A: <question_a>
              B: <question_b>
```

## Step 3.3 — SQL overlap check

For pairs flagged as DEDUPLICATE, also compare SQL structure (FROM clauses, GROUP BY
columns). If SQL is identical but questions differ: keep the better-phrased question,
discard the other.

If SQL differs but questions are nearly identical: keep both IF complexity scores differ
significantly (≥1 point), since they may be anchoring different SQL patterns.

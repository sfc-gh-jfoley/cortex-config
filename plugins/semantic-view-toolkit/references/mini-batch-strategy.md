# Mini-Batch Strategy

Implemented by `scripts/sample_batch.py`. Each generation evaluates candidates on a subset of verified queries (VQRs) to cut cost.

## What the code does

- Batch size is `ceil(total * batch_pct)`, at least 1. With fewer than 5 VQRs, all are used.
- VQRs are split by `previously_passed` into passing and failing pools; the batch is proportional with at least one from each pool when both exist.
- Questions used in the previous generation are taken last, so batches rotate.
- Selected questions are shuffled and recorded in `batch_history` (`generation`, `questions`, `batch_size`, `total_vqrs`).
- `--emit-eval-yaml <candidate>` writes the evaluation config with the sampled questions under `source_metadata.verified_queries` and `sql_correctness` pinned to `--metric-version` (default v3). `--reuse-questions <file>` renders that YAML from a saved list so every candidate in a generation gets the same questions.

## Evaluation semantics

Questions listed in `verified_queries` are removed from the evaluated copy of the view, and unlisted ones keep guiding SQL generation (`skills/sv-evaluation/SKILL.md`). A smaller batch therefore changes the effective view as well as the score, so compare scores only within one generation and one batch.

## Noise

SQL generation is non-deterministic, so a single mini-batch run is a noisy estimate and differences under about 0.03 may be noise. Mini-batch scores only rank candidates within a generation. Finalists must be evaluated at least twice on one full question list before a winner is named (`population_state.py record-final` / `finalize`).

## Not implemented

Pass/fail history is not updated automatically: supply `previously_passed` in the input from the latest results. There is no separate "unknown" pool and no maximum batch size.

Quality assurance toolkit for Cortex Code skill authors. If you build, modify, or maintain CoCo skills, this plugin catches regressions, non-determinism, and documentation drift before they reach users.

- **skill-tester** — Run any skill 3x in parallel with fixture-injected inputs. Compare outputs for consistency, execute assertions (DDL validity, count thresholds, string content), and produce a scored PASS/FAIL report. Catches non-determinism and silent regressions.
- **skill-timing** — Instrument skill executions with wall-clock timing, intermediate checkpoints, and token/credit estimation. Detect shortcuts (agent skipped phases), compare performance across models, and embed timing metadata into output files.
- **prompt-determinism-tester** — Give the same prompt to 3 independent Plan agents and compare their build plans. Scores convergence across 6 dimensions (objects, DDL structure, sequence, row counts, features, artifacts). Supports gated multi-prompt pipelines for HOL QA.
- **doc-reviewer** — Score documentation against a 6-dimension rubric (accuracy, completeness, clarity, consistency, staleness, structure) on a 100-point scale. Verifies file references exist, tests commands, validates links. Modes: FULL, FOCUSED, STALENESS.
- **plan-reviewer** — Score LLM-generated implementation plans for autonomous agent executability using an 8-dimension rubric. Catches ambiguity, missing dependencies, and judgment calls that would block a headless agent. Modes: FULL, COMPARISON, META-REVIEW, DELTA.

To enable: `cortex plugin enable coco-meta`

Start with: `$coco-meta:skill-tester` or `$coco-meta:prompt-determinism-tester`

# DSPy Methodology Reference

Background on the DSPy framework and how this skill implements MIPROv2 for
Snowflake Cortex Agents.

---

## What is DSPy?

**DSPy** (Declarative Self-improving Language Programs, Khattab et al. 2023) is a
Stanford research framework that treats LLM-based pipelines as *programs* that can
be automatically *compiled* (optimized) against a metric. Instead of hand-writing
prompts, you define the program structure and let an optimizer find the best
instructions and demonstrations.

Key DSPy concepts and how they map here:

| DSPy Concept | This Skill's Equivalent |
|---|---|
| Program | Cortex Agent (instruction files + spec) |
| Module | Individual instruction files (orchestration_instructions.md, response_instructions.md) |
| Metric | `answer_correctness` from `EXECUTE_AI_EVALUATION` |
| Trainset | DEV split of the eval table |
| Demonstrations | Bootstrapped traces from baseline eval results |
| Compilation | TPE search over (instruction pool × demo pool) |
| Compiled program | Winner instruction variant + few-shot demos |

---

## MIPROv2

**MIPROv2** (Multiprompt Instruction PRoposal Optimizer v2) is DSPy's most
capable optimizer. It works in three stages:

### Stage 1: Bootstrap Demonstrations

Run the program (agent) on the training set. Collect examples where it answers
correctly — these become the *demonstration pool*. Correct examples are
better demonstrations than hand-written ones because they capture the actual
behavior the model produces when it succeeds.

**In this skill:** `scripts/collect_traces.py` queries the baseline eval results
for high-scoring questions (score ≥ 0.75) and assembles them into `trace_pool.json`.

### Stage 2: Propose Instructions

Generate a discrete set of instruction candidates. MIPROv2 uses a meta-LLM to
propose instruction variants conditioned on the task description and failure
examples from Stage 1. The proposals are generated *upfront* as a finite pool —
the optimizer searches over this pool rather than generating instructions on-the-fly.

**In this skill:** `scripts/generate_candidates.py` outputs one prompt per
operator slot. CoCo fills in each variant using that prompt + `failure_context.json`.
The result is `instruction_pool.json` — 12 instruction proposals, each produced
by a targeted mutation operator.

### Stage 3: Joint Optimization via TPE

Search over the Cartesian product of (instruction_pool × demo_pool subsets).
MIPROv2 uses **Tree-structured Parzen Estimator (TPE)** from the optuna library
as its Bayesian backend. TPE builds two kernel density estimates (KDEs):

- `l(x)`: density over *good* parameter configurations (score > γ-percentile)
- `g(x)`: density over *bad* parameter configurations

At each step it acquires the next configuration by maximizing `l(x) / g(x)` —
the Expected Improvement acquisition function. After `n_startup_trials` random
trials, TPE uses the observed scores to focus search on promising regions.

**In this skill:**
- `scripts/tpe_suggest.py` calls `study.ask()` → receives next `(instruction_idx, fewshot_0, fewshot_1)` from TPE
- CoCo deploys the candidate, runs mini-batch eval, collects score
- `scripts/tpe_record.py` calls `study.tell(trial, score)` → TPE updates its KDE models
- After `n_trials` (default 20), `tpe_suggest.py` returns `done=true`

The optuna study is persisted in `tpe_study.db` (SQLite) — fully resumable
across session interruptions.

---

## Why TPE Over Random Search?

With 20 trials:
- **Random search** samples uniformly — no learning from prior results
- **TPE** starts random for `n_startup_trials` (default 5), then focuses on
  promising `(instruction, demo)` combinations based on observed scores

Empirically, TPE outperforms random search when the search space has structure
(i.e., some instruction variants are consistently better than others). Given that
failure-targeted instruction mutations should cluster improvements in specific
question categories, the search space has structure and TPE should yield 10-30%
better final scores vs random within the same budget.

---

## How This Differs From Vanilla MIPROv2

| Aspect | Vanilla MIPROv2 | This Skill |
|---|---|---|
| Program execution | LLM forward pass | Cortex Agent via `DATA_AGENT_RUN` |
| Metric evaluation | In-process Python function | `EXECUTE_AI_EVALUATION` API |
| Instruction generation | Meta-LLM from DSPy's prompt library | CoCo (the agent itself) using operator-templated prompts |
| Demo format | DSPy `Example` objects | `## Worked Examples` section in orchestration_instructions.md |
| Search state | In-memory optuna study | optuna SQLite study (resumable) |
| Logging | None (in-memory) | Snowflake tables: `_OPT_RUNS`, `_OPT_CANDIDATES`, `_QUESTION_MANIFEST`, `OPT_QUESTION_HISTORY` |

---

## References

- Khattab, O., Singhvi, A., Maheshwari, P., Zhang, Z., Shrivastava, A., Bahri, D.,
  Hall, K., Zou, J., Potts, C., & Zaharia, M. (2023). **DSPy: Compiling Declarative
  Language Model Calls into Self-Improving Pipelines.** arXiv:2310.03714.
- Bergstra, J., Bardenet, R., Bengio, Y., & Kégl, B. (2011). **Algorithms for
  Hyper-Parameter Optimization.** NeurIPS 2011. (Original TPE paper)
- optuna: https://optuna.readthedocs.io/en/stable/reference/samplers/generated/optuna.samplers.TPESampler.html

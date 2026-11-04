# Cortex Agent Toolkit Guide

This guide follows one team, the customer support operations group at a telecom company, as they build an agent over the semantic view their analytics group produced. It covers the four stages: create, tune, optimize, and monitor. Names, counts, and scores in the story are illustrative.

## Create

Marcus's team has a semantic view for subscriber billing and wants an agent that answers billing questions in plain language. He starts with **agent-ddl**, which builds the agent from the SV. The skill generates tool descriptions from the SV metadata, so the agent knows when to use the billing tool and when not to. Marcus reads them, sharpens one that overlaps with the network-outage tool, and continues.

The skill also writes `execution_environment.warehouse` on every Analyst tool, because the spec requires it. Marcus does not have to remember it.

He runs one smoke question through `DATA_AGENT_RUN`. It answers, so he moves on to measuring quality.

## Tune

Measurement comes first. Marcus builds a ground-truth set of real support questions with expected answers, labeled as dev or test. Then he runs **agent-evaluation** to get a baseline. The baseline shows that answer correctness is acceptable but tool selection is weaker: the agent often calls the billing tool for questions that belong to the plan-change tool.

Before tuning instructions, Marcus runs **agent-model-tester**. The model is often the biggest lever, and comparing variants is cheaper than rewriting prompts. He compares the current model against two alternatives on the same dev and test questions, with statistical comparison. A smaller model matches the larger one's accuracy at lower cost, and he picks it.

He then runs **agent-instruction-optimizer** for a fast first pass. It searches instruction and few-shot combinations in about twenty evaluations and suggests a revised instruction set. Marcus keeps the change because it is small and quick to verify.

## Optimize

Gains now come more slowly, so Marcus switches to **agent-optimizer**. It works on the dev split, makes one change per iteration, and reverts a change if it regresses the test split. The first iteration adds a clarifying line about plan changes versus billing disputes, and the test score improves. Marcus accepts it.

Later iterations are rejected. After three consecutive rejections, the optimizer stops.

Marcus then runs **agent-gepa-optimizer**. It evolves a population of instruction variants, selects winners through tournaments, and evaluates on mini-batches. Marcus reviews the winning configuration and approves it before anything touches production. The toolkit never overwrites production on its own.

Before release, he runs **agent-load-tester** to find out how many agents the support floor can use at once. The profile shows that model think time dominates latency, at roughly 80–90% of it in typical agents, and that SQL was under 5% of latency. Sizing the warehouse larger would barely change end-to-end latency, so the team does not pay for one.

## Monitor

The agent ships to a pilot group. Marcus commits the tested configuration as an immutable version with `ALTER AGENT … COMMIT` and points the production alias at it. The support tools call the alias, so a rollback is moving the alias back to the previous version.

Pilot agents get thumbs up and down. **agent-feedback-analyzer** reads those events, clusters the complaints, and explains the patterns. It is read-only: it diagnoses, and Marcus decides what to change. Most of the thumbs down cluster around refund questions the agent answers from an out-of-date policy document. Marcus promotes the representative failures into the ground-truth set through agent-optimizer's feedback pipeline, then re-runs **agent-evaluation** to confirm the fix.

After each deployment, Marcus runs a few smoke-test questions with **agent-query**. Document-level questions, such as "what does the refund policy say about prorated plans?", go through **agent-analytical-search**, which adds a `cortex_search` tool over the policy corpus.

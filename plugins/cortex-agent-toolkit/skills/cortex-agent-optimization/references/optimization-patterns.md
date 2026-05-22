# Optimization Patterns

Distilled learnings from real optimization work (6 iterations on a production agent). Use these patterns to guide instruction editing decisions.

## High-Impact Patterns

### 1. Tool retry logic has the highest single-iteration impact
Adding "retry up to 2x on transient errors before reporting failure" to orchestration instructions fixed complete failures caused by intermittent tool errors. Measured: +9.3% answer_correctness in one iteration.

### 2. Buggy examples in instructions are poisonous
If an example in the instructions contains an inconsistency (e.g., listing 3 items but the formula only uses 2), the agent will faithfully reproduce that inconsistency. Audit all examples for internal consistency.

### 3. Fix the examples, not just the rules
Adding a rule saying "be consistent" is less effective than fixing the example that demonstrates inconsistency. Agents learn more from examples than from abstract rules.

## Anti-Patterns (What Doesn't Work)

### 4. Verbose procedural instructions backfire
Adding multi-step verification checklists (e.g., "4-step PRE-FLIGHT CHECK before every tool call") degrades performance. Measured: -7.5% answer_correctness, -9.3% logical_consistency. Simpler, example-driven rules outperform procedural checklists.

### 5. Tool description changes have minimal routing influence
Adding warnings like "DO NOT use this tool for X" to tool descriptions had zero impact on DEV scores and hurt TEST performance. Tool descriptions appear to have less influence on tool selection than orchestration instructions.

### 6. Tool order changes in the spec cause unpredictable regressions
Reordering tools in the `tools` array caused the worst TEST regression across all iterations (-8.0%). Tool order is not a reliable lever for influencing behavior.

### 7. Progressive strengthening of the same rule has diminishing returns
If the same failure persists after 2-3 iterations of strengthening the same rule (adding more emphasis, more examples, more "NEVER" directives), it likely indicates a model behavior limit, not an instruction clarity issue. Consider architectural changes instead (tool-level guardrails, tool configuration, or workflow redesign).

## Methodology Patterns

### 8. Small, targeted changes per iteration
Change one pattern at a time when possible. This makes it clear which change caused improvement or regression. Bundling many changes makes attribution impossible.

### 9. "WRONG" examples are effective
Showing the agent what NOT to do (with explicit "WRONG" labels) is an effective complement to positive examples. Format: show the wrong approach, label it "WRONG", then show the correct approach.

### 10. Domain-specific consistency rules need nuance
Strict rules based on surface-level patterns (e.g., "counter count must match formula expression count") can be too aggressive. Documentation-based rules ("list all counters the documentation identifies as required") are more robust because they account for domain nuance (e.g., filtering counters not in the math expression).

### 11. Revert aggressively on TEST regression
Any TEST average regression is an overfitting signal. Don't try to "fix" a rejected iteration by making more changes on top — revert to the last accepted state and try a different approach.

### 12. Know when to stop
After 2-3 consecutive rejected iterations targeting the same failures, the agent has likely reached a local optimum for instruction-level changes. Document the remaining failures as known limitations and consider whether they require architectural changes (different tools, guardrails, or workflow restructuring).

### 13. Single eval runs are noisy — use multiple runs per split
LLM-based eval metrics have inherent variance from non-deterministic model responses. A +2% improvement on a single run can easily be noise. Running multiple evals and comparing means reduces the probability of accepting noise as signal or rejecting real improvements. The cost is N× eval time per iteration, which is justified for production agents where a wrong accept/reject decision wastes an entire iteration. See `setup/SKILL.md` for recommended `runs_per_split` values based on dataset size.

### 14. Classify failures with a decision tree, not intuition
Follow a fixed diagnostic order: routing → tool error → formatting → content → ambiguity → model limit. This prevents the optimizer from jumping to instruction rewrites when the real problem is a tool error, or adding formatting rules when the issue is routing. Consistent classification also makes the optimization log more useful — you can track which *categories* of failure are decreasing across iterations.

## Summary

| Category | DO | DON'T |
|----------|-----|-------|
| Instructions | Fix buggy examples, add "WRONG" examples, add retry logic | Add verbose checklists, over-strengthen failing rules |
| Tool config | Keep tool order stable, use orchestration instructions for routing | Modify tool descriptions for routing, reorder tools |
| Methodology | Small targeted changes, revert on TEST regression, log everything | Bundle many changes, build on rejected iterations |
| Termination | Stop after 2-3 consecutive rejections on the same failures | Keep iterating without architectural changes |

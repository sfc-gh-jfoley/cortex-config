# Manifest Validation and Remaining Integration Gaps

The read-only helper validates the event stream it receives. It does not collect
events, synchronize worktrees, authenticate writers, execute tests, or inspect Git
objects. A role field and SHA are evidence references, not cryptographic proof.

## Commands

Resolve ARCH_SKILL_ROOT to the absolute installed skill directory. Requires Python
3.9 or newer; the helper uses only the standard library. Examples use uv; an
operator-selected Python interpreter can run the same script if uv is unavailable.

```bash
uv run --no-project python "$ARCH_SKILL_ROOT/scripts/manifest.py" status .agent-project/manifest.log
uv run --no-project python "$ARCH_SKILL_ROOT/scripts/manifest.py" ready .agent-project/manifest.log --phase CODE_WRITTEN
uv run --no-project python "$ARCH_SKILL_ROOT/scripts/manifest.py" ship .agent-project/manifest.log
uv run --no-project python -B -m unittest discover -s "$ARCH_SKILL_ROOT/tests" -v
```

All commands return JSON except the test runner. Missing files, malformed task
records and invalid transitions fail closed. Ship additionally rejects empty scope,
incomplete successors, successor cycles and unclosed conditions. Current state
implicitly identifies the attempt through its ordered retry transitions; verdicts
must also match the current CODE_WRITTEN SHA.

## Integration Contract

- Worker and coordinator worktrees have distinct files. Follow
  `worktree-handoff.md`: publish task-scoped evidence and use `collect_events.py`
  to produce a validated candidate for the single coordinator-owned manifest.
- Worker CODE_WRITTEN records reference the code commit preceding the manifest
  commit. Reviewers must use that recorded artifact SHA, not branch HEAD.
- A dependency's DONE marker does not put its files into a dependent worker's
  checkout. The coordinator must establish a base containing verified dependencies.
- SecArch and Tester use separate detached worktrees at the approved artifact SHA.
  Disposable Git tests verify that this works while the worker branch is occupied.
- Primary exits in multi-team mode, yet major changes require Primary review.
  Treat those tasks as awaiting operator review; no persistent supervisor has been
  implemented by this patch.
- Existing startup and recovery grep snippets are diagnostics only. They cannot
  authorize deletion, classify a live run reliably, or supersede helper validation.

## Scope of Verification

Regression tests exercise local event parsing, lifecycle predicates, committed
event collection and replay, explicit dependency-code integration, and detached
reviews in disposable Git repositories. They do not establish platform task-tool
compatibility, background-agent survival, or end-to-end headless reliability.
No production code or customer data is used in these tests.

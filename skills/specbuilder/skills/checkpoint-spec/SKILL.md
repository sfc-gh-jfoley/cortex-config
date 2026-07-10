---
name: checkpoint-spec
version: "1.17.1"
description: "Execution checkpoint protocol — track and resume multi-proposal batch implementations"
triggers:
  - checkpoint
  - batch status
  - resume batch
  - init batch
  - record wave
---

# checkpoint-spec

Tracks batch implementation waves so interrupted multi-module implementations can be resumed without re-running completed waves. State is stored in `.specbuilder/execution-log.md` (gitignored). The execution log is the source of truth for wave plan and progress; committed proposal frontmatter statuses are used only to verify wave preconditions (e.g., that wave N-1 proposals are `implemented` before wave N begins).

## Tool Permissions

Read, Bash

## Prerequisites

Set `PYTHONPATH` so the `specbuilder` package is importable:

    for d in .cortex/skills . vendor; do
      [ -d "$d/specbuilder" ] && export PYTHONPATH="$d:${PYTHONPATH:-}" && break
    done

If the loop finds nothing, stop and tell the user SpecBuilder is not installed.

> **Windows:** File locking (`fcntl`) is unavailable on Windows. The exclusive lock that
> protects concurrent writes to the execution log (`checkpoint.py:47–48`, `55–56`) is
> silently skipped on Windows. Single-process sequential checkpoint use is safe; running
> parallel checkpoint commands against the same execution log on Windows is not protected.

## When to Use

Use checkpoint when implementing **2 or more proposals as a batch**. For a single proposal, invoke `implement-spec` directly — checkpoint adds overhead that is only justified for batches where partial failure recovery matters.

POC projects skip multi-module protocols; `checkpoint` is only applicable in full, strict, and prototype projects.

Use `--status` to check current batch progress. It reads from the execution log — if the log is missing, it returns an empty result and prints guidance to run `--init` first.

## Stopping Points

- ⚠️ **Wave precondition failure** — `--wave N` (for N > 1) verifies that all proposals in wave N-1 have `status: implemented` before recording. If preconditions fail, the command exits non-zero. Do NOT skip this check.
- ⚠️ **`--complete` confirmation gate** — `--complete` updates proposal frontmatter in place and moves files to `proposals/implemented/`. These mutations are not automatically reversible. Always pass `--confirm` explicitly; do not script around the flag.
- ⚠️ **Execution-log completeness check** — `--wave N` (for N > 1) also verifies that wave N-1 has been recorded in the execution log (`completed_waves ≥ N-1`), in addition to checking frontmatter statuses. If wave N-1 was never recorded via `--wave N-1`, the command exits non-zero even if all wave N-1 proposals have `status: implemented` in frontmatter. Both conditions must hold (`checkpoint.py:374–381`).
- ⚠️ **Incomplete-waves block in `--complete`** — `--complete` verifies that all waves in the batch have been recorded in the execution log before finalizing. If any wave is unrecorded, it exits non-zero and lists the missing wave numbers. This check fires after the `--confirm` gate and is independent of it — passing `--confirm` does not bypass it (`checkpoint.py:431–441`).

## Commands

### Initialize a batch

    python3 -m specbuilder checkpoint --init EXT-055,EXT-056,EXT-057

- Accepts a comma-separated list of proposal IDs (minimum 2 required)
- Reads each proposal's `depends_on` frontmatter to build a dependency graph
- Topologically sorts proposals into waves using Kahn's algorithm; circular dependencies raise an error
- Writes `.specbuilder/execution-log.md` with the full wave plan
- **Exits with an error if an execution log already exists** — pass `--force` to overwrite
- Prints wave breakdown and total wave count to stdout

> **Side effect:** `--init` also appends `.specbuilder/execution-log.md` to `.gitignore`
> (via `_ensure_gitignored()`, `checkpoint.py:230`) if that entry is not already present.
> This prevents the execution log from being committed to version control. The write is
> idempotent; running `--init` a second time does not add duplicate entries.

    python3 -m specbuilder checkpoint --status
    python3 -m specbuilder checkpoint --status --json

- Re-derives batch state from the execution log and current proposal frontmatter
- Prints progress (completed / total waves), per-wave proposal statuses, and the next unblocked wave
- **If no execution log exists**, returns an empty result and prints guidance to run `--init` first — it cannot re-derive state without the log
- **`--json`** — emits structured JSON output instead of human-readable text; useful for CI pipelines or scripting. The JSON object contains keys `batch` (list of all proposal IDs in the batch), `waves` (list of wave lists, each a list of proposal ID strings), `completed_waves` (int — number of waves recorded in the execution log), `proposal_statuses` (dict mapping proposal ID → current frontmatter status string), and `next_wave` (list of proposal IDs in the next incomplete wave, or null if all waves are complete). Passing `--json` without `--status` emits an advisory warning to stderr and is otherwise ignored.

### Record a completed wave

    python3 -m specbuilder checkpoint --wave N [--results TEXT]

- `N` — wave number (1-indexed); must be within range of the initialized batch
- `--results TEXT` — optional verification results string appended to the log (e.g., "908 passed, ruff clean")
- For wave > 1: verifies all proposals in wave N-1 have `status: implemented` in frontmatter before recording; exits non-zero on failure
- Prints the next wave's proposals on success

### Finalize the batch

    python3 -m specbuilder checkpoint --complete

- Updates all batch proposal statuses to `implemented` in their frontmatter files
- Moves proposal files from `spec/architecture/proposals/` to `spec/architecture/proposals/implemented/`
- Regenerates `spec/manifest.json` and `spec/README.md` via a direct internal call to `generate_index.generate()`
- Appends a completion marker to the execution log
- Exits non-zero if no execution log is found

## Standard Batch Workflow

    # 1. Initialize — creates execution log and prints wave plan
    python3 -m specbuilder checkpoint --init EXT-055,EXT-056,EXT-057,EXT-058

    # 2. For each wave:
    python3 -m specbuilder checkpoint --status        # confirm prerequisites and current wave
    # dispatch implement-spec for each proposal in the current wave
    python3 -m specbuilder checkpoint --wave N --results "tests pass, ruff clean"

    # 3. After all waves are complete:
    python3 -m specbuilder checkpoint --complete      # finalize and regenerate manifest

    # 4. Sync AC files (not called by --complete; run separately):
    python3 -m specbuilder sync-ac-files

**Programmatic recovery** (automatic): if the session is interrupted, run `checkpoint --status` to re-derive batch state from the execution log and committed proposal frontmatter statuses. No user action is required — this is the primary recovery path.

**Cortex memory** (optional manual step): you may paste a prior session's checkpoint summary into the new session context to restore human-readable progress notes. This is a separate manual workflow step and is not read by `--status` or any checkpoint command.

## Integration with implement-spec

The orchestrator invokes checkpoint before dispatching each `implement-spec` wave:

1. `checkpoint --init` establishes the dependency-ordered wave plan
2. `checkpoint --status` confirms which wave is next and that blocking proposals are `implemented`
3. `implement-spec` is dispatched for each proposal in the current wave (independent proposals within a wave can run in parallel)

> **Concurrency limit:** `MAX_CONCURRENT_AGENTS` in `config.py:162` controls the maximum number of agents dispatched per wave. Default is `0` (unlimited — defers to CoCo's native scheduling limits). Override directly in `config.py` if a hard cap is needed.
4. `checkpoint --wave N` records the wave result before starting the next wave

The wave number from `checkpoint --status` tells `implement-spec` which batch to resume from after a session interruption. The execution log is the source of truth — `--status` reads the log to determine wave plan and progress.

## Recovery from Interruption

If the session crashes mid-batch:

1. Run `python3 -m specbuilder checkpoint --status` — reads the execution log to show current wave plan and progress
2. The next unblocked wave is shown; resume by dispatching `implement-spec` for those proposals
3. Record the resumed wave with `checkpoint --wave N` once complete, then continue

If the execution log is missing (e.g., `.specbuilder/` was deleted), `--status` returns an empty result. Re-run `python3 -m specbuilder checkpoint --init --force` with the original proposal list to regenerate the wave plan before resuming. The `--force` flag is required when an execution log already exists from a prior `--init` run. Without it, `--init` exits with an error if a log file is present, to prevent accidentally overwriting a batch in progress.

## Recovery from --complete Partial Failure

If `--complete --confirm` exits with an error or crashes mid-loop, some proposals may have
been moved to `spec/architecture/proposals/implemented/` while others remain in their
original location.

To determine what was already processed:

1. Check which files are present under `spec/architecture/proposals/implemented/` — these
   were successfully moved.
2. Check which proposal files have `status: implemented` in frontmatter — these were
   successfully updated.

To complete the batch manually after locating all proposals:

    python3 -m specbuilder generate-manifest

After regenerating the manifest, also append the completion marker to the execution log so
that `--status` reflects the completed state:

    printf '\n## Batch Complete (%s)\n' "$(date -u +%Y-%m-%dT%H:%M)" \
      >> .specbuilder/execution-log.md

Without this step, `--status` permanently shows the batch as incomplete even though all
proposals have been processed and moved.

To roll back to the pre-`--complete` state:

    git restore spec/architecture/proposals/

This restores moved or modified proposal files to their committed state. The execution log
(`.specbuilder/execution-log.md`) is gitignored and must be regenerated with `--init
--force` if also lost.

## Used with multi-module protocol

`checkpoint-spec` is the execution-tracking layer for multi-module batch runs. When
orchestrating a set of proposals across multiple modules, see
[`refs/multi-module-protocol.md`](../../refs/multi-module-protocol.md) for the
batching strategy, module grouping rules, and inter-module dependency ordering.

The composition is:

- **`multi-module-protocol.md`** — governs the outer batch loop: which modules to
  group together, how to order them, and when to advance the batch to the next wave.
- **`checkpoint-spec`** — tracks inner execution state: which waves have been
  recorded, enforces per-wave preconditions, and provides `--status` visibility into
  batch progress. `--complete` is the gate that closes a batch run after all waves
  have been recorded.

In a multi-module batch, the orchestrator drives `--wave` invocations according to
the protocol's grouping rules; `checkpoint-spec` enforces that each wave is recorded
before the next begins. Neither file fully replaces the other — they compose.

## Output

- `.specbuilder/execution-log.md` — local batch state (gitignored); required for `--status` and `--wave`; re-run `--init` if lost
- Updated proposal frontmatter (`status: implemented`) after `--complete`
- Regenerated `spec/manifest.json` and `spec/README.md` after `--complete`

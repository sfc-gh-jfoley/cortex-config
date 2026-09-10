# Checkpoint Protocol

Use this protocol when implementing multiple proposals as a batch (2 or more) for resumption on failure.

## Before starting

```bash
python3 -m specbuilder checkpoint --init EXT-055,EXT-056,EXT-057,EXT-058,EXT-059,EXT-060
```

## After each wave completes

1. Run `specbuilder checkpoint --wave N` to record results
2. Run integration verification (full test suite + ruff + mypy), then commit wave results
3. Run `cortex memory remember "Wave N complete: [proposals]. Tests: X pass. Next: [proposals] unblocked."` — this is the primary cross-session handoff

## Before starting a new wave

1. Run `specbuilder checkpoint --status` to confirm prerequisites met
2. Verify all blocking proposals show `status: implemented` in manifest

## After all waves complete

```bash
python3 -m specbuilder checkpoint --complete
```

The execution log is local (`.specbuilder/execution-log.md`, gitignored). If the session crashes and the log is lost, `--status` returns an empty result — it cannot re-derive state without the log. Re-run `--init` with the original proposal list to regenerate the wave plan. The `cortex memory remember` calls bridge sessions.

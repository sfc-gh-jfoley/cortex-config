# Multi-Module Implementation Protocol

When the user requests implementing multiple modules ("implement all", "build everything accepted"):

1. Read `spec/manifest.json` to identify all modules with `status: accepted`
2. Build module-level dependency graph from `depends_on` fields in each module's frontmatter
3. Group independent modules into parallel batches (same topological sort as artifact batching)
4. For each batch of independent modules:
   a. Run `python3 -m specbuilder implement <module_num>` for each module to generate stubs + dispatch plan
   b. All modules share `impl/` for output and `.specbuilder/impl-status.json` (keyed by artifact path) for status
   c. Execute each module's implementation in parallel (each follows the standard implement-spec protocol)
   d. Barrier: wait for all modules in the batch to complete
   e. **Verify before next batch:** Run acceptance tests for each completed module. Fix failures before proceeding. Do NOT start the next batch with unverified modules — dependent modules build on prior output.
5. For dependent modules, execute in dependency order (next batch starts only after prior batch is verified)
6. Report combined status across all modules

**Concurrency note**: Apply the `MAX_CONCURRENT_AGENTS` cap globally across all parallel modules. Default: `0` (unlimited — defers to CoCo's native agent limits). The cap is configured via `MAX_CONCURRENT_AGENTS` in the SpecBuilder skill
configuration (default: 0, unlimited). If 3 modules each have 2 artifacts in their first batch, that's 6 agents — subdivide to stay within the configured cap.

## Checkpoint layer

Multi-module batches must be managed through the checkpoint layer to maintain wave ordering
and resumability across sessions.

Before beginning a multi-module implementation batch:

1. **Initialize:** `python3 -m specbuilder checkpoint --init`
   Reads all `depends_on` graphs, builds a topological wave plan, and writes the execution
   log to `.specbuilder/execution-log.md`. Also appends the log to `.gitignore`.

2. **Record wave completion:** `python3 -m specbuilder checkpoint --wave N`
   Records completion of wave N in the execution log. Verifies that all wave N-1 proposals
   have `status: implemented` before recording.

3. **Finalize batch:** `python3 -m specbuilder checkpoint --complete`
   Finalises the entire batch: updates proposal frontmatter to `implemented`, moves proposal
   files to `proposals/implemented/`, regenerates `spec/manifest.json` and `spec/README.md`,
   and appends a completion marker to the execution log.

See `skills/checkpoint-spec/SKILL.md` for the full protocol, stopping points, and recovery
procedures.

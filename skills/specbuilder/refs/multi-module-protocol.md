# Multi-Module Implementation Protocol

When the user requests implementing multiple modules ("implement all", "build everything accepted"):

1. Read `spec/manifest.json` to identify all modules with `status: accepted`
2. Build module-level dependency graph from `depends_on` fields in each module's frontmatter
3. Group independent modules into parallel batches (same topological sort as artifact batching)
4. For each batch of independent modules:
   a. Run `python3 -m specbuilder implement <module_num>` for each module to generate stubs + dispatch plan
   b. All modules share `impl/` for output and `.specbuilder/impl-status.json` (keyed by module ID) for status
   c. Execute each module's implementation in parallel (each follows the standard spec-implement protocol)
   d. Barrier: wait for all modules in the batch to complete
   e. **Verify before next batch:** Run acceptance tests for each completed module. Fix failures before proceeding. Do NOT start the next batch with unverified modules — dependent modules build on prior output.
5. For dependent modules, execute in dependency order (next batch starts only after prior batch is verified)
6. Report combined status across all modules

**Concurrency note**: Apply the `MAX_CONCURRENT_AGENTS` cap (from `config.py`) globally across all parallel modules. If 3 modules each have 2 artifacts in their first batch, that's 6 agents — subdivide to stay within the configured cap.

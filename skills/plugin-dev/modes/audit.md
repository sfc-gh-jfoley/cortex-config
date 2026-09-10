# Plugin Dev — Audit Mode

Inspect an existing plugin tree against the RC checklist. Report violations with concrete fixes.

---

## Phase 1 — Ingest the Plugin Tree

1. Ask for the plugin directory path if not already provided
2. Run: `find <plugin-root> -type f | sort` — capture full file list
3. Read `.cortex-plugin/plugin.json` — capture manifest
4. Identify which RCs likely apply (from manifest contents — `mcpServers` present → RC-A; `hooks` → RC-D/E/F; `skills` with `setup.sh` → RC-C; etc.)
5. Proceed to Phase 2

---

## Phase 2 — Automated Checks

Run every check. Mark each PASS / FAIL / SKIP (with reason).

### A1 — Manifest exists
**Check:** `.cortex-plugin/plugin.json` exists in the plugin root
**Fix if FAIL:** Create `.cortex-plugin/plugin.json` with at minimum `{"name": "...", "version": "1.0.0", "skills": ["./"]}`

### A2 — No load-bearing root `.mcp.json` (RC-A)
**Check:** Either no root `.mcp.json` exists, OR `mcpServers` is also declared in `plugin.json`
**SKIP if:** no MCP servers anywhere
**Fix if FAIL:** Move `mcpServers` block from `.mcp.json` into `.cortex-plugin/plugin.json`. The root `.mcp.json` is silently dropped by `cortex plugin publish`.

### A3 — MCP server scripts inside plugin tree (RC-A)
**Check:** For each entry in `plugin.json` `mcpServers`, the `args` path is a `${CORTEX_PLUGIN_ROOT}/...` reference pointing to a file that exists in the tree
**SKIP if:** no `mcpServers`
**Fix if FAIL:** Move the script into the plugin tree and update the manifest path

### A4 — Hook scripts inside plugin tree with `${CORTEX_PLUGIN_ROOT}` (RC-D/RC-E/RC-F)
**Check:** For each hook in `hooks/hooks.json` (or `plugin.json` hooks), the command contains `${CORTEX_PLUGIN_ROOT}` and the referenced file exists in the tree
**SKIP if:** no hooks declared
**Fix if FAIL:** Move hook scripts inside the tree; update commands to use `${CORTEX_PLUGIN_ROOT}`

### A5 — Hook runtime on base PATH (RC-E)
**Check:** For each hook command, the runtime invoked is `node`, `python3`, `sh`, `bash`, or an absolute path. Flag any runtime that is typically installed only via `nvm`, `pyenv`, `brew`, or similar that sets up PATH only in interactive shells
**SKIP if:** no hooks
**Judgment required:** some runtimes (e.g. `uv`) are typically in `/usr/local/bin` or system PATH; others (e.g. a custom binary) are not. Flag anything unusual.

### A6 — Stage limits (RC-A through RC-G)
**Check:** Count files (`find <root> -type f | wc -l`) — must be ≤ 50
**Check:** No single file > 2 MB
**Check:** Total tree size ≤ 10 MB (rough: `du -sh <root>`)
**Fix if FAIL:** Remove compiled bytecode (`__pycache__/`, `.pyc`), large data files, or split into multiple plugins

### A7 — Prerequisites documented in manifest description (RC-B/RC-C)
**Check:** If `mcpServers` is present and uses `uv`, or if `setup.sh` exists — does the manifest `description` mention required runtimes and any setup step?
**Fix if FAIL:** Add prerequisites and "run SETUP.md after install" to the manifest `description` field

### A8 — Setup completeness signal (RC-C)
**Check:** If `setup.sh` (or equivalent installer) exists — is there a session-start hook that checks for a completion signal (env var, marker file, or directory) and warns if absent?
**SKIP if:** no setup step
**Fix if FAIL:** Add the install-completeness self-check to the session-start hook (see RC-C in `reference/plugin-scenarios.md`)

### A9 — Session-start hook for rule injection (RC-D)
**Check:** If the plugin ships a skill with operating rules that need to be active each session — is there a `SessionStart` hook that injects them?
**Judgment required:** not all plugins need this; flag only if the plugin has a skill with behavioral directives that wouldn't otherwise be loaded

### A10 — Per-session state keyed by session_id (RC-F)
**Check:** If a `UserPromptSubmit` hook (or similar mid-session hook) writes state to a file — is that file path or name keyed by `session_id` from hook stdin?
**SKIP if:** no stateful mid-session hooks
**Fix if FAIL:** Key the state file by `session_id`, e.g. `/tmp/my-plugin-state-${session_id}.json`

### A11 — No root hidden files carrying load-bearing config
**Check:** `ls -la <plugin-root>` — are there root-level hidden files (other than `.cortex-plugin/`) that the plugin depends on at runtime?
**Fix if FAIL:** Move config into the manifest or a non-hidden path inside the tree

---

## Phase 3 — Judgment Flags

These can't be automatically verified — flag them for the user to confirm.

| Flag | What to ask |
|---|---|
| **RC-G read-only** | "The plugin exposes MCP tools. Are all tools purely read/query operations (no create/update/delete/exec)? If yes, the server is safe to auto-approve." |
| **RC-E PATH coverage** | "Hook commands use [runtime]. Is this runtime available in the base PATH on the target machine (i.e. installed system-wide, not via nvm/pyenv/brew shell setup)?" |
| **RC-C setup needed** | "Does this plugin require any one-off setup after install (env vars, directories, external auth)? If so, is there a SETUP.md and a bundled setup.sh?" |
| **Companion skill coverage** | "If the plugin ships an MCP, is there a companion skill that documents edge-case recovery guidance so MCP responses can stay lean?" |

---

## Phase 4 — Report

Produce a structured report:

```
## Plugin Audit: <plugin-name>

### Automated Checks
| Check | Status | Notes |
|---|---|---|
| A1 Manifest exists | PASS | |
| A2 No root .mcp.json | PASS | |
| A3 MCP scripts in tree | SKIP | No mcpServers |
...

### Judgment Flags
- [ ] RC-G read-only: **confirm needed** — plugin exposes X MCP tools; verify no mutations
...

### Violations (requires fix)
<for each FAIL>
**<check name>**: <what was found>
Fix: <concrete action>

### Recommendations
<optional: non-blocking improvements>
```

For each FAIL, provide the concrete fix inline — don't just state the problem. Reference the
applicable RC scenario card in `reference/plugin-scenarios.md` for full context.

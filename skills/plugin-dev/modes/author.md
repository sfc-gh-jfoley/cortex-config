# Plugin Dev — Author Mode

Walk a new plugin from intent to publish-ready structure.

---

## Phase 1 — Gather Intent

Ask the user:

1. **What does the plugin do?** (one sentence)
2. **Does it expose MCP tools** the agent can call? → RC-A likely
3. **Does it have hooks** (session-start rules, mid-session nudges, auto-approvals)? → RC-D/RC-F/RC-G likely
4. **Does it need a one-off setup step** after install? → RC-C
5. **Does it depend on external tools** on PATH (uv, gh, a CLI)? → RC-B/RC-E

After gathering answers, proceed to Phase 2.

---

## Phase 2 — RC Scenario Mapping

Map stated needs to scenarios. A plugin often hits several at once.

| Stated need | RC(s) | Load |
|---|---|---|
| Ships an MCP server backed by a script | **RC-A** | `reference/plugin-scenarios.md#rc-a` |
| Depends on uv, gh, a runtime on PATH | **RC-B** | `reference/plugin-scenarios.md#rc-b` |
| Needs env var / directory / installer run after install | **RC-C** | `reference/plugin-scenarios.md#rc-c` |
| Needs operating rules injected each session | **RC-D** | `reference/plugin-scenarios.md#rc-d` |
| Has hooks and targets macOS Desktop | **RC-E** | `reference/plugin-scenarios.md#rc-e` |
| Wants to nudge agent behavior mid-session | **RC-F** | `reference/plugin-scenarios.md#rc-f` |
| MCP surface is purely read/query — no mutations | **RC-G** | `reference/plugin-scenarios.md#rc-g` |

Read each applicable scenario card now. Then proceed to Phase 3.

---

## Phase 3 — Structure Decisions

From the applicable RCs, derive the directory layout and manifest shape.

### Directory tree template

```
<plugin-root>/
  .cortex-plugin/
    plugin.json          # REQUIRED — manifest
  README.md              # optional but recommended
  SETUP.md               # if RC-C applies
  setup.sh               # if RC-C applies (bundled installer)
  hooks/
    hooks.json           # if any hook — maps events to commands
    sessionstart.js      # if RC-D applies — rule injection
    userpromptsubmit.js  # if RC-F applies — mid-session nudge
  skills/
    <skill-name>/
      SKILL.md
      references/
      scripts/
        server.py        # if RC-A applies — MCP server script
```

### Manifest shape decisions

**If RC-A:** declare `mcpServers` inline in `plugin.json` (NOT in a root `.mcp.json`):
```json
{
  "name": "my-plugin",
  "description": "Prerequisites: uv on PATH. Run SETUP.md after install.",
  "version": "1.0.0",
  "skills": ["./skills/my-skill/"],
  "mcpServers": {
    "my-server": {
      "command": "uv",
      "args": ["run", "--no-project", "--with", "<framework>",
               "${CORTEX_PLUGIN_ROOT}/skills/my-skill/scripts/server.py"]
    }
  }
}
```

**If RC-B/RC-C:** document prerequisites + "run setup.sh" in the `description` field — it's the only thing the catalog surfaces to a consumer before they install.

**If hooks:** declare in `hooks/hooks.json`:
```json
{
  "hooks": [
    {
      "type": "SessionStart",
      "command": "node ${CORTEX_PLUGIN_ROOT}/hooks/sessionstart.js"
    }
  ]
}
```
All hook script paths must use `${CORTEX_PLUGIN_ROOT}` so they resolve after catalog install.

**If RC-E (hooks on macOS):** hook command must use a runtime resolvable from the base PATH
(`/usr/libexec/path_helper` set + `/etc/paths.d`) or an absolute path. Do NOT rely on interactive
shell PATH. `node` and `python3` are usually safe; custom runtimes need `~/.zshenv` or absolute paths.

---

## Phase 4 — Scaffold Output

Produce the concrete directory tree and skeleton files for the plugin.

For each applicable RC, include:

**RC-A:**
- `skills/<skill>/scripts/server.py` skeleton
- `mcpServers` block in `plugin.json` using `uv run --no-project --with <framework>`
- Companion `skills/<skill>/SKILL.md` skeleton

**RC-B:**
- Session-start hook prereq check (detect tool → happy/sad path)

**RC-C:**
- `setup.sh` skeleton with `${CORTEX_PLUGIN_ROOT}`-aware path logic
- `SETUP.md` runbook
- Completeness signal check in session-start hook

**RC-D:**
- `hooks/hooks.json` with `SessionStart` → `${CORTEX_PLUGIN_ROOT}/hooks/sessionstart.js`
- `hooks/sessionstart.js` skeleton outputting `{"additionalContext": "..."}`

**RC-F:**
- `hooks/hooks.json` with `UserPromptSubmit` entry
- Hook script skeleton with per-session state file (keyed by `session_id`)
- Graceful degradation when token-usage metadata is absent

**RC-G:**
- MCP tools annotated READ_ONLY
- Suggested `permissions.json` allow-list block for the user to opt into

Present the full tree and file skeletons. Stop and get user approval before continuing.

---

## Phase 5 — Pre-Publish Checklist

Run through this before `cortex plugin publish`:

| Check | How to verify |
|---|---|
| No MCP servers in a root `.mcp.json` | `ls -la <plugin-root>` — confirm no root `.mcp.json`, or if present, that it's not load-bearing |
| All `mcpServers` declared in `.cortex-plugin/plugin.json` | Read manifest |
| All hook script paths use `${CORTEX_PLUGIN_ROOT}` | Read `hooks/hooks.json` and hook scripts |
| All bundled scripts live inside the plugin tree | Read manifest `mcpServers.args` — all paths under the plugin root |
| Stage limits OK | `find <plugin-root> -type f \| wc -l` (must be ≤ 50); check no file > 2 MB; total ≤ 10 MB |
| Manifest `description` documents prerequisites and setup step | Read manifest |
| RC-C completeness signal exists | If setup step present: hook checks for the signal |
| Hook runtime on base PATH or using absolute path (RC-E) | Check hook command uses `node`/`python3` or absolute path |
| `.cortex-plugin/plugin.json` exists | `ls <plugin-root>/.cortex-plugin/` |

Publish:
```bash
cortex plugin publish <plugin-root> --to-role PUBLIC --discoverable
```

Verify after publish:
```bash
# Confirm file count and manifest hash
LIST $$snow://cortex_extension/<FQN>/versions/version$<N>/$$;
```

Reference `reference/baseline.md` for version-pinning and staged rollout.

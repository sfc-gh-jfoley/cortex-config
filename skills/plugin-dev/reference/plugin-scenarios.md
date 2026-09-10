# Plugin Scenarios — RC Reference Cards

Each card: the scenario shape, required structure, and the key pitfall.
A plugin often hits multiple RCs at once — check all that apply.

---

## RC-A — Ships Executable Runtime Code (MCP Server)

**Applies when:** plugin exposes an MCP server backed by a bundled script.

**Required structure:**
1. Script lives **inside the plugin tree** (e.g. `skills/<skill>/scripts/server.py` or anywhere under the root)
2. Manifest declares the server **inline in `.cortex-plugin/plugin.json`** under `mcpServers`, referencing it as:
   `"${CORTEX_PLUGIN_ROOT}/<path-to-script>"`
3. Launch via `uv` to avoid a separate install step:
   ```
   uv run --no-project --with <framework> ${CORTEX_PLUGIN_ROOT}/.../server.py
   ```
   `uv` resolves the framework at first launch and caches it.

**Companion skill pattern:** ship a skill alongside the MCP in the same plugin. MCP responses stay lean; edge-case recovery guidance lives in the co-shipped skill.

**Key pitfall:** A root-level `.mcp.json` is silently dropped by `cortex plugin publish`. It works for a locally-registered dev plugin but ships zero servers from the catalog. Inline `mcpServers` in the manifest is the only declaration that survives publish.

**First-launch note:** `uv` fetching the framework can exceed the startup timeout — reload once if so.

---

## RC-B — Host Prerequisites (Runtimes, Tools on PATH)

**Applies when:** plugin invokes an external tool that is not plugin-specific (a runtime, `uv`, `gh`, etc.).

**Required structure:**
1. Document prerequisites in the manifest `description` (catalog surfaces it, does not enforce it)
2. Carry a **session-start hook** that:
   - Happy path (prereq present) → proceed silently
   - Sad path (prereq absent) → warn + point to install instructions

**Key pitfall:** Prerequisites are completely unenforced by the catalog. A consumer without them gets no gate — the plugin silently fails or mis-operates. Make it fail loudly instead (see RC-C).

---

## RC-C — One-Off Setup Step (Plugin-Specific)

**Applies when:** plugin needs plugin-specific state before it works — env var set, directory created, bundled installer run. Unlike RC-B this only makes sense *after* the plugin is loaded.

**Required structure:**
1. **Self-contained installer inside the tree** (e.g. `setup.sh` at plugin root) — verbatim upload means it travels with the plugin
2. **Post-install runbook** (`SETUP.md`) telling the human to run the installer, with path resolved via `${CORTEX_PLUGIN_ROOT}`
3. **Prerequisite + "run setup" step documented in manifest `description`**
4. **Install-completeness self-check:** setup step sets a completion signal (env var, marker file, or created directory); a session-start hook checks for it — if absent, injects "setup is incomplete, run setup.sh"
5. **Rational defaults:** incomplete-install state should fail loudly, not silently mis-operate

**Key pitfall:** Without the completeness signal check, a catalog install that skipped setup looks loaded but is inert. Silent failure is worse than loud failure.

---

## RC-D — Rule Injection Each Session

**Applies when:** plugin's correct behavior depends on operating rules being in force each session (plugins don't carry persistent `AGENTS.md`-style rules).

**Required structure:**
1. Declare `SessionStart` hook in `hooks/hooks.json` mapping to a **bundled** hook script referenced via `${CORTEX_PLUGIN_ROOT}`
2. Hook script writes JSON to stdout:
   - Inject rules: `{"additionalContext": "<rules>"}`
   - No-op: `{"continue": true}`
3. The `additionalContext` text becomes the plugin's operating rules for the session

**Health self-test:** the injected context appears at session start — if you see the plugin's header/acknowledgement, the hook fired. Silence means RC-E.

**Key pitfall:** If the hook can't run (runtime not found — see RC-E), it fails silently and the context is absent.

---

## RC-E — Hook PATH / Env Var Resolution

**Applies when:** any hook-bearing plugin whose hook needs a tool, PATH entry, or env var that may not be in the base shell environment.

**Required structure:**
On macOS, Desktop-spawned hooks run in a **non-interactive shell that sources only `~/.zshenv`** — NOT `.zshrc` or `.zprofile`. PATH is the base path from `/etc/paths(.d)`.

Therefore:
- Put required PATH entries in `~/.zshenv` (the plugin's `setup.sh` can add them), **OR**
- Have the hook resolve the tool by **absolute path** itself

**Key pitfall:** Anything defined only in `.zshrc` or `.zprofile` is invisible to hooks. The failure is silent — looks like "the plugin just isn't working."

---

## RC-F — Proactive Behavioural Reminders (Stateful Mid-Session Hook)

**Applies when:** plugin needs to nudge the agent toward intended behaviours repeatedly during a session, not just at startup.

**Pattern:**
- Hook `UserPromptSubmit` (or a tool-use event) instead of (or in addition to) `SessionStart`
- Keep a small per-session state file (keyed by `session_id` from hook stdin) to track progress between firings
- Hook stdout `{"additionalContext": "<nudge>"}` injects the reminder into the next turn

**Available events:**

| Event | When | Can inject context? |
|---|---|---|
| `SessionStart` | session opens | yes |
| `UserPromptSubmit` | user submits prompt | yes (blocks) |
| `PostToolUse` | after tool finishes | yes |
| `PreToolUse` | before tool executes | yes (blocks) |
| `Stop` | agent turn ends | no (can force continuation) |
| `SessionEnd` | session closes | no — use for cleanup only |
| `PreCompact` | before compaction | no |
| `SubagentStop` | sub-agent turn ends | no |
| `Notification` | notification sent | no |
| `PermissionRequest` | before permission dialog | yes (blocks) |
| `Setup` | initial env setup | yes (blocks) |

**Hook metadata on stdin:** `session_id`, `cwd`, `hook_event_name` (all events); `tool_name`/`tool_input` (tool events); `tool_response` (PostToolUse); `prompt` (UserPromptSubmit). Token/context usage has been observed but is not in the public reference — degrade gracefully if absent.

**Key pitfalls:**
- Token/context usage is best-effort — don't assume it's always present
- Per-session state must be keyed by `session_id` or it bleeds across concurrent sessions
- Nudges steer; they don't compel

---

## RC-G — Read-Only MCP (Safe to Auto-Approve)

**Applies when:** plugin ships an MCP and the tool surface is structurally read-only — designed so the entire server can be blanket auto-approved.

**Required structure:**
1. Expose **only** read/query operations (list / get / show / search / log) — keep create/update/delete/exec entirely off this server
2. Annotate tools as read-only to advertise intent (e.g. `READ_ONLY` annotation on each tool)
3. Suggest auto-approval via either:
   - `~/.snowflake/cortex/permissions.json` allow-list: `{"allow": ["mcp__<server>__<tool>", …]}`
   - A `PermissionRequest` hook that auto-allows a matcher over the server's namespace

**Key pitfalls:**
- The guarantee holds only if the surface is genuinely read-only — one mutating tool defeats the whole point
- Auto-approve is a consumer setting; a plugin can ship a *suggested* allow-list but the user still opts in
- Read-only is a design contract, not enforced by the annotation alone

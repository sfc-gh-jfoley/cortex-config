# Plugin Dev — Baseline Reference

Mechanics that apply regardless of scenario. The scenario files (RC-A through RC-G) build on these.

---

## Upload Model — Verbatim, Flat, No Wrapper

`cortex plugin publish <path>` uploads the entire plugin tree verbatim and flat — where a file
sits on disk is where it lands in the extension. No added wrapper.

**One exception: root-level hidden files are NOT uploaded.** Files like `.mcp.json` at the
plugin root are silently dropped. Only `.cortex-plugin/` is carried. This is the most common
footgun — see RC-A.

*Re-confirm flat/verbatim behavior after CLI upgrades before relying on it.*

---

## Registration Forms

| Form | What it is | Live-linked? |
|---|---|---|
| `[settings]` | Dev-path entry in `settings.json` `plugins[]` | Yes — edits reflect immediately |
| `[managed]` | Copy under `<plugins-dir>/<name>/` | No — dev edits don't propagate until re-copied |

A catalog install always produces the `[managed]` form (a copy, not a live link).

---

## FQN & Naming

- FQN shape: `DB.SCHEMA.NAME` — for personal plugins: `USER$<YOURUSER>.SKILL_SHARING.<PLUGIN_NAME>`
- Extension name derives from the manifest `name` field, uppercased, `-`/whitespace → `_`
  - Example: `my-plugin` → `MY_PLUGIN`
- The folder name is NOT used — only the manifest `name` determines the extension name

---

## Stage Limits

| Limit | Value |
|---|---|
| Max files | 50 |
| Max file size | 2 MB |
| Max total | 10 MB |

A plugin bundling heavy dependencies can hit the file-count limit first.

---

## Command Surface

| Command | Purpose |
|---|---|
| `cortex plugin publish <path> --to-role PUBLIC --discoverable` | Upload tree as Cortex Extension; re-runs increment version |
| `cortex plugin install <FQN>` | Install into host; produces `[managed]` copy |
| `cortex plugin install '<FQN>' --cortex-extension-version 'version$N' --force` | Install specific version (quote both FQN and version) |
| `cortex plugin list` | Show registered plugins + registration form |
| `cortex plugin update <FQN>` | Move install to latest certified, else default version |
| `cortex plugin uninstall <name>` | Remove managed copy |
| `cortex plugin unpublish <FQN>` | Stop sharing |

Inspect shipped files:
```
LIST $$snow://cortex_extension/<FQN>/versions/version$<N>/$$;
```
Always use a committed `version$N`, not `live`.

---

## Version Resolution

Precedence (verified CLI v1.1.52): **explicit `--cortex-extension-version`** > **latest CERTIFIED** > **DEFAULT_VERSION** (defaults to `LAST`/newest)

| Command | Resolves to |
|---|---|
| `install <FQN>` (no version) | Latest certified, else default version |
| `install <FQN> --cortex-extension-version version$N` | Exact version |
| `update <FQN>` | Latest certified, else default version — MOVES the install |
| `check` | Same resolution target — reports `[update available]` when installed differs |

**Staged beta rollout:**
1. Pin stable as default: `ALTER CORTEX EXTENSION <FQN> SET DEFAULT_VERSION = 'version$<stable>';`
2. Certify stable (certified overrides default for both `install` and `update`)
3. Publish beta — it becomes newest but default stays on stable
4. Testers opt in via version-pinned deeplink: `coco://install_catalog_uri?uri=snow://skill_catalog/<FQN>/versions/version$<beta>/`
5. Do NOT certify the beta while testing
6. Promote by moving default to beta

---

## Manifest

`.cortex-plugin/plugin.json` — the only structurally required piece.

Key fields:
- `name` — determines extension name (uppercased, `-` → `_`)
- `description` — surfaced in catalog; use it to document prerequisites
- `version`
- `skills` — array of skill paths to register
- `mcpServers` — MCP server declarations (must be inline here, NOT in `.mcp.json`)
- `hooks` — (or declared separately in `hooks/hooks.json`)

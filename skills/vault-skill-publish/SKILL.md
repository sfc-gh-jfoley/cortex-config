---
name: vault-skill-publish
description: "Load a personal skill from the vault, apply changes, audit for bloat, publish to the catalog, and back up to git. Use when: load a skill from the vault, publish this skill to the catalog, republish a vault skill, audit skill bloat, clean stray vault artifacts, push skills to gitlab and github. Triggers: load <skill> from the vault, publish this skill to the snowhouse catalog, are these skills becoming bloated, any other vault artifacts that need cleaning, push to gitlab and github"
version: 1.0.0
---

# Skill: vault-skill-publish

Owns the lifecycle of a *personal* vault skill: resolve it by path, edit it, audit for bloat, publish to the catalog, and back up to git. It deliberately does not own catalog share mechanics or plugin-structure checks — those are delegated, because restating them here guarantees drift the moment the upstream skill changes.

## When to Use

- Someone asks to "load <skill> from the vault" and make changes to it.
- A personal skill needs publishing or republishing to the Cortex catalog.
- You need to check whether vault skills have grown bloated or accumulated stray files.
- Edits are done and the session needs to back up to GitLab + GitHub.

## When NOT to Use

- **Authoring a brand-new skill.** Use `skill-development` for the initial scaffold; come here once it exists in the vault.
- **Publishing a bundled or Snowflake-shipped skill.** This skill only touches `.my_skill`-marked personal items.
- **Running the actual share SQL.** Delegate to `share-skill-and-plugin` (below) — it owns the Cortex Extension DDL and visibility options.
- **Auditing a plugin's structure.** Delegate to `plugin-dev` audit mode.

## Vault Layout

The vault lives at `~/.snowflake/cortex/vault` — a symlink to `~/src/github/cortex-config`, which is a
**public** repo. See `## Repo Split` for what that means before committing anything. Under it:

- `skills/` — personal skills, one directory each, named by the skill.
- `plugins/` — personal plugins / toolkits.
- A `.my_skill` (empty) file inside a directory marks it as **personal**. The git backup and merge rules key off this marker; without it the directory is treated as upstream and skipped on personal backup.

Disambiguation that matters: a vault skill may share a *name* with a bundled skill. Resolving to the bundled one silently edits or publishes the wrong file — so resolve by **path under the vault**, never by name alone. Read `SKILL.md` from the resolved path before trusting it is the one you want.

Also: XO's memory store `~/.snowflake/cortex/xocortex` is colloquially "the vault" in XO docs. It is a separate thing. This skill never touches it.

## Workflow

### Phase 1 — Resolve by path

Turn the requested name into an explicit path: `~/.snowflake/cortex/vault/skills/<name>/SKILL.md`. Confirm the `.my_skill` marker exists in that directory. If the marker is absent, stop — the item is upstream, not personal, and editing it will be overwritten on the next merge.

Report the resolved absolute path back to the user before any edit. The name-collision failure is silent: a wrong-file edit looks identical to a right-file edit until someone publishes or diffs.

### Phase 2 — Apply changes

Make the requested edits to `SKILL.md` and any support files. Then check dependencies:

- If the skill is meant to be **standalone** (shareable to others), it must not require a toolkit sibling at load time. A `Prerequisites:` block pointing at a vault-only toolkit turns a shareable skill into a broken one for anyone who installs it alone. Either inline the needed context or mark the dependency as optional.
- If the skill *is* a vault-only companion (never shared), that dependency is fine — note it.

### Phase 3 — Bloat audit

Run the audit below. Fix anything flagged before publishing; bloat ships to every consumer and is harder to walk back after a publish.

### Phase 4 — Publish (STOPPING POINT)

Publish or republish by **delegating** to the bundled `share-skill-and-plugin` skill: invoke it with the `skill` tool and follow its instructions for the share SQL and visibility options. Do not hardcode Cortex Extension DDL here — it drifts.

Before running the share: confirm the **target** (which skill object) and the **visibility** (account / org / public) explicitly with the user. Republishing over a prior version to the wrong visibility is not silently reversible — anyone who already installed it keeps the old visibility, and you cannot force-revoke it from here.

### Phase 5 — Git backup (STOPPING POINT)

**The two repos are not mirrors, and one of them is public.** Read `## Repo Split` below
before running anything in this phase.

Follow the procedure in `~/.snowflake/cortex/AGENTS.md` → "GitLab Backup", targeting the
**private** repo:

1. Find `.my_skill` directories → stage to `/tmp`.
2. `rsync --delete` into `~/src/gitlab/cortex-config/skills/`.
3. Export memories to `~/src/gitlab/cortex-config/memory/` — private repo only.
4. `git add -A && commit && push` **in `~/src/gitlab/cortex-config`**.

Do not improvise a different staging method — the `rsync --delete` step is what keeps the
backup free of deleted-skill ghosts.

Committing in the vault itself is a *separate, public* action. Treat it as publishing:
run `git status` there first, confirm only skill/plugin content is staged, and get explicit
sign-off. `git add -A` in the vault is the specific command to avoid, because it will pick
up whatever untracked private material happens to be sitting in the tree.

## Repo Split

| | `~/src/github/cortex-config` | `~/src/gitlab/cortex-config` |
|---|---|---|
| Visibility | **public** | private |
| Role | the live vault (symlink target) | backup |
| Contents | skills, plugins, scripts, `AGENTS.md` | the above **plus** `memory/`, `hooks/`, `rules/`, `settings.json` |

The vault you edit is the public repo. That is deliberate — skills are meant to be
shareable — but it means memories, hooks, rules, and local settings deliberately live only
in the private backup, and must not be copied into the vault tree to "keep them in sync".

Memories in particular can contain customer names, account identifiers, and revenue
figures gathered during real engagements. A push that carries `memory/` to the public remote
is a data disclosure, not a tidy-up, and rewriting public history afterwards does not
un-publish it. This is why Phase 5 targets the private repo by default and treats any commit
in the vault as a publish decision needing sign-off.

## Bloat Audit

Run this checklist against the skill directory and the vault root:

- **SKILL.md over ~500 lines.** Context is shared with every conversation that loads the skill, so an oversized file crowds out the work it is meant to help. Split into `reference/` files loaded on demand.
- **Content duplicated from a delegated toolkit.** If the skill already delegates to a toolkit (catalog share, plugin audit, SV lifecycle), restating that content here means two copies drift. Delete the duplicate; keep only the pointer.
- **Stale reference files.** Files in `reference/`, `templates/`, or `assets/` no longer linked from `SKILL.md`. They load into context on glob/scan and waste budget. Remove or re-link them.
- **Stray non-skill artifacts in the vault root.** Scratch notes, exports, or one-off dumps sitting next to real skills. They confuse the backup globs and get committed accidentally. Move them out or delete them.
- **Triggers so broad they fire on unrelated requests.** A trigger like "publish" or "update" matches any session. Narrow triggers to the specific noun (skill name, "vault skill", "snowhouse catalog") so the skill does not hijack other work.

## Stopping Points

1. **After Phase 1** — confirm the resolved path is the intended file before editing. The name-collision failure is silent.
2. **Before Phase 4** — confirm the catalog target and visibility with the user. Wrong-visibility republish is not cleanly reversible for already-installed consumers.
3. **Before any `git push`** — a push is the hard-to-reverse step. Show the staged diff **and the
   resolved remote URL**, and say whether that remote is public or private, then wait for explicit
   confirmation. Naming the remote matters more than naming the branch here: the private backup and the
   public vault have near-identical paths and identical repo names, so "pushed cortex-config" is
   ambiguous in exactly the case where being wrong is unrecoverable.

## Output

Report back, in order:

1. **Resolved path** — the absolute `SKILL.md` path confirmed in Phase 1.
2. **Change summary** — what was edited and why (concise; not a diff dump).
3. **Bloat-audit findings** — each item above as pass/flag with a one-line reason.
4. **Publish confirmation** — the access link the delegated `share-skill-and-plugin` skill returns, plus the visibility chosen.
5. **Pushed commit** — the commit hash, the remote URL, and whether it was the public or private repo;
   or "not pushed — awaiting confirmation" if Phase 5 was stopped at the gate.

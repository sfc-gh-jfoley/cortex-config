# cortex-config — Shared Skill Vault

A shared library of Cortex Code skills and plugins. Anyone on the team can publish skills here, pull in what's useful, and contribute fixes or improvements back.

---

## How it works

**This repo is a library, not a live environment.**
Your local vault (`~/.snowflake/cortex/vault/`) is what Cortex Code actually runs. You selectively pull skills from this repo into your vault — you don't have to take everything.

```
GitHub repo  ←→  your local clone  →  your vault  →  Cortex Code
(shared)          (git working copy)    (what runs)
```

---

## One-time setup

```bash
git clone git@github.com:sfc-gh-jfoley/cortex-config.git ~/src/github/cortex-config
```

No further config needed. Pull in skills as you want them (see below).

---

## Pulling skills into your vault

**One skill or plugin:**
```bash
# Single plugin
rsync -a ~/src/github/cortex-config/plugins/semantic-view-toolkit/ \
         ~/.snowflake/cortex/vault/plugins/semantic-view-toolkit/

# Single standalone skill
rsync -a ~/src/github/cortex-config/skills/agent-architect/ \
         ~/.snowflake/cortex/vault/skills/agent-architect/
```

**Everything at once** (skips anything you've marked personal with `.my_skill`):
```bash
for dir in ~/src/github/cortex-config/plugins/*/; do
  name=$(basename "$dir")
  dst=~/.snowflake/cortex/vault/plugins/$name
  [ -f "$dst/.my_skill" ] && echo "SKIP $name (personal)" && continue
  rsync -a --delete "$dir" "$dst/" && echo "PULLED $name"
done
```

Always `git pull` the repo first to get latest changes before syncing to vault.

---

## Contributing a skill

1. Branch from main: `git checkout -b feature/my-skill-name`
2. Add your skill under `plugins/` (for toolkits) or `skills/` (for standalone skills)
3. Update the skill-loader registry: `skill-loader/SKILL.md` — add an entry for your skill
4. Push and open a PR against `main`

**Registry entry is required.** Without it, skill-loader can't find the skill.

---

## Repo structure

```
plugins/                  # Multi-skill toolkits
  cortex-agent-toolkit/   #   Agent lifecycle: build → eval → optimize
  semantic-view-toolkit/  #   SV lifecycle: discover → DDL → eval → optimize
  ...

skills/                   # Standalone skills
  agent-architect/
  semantic-view-ddl/      # LEGACY — use semantic-view-toolkit/skills/sv-ddl
  ...

skill-loader/
  SKILL.md                # Registry — all skills listed here with vault paths
```

---

## Protecting personal customizations

If you've customized a skill locally and don't want it overwritten when pulling updates, drop an empty marker file:

```bash
touch ~/.snowflake/cortex/vault/plugins/my-custom-skill/.my_skill
```

The bulk pull script skips any dir with this marker. Skills in the shared repo should **not** have `.my_skill` markers.

---

## Workflow summary

| What you want to do | How |
|---|---|
| Get a coworker's new skill | `git pull` → rsync that plugin to vault |
| Share a skill you built | Branch → add to `plugins/` or `skills/` + update registry → PR |
| Fix a bug in a shared skill | Branch → edit → PR (everyone gets it on next pull) |
| Keep a local customization safe | Mark with `.my_skill`, won't be overwritten |
| Try a skill before committing | Work in vault directly, push to repo when satisfied |

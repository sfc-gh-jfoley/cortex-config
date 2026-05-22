# rule-governance

Cortex Code CLI plugin for managing rules and memories in the ctx system.

## Install

```bash
cortex plugin install https://gitlab.com/joey.foley/rule-governance.git
```

## Skills

| Skill | Use When |
|---|---|
| `rule-governance:rule-creator` | Creating a new rule |
| `rule-governance:rule-reviewer` | Reviewing a rule for quality |
| `rule-governance:rule-loader` | Loading rules into a session |
| `rule-governance:bulk-rule-reviewer` | Auditing all rules at once |
| `rule-governance:memory-organizer` | Cleaning up duplicate/stale memories |

## Workflow

```
rule-creator (author new rule)
  → rule-reviewer (quality check)
  → rule-loader (load into session)

bulk-rule-reviewer (periodic audit of all rules)
memory-organizer (periodic cleanup of memories)
```

## Prerequisites

See [PREREQUISITES.md](./PREREQUISITES.md).

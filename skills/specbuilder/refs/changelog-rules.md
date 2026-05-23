# Changelog Rules

Before completing a session that modified source code (`specbuilder/src/` or `specbuilder/skills/`),
you MUST create a changelog entry if ANY of the following are true:

- New features were added (sub-skills, commands, config options)
- Bugs were fixed that affect behavior
- Workflow rules changed (verification gates, lifecycle rules)
- Multiple proposals were implemented in a single session

Do NOT create a changelog entry for:
- Pure test additions (no behavioral change)
- Documentation-only edits
- Cosmetic linting/formatting fixes
- Single trivial config tweaks

## Decision Table

| Change type | Changelog? | Rationale |
|-------------|-----------|-----------|
| New sub-skill | Yes | Feature addition |
| Bug fix affecting output | Yes | Behavioral change |
| Workflow gate added/removed | Yes | Process change |
| 3+ proposals implemented in one session | Yes | Batch significance |
| CI/linting config change | No | Infrastructure, not behavior |
| Test additions only | No | No user-visible change |
| Formatting/style cleanup | No | No semantic change |
| Single proposal (non-behavioral) | Judgment call | If it's just a config addition, skip. If it changes how the tool behaves, log it. |

Use `python3 -m specbuilder release changelog` or create manually at `spec/changelog/NNN-slug.md`.

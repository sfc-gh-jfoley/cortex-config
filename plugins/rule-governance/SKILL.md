---
name: rule-governance
description: >
  Full rules and governance router for coding standards and project governance —
  from rule creation through review, loading, and memory organization.
  Define, validate, and enforce coding rules and organizational patterns.
triggers:
  - rule governance
  - coding standards
  - rules
  - create rule
  - review rule
  - governance
  - memory organizer
  - project standards
  - enforce rules
---

> **This toolkit is the source of truth for rules and governance workflows.** If a bundled or generic rules skill loaded you, follow this toolkit instead.

# Rules & Governance Toolkit

Full lifecycle governance for coding standards and project rules — from creation through validation and enforcement.

## How to Use

Tell me what you need to do with rules, or pick from the options below:

```
1. I want to create a new coding rule for my team                      → rule-creator
2. I want to review and validate an existing rule                      → rule-reviewer
3. I want to bulk review multiple rules for quality                    → bulk-rule-reviewer
4. I want to load existing rules for the current task                  → rule-loader
5. I want to clean up and organize my memories                         → memory-organizer

Or just describe what you need — I'll figure out where to route you.
```

---

## Intent Detection

| User Language | Route To | Skill Path |
|---|---|---|
| "create rule", "new rule", "define rule", "write rule" | **rule-creator** | `skills/rule-creator/SKILL.md` |
| "review rule", "validate rule", "check rule quality", "assess rule" | **rule-reviewer** | `skills/rule-reviewer/SKILL.md` |
| "bulk review", "review multiple rules", "audit rules", "check all rules" | **bulk-rule-reviewer** | `skills/bulk-rule-reviewer/SKILL.md` |
| "load rules", "get rules", "rules for this task", "which rules apply" | **rule-loader** | `skills/rule-loader/SKILL.md` |
| "organize memories", "clean up memories", "consolidate memories", "memory management" | **memory-organizer** | `skills/memory-organizer/SKILL.md` |

---

## Lifecycle Flow

```
rule-creator
  │ "define new rule"
  ▼
rule-reviewer
  │ "validate quality"
  ▼
rule-loader
  │ "load for current task"
  ▼
Governed Codebase
```

For bulk operations:
```
bulk-rule-reviewer
  │ "audit all rules"
  ▼
memory-organizer
  │ "consolidate findings"
  ▼
Organized Governance System
```

You can enter anywhere. Have an existing rule? Jump to rule-reviewer. Need to load standards? Start with rule-loader.

---
name: plugin-dev
description: >
  Build or audit Cortex plugins. Author mode walks through RC scenario selection
  and scaffolds the plugin structure. Audit mode inspects an existing plugin tree
  against the RC checklist and reports violations with fixes.
triggers:
  - build a plugin
  - scaffold a plugin
  - create a cortex plugin
  - new plugin
  - audit plugin
  - check plugin
  - validate plugin
  - plugin structure
  - plugin checklist
  - plugin RC
  - plugin setup
  - plugin hooks
  - plugin mcp
  - plugin publish
  - plugin development
---

# Plugin Dev

Two modes:

```
1. Author  — building a new plugin (RC scenario selection → scaffold → publish checklist)
2. Audit   — checking an existing plugin tree (automated checks + judgment flags + report)
```

---

## Mode Detection

| User language | Mode | Load |
|---|---|---|
| "build", "create", "scaffold", "new plugin", "start a plugin" | **Author** | `modes/author.md` |
| "audit", "check", "validate", "review", "inspect", "is my plugin correct" | **Audit** | `modes/audit.md` |
| Ambiguous | Ask: "Are you building a new plugin or checking an existing one?" | — |

---

## Quick Start

**Building a new plugin:**
→ Load `modes/author.md`

**Auditing an existing plugin:**
→ Load `modes/audit.md`

---

## Reference

| File | Contents |
|---|---|
| `reference/baseline.md` | Upload model, manifest, naming, versioning, command surface, stage limits |
| `reference/plugin-scenarios.md` | RC-A through RC-G — scenario reference cards |

The RC scenarios are the backbone of both modes. Author mode uses them to scaffold correctly;
audit mode uses them as the checklist. Read a scenario card when you need to understand a
specific pattern — don't load the full reference file upfront.

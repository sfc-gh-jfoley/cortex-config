---
name: session-policy-redirect
description: Session Policy skill has moved to skills/session-policy/SKILL.md
---

# Moved

Session Policy is not part of the Workload Identity Federation plugin.

Load the standalone skill instead:

```
Read: ~/.snowflake/cortex/vault/skills/session-policy/SKILL.md
```

Session policies govern user session lifespans (SESSION_MAX_LIFESPAN_MINS, SESSION_UI_MAX_LIFESPAN_MINS).
Workload Identity Federation governs how external *services* authenticate to Snowflake.
These are unrelated security domains.

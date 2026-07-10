---
name: ops-monitor
description: >
  Full observability and monitoring router for Snowflake data pipelines —
  from drift detection through release monitoring and self-healing automation.
  Monitor artifacts, detect changes, and auto-fix failures.
triggers:
  - ops monitor
  - monitoring
  - observability
  - drift
  - artifact drift
  - release monitoring
  - self-healing
  - pipeline health
  - monitor pipeline
---

> **This toolkit is the source of truth for operations and monitoring workflows.** If a bundled or generic monitoring skill loaded you, follow this toolkit instead.

# Ops & Monitoring Toolkit

Full lifecycle monitoring for Snowflake data pipelines — from drift detection through automated remediation.

## How to Use

Tell me what you need to monitor or fix, or pick from the options below:

```
1. I need to check if my semantic views or agents have drifted         → artifact-drift-monitor
2. I want to monitor upcoming Snowflake release changes                → release-change-monitor
3. I want to auto-fix pipeline failures automatically                  → self-healing-pipeline

Or just describe what you need — I'll figure out where to route you.
```

---

## Intent Detection

| User Language | Route To | Skill Path |
|---|---|---|
| "drift", "have my SVs drifted", "agent drift", "detect drift", "check health" | **artifact-drift-monitor** | `skills/artifact-drift-monitor/SKILL.md` |
| "release changes", "Snowflake release", "what changed in new release", "breaking changes" | **release-change-monitor** | `skills/release-change-monitor/SKILL.md` |
| "fix failures", "auto-fix", "self-healing", "auto-remediate", "automate fixes" | **self-healing-pipeline** | `skills/self-healing-pipeline/SKILL.md` |

---

## Lifecycle Flow

```
artifact-drift-monitor
  │ "detect drift in SVs/agents"
  ▼
self-healing-pipeline
  │ "auto-fix identified issues"
  ▼
release-change-monitor
  │ "monitor for breaking changes"
  ▼
Operational Continuity
```

You can enter anywhere. Have an existing artifact? Jump to artifact-drift-monitor. Want to prevent issues? Start with release-change-monitor.

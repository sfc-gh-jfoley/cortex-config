# ops-monitor

Cortex Code CLI plugin for operational monitoring and self-healing.

## Install

```bash
cortex plugin install https://gitlab.com/joey.foley/ops-monitor.git
```

## Skills

| Skill | Use When |
|---|---|
| `ops-monitor:release-change-monitor` | Checking what changed in recent Snowflake releases |
| `ops-monitor:artifact-drift-monitor` | Detecting drift in deployed Cortex artifacts |
| `ops-monitor:self-healing-pipeline` | Auto-fixing broken pipelines |

## Workflow

```
release-change-monitor → detect breaking changes
  └── artifact-drift-monitor → check if your artifacts are affected
       └── self-healing-pipeline → auto-fix broken pipelines
```

## Prerequisites

See [PREREQUISITES.md](./PREREQUISITES.md).

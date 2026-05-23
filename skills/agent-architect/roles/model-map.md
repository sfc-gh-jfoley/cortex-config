# Model Map

Right-size models per role. Not everything needs Opus.

## Assignments

> Model names below use aliases from `~/.snowflake/cortex/vault/LLMs.md`. Run `update-llms.sh` to refresh. The resolved values shown are current as of last update.

| Role | Model ID | Rationale |
|---|---|---|
| **Architect** | `claude-opus-4-7` (`current_opus`) | Complex reasoning: plan synthesis, cross-team consistency, decision records, escalation judgment |
| **Researcher** | `claude-sonnet-4-6` (`current_sonnet`) | Fast read-only exploration. Doesn't need deep reasoning — gathers facts, reports structure |
| **Security Architect** | `claude-sonnet-4-6` (`current_sonnet`) | Checklist-driven structured output. Security patterns are well-defined — Sonnet handles them correctly |
| **Worker** | `claude-sonnet-4-6` (`current_sonnet`) | Code generation + TDD loop. Sonnet is strong at implementation given clear specs |
| **Tester** | `claude-sonnet-4-6` (`current_sonnet`) | Spec verification with structured output. Doesn't need creative reasoning |
| **Team Architect** | `claude-sonnet-4-6` (`current_sonnet`) | Executes a pre-defined charter from the Primary Architect. Charter scope is bounded — Primary already did cross-team synthesis and decomposition |

## When to Override

Upgrade a role to Opus when:
- **Worker on MAJOR_CHANGE task** — touches shared interfaces, auth logic, or cross-team contracts
- **SecArch on cryptographic/auth code** — subtle vulnerabilities need deeper reasoning
- **Researcher on architecture questions** — "what's the right approach?" vs "what files exist?"
- **Team Architect on large charter (>7 tasks) or cross-team contract tasks** — elevated scope warrants deeper reasoning

Downgrade to Haiku when:
- **Researcher on simple file discovery** — "find all .py files in src/"
- **Tester on config/DDL verification** — purely structural checks

## Usage

Every `Task()` call in the framework MUST include the `model` parameter:

```python
Task(
    subagent_type="general-purpose",
    model="claude-sonnet-4-6",   # current_sonnet — see LLMs.md
    ...
)
```

The Architect (this agent) runs on Opus by default — it's the session model.
Spawned teammates get their model explicitly set.

## Cost Impact

| Role | Typical invocations per project | Model | Relative cost |
|---|---|---|---|
| Architect | 1 (session) | Opus | 1x baseline |
| Researchers | 3-5 | Sonnet | 0.1x each |
| Workers | 5-15 | Sonnet | 0.1x each |
| SecArch | 5-15 | Sonnet | 0.1x each |
| Testers | 5-15 | Sonnet | 0.1x each |
| Team Architects | 1-4 (multi-team headless) | Sonnet | 0.1x each |

A typical 10-task project: 1 Opus session + ~40 Sonnet spawns.
Without right-sizing (all Opus): 10x+ cost increase with marginal quality gain.

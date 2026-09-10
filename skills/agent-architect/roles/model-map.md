# Model Map

Right-size models per role. Not everything needs the heaviest model.

## Assignments

> **Models are specified by capability tier, not by a fixed version string.** Pick a
> current model matching the tier from whatever your platform offers, and record the
> choice in `.agent-project/manifest.log` as `MODEL_<ROLE>=<value>` during Startup so
> the whole run is reproducible. Concrete IDs below are examples that were current
> when this was written — verify against your account before relying on them.
>
> **Two tiers must come from different model families** — see the Cross-family
> requirement below. That constraint is load-bearing, not a preference.

| Role | Capability tier | Example model | Rationale |
|---|---|---|---|
| **Architect** | Heavy reasoning, primary family | `claude-opus-4-7` | Complex reasoning: plan synthesis, cross-team consistency, decision records, escalation judgment |
| **Researcher** | Balanced, primary family | `claude-sonnet-4-6` | Fast read-only exploration. Doesn't need deep reasoning — gathers facts, reports structure |
| **Security Architect** | Heavy reasoning, **secondary family** | `openai-gpt-5.2` | Cross-model independence for security gates. A different family catches blind spots in auth/crypto patterns that the implementing family shares |
| **Worker** | Balanced, primary family | `claude-sonnet-4-6` | Code generation + TDD loop. Strong at implementation given clear specs |
| **Tester** | Balanced-to-heavy, **secondary family** | `openai-gpt-5.2` | Cross-model independence: catches Worker blind spots. Checklist-driven structured output |
| **Team Architect** | Balanced, primary family | `claude-sonnet-4-6` | Executes a pre-defined charter. Scope is bounded — Primary already did cross-team synthesis |

### Cross-family requirement (do not collapse to one family)

SecArch and Tester MUST run on a **different model family** than Worker and Architect.
Shared training means shared blind spots: a reviewer from the same family as the
implementer tends to miss the same things. If you only have one family available, say
so explicitly in the manifest (`MODEL_CROSS_FAMILY=unavailable`) and treat every gate
verdict as weaker evidence — do not pretend the gate is independent.

## When to Override

Upgrade a role to the heavy tier when:
- **Worker on MAJOR_CHANGE task** — touches shared interfaces, auth logic, or cross-team contracts
- **SecArch on cryptographic/auth code** — subtle vulnerabilities need deeper reasoning
- **Researcher on architecture questions** — "what's the right approach?" vs "what files exist?"
- **Team Architect on large charter (>7 tasks) or cross-team contract tasks** — elevated scope warrants deeper reasoning

Downgrade to the fast tier when:
- **Researcher on simple file discovery** — "find all .py files in src/"
- **Tester on config/DDL verification** — purely structural checks

## Usage

Every `Task()` call in the framework MUST include the `model` parameter, set to the
concrete model chosen for that tier at Startup:

```python
Task(
    subagent_type="general-purpose",
    model="<balanced-tier model recorded in manifest as MODEL_WORKER>",
    ...
)
```

The Architect runs on the heavy tier by default — it is the session model.
Spawned teammates get their model explicitly set.

## Cost Impact

| Role | Typical invocations per project | Tier | Relative cost |
|---|---|---|---|
| Architect | 1 (session) | Heavy | 1x baseline |
| Researchers | 3-5 | Balanced | 0.1x each |
| Workers | 5-15 | Balanced | 0.1x each |
| SecArch | 5-15 | Heavy, secondary family | ~0.15x each (slight premium for cross-model depth) |
| Testers | 5-15 | Balanced-to-heavy, secondary family | ~0.1x each |
| Team Architects | 1-4 (multi-team headless) | Balanced | 0.1x each |

A typical 10-task project: 1 heavy-tier session + ~30 balanced spawns + ~15 secondary-family
gate spawns. Without right-sizing (everything heavy): 10x+ cost increase with marginal
quality gain.

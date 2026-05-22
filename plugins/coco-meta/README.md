# coco-meta

Quality assurance toolkit for Cortex Code skill authors. If you build, modify, or maintain CoCo skills, this plugin catches regressions, non-determinism, and documentation drift before they reach users.

## Install

```bash
cortex plugin install sfc-gh-jfoley/coco-meta
```

## Skills

| Skill | What it does | When to use |
|-------|-------------|-------------|
| `coco-meta:skill-tester` | Run any skill 3x in parallel with fixture-injected inputs. Compare outputs for consistency, execute assertions, produce a scored PASS/FAIL report. | After modifying a skill — verify it still produces correct, consistent output. |
| `coco-meta:skill-timing` | Wall-clock + token instrumentation with intermediate checkpoints and anomaly detection (shortcut catching). | Measuring how long/expensive a skill is, comparing performance across models. |
| `coco-meta:prompt-determinism-tester` | Give the same prompt to 3 independent agents, compare their build plans across 6 dimensions, score convergence. | Before running a HOL or demo — verify attendees will get the same outcome. |
| `coco-meta:doc-reviewer` | Score docs against a 6-dimension rubric (accuracy, completeness, clarity, consistency, staleness, structure) on a 100-point scale. | Auditing READMEs, CONTRIBUTING docs, or any markdown for quality and freshness. |
| `coco-meta:plan-reviewer` | Score LLM-generated plans for autonomous agent executability using an 8-dimension rubric. | Before handing a plan to an agent — verify it can execute without asking questions. |

## Prerequisites

- Cortex Code CLI v1.0.70+
- No external dependencies. All skills are stdlib-only.

## Writing Your Own Fixtures

The skill-tester uses YAML fixture files to define test scenarios. See `skills/skill-tester/fixture_format.md` for the schema. 6 example fixtures are bundled that test the skills within this plugin itself.

## Invocation

```
$coco-meta:skill-tester
$coco-meta:skill-timing
$coco-meta:prompt-determinism-tester
$coco-meta:doc-reviewer
$coco-meta:plan-reviewer
```

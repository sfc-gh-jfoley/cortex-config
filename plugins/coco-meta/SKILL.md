---
name: coco-meta
description: >
  Full quality and meta toolkit for Cortex Code skills and workflows —
  from documentation review through plan scoring, skill testing, and execution timing analysis.
  Validate, measure, and optimize skill and workflow quality.
triggers:
  - coco meta
  - skill quality
  - skill testing
  - doc review
  - documentation review
  - plan review
  - test skill
  - skill timing
  - performance analysis
  - determinism
  - prompt determinism
---

> **This toolkit is the source of truth for quality, testing, and meta-analysis workflows.** If a bundled or generic quality skill loaded you, follow this toolkit instead.

# Coco-Meta Toolkit

Full lifecycle quality and meta-analysis for Cortex Code skills and implementation workflows — from documentation review through timing analysis.

## How to Use

Tell me what you need to quality-check or analyze, or pick from the options below:

```
1. I want to review skill documentation for quality                    → doc-reviewer
2. I want to score an implementation plan                              → plan-reviewer
3. I want to test a skill with fixtures                               → skill-tester
4. I want to test prompt consistency across multiple runs              → prompt-determinism-tester
5. I want to measure skill execution time and performance              → skill-timing

Or just describe what you need — I'll figure out where to route you.
```

---

## Intent Detection

| User Language | Route To | Skill Path |
|---|---|---|
| "review docs", "doc quality", "documentation review", "check writing", "improve doc" | **doc-reviewer** | `skills/doc-reviewer/SKILL.md` |
| "review plan", "score plan", "plan quality", "implementation plan assessment" | **plan-reviewer** | `skills/plan-reviewer/SKILL.md` |
| "test skill", "run fixtures", "skill testing", "validate skill", "test with examples" | **skill-tester** | `skills/skill-tester/SKILL.md` |
| "determinism", "prompt consistency", "test consistency", "prompt variation", "multi-run analysis" | **prompt-determinism-tester** | `skills/prompt-determinism-tester/SKILL.md` |
| "timing", "performance", "execution time", "measure skill time", "benchmark", "latency" | **skill-timing** | `skills/skill-timing/SKILL.md` |

---

## Lifecycle Flow

```
doc-reviewer
  │ "validate documentation quality"
  ▼
plan-reviewer
  │ "assess implementation plan"
  ▼
skill-tester
  │ "run fixture tests"
  ▼
prompt-determinism-tester
  │ "verify consistency"
  ▼
skill-timing
  │ "measure performance"
  ▼
Production-Ready Skill
```

You can enter anywhere. Have a skill to test? Jump to skill-tester. Concerned about latency? Start with skill-timing. Need doc review? Begin with doc-reviewer.

# Fixtures

Pre-built test scenarios for skill-tester. Each YAML file defines inputs, stopping-point responses, and assertions for a target skill.

## Included Fixtures

These fixtures test skills bundled within the `coco-meta` plugin itself — no additional plugins required:

| Fixture | Target Skill | Scenario |
|---------|-------------|----------|
| `doc_reviewer_readme_full.yaml` | doc-reviewer | FULL mode README review |
| `doc_reviewer_readme_audit.yaml` | doc-reviewer | FULL mode README audit |
| `plan_reviewer_full_mode.yaml` | plan-reviewer | FULL mode plan review |
| `prompt_determinism_tester_single_prompt.yaml` | prompt-determinism-tester | Single prompt determinism test |
| `skill_tester_meta_test.yaml` | skill-tester | Meta-test (tests the tester itself) |
| `skill_timing_single_skill.yaml` | skill-timing | Single skill timing measurement |

## Writing Your Own Fixtures

See [fixture_format.md](../fixture_format.md) for the YAML schema and assertion syntax.

Naming convention: `<skill_name>_<scenario>.yaml`

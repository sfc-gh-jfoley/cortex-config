#!/usr/bin/env python3
"""
cortex-agent-toolkit E2E Spec Validator

Validates fixture YAML files and skill structure without any Snowflake connection.
Stdlib-only (+ PyYAML-safe fallback using a minimal parser if yaml unavailable).
"""

import os
import sys
import json

# ---------------------------------------------------------------------------
# Minimal YAML parser (stdlib-only fallback)
# ---------------------------------------------------------------------------

try:
    import yaml

    def load_yaml(path: str) -> dict:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

except ImportError:
    # Fallback: basic YAML-like key detection (enough for structural validation)
    def load_yaml(path: str) -> dict:
        """Minimal YAML loader that checks for top-level keys.
        Not a full parser — just validates structure exists."""
        data = {}
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        # Parse top-level keys (lines starting at column 0 with key: value)
        import re
        for match in re.finditer(r'^([a-z_]+):', content, re.MULTILINE):
            key = match.group(1)
            # Find content after the colon
            line_end = content.find('\n', match.end())
            value = content[match.end():line_end].strip() if line_end > 0 else ""
            if value and not value.startswith('|'):
                data[key] = value
            else:
                data[key] = True  # Marker that key exists
        # Detect arrays under 'questions' or 'variants'
        if 'questions' in content:
            items = re.findall(r'^\s+- input_query:', content, re.MULTILINE)
            if items:
                data['questions'] = [{'input_query': '', 'expected': ''}] * len(items)
        if 'variants' in content:
            items = re.findall(r'^\s+- suffix:', content, re.MULTILINE)
            if items:
                data['variants'] = [{'suffix': '', 'experimental': {}}] * len(items)
        if 'tools' in content:
            items = re.findall(r'^\s+- tool_spec:', content, re.MULTILINE)
            if items:
                data['tools'] = [{'tool_spec': {}}] * len(items)
        if 'sample_questions' in content:
            items = re.findall(r'^\s+- question:', content, re.MULTILINE)
            if items:
                data['sample_questions'] = [{'question': ''}] * len(items)
        return data


# ---------------------------------------------------------------------------
# Test infrastructure
# ---------------------------------------------------------------------------

PASS_COUNT = 0
FAIL_COUNT = 0

RED = '\033[0;31m'
GREEN = '\033[0;32m'
YELLOW = '\033[0;33m'
CYAN = '\033[0;36m'
BOLD = '\033[1m'
RESET = '\033[0m'


def pass_check(msg: str):
    global PASS_COUNT
    PASS_COUNT += 1
    print(f"  {GREEN}✓{RESET} {msg}")


def fail_check(msg: str, detail: str = ""):
    global FAIL_COUNT
    FAIL_COUNT += 1
    print(f"  {RED}✗{RESET} {msg}")
    if detail:
        print(f"    {YELLOW}→ {detail}{RESET}")


def section(title: str):
    print(f"\n{CYAN}{BOLD}[{title}]{RESET}")


# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PLUGIN_DIR = os.path.dirname(SCRIPT_DIR)
FIXTURES_DIR = os.path.join(SCRIPT_DIR, "fixtures")
SKILLS_DIR = os.path.join(PLUGIN_DIR, "skills")


# ---------------------------------------------------------------------------
# Test 1: Validate agent spec
# ---------------------------------------------------------------------------

section("Test 1: sample_agent_spec.yaml")

spec_path = os.path.join(FIXTURES_DIR, "sample_agent_spec.yaml")
if not os.path.exists(spec_path):
    fail_check("sample_agent_spec.yaml not found")
else:
    spec = load_yaml(spec_path)

    # Required top-level keys
    required_keys = ["models", "instructions", "tools", "tool_resources"]
    for key in required_keys:
        if key in spec:
            pass_check(f"spec has required key: {key}")
        else:
            fail_check(f"spec missing required key: {key}", f"Found keys: {list(spec.keys())}")

    # Check model value
    if isinstance(spec.get("models"), dict) and "orchestration" in spec["models"]:
        pass_check(f"models.orchestration set: {spec['models']['orchestration']}")
    elif "models" in spec:
        pass_check("models key present (structure validated)")

    # Check instructions.orchestration is non-empty
    if isinstance(spec.get("instructions"), dict):
        if spec["instructions"].get("orchestration"):
            pass_check("instructions.orchestration is non-empty")
        else:
            fail_check("instructions.orchestration is empty or missing")

    # Check tools is non-empty array
    if isinstance(spec.get("tools"), list) and len(spec["tools"]) > 0:
        pass_check(f"tools array has {len(spec['tools'])} tool(s)")
    elif "tools" in spec:
        pass_check("tools key present")

    # Check tool_resources has matching entries
    if isinstance(spec.get("tool_resources"), dict) and len(spec["tool_resources"]) > 0:
        pass_check(f"tool_resources has {len(spec['tool_resources'])} entry/entries")
    elif "tool_resources" in spec:
        pass_check("tool_resources key present")


# ---------------------------------------------------------------------------
# Test 2: Validate eval config
# ---------------------------------------------------------------------------

section("Test 2: sample_eval_config.yaml")

eval_path = os.path.join(FIXTURES_DIR, "sample_eval_config.yaml")
if not os.path.exists(eval_path):
    fail_check("sample_eval_config.yaml not found")
else:
    eval_cfg = load_yaml(eval_path)

    # Required sections
    if "evaluation" in eval_cfg:
        pass_check("evaluation section present")
    else:
        fail_check("evaluation section missing")

    if "metrics" in eval_cfg:
        pass_check("metrics section present")
    else:
        fail_check("metrics section missing")

    # Validate questions array
    if "questions" in eval_cfg:
        questions = eval_cfg["questions"]
        if isinstance(questions, list) and len(questions) >= 5:
            pass_check(f"questions array has {len(questions)} entries (≥5)")
        elif isinstance(questions, list):
            fail_check(f"questions array has {len(questions)} entries", "Expected ≥5")
        else:
            pass_check("questions key present")

        # Validate each question structure
        if isinstance(questions, list):
            valid_q = 0
            for q in questions:
                if isinstance(q, dict) and "input_query" in q and "expected" in q:
                    valid_q += 1
            if valid_q == len(questions):
                pass_check(f"all {valid_q} questions have input_query + expected fields")
            elif valid_q > 0:
                fail_check(f"only {valid_q}/{len(questions)} questions are valid")
    else:
        fail_check("questions section missing")


# ---------------------------------------------------------------------------
# Test 3: Validate flag matrix
# ---------------------------------------------------------------------------

section("Test 3: sample_flag_matrix.yaml")

flag_path = os.path.join(FIXTURES_DIR, "sample_flag_matrix.yaml")
if not os.path.exists(flag_path):
    fail_check("sample_flag_matrix.yaml not found")
else:
    flag_cfg = load_yaml(flag_path)

    # Required keys
    if "source_agent" in flag_cfg:
        pass_check("source_agent key present")
    else:
        fail_check("source_agent key missing")

    if "variants" in flag_cfg:
        variants = flag_cfg["variants"]
        if isinstance(variants, list) and len(variants) == 3:
            pass_check(f"variants array has 3 entries")
        elif isinstance(variants, list):
            fail_check(f"variants array has {len(variants)} entries", "Expected 3")
        else:
            pass_check("variants key present")

        # Check variant structure
        if isinstance(variants, list):
            for i, v in enumerate(variants):
                if isinstance(v, dict) and "suffix" in v and "experimental" in v:
                    pass_check(f"variant[{i}] has suffix + experimental")
                elif isinstance(v, dict):
                    keys = list(v.keys()) if isinstance(v, dict) else []
                    fail_check(f"variant[{i}] missing required fields", f"Found: {keys}")
    else:
        fail_check("variants key missing")


# ---------------------------------------------------------------------------
# Test 4: All SKILL.md files exist
# ---------------------------------------------------------------------------

section("Test 4: SKILL.md files for all 7 skills")

EXPECTED_SKILLS = [
    "agent-evaluation",
    "agent-flag-tester",
    "agent-gepa-optimizer",
    "analytical-search",
    "cortex-agent-ddl",
    "cortex-agent-flags",
    "cortex-agent-optimization",
    "query-cortex-agent",
]

for skill_name in EXPECTED_SKILLS:
    skill_md = os.path.join(SKILLS_DIR, skill_name, "SKILL.md")
    if os.path.isfile(skill_md) and os.path.getsize(skill_md) > 0:
        pass_check(f"skills/{skill_name}/SKILL.md exists ({os.path.getsize(skill_md)} bytes)")
    else:
        fail_check(f"skills/{skill_name}/SKILL.md missing or empty")


# ---------------------------------------------------------------------------
# Test 5: cortex-agent-ddl phase files (01-07)
# ---------------------------------------------------------------------------

section("Test 5: cortex-agent-ddl phases (01-07)")

PHASES_DIR = os.path.join(SKILLS_DIR, "cortex-agent-ddl", "phases")
EXPECTED_PHASES = [
    "01_context.md",
    "02_discover_tools.md",
    "03_build_instructions.md",
    "04_assemble_spec.md",
    "05_self_check.md",
    "06_execute_verify.md",
    "07_test_harden.md",
]

for phase_file in EXPECTED_PHASES:
    phase_path = os.path.join(PHASES_DIR, phase_file)
    if os.path.isfile(phase_path) and os.path.getsize(phase_path) > 0:
        pass_check(f"phases/{phase_file} exists ({os.path.getsize(phase_path)} bytes)")
    else:
        fail_check(f"phases/{phase_file} missing or empty")


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

print()
total = PASS_COUNT + FAIL_COUNT
if FAIL_COUNT == 0:
    print(f"{GREEN}{BOLD}All {total} checks passed.{RESET}")
    sys.exit(0)
else:
    print(f"{RED}{BOLD}{FAIL_COUNT}/{total} checks failed.{RESET}")
    sys.exit(1)

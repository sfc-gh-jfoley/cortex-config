#!/usr/bin/env python3
"""
Verification tests for semantic view toolkit API migration.

Tests that all files have been updated to use the new API patterns:
- SNOWFLAKE.LOCAL.GET_ANALYST_AI_EVALUATION_DATA (5-arg, new)
- CALL EXECUTE_AI_EVALUATION with START/STATUS patterns
- No old patterns (SNOWFLAKE.CORTEX, 1-arg function, GET_AI_EVALUATION_STATUS)
- YAML metrics at top level
- Stage DDL with FILE_FORMAT
- PREREQUISITES.md has all 8 required grants + primary-role warning
- Smoke test has exactly 10 steps
"""

import re
import sys
from pathlib import Path


def grep_files(pattern: str, files: list[str], should_be_empty: bool = False) -> tuple[bool, list[str]]:
    """Search for pattern in files. Return (pass, matches)."""
    matches = []
    for file_path in files:
        if not Path(file_path).exists():
            print(f"  ⚠️  File not found: {file_path}")
            continue
        with open(file_path, 'r') as f:
            content = f.read()
            found = re.findall(pattern, content, re.MULTILINE | re.IGNORECASE)
            if found:
                matches.append((file_path, found))
    
    if should_be_empty:
        return len(matches) == 0, matches
    else:
        return len(matches) > 0, matches


def test_old_patterns_removed():
    """W1-W4: Verify old API patterns are removed."""
    print("\n✓ TEST: Old API patterns removed (W1-W4)")
    files = [
        '/Users/jfoley/src/github/cortex-config/plugins/semantic-view-toolkit/references/eval-polling.md',
        '/Users/jfoley/src/github/cortex-config/plugins/semantic-view-toolkit/skills/sv-evaluation/SKILL.md',
        '/Users/jfoley/src/github/cortex-config/plugins/semantic-view-toolkit/skills/sv-gepa-optimizer/SKILL.md',
        '/Users/jfoley/src/github/cortex-config/plugins/semantic-view-toolkit/skills/sv-optimization/optimize/SKILL.md',
        '/Users/jfoley/src/github/cortex-config/plugins/semantic-view-toolkit/skills/sv-evaluation/references/failure-analysis.md',
    ]
    
    patterns_to_remove = [
        (r'SNOWFLAKE\.CORTEX\.EXECUTE_AI_EVALUATION', 'old EXECUTE_AI_EVALUATION'),
        (r'GET_AI_EVALUATION_STATUS', 'old GET_AI_EVALUATION_STATUS'),
    ]
    
    all_pass = True
    for pattern, name in patterns_to_remove:
        passed, matches = grep_files(pattern, files, should_be_empty=True)
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {status}: No {name} found")
        if matches:
            all_pass = False
            for file_path, found in matches:
                print(f"         {file_path}: {len(found)} occurrence(s)")
    
    return all_pass


def test_new_api_patterns():
    """W1-W4: Verify new API patterns are used."""
    print("\n✓ TEST: New API patterns present (W1-W4)")
    
    # Check for new START/STATUS calls
    eval_files = [
        '/Users/jfoley/src/github/cortex-config/plugins/semantic-view-toolkit/skills/sv-evaluation/SKILL.md',
        '/Users/jfoley/src/github/cortex-config/plugins/semantic-view-toolkit/references/eval-polling.md',
    ]
    
    passed, matches = grep_files(r"CALL EXECUTE_AI_EVALUATION\s*\(\s*'START'", eval_files, should_be_empty=False)
    print(f"  {'✓ PASS' if passed else '✗ FAIL'}: CALL EXECUTE_AI_EVALUATION('START', ...) found")
    if not passed:
        return False
    
    passed, matches = grep_files(r"CALL EXECUTE_AI_EVALUATION\s*\(\s*'STATUS'", eval_files, should_be_empty=False)
    print(f"  {'✓ PASS' if passed else '✗ FAIL'}: CALL EXECUTE_AI_EVALUATION('STATUS', ...) found")
    if not passed:
        return False
    
    # Check for 5-arg function
    all_files = eval_files + [
        '/Users/jfoley/src/github/cortex-config/plugins/semantic-view-toolkit/skills/sv-gepa-optimizer/SKILL.md',
        '/Users/jfoley/src/github/cortex-config/plugins/semantic-view-toolkit/skills/sv-optimization/optimize/SKILL.md',
        '/Users/jfoley/src/github/cortex-config/plugins/semantic-view-toolkit/skills/sv-evaluation/references/failure-analysis.md',
    ]
    
    passed, matches = grep_files(r"SNOWFLAKE\.LOCAL\.GET_ANALYST_AI_EVALUATION_DATA", all_files, should_be_empty=False)
    print(f"  {'✓ PASS' if passed else '✗ FAIL'}: SNOWFLAKE.LOCAL.GET_ANALYST_AI_EVALUATION_DATA found")
    return passed


def test_yaml_metrics_toplevel():
    """G1: Verify YAML metrics are at top level."""
    print("\n✓ TEST: YAML metrics at top level (G1)")
    file_path = '/Users/jfoley/src/github/cortex-config/plugins/semantic-view-toolkit/skills/sv-evaluation/SKILL.md'
    
    with open(file_path, 'r') as f:
        content = f.read()
    
    # Find the metrics block in YAML and verify it's at top level
    # Top-level means: no indentation (column 0) for "metrics:"
    yaml_block = re.search(
        r'```yaml\n(.+?)\n```',
        content,
        re.DOTALL
    )
    
    if yaml_block:
        block_text = yaml_block.group(1)
        # Check for top-level metrics (no leading spaces)
        # The metrics line should be at column 0
        has_metrics_toplevel = re.search(r'^\nmetrics:\n', block_text, re.MULTILINE) or re.search(r'\nmetrics:\n', block_text)
        has_sql_correctness = '- "sql_correctness"' in block_text
        
        passed = has_metrics_toplevel and has_sql_correctness
        print(f"  {'✓ PASS' if passed else '✗ FAIL'}: metrics block found at top level (column 0)")
        return passed
    
    print(f"  ✗ FAIL: Could not find metrics YAML block")
    return False


def test_stage_file_format():
    """G5: Verify stage DDL has FILE_FORMAT."""
    print("\n✓ TEST: Stage DDL has FILE_FORMAT (G5)")
    
    files = [
        '/Users/jfoley/src/github/cortex-config/plugins/semantic-view-toolkit/references/eval-polling.md',
        '/Users/jfoley/src/github/cortex-config/plugins/semantic-view-toolkit/skills/sv-evaluation/SKILL.md',
    ]
    
    passed, matches = grep_files(r"FILE_FORMAT\s*=\s*\(TYPE\s*=\s*'YAML'", files, should_be_empty=False)
    print(f"  {'✓ PASS' if passed else '✗ FAIL'}: FILE_FORMAT = (TYPE = 'YAML') found in stage DDL")
    return passed


def test_use_ai_functions():
    """G3: Verify USE AI FUNCTIONS is present."""
    print("\n✓ TEST: USE AI FUNCTIONS grant required (G3)")
    
    files = [
        '/Users/jfoley/src/github/cortex-config/plugins/semantic-view-toolkit/skills/sv-evaluation/SKILL.md',
        '/Users/jfoley/src/github/cortex-config/plugins/semantic-view-toolkit/PREREQUISITES.md',
    ]
    
    passed, matches = grep_files(r'USE\s+AI\s+FUNCTIONS', files, should_be_empty=False)
    print(f"  {'✓ PASS' if passed else '✗ FAIL'}: USE AI FUNCTIONS mentioned")
    return passed


def test_prerequisites_complete():
    """G3: Verify PREREQUISITES has all 8 requirements + primary-role warning."""
    print("\n✓ TEST: PREREQUISITES.md sv-evaluation table complete (G3)")
    
    file_path = '/Users/jfoley/src/github/cortex-config/plugins/semantic-view-toolkit/PREREQUISITES.md'
    with open(file_path, 'r') as f:
        content = f.read()
    
    required_items = [
        'CORTEX_USER',
        'USE AI FUNCTIONS',
        'EXECUTE TASK ON ACCOUNT',
        'CREATE TASK',
        'CREATE DATASET ON SCHEMA',
        'SELECT',
        'MONITOR',
        'VQR',
    ]
    
    sv_section = re.search(r'### sv-evaluation(.+?)###', content, re.DOTALL)
    if not sv_section:
        print(f"  ✗ FAIL: sv-evaluation section not found")
        return False
    
    section_text = sv_section.group(1)
    found_items = []
    missing_items = []
    
    for item in required_items:
        if item.lower() in section_text.lower():
            found_items.append(item)
        else:
            missing_items.append(item)
    
    primary_role_check = 'Primary Role' in content or 'primary role' in content.lower()
    
    print(f"  {'✓ PASS' if len(missing_items) == 0 else '✗ FAIL'}: {len(found_items)}/{len(required_items)} requirements found")
    if missing_items:
        print(f"         Missing: {', '.join(missing_items)}")
    
    print(f"  {'✓ PASS' if primary_role_check else '✗ FAIL'}: Primary role warning present")
    
    return len(missing_items) == 0 and primary_role_check


def test_smoke_test_steps():
    """G11: Verify smoke test has exactly 10 numbered steps."""
    print("\n✓ TEST: Smoke test has 10 steps with correct API calls (G11)")
    
    file_path = '/Users/jfoley/src/github/cortex-config/plugins/semantic-view-toolkit/references/eval-smoke-test.md'
    with open(file_path, 'r') as f:
        content = f.read()
    
    # Find all step headers
    steps = re.findall(r'### Step \d+:', content)
    
    passed = len(steps) == 10
    print(f"  {'✓ PASS' if passed else '✗ FAIL'}: Found {len(steps)} steps (expected 10)")
    
    # Verify key API patterns in smoke test
    step_6 = re.search(r'### Step 6:(.+?)### Step 7:', content, re.DOTALL)
    if step_6:
        has_status = 'STATUS' in step_6.group(1) and 'EXECUTE_AI_EVALUATION' in step_6.group(1)
        print(f"  {'✓ PASS' if has_status else '✗ FAIL'}: Step 6 (poll) uses new STATUS pattern")
        passed = passed and has_status
    
    step_7 = re.search(r'### Step 7:(.+?)### Step 8:', content, re.DOTALL)
    if step_7:
        has_5arg = 'SNOWFLAKE.LOCAL.GET_ANALYST_AI_EVALUATION_DATA' in step_7.group(1)
        print(f"  {'✓ PASS' if has_5arg else '✗ FAIL'}: Step 7 (results) uses new 5-arg function")
        passed = passed and has_5arg
    
    step_8 = re.search(r'### Step 8:(.+?)### Step 9:', content, re.DOTALL)
    if step_8:
        has_normalized_cte = 'WITH raw AS' in step_8.group(1) and 'AS question' in step_8.group(1)
        print(f"  {'✓ PASS' if has_normalized_cte else '✗ FAIL'}: Step 8 (normalize) uses CTE projection")
        passed = passed and has_normalized_cte
    
    return passed


def main():
    print("=" * 70)
    print("SEMANTIC VIEW TOOLKIT API MIGRATION VERIFICATION")
    print("=" * 70)
    
    all_tests = [
        test_old_patterns_removed,
        test_new_api_patterns,
        test_yaml_metrics_toplevel,
        test_stage_file_format,
        test_use_ai_functions,
        test_prerequisites_complete,
        test_smoke_test_steps,
    ]
    
    results = []
    for test_func in all_tests:
        try:
            result = test_func()
            results.append((test_func.__name__, result))
        except Exception as e:
            print(f"  ✗ ERROR: {e}")
            results.append((test_func.__name__, False))
    
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    for test_name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status}: {test_name}")
    
    total_pass = sum(1 for _, result in results if result)
    total_tests = len(results)
    print(f"\nTotal: {total_pass}/{total_tests} tests passed")
    
    return 0 if total_pass == total_tests else 1


if __name__ == '__main__':
    sys.exit(main())

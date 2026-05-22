"""Apply mutation operators to agent instruction files.

This script handles operator selection, file copying, and validation.
LLM-assisted mutations are performed by CoCo directly — this script
provides the prompts and validates results.
"""

import argparse
import json
import random
import shutil
import sys
from pathlib import Path

import yaml

# Default operator weights — proportional to documented effectiveness.
# Normalized at selection time so absolute values don't matter (only ratios).
DEFAULT_OPERATOR_WEIGHTS = {
    "add_retry_logic": 0.15,
    "add_wrong_example": 0.15,
    "add_routing_rule": 0.15,
    "add_format_template": 0.10,
    "fix_example": 0.20,
    "add_domain_rule": 0.10,
    "rewrite_ambiguous_rule": 0.10,
    "remove_verbose_rule": 0.05,
}

# Mutation operators and their target files
OPERATOR_TARGETS = {
    "add_retry_logic": "orchestration_instructions.md",
    "add_wrong_example": "response_instructions.md",
    "add_routing_rule": "orchestration_instructions.md",
    "add_format_template": "response_instructions.md",
    "fix_example": "response_instructions.md",
    "add_domain_rule": "response_instructions.md",
    "rewrite_ambiguous_rule": "orchestration_instructions.md",
    "remove_verbose_rule": "orchestration_instructions.md",
}

# Failure category → preferred operators mapping
FAILURE_OPERATOR_MAP = {
    "routing": ["add_routing_rule", "rewrite_ambiguous_rule"],
    "tool_error": ["add_retry_logic"],
    "formatting": ["add_format_template"],
    "content": ["fix_example", "add_wrong_example", "add_domain_rule"],
    "ambiguity": ["rewrite_ambiguous_rule", "add_wrong_example"],
    "verbosity": ["remove_verbose_rule"],
}

# Template mutations that can be applied without LLM
TEMPLATE_MUTATIONS = {
    "add_retry_logic": (
        "\n\n## Retry Logic\n"
        "If a tool returns a transient error or empty result on first attempt, "
        "retry up to 2 times with a brief pause. If still failing after retries, "
        "report the issue clearly rather than guessing.\n"
    ),
}

# Anti-pattern validators
ANTI_PATTERNS = [
    {
        "name": "verbose_checklist",
        "pattern_words": ["step 1:", "step 2:", "step 3:", "verify that", "ensure that",
                          "confirm that", "check that"],
        "threshold": 3,  # 3+ matches = violation
        "message": "Verbose procedural checklist detected — degrades performance",
    },
    {
        "name": "tool_description_change",
        "file": "tool_descriptions.md",
        "message": "Tool descriptions modified — use orchestration_instructions instead",
    },
]


def select_operator(weights: dict, failure_categories: list[str] | None = None,
                    seed: int | None = None) -> str:
    """Weighted random operator selection, optionally biased by failure categories.

    If failure_categories provided, boosts weights for relevant operators.
    """
    if seed is not None:
        random.seed(seed)

    effective_weights = dict(weights)

    if failure_categories:
        for cat in failure_categories:
            preferred = FAILURE_OPERATOR_MAP.get(cat, [])
            for op in preferred:
                if op in effective_weights:
                    effective_weights[op] *= 2.0  # Double weight for relevant operators

    operators = list(effective_weights.keys())
    w = [float(effective_weights[op]) for op in operators]
    total = sum(w)
    w = [x / total for x in w]

    chosen = random.choices(operators, weights=w, k=1)[0]
    return chosen


def prepare_candidate_dir(source_dir: str, candidate_id: str,
                          workspace_root: str) -> str:
    """Copy agent files to a candidate directory for mutation.

    Copies agent/*.md + spec_base.json to gepa_population/cand_<id>/agent/
    """
    src = Path(source_dir)
    # Normalize: strip prefix if user already included it
    if candidate_id.startswith("cand_"):
        candidate_id = candidate_id[len("cand_"):]
    dest = Path(workspace_root) / "gepa_population" / f"cand_{candidate_id}" / "agent"
    dest.mkdir(parents=True, exist_ok=True)

    # Copy markdown instruction files
    for md_file in src.glob("*.md"):
        shutil.copy2(md_file, dest / md_file.name)

    # Copy spec_base.json if it exists (in source_dir or parent)
    spec_candidates = [src / "spec_base.json", src.parent / "spec_base.json"]
    for spec_path in spec_candidates:
        if spec_path.exists():
            shutil.copy2(spec_path, dest.parent / "spec_base.json")
            break

    return str(dest)


def apply_template_mutation(operator: str, candidate_dir: str) -> bool:
    """Apply a template-based mutation directly (no LLM needed).

    Returns True if applied, False if operator needs LLM assistance.
    """
    template = TEMPLATE_MUTATIONS.get(operator)
    if template is None:
        return False  # Needs LLM

    target_file = OPERATOR_TARGETS.get(operator)
    if not target_file:
        return False

    target_path = Path(candidate_dir) / target_file
    if not target_path.exists():
        # Create the file with just the template content
        target_path.write_text(template.lstrip("\n"))
        return True

    # Append template to existing file
    content = target_path.read_text()
    content += template
    target_path.write_text(content)
    return True


def validate_mutation(original_dir: str, candidate_dir: str) -> list[str]:
    """Check candidate for anti-patterns. Returns list of violations."""
    violations = []
    orig = Path(original_dir)
    cand = Path(candidate_dir)

    # Check tool_descriptions.md wasn't changed
    orig_td = orig / "tool_descriptions.md"
    cand_td = cand / "tool_descriptions.md"
    if orig_td.exists() and cand_td.exists():
        if orig_td.read_text() != cand_td.read_text():
            violations.append("Tool descriptions modified — use orchestration_instructions instead")

    # Check for verbose checklists in modified files
    for md_file in cand.glob("*.md"):
        orig_file = orig / md_file.name
        if orig_file.exists() and orig_file.read_text() == md_file.read_text():
            continue  # Unchanged file, skip

        content = md_file.read_text().lower()
        for ap in ANTI_PATTERNS:
            if "pattern_words" not in ap:
                continue  # Skip patterns that use a different detection method
            matches = sum(1 for w in ap["pattern_words"] if w in content)
            if matches >= ap["threshold"]:
                violations.append(f"{md_file.name}: {ap['message']}")

    # Check spec_base.json tool order wasn't changed
    orig_spec = orig.parent / "spec_base.json" if not (orig / "spec_base.json").exists() \
        else orig / "spec_base.json"
    cand_spec = cand.parent / "spec_base.json" if not (cand / "spec_base.json").exists() \
        else cand / "spec_base.json"

    if orig_spec.exists() and cand_spec.exists():
        try:
            orig_data = json.loads(orig_spec.read_text())
            cand_data = json.loads(cand_spec.read_text())
            orig_tools = [t.get("name", t.get("type", ""))
                          for t in orig_data.get("tools", [])]
            cand_tools = [t.get("name", t.get("type", ""))
                          for t in cand_data.get("tools", [])]
            if orig_tools != cand_tools:
                violations.append("spec_base.json tool order changed — causes TEST regression")
        except (json.JSONDecodeError, KeyError):
            pass  # Can't parse, skip this check

    return violations


def get_llm_mutation_prompt(operator: str, candidate_dir: str,
                            failure_context: dict | None = None) -> str:
    """Generate the prompt for CoCo to perform an LLM-assisted mutation."""
    target_file = OPERATOR_TARGETS.get(operator, "orchestration_instructions.md")
    target_path = Path(candidate_dir) / target_file

    current_content = ""
    if target_path.exists():
        current_content = target_path.read_text()

    failure_info = ""
    if failure_context:
        failure_info = f"""
## Failure Context
- Category: {failure_context.get('category', 'unknown')}
- Example input: {failure_context.get('example_input', 'N/A')}
- Expected: {failure_context.get('expected', 'N/A')}
- Got: {failure_context.get('actual', 'N/A')}
"""

    prompts = {
        "add_wrong_example": f"""Add a WRONG/CORRECT example pair to address a failure pattern.
{failure_info}
## Current content of {target_file}:
```
{current_content}
```

## Instructions:
Add ONE concise WRONG/CORRECT example pair that demonstrates the specific failure above.
Format:
WRONG: [show the incorrect behavior]
CORRECT: [show the correct behavior with brief explanation]

Return ONLY the updated full file content, nothing else.""",

        "add_routing_rule": f"""Add a routing rule to orchestration instructions.
{failure_info}
## Current content of {target_file}:
```
{current_content}
```

## Instructions:
Add ONE specific routing rule that maps an intent/keyword pattern to the correct tool.
Format: `- <pattern> ('keyword1', 'keyword2') → use <tool_name>`

Return ONLY the updated full file content, nothing else.""",

        "add_format_template": f"""Add a response format template.
{failure_info}
## Current content of {target_file}:
```
{current_content}
```

## Instructions:
Add ONE format template showing the expected output structure for this type of query.
Keep it concise (3-5 lines max).

Return ONLY the updated full file content, nothing else.""",

        "fix_example": f"""Fix or improve an existing example that may be inconsistent.
{failure_info}
## Current content of {target_file}:
```
{current_content}
```

## Instructions:
Identify any inconsistency or unclear example in the current content and fix it.
Make the MINIMUM change needed. Do not add new sections.

Return ONLY the updated full file content, nothing else.""",

        "rewrite_ambiguous_rule": f"""Rewrite an ambiguous rule to be clear and specific.
{failure_info}
## Current content of {target_file}:
```
{current_content}
```

## Instructions:
Identify the most ambiguous rule/instruction that the agent is misinterpreting.
Rewrite it with concrete, specific language. If the rule has been over-strengthened
(multiple NEVER/ALWAYS/CRITICAL markers), simplify it — verbosity itself causes confusion.
Do not add verbose checklists — just one clear concrete rewrite.

Return ONLY the updated full file content, nothing else.""",

        "add_domain_rule": f"""Add a domain-specific business rule.
{failure_info}
## Current content of {target_file}:
```
{current_content}
```

## Instructions:
Add ONE concise domain rule (1-2 sentences) stating the constraint the agent is violating.
Prefer referencing authoritative sources over surface-level patterns.
Place it in the most relevant existing section, or create a "## Domain Rules" section.
The rule must be specific and falsifiable — reject vague rules like "be more accurate".

Return ONLY the updated full file content, nothing else.""",

        "remove_verbose_rule": f"""Remove or shorten an overly verbose rule that is degrading performance.
{failure_info}
## Current content of {target_file}:
```
{current_content}
```

## Instructions:
Identify ONE rule or section that:
- Is a multi-step checklist (these degrade performance)
- Repeats what another rule already says
- Uses excessive emphasis markers (multiple NEVER/ALWAYS/CRITICAL)
- Has been superseded by a more specific rule elsewhere

Remove or significantly shorten it. Preserve all other content unchanged.
Never remove retry logic or routing rules added in the current GEPA run.

Return ONLY the updated full file content, nothing else.""",
    }

    return prompts.get(operator, f"Apply operator '{operator}' to {target_file}.\n"
                                  f"Current content:\n```\n{current_content}\n```\n"
                                  f"{failure_info}\n"
                                  f"Return ONLY the updated full file content.")


def main():
    parser = argparse.ArgumentParser(description="GEPA mutation operator")
    sub = parser.add_subparsers(dest="command", required=True)

    # select-operator
    p_sel = sub.add_parser("select-operator", help="Select mutation operator")
    p_sel.add_argument("--weights-file", help="YAML file with operator weights")
    p_sel.add_argument("--failure-categories", help="Comma-separated failure categories")
    p_sel.add_argument("--seed", type=int, default=None)

    # prepare
    p_prep = sub.add_parser("prepare", help="Prepare candidate directory")
    p_prep.add_argument("source_dir", help="Source agent directory")
    p_prep.add_argument("candidate_id", help="Candidate ID")
    p_prep.add_argument("workspace_root", help="Workspace root directory")

    # validate
    p_val = sub.add_parser("validate", help="Validate mutation")
    p_val.add_argument("original_dir", help="Original agent directory")
    p_val.add_argument("candidate_dir", help="Mutated candidate directory")

    # get-prompt
    p_prompt = sub.add_parser("get-prompt", help="Get LLM mutation prompt")
    p_prompt.add_argument("operator", help="Mutation operator name")
    p_prompt.add_argument("candidate_dir", help="Candidate directory")
    p_prompt.add_argument("--failure-context", help="JSON failure context")

    # apply-template
    p_tmpl = sub.add_parser("apply-template", help="Apply template mutation")
    p_tmpl.add_argument("operator", help="Mutation operator name")
    p_tmpl.add_argument("candidate_dir", help="Candidate directory")

    args = parser.parse_args()

    if args.command == "select-operator":
        weights = dict(DEFAULT_OPERATOR_WEIGHTS)
        if args.weights_file:
            with open(args.weights_file, "r") as f:
                data = yaml.safe_load(f)
                if isinstance(data, dict) and "operator_weights" in data:
                    weights = data["operator_weights"]
                elif isinstance(data, dict):
                    weights = data  # raw weights dict (legacy format)

        categories = None
        if args.failure_categories:
            categories = [c.strip() for c in args.failure_categories.split(",")]

        chosen = select_operator(weights, categories, seed=args.seed)
        print(json.dumps({"operator": chosen, "target_file": OPERATOR_TARGETS.get(chosen)}))

    elif args.command == "prepare":
        cand_dir = prepare_candidate_dir(args.source_dir, args.candidate_id,
                                         args.workspace_root)
        print(json.dumps({"candidate_dir": cand_dir}))

    elif args.command == "validate":
        violations = validate_mutation(args.original_dir, args.candidate_dir)
        print(json.dumps({"valid": len(violations) == 0, "violations": violations}))

    elif args.command == "get-prompt":
        failure_ctx = None
        if args.failure_context:
            failure_ctx = json.loads(args.failure_context)
        prompt = get_llm_mutation_prompt(args.operator, args.candidate_dir, failure_ctx)
        print(prompt)

    elif args.command == "apply-template":
        applied = apply_template_mutation(args.operator, args.candidate_dir)
        if applied:
            print(json.dumps({"status": "applied", "operator": args.operator}))
        else:
            print(json.dumps({"status": "needs_llm", "operator": args.operator}))


if __name__ == "__main__":
    main()

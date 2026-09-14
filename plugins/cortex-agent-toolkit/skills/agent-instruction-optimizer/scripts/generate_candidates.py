"""Generate the instruction candidate pool — outputs prompts for CoCo to fill in.

Does NOT call an LLM. Produces instruction_pool.json with one slot per candidate,
each containing the prompt CoCo should use to generate the instruction variant.
"""

import argparse
import json
import random
import sys
from pathlib import Path


# Operator catalog aligned to mutation-templates.md (the canonical reference).
# Keys match the operator names in references/mutation-templates.md exactly.
OPERATOR_CATALOG = {
    "add_retry_logic": {
        "target_file": "orchestration_instructions.md",
        "failure_categories": ["tool_error", "routing"],
        "weight": 0.15,
        "prompt_template": (
            "You are editing orchestration instructions for a Snowflake Cortex Agent.\n\n"
            "Current orchestration instructions:\n---\n{current_text}\n---\n\n"
            "Failing questions:\n{failure_context}\n\n"
            "TASK: Add a retry rule. When a tool returns an error or empty result on first "
            "attempt, the agent should retry up to 2 times before reporting the issue. "
            "Keep the rule to 2-3 sentences. Do NOT add a verbose multi-step checklist.\n\n"
            "Return ONLY the full revised instruction file."
        ),
    },
    "add_negative_example": {
        "target_file": "response_instructions.md",
        "failure_categories": ["content", "ambiguity"],
        "weight": 0.15,
        "prompt_template": (
            "You are editing response instructions for a Snowflake Cortex Agent.\n\n"
            "Current response instructions:\n---\n{current_text}\n---\n\n"
            "The agent produces this incorrect behavior:\n{failure_context}\n\n"
            "TASK: Add ONE WRONG/CORRECT example pair showing the specific mistake and "
            "correct approach. Format:\n\n"
            "\u274c WRONG: [what the agent does]\n"
            "\u2705 CORRECT: [what it should do]\n\n"
            "Keep to 3-5 lines. Do NOT duplicate existing examples.\n\n"
            "Return ONLY the full revised instruction file."
        ),
    },
    "add_routing_rule": {
        "target_file": "orchestration_instructions.md",
        "failure_categories": ["routing", "ambiguity"],
        "weight": 0.15,
        "prompt_template": (
            "You are editing orchestration instructions for a Snowflake Cortex Agent.\n\n"
            "Current orchestration instructions:\n---\n{current_text}\n---\n\n"
            "Failing questions (wrong tool selected):\n{failure_context}\n\n"
            "TASK: Add ONE specific routing rule that maps an intent pattern to the correct "
            "tool. Format: `- <pattern> ('keyword1', 'keyword2') \u2192 use <tool_name>`\n\n"
            "Return ONLY the full revised instruction file."
        ),
    },
    "adjust_response_format": {
        "target_file": "response_instructions.md",
        "failure_categories": ["formatting"],
        "weight": 0.10,
        "prompt_template": (
            "You are editing response instructions for a Snowflake Cortex Agent.\n\n"
            "Current response instructions:\n---\n{current_text}\n---\n\n"
            "User feedback patterns:\n{failure_context}\n\n"
            "TASK: Add ONE response format template showing the expected output structure "
            "for this query type. Keep it to 3-5 lines. Do NOT change tool routing or "
            "orchestration logic.\n\n"
            "Return ONLY the full revised instruction file."
        ),
    },
    "add_worked_example": {
        "target_file": "orchestration_instructions.md",
        "failure_categories": ["content", "routing"],
        "weight": 0.20,
        "prompt_template": (
            "You are editing orchestration instructions for a Snowflake Cortex Agent.\n\n"
            "Current orchestration instructions:\n---\n{current_text}\n---\n\n"
            "The agent fails on:\n{failure_context}\n\n"
            "TASK: Either (a) add ONE new worked example showing the agent how to correctly "
            "handle this failure pattern, OR (b) fix an existing example that is inconsistent "
            "or unclear. Choose whichever makes the minimum effective change. Worked examples "
            "are the highest-leverage instruction change — prefer adding over rewriting.\n\n"
            "Return ONLY the full revised instruction file."
        ),
    },
    "add_domain_rule": {
        "target_file": "response_instructions.md",
        "failure_categories": ["content", "routing"],
        "weight": 0.10,
        "prompt_template": (
            "You are editing response instructions for a Snowflake Cortex Agent.\n\n"
            "Current response instructions:\n---\n{current_text}\n---\n\n"
            "The agent violates this domain constraint:\n{failure_context}\n\n"
            "TASK: Add ONE concise domain-specific rule (1-2 sentences) stating the "
            "constraint. The rule must be specific and falsifiable. Place it in the most "
            "relevant existing section, or create '## Domain Rules'. Reject vague rules "
            "like 'be more accurate'.\n\n"
            "Return ONLY the full revised instruction file."
        ),
    },
    "sharpen_ambiguity": {
        "target_file": "orchestration_instructions.md",
        "failure_categories": ["ambiguity", "routing"],
        "weight": 0.10,
        "prompt_template": (
            "You are editing orchestration instructions for a Snowflake Cortex Agent.\n\n"
            "Current orchestration instructions:\n---\n{current_text}\n---\n\n"
            "The agent misinterprets instructions on these questions:\n{failure_context}\n\n"
            "TASK: Identify the most ambiguous rule the agent is misinterpreting. Rewrite "
            "it with concrete, specific language. Examples:\n"
            "- 'Try to use the right tool' \u2192 'For revenue questions, always call REVENUE_TOOL first'\n"
            "- 'Be careful with numbers' \u2192 'Never perform arithmetic on tool outputs'\n"
            "Change 1-2 rules. Do NOT add verbose checklists.\n\n"
            "Return ONLY the full revised instruction file."
        ),
    },
    "compress_verbose": {
        "target_file": "orchestration_instructions.md",
        "failure_categories": ["verbosity"],
        "weight": 0.05,
        "prompt_template": (
            "You are editing orchestration instructions for a Snowflake Cortex Agent.\n\n"
            "Current orchestration instructions:\n---\n{current_text}\n---\n\n"
            "Context:\n{failure_context}\n\n"
            "TASK: Compress verbose sections. Remove redundant phrasing, merge overlapping "
            "rules, eliminate filler words. Preserve all domain-specific terms, metric names, "
            "and behavioral rules exactly as-is. Target: reduce length by 20-40%.\n\n"
            "Do NOT remove examples or domain context. Do NOT change tool routing logic.\n\n"
            "Return ONLY the full revised instruction file."
        ),
    },
    "restructure_sections": {
        "target_file": "orchestration_instructions.md",
        "failure_categories": ["ambiguity", "verbosity"],
        "weight": 0.05,
        "prompt_template": (
            "You are editing orchestration instructions for a Snowflake Cortex Agent.\n\n"
            "Current orchestration instructions:\n---\n{current_text}\n---\n\n"
            "Context:\n{failure_context}\n\n"
            "TASK: Reorder sections so the most impactful rules come first. LLMs exhibit "
            "primacy bias — earlier instructions get more attention. Move routing rules and "
            "worked examples toward the top. Move format and style rules toward the bottom. "
            "Do NOT add, remove, or rewrite any content — only reorder sections.\n\n"
            "Return ONLY the full revised instruction file."
        ),
    },
}

# Operator families for coverage enforcement — at least 1 slot per family guaranteed
OPERATOR_FAMILIES = {
    "retry": ["add_retry_logic"],
    "example": ["add_negative_example", "add_worked_example"],
    "routing": ["add_routing_rule", "sharpen_ambiguity"],
    "format": ["adjust_response_format"],
    "domain": ["add_domain_rule"],
    "compression": ["compress_verbose", "restructure_sections"],
}


def load_instruction_text(agent_dir: str, target_file: str) -> str:
    """Read instruction file from agent dir, return empty string if not found."""
    path = Path(agent_dir) / target_file
    if path.exists():
        return path.read_text()
    # Try without .md extension for lookup robustness
    for f in Path(agent_dir).glob("*.md"):
        if f.stem.lower() == Path(target_file).stem.lower():
            return f.read_text()
    return f"[{target_file} not found in {agent_dir}]"


def filter_failures(failures: list[dict], categories: list[str]) -> str:
    """Return failure context string filtered to relevant failure categories."""
    if not failures:
        return "(no specific failure context provided)"
    relevant = [
        f for f in failures
        if f.get("failure_type", "").lower() in [c.lower() for c in categories]
    ]
    if not relevant:
        relevant = failures[:3]  # Fall back to first 3 if no category match
    lines = []
    for f in relevant[:5]:
        q = f.get("question", "")
        desc = f.get("description", "")
        lines.append(f"- Q: {q}" + (f" ({desc})" if desc else ""))
    return "\n".join(lines)


def assign_slots(pool_size: int) -> list[str]:
    """Assign operator names to pool slots.

    Rules:
    - At least 1 slot per operator family.
    - No two slots with the same operator+target_file combo.
    - Remaining slots filled by weighted sampling.
    """
    operators = list(OPERATOR_CATALOG.keys())
    families = list(OPERATOR_FAMILIES.keys())

    slots: list[str] = []
    used_combos: set[tuple[str, str]] = set()

    # Guarantee at least one from each family
    for family in families:
        candidates = [
            op for op in OPERATOR_FAMILIES[family]
            if (op, OPERATOR_CATALOG[op]["target_file"]) not in used_combos
        ]
        if candidates:
            chosen = candidates[0]
            slots.append(chosen)
            used_combos.add((chosen, OPERATOR_CATALOG[chosen]["target_file"]))

    # Fill remaining slots by weighted sampling (no duplicate op+target combos)
    weights = [OPERATOR_CATALOG[op]["weight"] for op in operators]
    attempts = 0
    while len(slots) < pool_size and attempts < pool_size * 10:
        attempts += 1
        [chosen] = random.choices(operators, weights=weights, k=1)
        combo = (chosen, OPERATOR_CATALOG[chosen]["target_file"])
        if combo not in used_combos:
            slots.append(chosen)
            used_combos.add(combo)

    # If still short (small pool, many combos), allow repeats with different targets
    # by cycling through operators in weight order
    if len(slots) < pool_size:
        for op in sorted(operators, key=lambda o: -OPERATOR_CATALOG[o]["weight"]):
            if len(slots) >= pool_size:
                break
            slots.append(op)

    return slots[:pool_size]


def main():
    parser = argparse.ArgumentParser(
        description="Generate instruction candidate pool for TPE optimizer"
    )
    parser.add_argument("--agent-dir", required=True,
                        help="Path to agent/ directory with instruction .md files")
    parser.add_argument("--failure-context", default=None,
                        help="Path to failure_context.json")
    parser.add_argument("--pool-size", type=int, default=12)
    parser.add_argument("--output", default="instruction_pool.json")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print operator assignments without writing output")
    args = parser.parse_args()

    # Load failure context
    failures: list[dict] = []
    if args.failure_context:
        with open(args.failure_context) as f:
            failures = json.load(f)
        print(f"Loaded {len(failures)} failure entries", file=sys.stderr)

    slots = assign_slots(args.pool_size)

    # Operator distribution summary
    dist: dict[str, int] = {}
    for op in slots:
        dist[op] = dist.get(op, 0) + 1
    print("Operator distribution:", file=sys.stderr)
    for op, count in sorted(dist.items(), key=lambda x: -x[1]):
        print(f"  {op}: {count}", file=sys.stderr)

    if args.dry_run:
        print(json.dumps({"dry_run": True, "slots": slots, "distribution": dist}))
        return

    pool = []
    for idx, operator in enumerate(slots):
        spec = OPERATOR_CATALOG[operator]
        target_file = spec["target_file"]
        current_text = load_instruction_text(args.agent_dir, target_file)
        failure_context_str = filter_failures(failures, spec["failure_categories"])
        prompt = spec["prompt_template"].format(
            current_text=current_text,
            failure_context=failure_context_str,
        )
        pool.append({
            "id": idx,
            "operator": operator,
            "target_file": target_file,
            "prompt": prompt,
            "text": "",  # CoCo fills this in after generating the variant
            "diff_summary": "",  # CoCo fills this in
        })

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w") as f:
        json.dump(pool, f, indent=2)
    print(f"Wrote {len(pool)} candidates to {args.output}", file=sys.stderr)
    print(json.dumps({"status": "ok", "count": len(pool), "output": args.output}))


if __name__ == "__main__":
    main()

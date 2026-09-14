"""Assemble a complete agent spec from an instruction variant + few-shot demos.

Combines instruction_pool[instruction_idx] text with selected trace_pool demos,
appends a few-shot section, and writes a ready-to-deploy candidate_spec.json.
"""

import argparse
import json
import sys
from pathlib import Path


FEW_SHOT_HEADER = "\n\n## Worked Examples\n"


def format_few_shot_section(traces: list[dict]) -> str:
    """Build the few-shot block to append to instruction text."""
    if not traces:
        return ""
    lines = [FEW_SHOT_HEADER]
    for t in traces:
        q = t.get("input", "")
        # Prefer agent_response when non-empty; fall back to expected_output
        answer = t.get("agent_response") or t.get("expected_output", "")
        if isinstance(answer, dict) and "ground_truth_output" in answer:
            answer = answer["ground_truth_output"]
        if isinstance(answer, (dict, list)):
            answer = json.dumps(answer)
        lines.append(f"**Q:** {q}")
        lines.append(f"**A:** {answer}")
        lines.append("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Build candidate agent spec from instruction variant + few-shot demos"
    )
    parser.add_argument("--base-spec", required=True,
                        help="Path to agent_spec.json (base agent spec)")
    parser.add_argument("--instruction-pool", required=True,
                        help="Path to instruction_pool.json")
    parser.add_argument("--trace-pool", required=True,
                        help="Path to trace_pool.json")
    parser.add_argument("--instruction-idx", type=int, required=True,
                        help="Index into instruction_pool")
    parser.add_argument("--fewshot-indices", required=True,
                        help="Comma-separated indices into trace_pool (e.g. '1,7,12')")
    parser.add_argument("--output", default="candidate_spec.json")
    args = parser.parse_args()

    # Load pools
    with open(args.instruction_pool) as f:
        instruction_pool = json.load(f)
    with open(args.trace_pool) as f:
        trace_pool = json.load(f)
    with open(args.base_spec) as f:
        base_spec = json.load(f)

    # Validate instruction variant has been filled in
    entry = instruction_pool[args.instruction_idx]
    instruction_text = entry.get("text", "")
    if not instruction_text.strip():
        print(
            f"ERROR: instruction_pool[{args.instruction_idx}].text is empty. "
            "CoCo must generate the variant before calling build_candidate.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Resolve few-shot traces, deduplicating by input text
    raw_indices = [int(i.strip()) for i in args.fewshot_indices.split(",") if i.strip()]
    seen_inputs: set[str] = set()
    demos: list[dict] = []
    for idx in raw_indices:
        if idx >= len(trace_pool):
            print(f"WARNING: fewshot index {idx} out of range (pool size {len(trace_pool)})",
                  file=sys.stderr)
            continue
        trace = trace_pool[idx]
        inp = str(trace.get("input", ""))
        if inp in seen_inputs:
            continue
        seen_inputs.add(inp)
        demos.append(trace)

    few_shot_section = format_few_shot_section(demos)
    combined_text = instruction_text + few_shot_section

    spec = dict(base_spec)
    target_fields = {
        "orchestration_instructions.md": "orchestration",
        "response_instructions.md": "response",
    }
    target = entry.get("target_file")
    if target not in target_fields:
        raise ValueError(f"Unsupported instruction target: {target!r}")
    instructions = spec.get("instructions", {})
    if not isinstance(instructions, dict):
        raise ValueError("Agent instructions must be an object")
    spec["instructions"] = dict(instructions)
    spec["instructions"][target_fields[target]] = combined_text

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w") as f:
        json.dump(spec, f, indent=2)

    print(
        f"Built candidate spec:\n"
        f"  instruction_idx={args.instruction_idx} (operator={entry.get('operator')})",
        file=sys.stderr,
    )
    print(f"  demos={len(demos)} (indices={raw_indices})", file=sys.stderr)
    print(f"  combined instruction length: {len(combined_text)} chars", file=sys.stderr)
    print(f"  output: {args.output}", file=sys.stderr)
    print(json.dumps({
        "status": "ok",
        "instruction_idx": args.instruction_idx,
        "operator": entry.get("operator"),
        "demo_count": len(demos),
        "combined_length": len(combined_text),
        "output": args.output,
    }))


if __name__ == "__main__":
    main()

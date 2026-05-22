#!/usr/bin/env python3
"""Merge multiple spec.json parts into a single spec.json.

Usage:
    python merge_spec.py part1.json part2.json [part3.json ...] --output spec.json

Rules:
- part1.json must contain: config_version, config, slides (base file)
- part2+ must contain: slides (appended to part1's slides)
- agenda_items from part1 is preserved if present
"""
import argparse, json, sys


def merge(parts):
    with open(parts[0]) as f:
        base = json.load(f)

    if "config" not in base:
        print(f"ERROR: {parts[0]} must contain 'config' section (base file)")
        sys.exit(2)
    if "slides" not in base:
        print(f"ERROR: {parts[0]} must contain 'slides' array")
        sys.exit(2)

    for p in parts[1:]:
        with open(p) as f:
            fragment = json.load(f)
        if "slides" not in fragment:
            print(f"ERROR: {p} must contain 'slides' array")
            sys.exit(2)
        base["slides"].extend(fragment["slides"])

    return base


def main():
    parser = argparse.ArgumentParser(description="Merge spec.json parts")
    parser.add_argument("parts", nargs="+", help="Part JSON files (first = base with config)")
    parser.add_argument("--output", "-o", required=True, help="Output merged spec.json")
    args = parser.parse_args()

    if len(args.parts) < 2:
        print("ERROR: Need at least 2 part files to merge")
        sys.exit(2)

    result = merge(args.parts)
    print(f"Merged {len(args.parts)} parts → {len(result['slides'])} slides")

    with open(args.output, "w") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"Written to {args.output}")


if __name__ == "__main__":
    main()

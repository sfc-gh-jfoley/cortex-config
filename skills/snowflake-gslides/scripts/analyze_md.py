#!/usr/bin/env python3
"""Analyze markdown structure for slide generation planning.

Outputs section breakdown, element counts, and estimated slide count.

Usage:
    python analyze_md.py <md_file> [--output analysis.md]
"""
import argparse, re
from pathlib import Path


def analyze(md_text):
    lines = md_text.split("\n")
    total_lines = len(lines)

    sections = []
    current_section = {"name": "(Preamble)", "start": 0, "tables": 0, "code_blocks": 0, "code_details": [], "table_details": [], "lines": 0, "diagram_candidate": False}
    in_code = False
    code_lang = ""
    code_start_line = 0
    code_line_count = 0
    table_rows = 0
    table_cols = 0
    in_table = False

    for i, line in enumerate(lines):
        if line.startswith("```"):
            if not in_code:
                in_code = True
                code_lang = line[3:].strip().split()[0] if line[3:].strip() else "text"
                code_start_line = i + 1
                code_line_count = 0
            else:
                in_code = False
                current_section["code_blocks"] += 1
                current_section["code_details"].append({
                    "language": code_lang,
                    "lines": code_line_count,
                    "needs_trim": code_line_count > 25,
                    "_start": code_start_line,
                })
            continue

        if in_code:
            code_line_count += 1
            continue

        if re.match(r'^## ', line):
            current_section["lines"] = i - current_section["start"]
            if current_section["name"] != "(Preamble)" or current_section["tables"] > 0 or current_section["code_blocks"] > 0:
                sections.append(current_section)
            current_section = {"name": line[3:].strip(), "start": i, "tables": 0, "code_blocks": 0, "code_details": [], "table_details": [], "lines": 0, "diagram_candidate": False}
            in_table = False
            table_rows = 0
            continue

        if re.match(r'^\|.*\|', line) and not re.match(r'^\|[-:\s|]+\|$', line):
            if not in_table:
                in_table = True
                table_rows = 1
                table_cols = line.count("|") - 1
            else:
                table_rows += 1
        else:
            if in_table:
                current_section["tables"] += 1
                current_section["table_details"].append({
                    "rows": table_rows,
                    "cols": table_cols,
                    "large": table_rows > 8,
                    "wide": table_cols > 5,
                })
                in_table = False
                table_rows = 0

    if in_table:
        current_section["tables"] += 1
        current_section["table_details"].append({"rows": table_rows, "cols": table_cols, "large": table_rows > 8, "wide": table_cols > 5})
    current_section["lines"] = total_lines - current_section["start"]
    sections.append(current_section)

    arrow_sym = re.compile(r'→|->|=>|──>|━>|↔|<-|<--|<═')
    chain_pat = re.compile(r'\S+\s*(?:→|->|=>|──>|━>)\s*\S+(?:\s*(?:→|->|=>|──>|━>)\s*\S+)+')
    pair_pat = re.compile(r'\S+\s*(?:→|->|=>|──>|━>|↔)\s*\S+')
    for s in sections:
        if s["name"] == "(Preamble)":
            continue
        sec_lines = lines[s["start"]:s["start"] + s["lines"]]
        sec_text = "\n".join(sec_lines)

        score = 0
        reasons = []

        chains = chain_pat.findall(sec_text)
        if chains:
            score += len(chains) * 3
            chain_elements = set()
            for c in chains:
                chain_elements.update(re.split(r'\s*(?:→|->|=>|──>|━>)\s*', c))
            score += min(len(chain_elements), 3)
            reasons.append(f"{len(chains)} arrow chain(s), {len(chain_elements)} elements")

        pairs = pair_pat.findall(sec_text)
        pair_score = min(len(pairs), 4)
        if pair_score > 0 and not chains:
            score += pair_score
            reasons.append(f"{len(pairs)} arrow pair(s)")

        code_has_arrows = False
        for cd in s.get("code_details", []):
            code_start = cd.get("_start", 0)
            code_end = code_start + cd.get("lines", 0)
            code_text = "\n".join(lines[code_start:code_end])
            if arrow_sym.search(code_text):
                code_has_arrows = True
                break
        if code_has_arrows:
            score += 3
            reasons.append("arrows in code block")

        if score >= 4:
            s["diagram_candidate"] = True
            s["diagram_reason"] = "; ".join(reasons)
            arrow_lines = [s["start"] + j + 1 for j, l in enumerate(sec_lines) if arrow_sym.search(l)]
            if arrow_lines:
                s["diagram_lines"] = arrow_lines[:5]

    total_tables = sum(s["tables"] for s in sections)
    total_code = sum(s["code_blocks"] for s in sections)
    total_sections = len([s for s in sections if s["name"] != "(Preamble)"])
    total_diagrams = len([s for s in sections if s.get("diagram_candidate")])

    est_table_slides = total_tables
    est_code_slides = total_code
    est_bullet_slides = max(total_sections, int(total_sections * 1.5))
    est_structure = total_sections + 3
    est_total = est_table_slides + est_code_slides + est_bullet_slides + est_structure

    return {
        "total_lines": total_lines,
        "total_sections": total_sections,
        "total_tables": total_tables,
        "total_code_blocks": total_code,
        "total_diagram_candidates": total_diagrams,
        "estimated_slides": est_total,
        "phase_split_required": est_total > 50,
        "sections": sections,
    }


def format_output(result):
    out = []
    out.append(f"# MD Analysis\n")
    out.append(f"- Total lines: {result['total_lines']}")
    out.append(f"- Sections (##): {result['total_sections']}")
    out.append(f"- Tables: {result['total_tables']}")
    out.append(f"- Code blocks: {result['total_code_blocks']}")
    out.append(f"- Diagram candidates: {result['total_diagram_candidates']}")
    out.append(f"- **Estimated slides: {result['estimated_slides']}**")
    out.append(f"- Phase split required: {'YES' if result['phase_split_required'] else 'No'}")
    out.append("")

    out.append("## Section Summary\n")
    out.append("| # | Section | Tables | Code | Diagram? | Lines |")
    out.append("|---|---------|--------|------|----------|-------|")
    for i, s in enumerate(result["sections"], 1):
        if s["name"] == "(Preamble)" and s["tables"] == 0 and s["code_blocks"] == 0:
            continue
        diag = "✓" if s.get("diagram_candidate") else ""
        out.append(f"| {i} | {s['name'][:40]} | {s['tables']} | {s['code_blocks']} | {diag} | {s['lines']} |")
    out.append("")

    diag_sections = [s for s in result["sections"] if s.get("diagram_candidate")]
    if diag_sections:
        out.append("## Diagram Candidates\n")
        for s in diag_sections:
            reason = s.get("diagram_reason", "")
            lines_hint = s.get("diagram_lines", [])
            lines_str = f" (lines {', '.join(str(l) for l in lines_hint)})" if lines_hint else ""
            out.append(f"- **{s['name']}**: {reason}{lines_str}")
        out.append("")

    code_trim = [d for s in result["sections"] for d in s["code_details"] if d["needs_trim"]]
    if code_trim:
        out.append("## Code Blocks Needing Trim (>25 lines)\n")
        out.append("| # | Section | Language | Lines |")
        out.append("|---|---------|----------|-------|")
        idx = 0
        for s in result["sections"]:
            for d in s["code_details"]:
                if d["needs_trim"]:
                    idx += 1
                    out.append(f"| {idx} | {s['name'][:30]} | {d['language']} | {d['lines']} |")
        out.append("")

    large_tables = [(s["name"], d) for s in result["sections"] for d in s["table_details"] if d["large"] or d["wide"]]
    if large_tables:
        out.append("## Large/Wide Tables\n")
        out.append("| # | Section | Cols | Rows | Note |")
        out.append("|---|---------|------|------|------|")
        for idx, (name, d) in enumerate(large_tables, 1):
            notes = []
            if d["large"]:
                notes.append("many rows")
            if d["wide"]:
                notes.append(">5 cols")
            out.append(f"| {idx} | {name[:30]} | {d['cols']} | {d['rows']} | {', '.join(notes)} |")
        out.append("")

    return "\n".join(out)


def main():
    parser = argparse.ArgumentParser(description="Analyze markdown structure for slide planning")
    parser.add_argument("md_file", help="Markdown file to analyze")
    parser.add_argument("--output", "-o", help="Output analysis file (default: stdout)")
    parser.add_argument("--lines", help="Line range to analyze (e.g. '47-292')")
    args = parser.parse_args()

    with open(args.md_file, encoding="utf-8") as f:
        all_lines = f.readlines()

    if args.lines:
        parts = args.lines.split("-")
        start = int(parts[0]) - 1
        end = int(parts[1]) if len(parts) > 1 else len(all_lines)
        md_text = "".join(all_lines[start:end])
    else:
        md_text = "".join(all_lines)

    result = analyze(md_text)
    output = format_output(result)

    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"Analysis written to {args.output}")
        print(f"  Sections: {result['total_sections']}, Tables: {result['total_tables']}, Code: {result['total_code_blocks']}")
        print(f"  Estimated slides: {result['estimated_slides']}, Phase split: {'YES' if result['phase_split_required'] else 'No'}")
    else:
        print(output)


if __name__ == "__main__":
    main()

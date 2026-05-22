#!/usr/bin/env python3
"""Lint a spec.json for rule compliance before running build/rebuild.

Validates:
- config section: structure, version, required sections, internal consistency
- features: coherence with slides content
- slides: required fields, types, title/subtitle rules, table/code constraints
- overflow: EMU layout calculations (body, table, code)

Usage:
    python lint_spec.py <spec.json> [--audit audit.json]
"""
import argparse, difflib, json, re, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from utils import display_len, estimate_body_h

SUPPORTED_CONFIG_VERSION = 1

REQUIRED_CONFIG_SECTIONS = ["fonts", "sizes", "colors", "table", "code_block", "layout", "rules", "features"]
REQUIRED_FONTS = ["primary", "code"]
REQUIRED_SIZES = ["cover_title", "cover_subtitle", "cover_date", "title", "title_min", "subtitle", "body", "body_header", "agenda_title", "agenda_items", "divider", "table_body", "table_header_increment", "code"]
REQUIRED_COLORS = ["snowflake_blue", "accent", "body_text", "code_background"]
REQUIRED_TABLE = ["default_x", "default_w", "default_row_height", "min_column_width", "background_color", "background_zebra_color", "border_color"]
REQUIRED_CODE_BLOCK = ["accent_bar_width", "padding", "max_lines", "accent_colors"]
REQUIRED_LAYOUT = ["page_bottom_margin", "body_start_y", "body_table_gap", "content_x", "content_w", "body_line_spacing"]
REQUIRED_RULES = ["title_base_max_chars", "subtitle_max_chars", "agenda_max_items"]
REQUIRED_FEATURES = ["cover_slide", "agenda_slide", "section_dividers", "thanks_slide", "title_section_prefix", "table_zebra_stripes", "jp_period_to_newline", "auto_link_snowflake_views", "body_accent_emphasis", "cover_date", "subtitle_required", "diagram_slide"]


def _check_keys(section, required_keys, label):
    errors = []
    for key in required_keys:
        if key not in section:
            errors.append(f"config.{label}: missing required key '{key}'")
    return errors


def validate_config(spec):
    errors = []
    warnings = []

    if "config_version" not in spec:
        errors.append("Missing 'config_version' at top level")
    elif spec["config_version"] != SUPPORTED_CONFIG_VERSION:
        errors.append(f"config_version={spec['config_version']} not supported (expected {SUPPORTED_CONFIG_VERSION}). Regenerate spec.json with latest yaml")

    config = spec.get("config")
    if not config:
        errors.append("Missing 'config' section at top level")
        return errors, warnings

    for section in REQUIRED_CONFIG_SECTIONS:
        if section not in config:
            errors.append(f"config: missing required section '{section}'")

    if "fonts" in config:
        errors.extend(_check_keys(config["fonts"], REQUIRED_FONTS, "fonts"))
    if "sizes" in config:
        errors.extend(_check_keys(config["sizes"], REQUIRED_SIZES, "sizes"))
    if "colors" in config:
        errors.extend(_check_keys(config["colors"], REQUIRED_COLORS, "colors"))
        for key, val in config["colors"].items():
            if not isinstance(val, list) or len(val) != 3:
                errors.append(f"config.colors.{key}: must be [r, g, b] array (0.0-1.0)")
    if "table" in config:
        errors.extend(_check_keys(config["table"], REQUIRED_TABLE, "table"))
    if "code_block" in config:
        errors.extend(_check_keys(config["code_block"], REQUIRED_CODE_BLOCK, "code_block"))
    if "layout" in config:
        errors.extend(_check_keys(config["layout"], REQUIRED_LAYOUT, "layout"))
    if "rules" in config:
        errors.extend(_check_keys(config["rules"], REQUIRED_RULES, "rules"))
    if "features" in config:
        errors.extend(_check_keys(config["features"], REQUIRED_FEATURES, "features"))

    if "sizes" in config and "rules" in config:
        title_size = config["sizes"].get("title", 24)
        base_max = config["rules"].get("title_base_max_chars", 50)
        if title_size < config["sizes"].get("title_min", 20):
            errors.append(f"config.sizes.title ({title_size}) is below config.sizes.title_min ({config['sizes']['title_min']})")

    return errors, warnings


def validate_overflow(spec):
    """Check EMU overflow for body, table, and code blocks."""
    warnings = []
    config = spec.get("config", {})
    layout = config.get("layout", {})
    sizes = config.get("sizes", {})

    features = config.get("features", {})
    jp_period = features.get("jp_period_to_newline", True)

    page_height = 5143500
    margin = layout.get("page_bottom_margin", 450000)
    max_bottom = page_height - margin
    sub_bottom = layout.get("body_start_y", 1080000)
    gap = layout.get("body_table_gap", 60000)
    content_w = layout.get("content_w", 8200000)

    for i, s in enumerate(spec.get("slides", [])):
        slide_layout = s.get("layout", "")
        if slide_layout not in ("multi", "one_column", "blank"):
            continue
        label = f"Slide {i+1} ({s.get('id', '?')})"
        next_y = sub_bottom

        if s.get("body"):
            body_fs = s.get("bodySize", sizes.get("body", 10))
            body_h = estimate_body_h(s["body"], body_fs, content_w)
            body_y = s.get("bodyY", next_y)
            body_bottom = body_y + body_h
            next_y = body_bottom + gap
            if body_bottom > max_bottom:
                overflow_emu = body_bottom - max_bottom
                line_h_est = int(body_fs * 914400 / 72 * 1.5)
                overflow_lines = max(1, -(-overflow_emu // max(line_h_est, 1)))
                warnings.append(
                    f"ERROR: {label}: body exceeds bottom limit. "
                    f"Overflow: {overflow_emu} EMU (~{overflow_lines} lines). "
                    f"Split into multiple slides or reduce content."
                )

        if s.get("type") == "table" and s.get("table"):
            tbl = s["table"]
            table_y = tbl.get("y", next_y)
            data = tbl.get("data", [])
            nr = len(data)
            nc = len(data[0]) if data else 1
            rh = tbl.get("rowHeight", config.get("table", {}).get("default_row_height", 330000))
            tbl_fs = tbl.get("fontSize", sizes.get("table_body", 8))
            col_widths = tbl.get("columnWidths")
            tbl_w = tbl.get("w", config.get("table", {}).get("default_w", 8200000))

            effective_h = 0
            for ri, row in enumerate(data):
                max_row_lines = 1
                for ci, cell in enumerate(row):
                    cell_text = str(cell) if cell else ""
                    if jp_period and ri > 0 and "。" in cell_text:
                        cell_text = cell_text.replace("。", "\n")
                    cell_lines = cell_text.count("\n") + 1
                    if col_widths and ci < len(col_widths):
                        cw = col_widths[ci]
                    else:
                        cw = tbl_w // nc
                    usable_w = max(cw - 80000, 100000)
                    char_w = int(tbl_fs * 914400 / 72 * 0.5)
                    chars_per = max(usable_w // max(char_w, 1), 1)
                    for line in cell_text.split("\n"):
                        lc = display_len(line.strip())
                        wrapped = max(1, -(-lc // chars_per))
                        if wrapped > 1:
                            cell_lines += wrapped - 1
                    max_row_lines = max(max_row_lines, cell_lines)
                cell_line_h = int(tbl_fs * 914400 / 72 * 1.4)
                if ri == 0:
                    cell_line_h = int((tbl_fs + 1) * 914400 / 72 * 1.4)
                row_h = max(rh, max_row_lines * cell_line_h + 80000) + 73000
                effective_h += row_h

            table_bottom = table_y + effective_h
            if table_bottom > max_bottom:
                scale = (max_bottom - table_y) / max(effective_h, 1)
                new_rh = max(int(rh * scale), 200000)
                recalc_h = 0
                for ri2, row2 in enumerate(data):
                    max_rl2 = 1
                    for ci2, cell2 in enumerate(row2):
                        ct2 = str(cell2) if cell2 else ""
                        if jp_period and ri2 > 0 and "。" in ct2:
                            ct2 = ct2.replace("。", "\n")
                        cl2 = ct2.count("\n") + 1
                        if col_widths and ci2 < len(col_widths):
                            cw2 = col_widths[ci2]
                        else:
                            cw2 = tbl_w // nc
                        uw2 = max(cw2 - 80000, 100000)
                        cw_ch2 = int(tbl_fs * 914400 / 72 * 0.5)
                        cp2 = max(uw2 // max(cw_ch2, 1), 1)
                        for ln2 in ct2.split("\n"):
                            lc2 = display_len(ln2.strip())
                            wr2 = max(1, -(-lc2 // cp2))
                            if wr2 > 1:
                                cl2 += wr2 - 1
                        max_rl2 = max(max_rl2, cl2)
                    clh2 = int(tbl_fs * 914400 / 72 * 1.4)
                    if ri2 == 0:
                        clh2 = int((tbl_fs + 1) * 914400 / 72 * 1.4)
                    rh2 = max(new_rh, max_rl2 * clh2 + 80000) + 73000
                    recalc_h += rh2
                recalc_bottom = table_y + recalc_h
                if recalc_bottom > max_bottom:
                    warnings.append(
                        f"ERROR: {label}: table overflows even after rowHeight shrink ({nr} rows). "
                        f"Split into multiple table slides."
                    )
                else:
                    warnings.append(
                        f"WARN: {label}: table exceeds bottom → rowHeight will be auto-shrunk {rh}→{new_rh} by build."
                    )

        if s.get("type") == "code" and s.get("code"):
            code_spec = s["code"]
            code_fs = code_spec.get("fontSize", sizes.get("code", 8))
            source_lines = code_spec["source"].count("\n") + 1
            line_h = int(code_fs * 914400 / 72 * 1.4)
            code_h = code_spec.get("h", source_lines * line_h + 160000)
            code_bottom = next_y + code_h
            code_limit = page_height - margin
            if code_bottom > code_limit:
                warnings.append(
                    f"ERROR: {label}: code exceeds bottom limit. "
                    f"Extract key portions to fit ~{config.get('code_block', {}).get('max_lines', 25)} lines."
                )

    return warnings


def validate_slides(spec, audit=None):
    errors = []
    warnings = []
    config = spec.get("config", {})
    sizes = config.get("sizes", {})
    rules = config.get("rules", {})
    features = config.get("features", {})
    slides = spec.get("slides", [])

    if not slides:
        errors.append("No slides defined in spec")
        return errors, warnings

    valid_layout_ids = set()
    if audit:
        for layout in audit.get("layouts", []):
            valid_layout_ids.add(layout["id"])

    seen_ids = set()
    content_titles = []

    for i, s in enumerate(slides):
        label = f"Slide {i+1} ({s.get('id', '?')})"

        if not s.get("id"):
            errors.append(f"{label}: missing 'id'")
        elif len(s["id"]) < 5:
            errors.append(f"{label}: id must be at least 5 characters")
        elif s["id"] in seen_ids:
            errors.append(f"{label}: duplicate id '{s['id']}'")
        else:
            seen_ids.add(s["id"])

        if not s.get("layout"):
            errors.append(f"{label}: missing 'layout'")
        if not s.get("layoutId"):
            errors.append(f"{label}: missing 'layoutId'")
        elif valid_layout_ids and s["layoutId"] not in valid_layout_ids:
            errors.append(f"{label}: layoutId '{s['layoutId']}' not found in audit")

        layout = s.get("layout", "")

        if layout in ("multi", "one_column", "blank"):
            body = s.get("body")
            if body is not None and not isinstance(body, str):
                if isinstance(body, list):
                    errors.append(f"{label}: body must be a string, not a list")
                else:
                    errors.append(f"{label}: body must be a string, got {type(body).__name__}")
            if isinstance(body, str):
                if '```' in body:
                    errors.append(f"{label}: body contains code fence (```). Use type='code' slide instead")
                pipe_lines = [l for l in body.split("\n") if l.count("|") >= 3]
                if pipe_lines:
                    warnings.append(f"{label}: body contains lines with 3+ pipe characters — possible md table")

            title = s.get("title", "")
            if not title:
                errors.append(f"{label}: missing 'title'")
            else:
                if "\n" in title:
                    errors.append(f"{label}: title must be 1 line (contains newline)")
                title_fs = s.get("titleSize", sizes.get("title", 24))
                title_min = sizes.get("title_min", 20)
                if title_fs < title_min:
                    errors.append(f"{label}: titleSize={title_fs} is below minimum ({title_min})")
                    title_fs = title_min
                base_max = rules.get("title_base_max_chars", 50)
                title_max = int(base_max * (24 / title_fs))
                if display_len(title) > title_max:
                    errors.append(f"{label}: title too long ({display_len(title)} display chars, max {title_max} at {title_fs}pt)")
                content_titles.append((title, s.get("subtitle", ""), i, s.get("id", "?")))

            sub = s.get("subtitle", "")
            if not sub and features.get("subtitle_required", True):
                errors.append(f"{label}: missing 'subtitle'")
            elif sub and "\n" in sub:
                errors.append(f"{label}: subtitle must be 1 line (contains newline)")
            else:
                sub_max = rules.get("subtitle_max_chars", 70)
                if display_len(sub) > sub_max:
                    errors.append(f"{label}: subtitle too long ({display_len(sub)} display chars, max {sub_max})")

            stype = s.get("type", "bullets")
            if stype == "table" and s.get("code"):
                errors.append(f"{label}: table and code cannot coexist on same slide")
            if stype == "code" and s.get("table"):
                errors.append(f"{label}: table and code cannot coexist on same slide")
            if stype == "diagram" and s.get("table"):
                errors.append(f"{label}: diagram and table cannot coexist on same slide")
            if stype == "diagram" and s.get("code"):
                errors.append(f"{label}: diagram and code cannot coexist on same slide")
            if stype == "diagram" and not s.get("diagram"):
                errors.append(f"{label}: type=diagram but no diagram field")

            if stype == "table":
                tbl = s.get("table")
                if not tbl:
                    errors.append(f"{label}: type=table but no table field")
                elif not tbl.get("data"):
                    errors.append(f"{label}: table.data is empty")
                else:
                    data = tbl["data"]
                    nc = len(data[0])
                    for ri, row in enumerate(data):
                        if len(row) != nc:
                            errors.append(f"{label}: table row {ri} has {len(row)} cols, header has {nc}")
                    cw = tbl.get("columnWidths")
                    tw = tbl.get("w", config.get("table", {}).get("default_w", 8200000))

                    header_row = data[0]
                    header_issues = []
                    if any("\n" in str(c) for c in header_row if c):
                        header_issues.append("contains newlines")
                    if any("**" in str(c) for c in header_row if c):
                        header_issues.append("contains **bold** markers")
                    if any("`" in str(c) for c in header_row if c):
                        header_issues.append("contains `backtick` markers")
                    if len(data) > 1 and not header_issues:
                        header_avg = sum(display_len(str(c)) for c in header_row if c) / max(len([c for c in header_row if c]), 1)
                        data_lens = [display_len(str(c)) for row in data[1:] for c in row if c]
                        data_avg = sum(data_lens) / max(len(data_lens), 1)
                        if header_avg > 0 and data_avg > 0 and header_avg >= data_avg * 1.5:
                            header_issues.append(f"avg header cell length ({header_avg:.0f}) >= 1.5x data avg ({data_avg:.0f})")
                    if header_issues:
                        warnings.append(f"{label}: table.data[0] may not be a proper header: {'; '.join(header_issues)}")

                    if len(data) > 1:
                        for ri, row in enumerate(data[1:], 1):
                            for ci, cell in enumerate(row):
                                cell_str = str(cell) if cell else ""
                                if cell_str.count("**") % 2 != 0:
                                    errors.append(f"{label}: table cell [{ri}][{ci}] has unclosed ** marker")
                                if cell_str.count("`") % 2 != 0:
                                    errors.append(f"{label}: table cell [{ri}][{ci}] has unclosed backtick marker")

                    if cw:
                        if len(cw) != nc:
                            errors.append(f"{label}: columnWidths has {len(cw)} values but table has {nc} columns")
                        cw_sum = sum(cw)
                        if cw_sum < tw * 0.5:
                            errors.append(f"{label}: columnWidths sum ({cw_sum}) < 50% of table width ({tw}). Values must be EMU")
                        for ci, val in enumerate(cw):
                            if val < 100000:
                                errors.append(f"{label}: columnWidths[{ci}]={val} too small. Must be EMU (e.g. 500000)")

            if stype == "code":
                code = s.get("code")
                if not code:
                    errors.append(f"{label}: type=code but no code field")
                elif not code.get("source"):
                    errors.append(f"{label}: code.source is empty")

        elif layout == "cover":
            if not s.get("title"):
                errors.append(f"{label}: cover requires 'title'")
            date_val = s.get("date", "")
            if features.get("cover_date", True):
                if date_val and not re.match(r'^Snowflake \| [A-Z][a-z]+ \d{1,2}, \d{4}$', date_val):
                    errors.append(f"{label}: cover date must follow 'Snowflake | Month DD, YYYY'. Got: '{date_val}'")
            if not features.get("cover_slide", True):
                errors.append(f"{label}: cover slide exists but features.cover_slide=false. → Fix: Remove cover slide or set cover_slide=true")

        elif layout == "agenda":
            if not s.get("items"):
                errors.append(f"{label}: agenda has no items. Add 'items' array to the agenda slide definition")
            else:
                max_items = rules.get("agenda_max_items", 20)
                if len(s["items"]) > max_items:
                    errors.append(f"{label}: agenda has {len(s['items'])} items (max {max_items})")
                elif len(s["items"]) > 15:
                    warnings.append(f"{label}: agenda has {len(s['items'])} items (font auto-shrunk to 12pt)")
            if not features.get("agenda_slide", True):
                errors.append(f"{label}: agenda slide exists but features.agenda_slide=false. → Fix: Remove agenda slide or set agenda_slide=true")

        elif layout == "divider":
            if not s.get("title"):
                errors.append(f"{label}: divider requires 'title'")
            if not features.get("section_dividers", True):
                errors.append(f"{label}: divider exists but features.section_dividers=false. → Fix: Remove divider or set section_dividers=true")

        elif layout == "thanks":
            if not features.get("thanks_slide", True):
                errors.append(f"{label}: thanks slide exists but features.thanks_slide=false. → Fix: Remove thanks slide or set thanks_slide=true")

    title_counts = {}
    for t, _, _, _ in content_titles:
        clean_t = re.sub(r'\s*\(\d+/\d+\)\s*$', '', t)
        title_counts[clean_t] = title_counts.get(clean_t, 0) + 1
    for t, count in title_counts.items():
        if count > 1:
            matching = [(ct, sub) for ct, sub, _, _ in content_titles if re.sub(r'\s*\(\d+/\d+\)\s*$', '', ct) == t]
            if not any(re.search(r'\(\d+/\d+\)$', ct) for ct, _ in matching):
                subtitles = [sub for _, sub in matching]
                if len(set(subtitles)) <= 1:
                    errors.append(f"Title '{t}' appears {count} times with same subtitle and no (1/N) suffix. → Fix: Add (1/N) suffix or differentiate subtitles.")
                else:
                    pass

    agenda_items = []
    divider_titles = []
    for s in slides:
        if s.get("layout") == "agenda":
            agenda_items = [it.strip() for it in s.get("items", [])]
        elif s.get("layout") == "divider":
            divider_titles.append(s.get("title", "").strip())

    if features.get("title_section_prefix", True) and agenda_items and content_titles:
        for title_text, _, slide_idx, slide_id in content_titles:
            if " — " not in title_text:
                title_clean = re.sub(r'\s*\(\d+/\d+\)\s*$', '', title_text).strip()
                if title_clean not in agenda_items:
                    errors.append(f"Slide {slide_idx+1} ({slide_id}): title '{title_text}' missing ' — ' separator and does not match any Agenda item")

    if features.get("section_dividers", True) and agenda_items and divider_titles:
        if len(agenda_items) != len(divider_titles):
            errors.append(f"Agenda has {len(agenda_items)} items but {len(divider_titles)} dividers exist (must be 1:1)")
        for item in agenda_items:
            if item not in divider_titles:
                errors.append(f"Agenda item '{item}' has no matching divider")
        for title in divider_titles:
            if title not in agenda_items:
                warnings.append(f"Divider '{title}' has no matching agenda item")

    return errors, warnings


VALID_EDGE_LINES = {"elbow", "straight", "curved"}
VALID_EDGE_ARROWS = {"arrow", "none"}
VALID_EDGE_COLORS = {"dark_blue", "gray", "accent"}
VALID_ICON_SIZES = {20, 30, 40}
VALID_GROUP_COLORS = {
    "snowflake", "aws", "azure", "gcp", "default",
    "gray", "green", "coral", "purple", "teal", "amber",
    "bronze", "silver", "gold",
}
VALID_SIDES = {"top", "right", "bottom", "left"}


def _load_icons_list():
    p = Path(__file__).parent.parent / "config" / "icons_list.json"
    if p.exists():
        with open(p) as f:
            data = json.load(f)
        if isinstance(data, dict):
            all_icons = set()
            for icons in data.values():
                all_icons.update(icons)
            return all_icons
        return set(data)
    return set()


def _load_logos_set():
    p = Path(__file__).parent.parent / "config" / "icons_list.json"
    if p.exists():
        with open(p) as f:
            data = json.load(f)
        if isinstance(data, dict):
            return set(data.get("logos", []))
    return set()


def _load_aliases():
    p = Path(__file__).parent.parent / "config" / "icon_aliases.json"
    if p.exists():
        with open(p) as f:
            return json.load(f)
    return {}


def validate_diagram(spec):
    errors = []
    warnings = []
    config = spec.get("config", {})
    features = config.get("features", {})
    icons_list = _load_icons_list()
    aliases = _load_aliases()
    logos_set = _load_logos_set()

    for i, s in enumerate(spec.get("slides", [])):
        if s.get("type") != "diagram" or not s.get("diagram"):
            continue
        label = f"Slide {i+1} ({s.get('id', '?')})"
        diag = s["diagram"]

        if not features.get("diagram_slide", True):
            errors.append(f"{label}: diagram slide exists but features.diagram_slide=false. → Fix: Remove diagram slide from spec or set diagram_slide=true")

        icon_size = diag.get("iconSize", 40)
        if icon_size not in VALID_ICON_SIZES:
            errors.append(f"{label}: diagram.iconSize={icon_size} not in {sorted(VALID_ICON_SIZES)}. → Fix: Use 20, 30, or 40.")

        groups = diag.get("groups", [])
        if not isinstance(groups, list):
            errors.append(f"{label}: diagram.groups must be an array.")
            groups = []
        groups = [g for g in groups if isinstance(g, dict)]
        group_ids = set()
        group_by_id = {}
        for g in groups:
            gid = g.get("id", "")
            if gid in group_ids:
                errors.append(f"{label}: duplicate group id '{gid}'. → Fix: Rename one of the duplicate groups.")
            group_ids.add(gid)
            group_by_id[gid] = g
            if g.get("colSpan", 1) <= 0 or g.get("rowSpan", 1) <= 0:
                errors.append(f"{label}: group '{gid}' colSpan/rowSpan must be > 0. → Fix: Set colSpan and rowSpan to at least 1.")
            gc = g.get("color", "default")
            if gc not in VALID_GROUP_COLORS:
                errors.append(f"{label}: group '{gid}' color='{gc}' not in {sorted(VALID_GROUP_COLORS)}. → Fix: Choose a valid color from the list.")
            pid = g.get("parentGroupId")
            if pid:
                if pid not in group_ids:
                    errors.append(f"{label}: group '{gid}' parentGroupId='{pid}' not found. → Fix: Define parent group earlier in the array, or fix parentGroupId spelling.")
                elif pid == gid:
                    errors.append(f"{label}: group '{gid}' parentGroupId cannot reference itself. → Fix: Remove parentGroupId or point to a different group.")
                else:
                    parent = group_by_id.get(pid, {})
                    if parent.get("parentGroupId"):
                        errors.append(f"{label}: group '{gid}' nested depth > 1. → Fix: Flatten to max 1 level of nesting (parent→child only).")

        nodes = diag.get("nodes", [])
        if not isinstance(nodes, list):
            errors.append(f"{label}: diagram.nodes must be an array.")
            nodes = []
        nodes = [n for n in nodes if isinstance(n, dict)]

        for g in groups:
            gid = g.get("id", "")
            g_nodes = [n for n in nodes if n.get("groupId") == gid]
            child_groups = [g2 for g2 in groups if g2.get("parentGroupId") == gid]
            if not g_nodes and not child_groups:
                warnings.append(f"{label}: group '{gid}' has no nodes or child groups (renders as empty box).")
        node_ids = set()
        node_positions = {}
        for n in nodes:
            nid = n.get("id", "")
            if not nid:
                errors.append(f"{label}: node missing 'id'. → Fix: Add a unique id field (e.g. 'n1', 'n2').")
                continue
            if nid in node_ids:
                errors.append(f"{label}: duplicate node id '{nid}'. → Fix: Rename one of the duplicate nodes.")
            node_ids.add(nid)

            gid = n.get("groupId")
            if gid and gid not in group_ids:
                errors.append(f"{label}: node '{nid}' groupId='{gid}' not found in groups. → Fix: Add the group or remove groupId from this node.")

            if gid:
                grp = next((g for g in groups if g.get("id") == gid), None)
                if grp:
                    col = n.get("col", 0)
                    row = n.get("row", 0)
                    if col >= grp.get("colSpan", 1):
                        errors.append(f"{label}: node '{nid}' col={col} exceeds group '{gid}' colSpan={grp['colSpan']}. → Fix: Increase group colSpan to at least {col+1}, or move node to lower col.")
                    if row >= grp.get("rowSpan", 1):
                        errors.append(f"{label}: node '{nid}' row={row} exceeds group '{gid}' rowSpan={grp['rowSpan']}. → Fix: Increase group rowSpan to at least {row+1}, or move node to lower row.")

            pos_key = (n.get("groupId", "__global__"), n.get("col", 0), n.get("row", 0))
            if pos_key in node_positions:
                errors.append(f"{label}: node '{nid}' same col/row as '{node_positions[pos_key]}' in group '{pos_key[0]}'. → Fix: Move one node to a different col or row.")
            else:
                node_positions[pos_key] = nid

            shape = n.get("shape", "icon")
            if shape == "icon":
                icon_name = n.get("icon", "")
                normalized = icon_name.lower().replace("-", "_").replace(" ", "_")
                resolved = aliases.get(normalized, aliases.get(icon_name, normalized))
                if icons_list and resolved not in icons_list and normalized not in icons_list:
                    suggestions = difflib.get_close_matches(normalized, icons_list, n=3, cutoff=0.6)
                    hint = f" Did you mean: {', '.join(suggestions)}?" if suggestions else ""
                    errors.append(f"{label}: node '{nid}' icon='{icon_name}' (resolved: '{resolved}') not found in icons_list. → Fix: Use a valid icon name from icons_list.json.{hint}")
                node_label = n.get("label", "")
                generic_icons = {"database", "server", "cube", "cloud", "application", "process_1", "data", "storage", "monitor", "log"}
                if resolved in generic_icons and node_label:
                    label_norm = node_label.lower().replace("-", "_").replace(" ", "_")
                    label_match = aliases.get(label_norm)
                    if not label_match and label_norm in logos_set:
                        label_match = label_norm
                    if not label_match:
                        for licon in logos_set:
                            if licon in label_norm or label_norm in licon:
                                label_match = licon
                                break
                    if label_match and label_match != resolved:
                        if label_match in logos_set:
                            errors.append(f"{label}: node '{nid}' uses generic icon '{resolved}' but label '{node_label}' matches brand icon '{label_match}' in logos. → Fix: Use icon='{label_match}'.")
                        else:
                            warnings.append(f"{label}: node '{nid}' uses generic icon '{resolved}' but label '{node_label}' matches alias '{label_norm}' → '{label_match}'. Consider using the specific icon.")
            elif shape in ("box", "rect"):
                pass
            else:
                errors.append(f"{label}: node '{nid}' invalid shape='{shape}'. → Fix: Use 'icon' (default) or remove the shape field.")

        edges = diag.get("edges", [])
        edge_pairs = set()
        for ei, e in enumerate(edges):
            efrom = e.get("from", "")
            eto = e.get("to", "")
            if efrom not in node_ids:
                errors.append(f"{label}: edge[{ei}] from='{efrom}' not found in nodes. → Fix: Check node id spelling or add the missing node.")
            if eto not in node_ids:
                errors.append(f"{label}: edge[{ei}] to='{eto}' not found in nodes. → Fix: Check node id spelling or add the missing node.")
            if efrom == eto:
                errors.append(f"{label}: edge[{ei}] self-loop (from==to='{efrom}'). → Fix: Edges cannot connect a node to itself.")
            pair = (efrom, eto)
            reverse_pair = (eto, efrom)
            if pair in edge_pairs:
                prev_e = next((pe for pe in edges if (pe.get("from",""), pe.get("to","")) == pair and pe is not e), None)
                prev_label = prev_e.get("label", "") if prev_e else ""
                cur_label = e.get("label", "")
                if prev_label == cur_label:
                    errors.append(f"{label}: edge[{ei}] duplicate edge {efrom}->{eto} with same label. → Fix: Remove the duplicate edge.")
                else:
                    warnings.append(f"{label}: edge[{ei}] duplicate edge {efrom}->{eto} (different labels)")
            if reverse_pair in edge_pairs:
                errors.append(f"{label}: edge[{ei}] reverse edge {efrom}->{eto} exists alongside {eto}->{efrom}. → Fix: Remove one edge and set startArrow='arrow', endArrow='arrow' on the remaining one.")
            edge_pairs.add(pair)

            line = e.get("line", "")
            if line not in VALID_EDGE_LINES:
                errors.append(f"{label}: edge[{ei}] line='{line}' invalid. → Fix: Use 'elbow', 'straight', or 'curved'.")
            sa = e.get("startArrow", "")
            if sa not in VALID_EDGE_ARROWS:
                errors.append(f"{label}: edge[{ei}] startArrow='{sa}' invalid. → Fix: Use 'arrow' or 'none'.")
            ea = e.get("endArrow", "")
            if ea not in VALID_EDGE_ARROWS:
                errors.append(f"{label}: edge[{ei}] endArrow='{ea}' invalid. → Fix: Use 'arrow' or 'none'.")
            ec = e.get("color", "")
            if ec not in VALID_EDGE_COLORS:
                errors.append(f"{label}: edge[{ei}] color='{ec}' invalid. → Fix: Use 'dark_blue', 'gray', or 'accent'.")
            dashed = e.get("dashed")
            if dashed is not None and not isinstance(dashed, bool):
                errors.append(f"{label}: edge[{ei}] dashed must be boolean, got {type(dashed).__name__}. → Fix: Set dashed to true or false (no quotes).")

            for side_key in ("fromSide", "toSide"):
                sv = e.get(side_key)
                if sv is not None and sv not in VALID_SIDES:
                    errors.append(f"{label}: edge[{ei}] {side_key}='{sv}' invalid. → Fix: Use 'top', 'right', 'bottom', or 'left'.")

        # --- Check edges crossing intermediate nodes (pixel-based) ---
        from diagram_layout import compute_layout, edge_segments, seg_intersects_rect, DRAW_RIGHT, DRAW_BOTTOM, DIAGRAM_GRID
        has_body = bool(s.get("body"))
        body_start_y_emu = config.get("layout", {}).get("body_start_y", 1080000)
        if has_body:
            body_fs = s.get("bodySize", config.get("sizes", {}).get("body", 10))
            body_h_emu = estimate_body_h(s["body"], body_fs)
            start_y_emu = body_start_y_emu + body_h_emu + 60000 + 60000
        else:
            start_y_emu = body_start_y_emu + 60000
        layout_start_y_pt = start_y_emu / 12700
        layout_cell = DIAGRAM_GRID.get(icon_size, DIAGRAM_GRID[40])["cell"]
        try:
            layout = compute_layout(diag, {}, start_y_emu)
            node_px = layout["node_positions"]
            l_icon = layout["icon_size"]
            l_cell = layout["cell"]
            layout_start_y_pt = layout["start_y_pt"]
            layout_cell = l_cell

            for ei, e in enumerate(edges):
                efrom = e.get("from", "")
                eto = e.get("to", "")
                if efrom not in node_px or eto not in node_px:
                    continue
                fp = node_px[efrom]
                tp = node_px[eto]
                line_type = e.get("line", "elbow")
                if line_type == "straight":
                    dx = tp["x"] - fp["x"]
                    dy = tp["y"] - fp["y"]
                    if abs(dy) < 0.1:
                        segs = [((fp["x"] + l_icon, fp["y"] + l_icon / 2), (tp["x"], tp["y"] + l_icon / 2))]
                    elif abs(dx) < 0.1:
                        segs = [((fp["x"] + l_icon / 2, fp["y"] + l_icon), (tp["x"] + l_icon / 2, tp["y"]))]
                    else:
                        continue
                else:
                    segs = edge_segments(fp, tp, l_icon, None, None)
                for nid, npos in node_px.items():
                    if nid == efrom or nid == eto:
                        continue
                    margin = 5
                    rect = (npos["x"] + margin, npos["y"] + margin, npos["x"] + l_icon - margin, npos["y"] + l_icon - margin)
                    for seg in segs:
                        if seg_intersects_rect(seg, rect):
                            dx = tp["x"] - fp["x"]
                            dy = tp["y"] - fp["y"]
                            dirs = []
                            if dx > 0: dirs.append("right")
                            elif dx < 0: dirs.append("left")
                            if dy > 0: dirs.append("down")
                            elif dy < 0: dirs.append("up")
                            dir_str = "+".join(dirs) if dirs else "same position"
                            n_node = [n for n in nodes if n["id"] == nid]
                            n_loc = f"col={n_node[0].get('col')},row={n_node[0].get('row')}" if n_node else ""
                            errors.append(f"[CROSSING] {label}: edge[{ei}] {efrom}->{eto} crosses node '{nid}' (edge goes {dir_str}, node at {n_loc}). → Priority: (1) Rearrange node col/row to remove the intermediate node from the edge path, (2) fromSide/toSide may help only when the crossing node is offset from the direct path — it does NOT reroute around obstacles.")
                            break
                    else:
                        continue
                    break

            for nid, npos in node_px.items():
                if npos["x"] < -2:
                    errors.append(f"{label}: node '{nid}' is outside slide left edge (x={npos['x']:.0f}pt). → Fix: Remove offsetX or increase col. Do NOT use offsetX to escape overlap — rearrange group col or free node col instead.")
                if npos["y"] < layout_start_y_pt - 5:
                    errors.append(f"{label}: node '{nid}' is above diagram area (y={npos['y']:.0f}pt). → Fix: Remove offsetY or increase row.")
                if npos["x"] + l_icon > DRAW_RIGHT + 15:
                    errors.append(f"{label}: node '{nid}' exceeds slide width ({npos['x'] + l_icon:.0f}pt > {DRAW_RIGHT}pt). → Fix: Reduce iconSize or max col.")
                elif npos["x"] + l_icon > DRAW_RIGHT + 5:
                    warnings.append(f"{label}: node '{nid}' near slide right edge ({npos['x'] + l_icon:.0f}pt, limit {DRAW_RIGHT}pt).")
                if npos["y"] + l_icon > DRAW_BOTTOM + 25:
                    errors.append(f"{label}: node '{nid}' exceeds slide height ({npos['y'] + l_icon:.0f}pt > {DRAW_BOTTOM + 20}pt). → Fix: Reduce iconSize or row count.")
            for gid, gp in layout["group_positions"].items():
                if gp["x"] + gp["w"] > DRAW_RIGHT + 15:
                    errors.append(f"{label}: group '{gid}' exceeds slide width ({gp['x'] + gp['w']:.0f}pt > {DRAW_RIGHT}pt).")
                elif gp["x"] + gp["w"] > DRAW_RIGHT + 5:
                    warnings.append(f"{label}: group '{gid}' near slide right edge ({gp['x'] + gp['w']:.0f}pt, limit {DRAW_RIGHT}pt).")
                if gp["y"] + gp["h"] > DRAW_BOTTOM + 5:
                    errors.append(f"{label}: group '{gid}' exceeds slide height ({gp['y'] + gp['h']:.0f}pt > {DRAW_BOTTOM}pt).")

            grouped_node_ids = {n.get("id") for n in nodes if n.get("groupId")}
            for nid, npos in node_px.items():
                if nid in grouped_node_ids:
                    continue
                nx1 = npos["x"]
                ny1 = npos["y"]
                nx2 = npos["x"] + l_icon
                ny2 = npos["y"] + l_icon
                for gid, gp in layout["group_positions"].items():
                    gx1, gy1 = gp["x"], gp["y"]
                    gx2, gy2 = gx1 + gp["w"], gy1 + gp["h"]
                    if nx1 < gx2 and nx2 > gx1 and ny1 < gy2 and ny2 > gy1:
                        errors.append(f"{label}: free node '{nid}' overlaps group '{gid}'. → Fix: (1) Move group col right so free node col is outside, (2) Rearrange free node row/col to non-overlapping position, or (3) Wrap free node in its own single-node group. Do NOT use offsetX/offsetY to escape — it may push nodes outside the slide.")
        except Exception as exc:
            warnings.append(f"{label}: layout computation failed ({exc}), edge crossing and bounds checks skipped.")

        # --- Structural group checks ---
        top_groups_no_parent = [g2 for g2 in groups if not g2.get("parentGroupId")]
        _overlap_checked = set()
        for g in groups:
            gid = g.get("id", "")
            gc = g.get("col", 0)
            gr = g.get("row", 0)
            gcs = g.get("colSpan", 1)
            grs = g.get("rowSpan", 1)
            parent_id = g.get("parentGroupId")
            if parent_id:
                parent = next((pg for pg in groups if pg.get("id") == parent_id), None)
                if parent and grs >= parent.get("rowSpan", 1):
                    errors.append(f"{label}: child group '{gid}' rowSpan={grs} >= parent '{parent_id}' rowSpan={parent.get('rowSpan', 1)}. → Fix: Increase parent rowSpan to at least {grs + 1}.")
            if not parent_id:
                padding_y_val = 30
                padding_bottom_val = 10
                available_h = DRAW_BOTTOM - layout_start_y_pt - padding_y_val - padding_bottom_val
                max_rs = max(1, int(available_h / layout_cell))
                if grs > max_rs:
                    suggestions = []
                    for sz_key in sorted(DIAGRAM_GRID.keys()):
                        if sz_key < icon_size:
                            sz_cell = DIAGRAM_GRID[sz_key]["cell"]
                            sz_max = max(1, int((DRAW_BOTTOM - layout_start_y_pt - padding_y_val - padding_bottom_val) / sz_cell))
                            if sz_max >= grs:
                                suggestions.append(f"iconSize={sz_key} (allows rowSpan up to {sz_max})")
                    fix_msg = f"Use {suggestions[0]}" if suggestions else f"Reduce rowSpan to {max_rs}"
                    errors.append(f"{label}: group '{gid}' rowSpan={grs} exceeds max ({max_rs}) for iconSize={icon_size}{' with body' if has_body else ''}. → Fix: {fix_msg}.")
                if gcs <= 0:
                    errors.append(f"{label}: group '{gid}' has colSpan={gcs}. Must be >= 1.")
            if not parent_id:
                for g2 in top_groups_no_parent:
                    g2id = g2.get("id", "")
                    if g2id == gid:
                        continue
                    pair = tuple(sorted([gid, g2id]))
                    if pair in _overlap_checked:
                        continue
                    _overlap_checked.add(pair)
                    g2r = g2.get("row", 0)
                    g2rs = g2.get("rowSpan", 1)
                    g2c = g2.get("col", 0)
                    g2cs = g2.get("colSpan", 1)
                    if gr == g2r and grs == g2rs:
                        continue
                    col_overlap = g2c < gc + gcs and g2c + g2cs > gc
                    if not col_overlap:
                        continue
                    if g2r < gr + grs and g2r + g2rs > gr:
                        errors.append(f"{label}: groups '{gid}' and '{g2id}' overlap vertically (rows {gr}-{gr+grs} vs {g2r}-{g2r+g2rs}). → Fix: Adjust row/rowSpan so groups don't overlap.")

        # --- iconSize upgrade check ---
        if icon_size < 40:
            all_cols = [n.get("col", 0) for n in nodes]
            all_rows = [n.get("row", 0) for n in nodes]
            all_rowspans = [g.get("rowSpan", 1) for g in groups if not g.get("parentGroupId")]
            if all_cols and all_rows:
                max_c = max(all_cols)
                max_r = max(all_rows)
                max_rs = max(all_rowspans) if all_rowspans else max_r + 1
                pad_x = 20
                pad_y = 30
                pad_bottom = 10
                avail_w = DRAW_RIGHT - 20 - pad_x * 2
                avail_h = DRAW_BOTTOM - layout_start_y_pt - pad_y - pad_bottom
                top_groups = [g for g in groups if not g.get("parentGroupId")]
                best = icon_size
                for sz in sorted(DIAGRAM_GRID.keys(), reverse=True):
                    if sz <= icon_size:
                        continue
                    sz_cell = DIAGRAM_GRID[sz]["cell"]
                    need_w = (max_c + 1) * sz_cell + pad_x * 2
                    need_h_nodes = (max_r + 1) * sz_cell + pad_y + pad_bottom
                    need_h_groups = max_rs * sz_cell + pad_y + pad_bottom
                    need_h = max(need_h_nodes, need_h_groups)
                    fits_h = need_h <= avail_h
                    fits_w = need_w <= avail_w
                    if fits_w and top_groups:
                        row_groups = {}
                        for g in top_groups:
                            gr = g.get("row", 0)
                            g_nodes = [nd for nd in nodes if nd.get("groupId") == g.get("id")]
                            g_max_col = max((nd.get("col", 0) for nd in g_nodes), default=0)
                            min_w = (g_max_col + 1) * sz_cell + pad_x * 2
                            row_groups.setdefault(gr, []).append(min_w)
                        for gr, widths in row_groups.items():
                            total_min_w = sum(widths) + 20 * (len(widths) - 1)
                            if total_min_w > DRAW_RIGHT - 20:
                                fits_w = False
                                break
                    if fits_w and fits_h:
                        best = sz
                        break
                if best > icon_size:
                    errors.append(f"{label}: iconSize={icon_size} but all nodes fit with iconSize={best}. → Fix: Use iconSize={best} for better readability.")

        # --- Orphan node check (WARNING) ---
        if edges:
            nodes_in_edges = set()
            for e in edges:
                nodes_in_edges.add(e.get("from", ""))
                nodes_in_edges.add(e.get("to", ""))
            for n in nodes:
                nid = n.get("id", "")
                if nid and nid not in nodes_in_edges and not n.get("groupId"):
                    warnings.append(f"{label}: node '{nid}' has no edges (orphan). Verify this is intentional.")

        # --- Entity-Edge Manifest verification ---
        manifest = diag.get("_manifest")
        if manifest is None:
            errors.append(f"{label}: diagram missing '_manifest' field. → Fix: Add _manifest with entities and flows arrays before writing diagram JSON.")
        elif isinstance(manifest, dict):
            m_entities = manifest.get("entities", [])
            m_flows = manifest.get("flows", [])
            if not isinstance(m_entities, list) or not m_entities:
                errors.append(f"{label}: _manifest.entities is empty or invalid. → Fix: List all entities from the source md section.")
            else:
                def _norm(s):
                    import re
                    n = re.sub(r'[^a-z0-9_]', '_', s.lower().replace("\n", " "))
                    return re.sub(r'_+', '_', n).strip('_')
                node_keys = set()
                for n in nodes:
                    nid = n.get("id", "")
                    nlabel = n.get("label", "")
                    if nid:
                        node_keys.add(_norm(nid))
                    if nlabel:
                        node_keys.add(_norm(nlabel))
                for ent in m_entities:
                    if _norm(str(ent)) not in node_keys:
                        candidates = difflib.get_close_matches(_norm(str(ent)), list(node_keys), n=2, cutoff=0.4)
                        hint = f" Did you mean: {', '.join(candidates)}?" if candidates else ""
                        errors.append(f"{label}: _manifest entity '{ent}' has no matching node. → Fix: Add a node for '{ent}' or update _manifest.{hint}")
            if not isinstance(m_flows, list):
                errors.append(f"{label}: _manifest.flows must be an array.")
            elif not m_flows and edges:
                errors.append(f"{label}: _manifest.flows is empty but edges exist. → Fix: List all from→to flows from the source md section.")
            elif m_flows:
                for flow in m_flows:
                    if isinstance(flow, dict):
                        ff = flow.get("from", "")
                        ft = flow.get("to", "")
                    elif isinstance(flow, str) and "→" in flow:
                        parts = flow.split("→")
                        ff = parts[0].strip()
                        ft = parts[-1].strip()
                    else:
                        continue
                    ff_n = _norm(ff)
                    ft_n = _norm(ft)
                    matched = False
                    node_id_by_name = {}
                    for n in nodes:
                        nid = n.get("id", "")
                        nlabel = n.get("label", "")
                        if nid:
                            node_id_by_name[_norm(nid)] = nid
                        if nlabel:
                            node_id_by_name[_norm(nlabel)] = nid
                    ff_id = node_id_by_name.get(ff_n, ff_n)
                    ft_id = node_id_by_name.get(ft_n, ft_n)
                    for e in edges:
                        ef = _norm(e.get("from", ""))
                        et = _norm(e.get("to", ""))
                        if (ef == _norm(ff_id) or ef == ff_n) and (et == _norm(ft_id) or et == ft_n):
                            matched = True
                            break
                    if not matched:
                        errors.append(f"{label}: _manifest flow '{ff}→{ft}' has no matching edge. → Fix: Add an edge from '{ff}' to '{ft}' or update _manifest.")
        else:
            errors.append(f"{label}: _manifest must be a dict with 'entities' and 'flows' arrays.")

        # --- Group rowSpan efficiency check (WARNING) ---
        for g in groups:
            gid = g.get("id", "")
            rs = g.get("rowSpan", 1)
            g_nodes = [n for n in nodes if n.get("groupId") == gid]
            child_groups = [g2 for g2 in groups if g2.get("parentGroupId") == gid]
            if not child_groups and g_nodes:
                max_row = max(n.get("row", 0) for n in g_nodes)
                needed_rs = max_row + 1
                if rs >= needed_rs * 2 and needed_rs >= 2:
                    warnings.append(f"{label}: group '{gid}' rowSpan={rs} but content only needs {needed_rs}. Consider rowSpan={needed_rs}.")

    return errors, warnings


def lint(spec, audit=None):
    all_errors = []
    all_warnings = []

    cfg_errors, cfg_warnings = validate_config(spec)
    all_errors.extend(cfg_errors)
    all_warnings.extend(cfg_warnings)

    if cfg_errors:
        return all_errors, all_warnings

    slide_errors, slide_warnings = validate_slides(spec, audit)
    all_errors.extend(slide_errors)
    all_warnings.extend(slide_warnings)

    diag_errors, diag_warnings = validate_diagram(spec)
    all_errors.extend(diag_errors)
    all_warnings.extend(diag_warnings)

    overflow_results = validate_overflow(spec)
    for r in overflow_results:
        if r.startswith("ERROR:"):
            all_errors.append(r[7:])
        elif r.startswith("WARN:"):
            all_warnings.append(r[6:])
        else:
            all_warnings.append(r)

    return all_errors, all_warnings


def main():
    parser = argparse.ArgumentParser(description="Lint spec.json for rule compliance")
    parser.add_argument("spec", help="JSON specification file to lint")
    parser.add_argument("--audit", help="audit.json for layoutId validation")
    args = parser.parse_args()

    with open(args.spec) as f:
        try:
            spec = json.load(f)
        except json.JSONDecodeError as e:
            print(f"ERROR: Invalid JSON: {e}")
            sys.exit(3)

    audit = None
    if args.audit:
        with open(args.audit) as f:
            audit = json.load(f)

    errors, warnings = lint(spec, audit)

    if warnings:
        for w in warnings:
            print(f"  WARN: {w}")
    if errors:
        for e in errors:
            print(f"  ERROR: {e}")
        print(f"\n{len(errors)} error(s), {len(warnings)} warning(s). Fix before building.")
        sys.exit(1)
    else:
        print(f"  OK ({len(warnings)} warnings)")
        sys.exit(0)


if __name__ == "__main__":
    main()

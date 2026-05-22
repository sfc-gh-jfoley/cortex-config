# Google Slides API Patterns

API patterns used by build_slides.py. Reference for CoCo when generating spec.json.

## Execution Modes

| Mode | Command | Behavior |
|------|---------|----------|
| Full generation | `build_slides.py <pid> spec.json` | Backup → delete all existing → recreate |
| Full (keep existing) | `build_slides.py <pid> spec.json --keep-existing` | Backup → keep existing, prepend new |
| Append (end) | `build_slides.py <pid> spec.json --append` | Keep existing, append at end |
| Append (position) | `build_slides.py <pid> spec.json --append --insert-after 5` | Keep existing, insert after slide 5 |
| Update | `rebuild_slide.py <pid> --slide <N> --spec patch.json` | Move old slide to end (skipped), create new at same position |

Append mode never deletes existing slides.

## spec.json Schema

```json
{
  "config_version": 1,
  "config": {
    "fonts": {"primary": "Arial", "code": "Courier New"},
    "sizes": {"cover_title": 44, "cover_subtitle": 20, "cover_date": 14, "title": 24, "title_min": 20, "subtitle": 14, "body": 10, "body_header": 11, "agenda_title": 28, "agenda_items": 16, "divider": 36, "table_body": 8, "table_header_increment": 1, "code": 8},
    "colors": {"snowflake_blue": [0.16, 0.71, 0.91], "accent": [0.831, 0.357, 0.565], "body_text": [0, 0, 0], "code_background": [0.051, 0.067, 0.09]},
    "table": {"default_x": 450000, "default_w": 8200000, "default_row_height": 330000, "min_column_width": 500000, "background_color": [0.92, 0.97, 1.0], "background_zebra_color": [0.86, 0.94, 0.99], "border_color": [1, 1, 1]},
    "code_block": {"accent_bar_width": 50000, "padding": 80000, "max_lines": 25, "accent_colors": {"sql": [0.16, 0.71, 0.91], "programming": [0.494, 0.341, 0.761], "config": [0.545, 0.580, 0.620], "other": [0.306, 0.667, 0.145]}},
    "layout": {"page_bottom_margin": 450000, "body_start_y": 1080000, "body_table_gap": 60000, "content_x": 450000, "content_w": 8200000, "body_line_spacing": 115},
    "rules": {"title_base_max_chars": 50, "subtitle_max_chars": 70, "agenda_max_items": 20},
    "features": {"cover_slide": true, "agenda_slide": true, "section_dividers": true, "thanks_slide": true, "title_section_prefix": true, "table_zebra_stripes": true, "jp_period_to_newline": true, "auto_link_snowflake_views": true, "body_accent_emphasis": true, "cover_date": true, "subtitle_required": true, "diagram_slide": true}
  },
  "agenda_items": ["Item 1", "Item 2", "New Item"],
  "slides": [
    {
      "id": "sl_xxx",        // Unique slide ID (5+ chars)
      "layout": "cover|agenda|multi|divider|blank|thanks",
      "layoutId": "g1ed...", // Actual layout ID from audit_template.py
      "title": "...",
      "subtitle": "...",     // multi: must be 1 line. Goes into SUBTITLE placeholder
      "body": "...",         // multi: Body bullets. Separate text box. Non-bullet lines ending with : or # headings = header (11pt bold)
      "bodyY": 1080000,      // optional: body Y position (default 1080000)
      "bodyH": 1500000,      // optional: body height (default auto-calculated)
      "bodySize": 10,        // optional: body font size (default 10)
      "date": "...",         // cover only
      "items": ["..."],      // agenda only
      "type": "bullets|table|code|diagram",  // multi/blank content type
      "titleSize": 24,       // optional (default 24)
      "subtitleSize": 14,    // optional (default 14)
      "table": {             // type=table
        "data": [["header1", "header2"], ["val1", "val2"]],
        "x": 450000, "w": 8200000,
        "rowHeight": 330000, "fontSize": 8,
        "columnWidths": [500000, 3850000, 3850000]  // optional: column widths in EMU (NOT pt). Sum ≈ table w
        // NOTE: do not specify y (auto-calculated from body bottom)
      },
      "code": {              // type=code
        "language": "sql",   // Pygments-supported language (sql, python, json, yaml, etc.)
        "source": "SELECT ...",  // Code text
        "fontSize": 8,       // optional (default 8). Courier New bold
        "x": 450000,         // optional
        "w": 8200000,        // optional
        "h": null            // optional: auto-calculated (line-based). Manual override possible
        // NOTE: do not specify y (auto-calculated from body bottom)
      }
    }
  ]
}
```

See `config/snowflake-gslides-config.yaml` for full config reference with comments. All build/lint operations use config values from spec.json exclusively.

## Table Placement Guidelines

> **Note**: These are reference values for understanding layout. In spec.json, do NOT specify `table.y` — it is auto-calculated from body bottom by build_slides.py.

| Slide structure | Table y | Notes |
|----------------|---------|-------|
| Title + subtitle (1 line) + table | 1400000 | Short subtitle |
| Title + subtitle (2-3 lines) + table | 1700000 | Subtitle with description |
| Title + table only | 1200000 | No subtitle |

Row height guideline: rows × rowHeight must not exceed page bottom (5,143,500 - `config.layout.page_bottom_margin`).
Margins: `config.layout.page_bottom_margin` EMU on bottom.
Table header: bold + white text + fontSize `config.sizes.table_header_increment` pt larger than body rows (automatic).
Column widths: if `columnWidths` is specified in spec.json, those values are used. If omitted, build_slides.py auto-calculates proportional widths based on max cell content length per column (CJK chars counted as 2). Minimum column width: `config.table.min_column_width` EMU.
Zebra stripes: 2-tone light blue auto-applied (odd rows `config.table.background_zebra_color` / even rows `config.table.background_color`).
Borders: all white (row/column/outer). Visual row separation via background color + borders.
Table cell bullet formatting: Markdown tables are single-line per cell. When multiple items should appear as bullet points, use `\n` in spec.json cell text. The script auto-applies native bullet format to any data cell containing `\n`.
Japanese `。` in table cells: also auto-converted to newline + native bullet format (header row excluded).
Table bullet indent: indentFirstLine=0.06in (bullet position), indentStart=0.19in (text wrap position).
Table cell bold: `**text**` in data cells → bold only (no accent color). `**` markers are removed. Header row is already fully bold.
Table cell code: `` `text` `` in data cells → Courier New (monospace) + bold. Backtick markers are removed. Use for identifiers, object names, code references.
Table cell hyperlinks: `[text](url)` → clickable link text.

## Code Block (code)

| Item | Value |
|------|-------|
| Theme | GitHub Dark Default |
| Background | #0d1117 |
| Header bar | None (removed) |
| Left accent bar | Language-dependent (see below) |
| Font | `config.fonts.code` `config.sizes.code`pt bold |
| Syntax highlighting | Pygments + Snowflake reclassification |

| Token | Color |
|-------|-------|
| Keywords (SELECT, CREATE) | #ff7b72 (red) |
| Builtins (VARCHAR, INT) | #79c0ff (blue) |
| Functions (MAX_BY, FLATTEN) | #d2a8ff (purple) |
| Strings | #a5d6ff (light blue) |
| Numbers | #79c0ff (blue) |
| Comments | #8b949e (gray) |
| Operators | #ff7b72 (red) |
| Default text | #e6edf3 (white) |

Code block structure: background rectangle (#0d1117) + left accent bar (color by language category) + transparent text box (code body).

Left accent bar colors by language category:
| Category | Languages | Color | Hex |
|----------|-----------|-------|-----|
| SQL | sql | Snowflake Blue | #29B5E8 |
| Programming | python, java, javascript, typescript, go, rust, scala, ruby | Purple | #7E57C2 |
| Config | json, yaml, toml, xml, ini | Gray | #8B949E |
| Other | bash, shell, text, etc. | Green | #4EAA25 |
Y position auto-calculated from body bottom. Mutually exclusive with table (1 slide = 1 content type).
~25 lines of code is appropriate. Extract key portions from longer code.

## Body Format

| Markup | Display Result |
|--------|---------------|
| Lines starting with `•` or `-` | Google Slides native bullets |
| Non-bullet line ending with `:` | 11pt bold (header line, auto-detected) |
| Lines starting with `#` to `####` | 11pt bold (header line, `#` removed from display) |
| `**text**` | Accent Color (#d45b90) bold emphasis (full line or partial) |
| `` `text` `` | Bold text. If text matches known Snowflake view/function, auto-linked to docs |
| `[text](url)` | Hyperlinked text |
| Other lines | 10pt normal text |

Auto-linking: Known Snowflake view/function names (QUERY_HISTORY, METERING_DAILY_HISTORY, AI_COMPLETE, etc.) appearing as bare text (10+ chars) or in backticks in body are auto-linked to their official docs page.

## Snowflake Brand Colors

| Color | RGB | Usage |
|-------|-----|-------|
| Snowflake Blue | (0.16, 0.71, 0.91) | Table header, SQL accent bar |
| Accent Color | (0.831, 0.357, 0.565) | Body `**bold**` emphasis |
| Body Text | (0, 0, 0) | Body text |
| Code Background | (0.051, 0.067, 0.09) | Code block background |

## Font

`config.fonts.primary` for all elements (Snowflake template standard).
Non-Latin text (Japanese, Korean, Chinese, etc.) with the primary font specified will auto-fallback to the appropriate font on Google Slides side.

## Empty Placeholder Handling

Layout-inherited placeholders cannot be deleted via deleteObject.
Unfilled placeholders show "Click to add title" text, so they are moved off-screen to hide:

```python
transform = {scaleX: 0.01, scaleY: 0.01, translateX: 20000000, translateY: 20000000}
```

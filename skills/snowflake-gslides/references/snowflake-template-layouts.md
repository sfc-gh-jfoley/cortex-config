# Snowflake Template Layouts Reference

Layout specs for Snowflake Google Slides Template 2026.
Dynamically obtainable via `audit_template.py`, but frequently used layouts documented below.

## Key Layouts

| Purpose | displayName | Placeholders | Selection |
|---------|------------|--------------|-----------|
| Title page | Cover 04 | TITLE x3 (title, subtitle, date) | `recommendedLayouts.cover` |
| Table of contents | Agenda | BODY x2, SLIDE_NUMBER | `recommendedLayouts.agenda` |
| Content | Multi-use layout | TITLE, SUBTITLE, SLIDE_NUMBER | `recommendedLayouts.multi` |
| Long text | One Column Layout | BODY, TITLE, SUBTITLE, SLIDE_NUMBER | `recommendedLayouts.one_column` |
| Section divider | Divider - Dark Blue 02 | BODY | `recommendedLayouts.divider` |
| General | Blank (footer only) | SLIDE_NUMBER | `recommendedLayouts.blank` |
| Back cover | Thank You 02 | BODY | `recommendedLayouts.thanks` |

## Placeholder Types

| type | Description | Used in |
|------|-------------|---------|
| TITLE | Title text | Cover, Multi-use |
| SUBTITLE | Subtitle | Multi-use |
| BODY | Body text | Agenda, Divider, One Column, Thank You |
| SLIDE_NUMBER | Slide number (auto-managed by Google Slides UI, do not fill via API) | All layouts |

## Slide Type Patterns

### Cover
- TITLE[0]: Main title (`config.sizes.cover_title` pt, bold, white). Adjust text length to avoid line breaks. Text box width auto-expanded. Vertical alignment BOTTOM (text box bottom-aligned → displays near slide center)
- TITLE[1]: Subtitle (`config.sizes.cover_subtitle` pt, bold). Required. Report description (e.g., "Monthly Report — April 2026"). Do not include fixed text like "Snowflake Professional Services"
- TITLE[2]: "Snowflake | date" format (`config.sizes.cover_date` pt). e.g., "Snowflake | April 28, 2026"

### Agenda
- BODY[0]: "Agenda" (`config.sizes.agenda_title` pt, bold)
- BODY[1]: Agenda items (`config.sizes.agenda_items` pt default; auto-shrunk to 14pt for 11-15 items, 12pt for 16-20 items)

### Content (multi) — 3 Patterns
1. **Bullets only**: TITLE + SUBTITLE (1 line) + body text box (header lines bold)
2. **With table**: TITLE + SUBTITLE (1 line) + body text box (table description 1+ lines) + table
3. **With code block**: TITLE + SUBTITLE (1 line) + body text box + syntax-highlighted code block (GitHub Dark Default theme)

- Title (`config.sizes.title` pt) and subtitle (`config.sizes.subtitle` pt) required on all content slides
- Subtitle must be exactly 1 line (goes into SUBTITLE placeholder)
- Body specified via body field (placed as separate text box)
- Body header lines (non-bullet lines ending with `:` or starting with `#`~`####`) → auto bold (`config.sizes.body_header` pt)
- Table header is bold, `config.sizes.table_header_increment` pt larger than body rows
- `#` columns narrow via columnWidths
- Table zebra stripes auto-applied (odd rows `config.table.background_zebra_color` / even rows `config.table.background_color`, `config.table.border_color` borders)

### Divider
- BODY: Section name (`config.sizes.divider` pt, bold)
- Note: The Slides placeholder type is BODY, but the spec.json field is `title` (not `body`). build_slides.py maps `title` → BODY[0].

### Thank You (thanks)
- BODY: "THANK YOU" text (70pt, bold, white with black "YOU"). Template has built-in graphic.

## Template Version Differences

Layout IDs vary by template version.
Always use `recommendedLayouts` from `audit_template.py`.
displayName is relatively stable, so name-based matching is recommended.

## Page Size

| Item | Value |
|------|-------|
| Width | 9,144,000 EMU (10.0 inches) |
| Height | 5,143,500 EMU (5.6 inches) |
| 1 inch | 914,400 EMU |

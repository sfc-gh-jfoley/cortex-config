# snowflake-gslides

Auto-generate Snowflake-branded Google Slides from markdown content using CoCo skill.

## Prerequisites

- **Programmatic access to Google Workspace APIs** — This skill uses OAuth tokens obtained via `gcloud auth application-default login` (ADC) to call Google Slides API / Drive API. The GCP project must have these APIs enabled. If `gcloud services enable slides.googleapis.com drive.googleapis.com` returns `PERMISSION_DENIED`, file a Lift ticket ("**Request Google Workspace Admin Assistance**") to request Google Workspace APIs (Drive, Docs, Sheets, Slides) access on your GCP project (e.g., `snowflake-corp-cs-dev`)
- `gcloud auth application-default login` completed for ADC authentication
- Python 3.11+ / uv installed
- **Diagram icon insertion (first-time only)** — Open the following URL in your browser and complete the OAuth consent to authorize the icon insertion service: https://script.google.com/a/macros/snowflake.com/s/AKfycbyAet8HBRxZ3oBIkFe1hjZm_vGmib0eeFN_uQIl495tBifKbqotx07zXHTWGDHn-Oa1Xg/exec — This is required once per user. After consent, diagram slides with icons will work automatically.
- **Output Google Slides file must be created from Snowflake template** — Template "layouts" (master side) are required. Slides can be all deleted, partially remaining, or all 73 sample slides intact. Layouts persist even when slides are deleted.

## Setup

1. **Create markdown** — Write content following the [Slide Markdown Format](references/slide-markdown-format.md) guide. Or provide any text/document — the skill auto-converts to optimized md.
2. **Prepare Google Slides file** (optional) — Either create a new file from the Snowflake template, or use an existing Snowflake-template-based gslides file. If not specified, the skill auto-creates one from the configured template.
3. **Rename file** (if manually created) — Give it an appropriate name (e.g., `20260428_Monthly_Report.gslides`)

## Customization

Place a `snowflake-gslides-config.yaml` in your project folder to override default settings. Only include the keys you want to change — unspecified keys use defaults from `config/snowflake-gslides-config.yaml`.

Example override (project-level):
```yaml
sizes:
  title: 20
features:
  section_dividers: false
  table_zebra_stripes: false
```

## Prompt Examples

### Full generation — from markdown

```
Create slides from @monthly_report.md into @report.gslides
```

### From non-md file

```
Create slides from @meeting_notes.txt into @presentation.gslides
```

### From prompt (no file)

```
Make a 5-page presentation about our Q1 achievements into @quarterly.gslides:
- WH Health Check completed
- Performance optimization adopted
- WIF verification done
```

### Append mode — add slides from part of md

```
Add slides from @design_doc.md lines 50-80 into @presentation.gslides
```

### Update mode — modify a specific slide

```
Update slide 5 of @report.gslides with updated table data
```

### Add element — add icon/arrow to existing diagram

```
Add a "Tableau" icon to slide 8 of @report.gslides and connect it to the Snowflake node
```

## Icons

1300+ icons are available for diagram slides (Snowflake, AWS, Azure, Fabric, logos, general).

- **[Icon Catalog](https://drive.google.com/drive/folders/1lThLF4V1emweSG5BRI55LWUQaH_xc5Nn)** — Browse `icon_catalog.html` for a visual catalog with search. SVG and PNG versions are also available in `icons_svg/` and `icons_png/` subfolders for use in your own documents.
- Icon names: `config/icons_list.json` (categorized list)
- Aliases: `config/icon_aliases.json` (e.g., "s3" → "amazon_simple_storage_service")

## Processing Flow

1. **Input format handling** — If input is not md, convert to slide-optimized md and confirm. If gslides not specified, auto-create from template
2. **Mode selection** — Replace / Replace (keep existing) / Append / Update
3. **Template audit** — Auto-analyze gslides layout structure
4. **Analyze md** — Count sections, tables, code blocks; determine if Phase split needed
5. **Read config yaml** — Load default + local override (deep merge)
6. **Slide structure design** — Generate spec.json (config + slides) from md content
7. **Lint** — Validate spec.json (config structure, rules, overflow)
8. **Build** — Backup → Slides API: create slides, fill content
9. **Verification** — Overflow check, placeholder processing

## File Structure

```
snowflake-gslides/
├── SKILL.md                              ← CoCo instructions (Step 0-7 + Constraints)
├── README.md                             ← User documentation + parameter reference
├── pyproject.toml                        ← Python dependencies
├── config/
│   ├── snowflake-gslides-config.yaml     ← Default settings (all parameters)
│   ├── snowflake_docs_links.json         ← Auto-link URL dictionary (174 entries)
│   ├── index.json                        ← Icon catalog by category (diagram)
│   ├── icon_aliases.json                 ← Icon shorthand aliases (diagram)
│   └── icons_list.json                   ← Valid icon names for validation (diagram)
├── scripts/
│   ├── utils.py                          ← Shared utilities
│   ├── analyze_md.py                     ← MD structure analysis
│   ├── audit_template.py                 ← Template structure analysis
│   ├── lint_spec.py                      ← spec.json full validation
│   ├── check_urls.py                     ← Verify doc URLs are not broken (404)
│   ├── build_slides.py                   ← Slide generation
│   ├── diagram_builder.py               ← Diagram rendering engine
│   ├── diagram_layout.py                ← Shared layout computation (builder + lint)
│   ├── rebuild_slide.py                  ← Single slide update
│   ├── merge_spec.py                     ← Part merging (large inputs)
│   ├── add_elements.py                   ← Lightweight element addition to existing slides
│   └── read_slide_elements.py            ← Read existing slide elements
└── references/
    ├── snowflake-template-layouts.md     ← Layout specifications
    ├── slides-api-patterns.md            ← spec.json schema + API patterns
    ├── slide-markdown-format.md          ← Input md format guide
    ├── diagram-patterns.md              ← Diagram schema & 14 layout patterns
    └── diagram-visual-check.md          ← Diagram visual verification criteria
```

## Scripts

| Script | Purpose |
|--------|---------|
| `analyze_md.py` | Analyze md structure (sections, tables, code blocks, estimated slides) |
| `audit_template.py` | Analyze Google Slides template structure |
| `lint_spec.py` | Validate spec.json (config, rules, overflow) |
| `check_urls.py` | Verify docs.snowflake.com URLs (404 detection) |
| `build_slides.py` | Generate slides from spec.json |
| `diagram_builder.py` | Render diagram slides (icons, groups, edges) |
| `diagram_layout.py` | Shared layout computation used by builder and lint |
| `rebuild_slide.py` | Update a single slide in-place |
| `utils.py` | Shared utilities (API connection, text parsing, layout calculation) |
| `merge_spec.py` | Merge multiple part JSON files into a single spec.json (for large inputs) |
| `add_elements.py` | Add icons/groups/edges to existing slides without rebuild |
| `read_slide_elements.py` | Read existing slide elements for inspection |

## Slide Types

| Type | Purpose | Example |
|------|---------|---------|
| cover | Title page | Title + subtitle + date |
| agenda | Table of contents | Numbered list |
| divider | Section separator | Corresponds to `##` headings |
| multi (bullets) | Content (bullets) | Title + subtitle + bullets |
| multi (table) | Content (with table) | Title + subtitle + description + table |
| multi (code) | Content (with code) | Title + subtitle + syntax-highlighted code |
| multi (diagram) | Content (with diagram) | Title + subtitle + icon-based architecture diagram |
| thanks | Back cover | Thank You page |

## Guardrails

- **Full generation**: Always auto-creates backup. Default deletes existing slides. `--keep-existing` keeps them and prepends new slides
- **Append mode**: Never deletes existing slides. Include `agenda_items` in spec.json to auto-update Agenda
- **Update mode**: Old slide moved after Thanks (skipped). New slide at original position. No backup file

## Post-Generation

1. **Enable slide numbers** — Insert → Slide numbers → Apply (one-time)
2. **Review** — Open in Google Slides and check all slides
3. **Adjust** — Fine-tune layout/placement as needed
4. **Diagram slides** — Diagram slides auto-generate icon-based architecture/flow diagrams. Node placement and arrow routing are automated, but complex diagrams (many fan-out edges, cross-group connections, dense layouts) may have arrow overlaps or tight spacing. Adjust positions directly in Google Slides as needed

---

## Parameter Reference

### template_id

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `template_id` | string | See `config/snowflake-gslides-config.yaml` | Snowflake template presentation ID (auto-copied when gslides not specified) |

### fonts

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `fonts.primary` | string | `"Arial"` | Font for all text (titles, body, tables) |
| `fonts.code` | string | `"Courier New"` | Font for code blocks and backtick text in table cells |

### sizes (pt)

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `sizes.cover_title` | pt | 44 | Cover slide main title |
| `sizes.cover_subtitle` | pt | 20 | Cover slide subtitle |
| `sizes.cover_date` | pt | 14 | Cover slide date line |
| `sizes.title` | pt | 24 | Content slide title |
| `sizes.title_min` | pt | 20 | Minimum allowed title size |
| `sizes.subtitle` | pt | 14 | Content slide subtitle |
| `sizes.body` | pt | 10 | Body text |
| `sizes.body_header` | pt | 11 | Body header lines (`:` ending or `#` heading) |
| `sizes.agenda_title` | pt | 28 | "Agenda" heading |
| `sizes.agenda_items` | pt | 16 | Agenda list items (auto-shrunk: 11-15→14, 16-20→12) |
| `sizes.divider` | pt | 36 | Section divider title |
| `sizes.table_body` | pt | 8 | Table data row font |
| `sizes.table_header_increment` | pt | 1 | Header = table_body + this |
| `sizes.code` | pt | 8 | Code block font |

### colors (RGB 0.0-1.0)

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `colors.snowflake_blue` | [r,g,b] | [0.16, 0.71, 0.91] | Table header bg, SQL accent bar |
| `colors.accent` | [r,g,b] | [0.831, 0.357, 0.565] | Body `**bold**` emphasis (#d45b90) |
| `colors.body_text` | [r,g,b] | [0, 0, 0] | Body text color (black) |
| `colors.code_background` | [r,g,b] | [0.051, 0.067, 0.09] | Code block background (#0d1117) |

### table

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `table.default_x` | EMU | 450000 | Table X position |
| `table.default_w` | EMU | 8200000 | Table width |
| `table.default_row_height` | EMU | 330000 | Default row height |
| `table.min_column_width` | EMU | 500000 | Minimum column width |
| `table.background_color` | [r,g,b] | [0.92, 0.97, 1.0] | Base row background (all rows when zebra off) |
| `table.background_zebra_color` | [r,g,b] | [0.86, 0.94, 0.99] | Alternating row color (odd rows when zebra on) |
| `table.border_color` | [r,g,b] | [1, 1, 1] | Table border color (white) |

### code_block

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `code_block.accent_bar_width` | EMU | 50000 | Left accent bar width |
| `code_block.padding` | EMU | 80000 | Internal padding |
| `code_block.max_lines` | int | 25 | Max lines per code slide |
| `code_block.accent_colors.sql` | [r,g,b] | [0.16, 0.71, 0.91] | SQL accent bar (Snowflake Blue) |
| `code_block.accent_colors.programming` | [r,g,b] | [0.494, 0.341, 0.761] | Python/Java/JS etc. (Purple) |
| `code_block.accent_colors.config` | [r,g,b] | [0.545, 0.580, 0.620] | JSON/YAML/TOML (Gray) |
| `code_block.accent_colors.other` | [r,g,b] | [0.306, 0.667, 0.145] | Bash/Shell/Text (Green) |

### layout (EMU)

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `layout.page_bottom_margin` | EMU | 450000 | Bottom margin before content cutoff |
| `layout.body_start_y` | EMU | 1080000 | Body Y start (below subtitle) |
| `layout.body_table_gap` | EMU | 60000 | Gap between body and table/code |
| `layout.content_x` | EMU | 450000 | Default content X position |
| `layout.content_w` | EMU | 8200000 | Default content width |
| `layout.body_line_spacing` | % | 115 | Line spacing (115 = 1.15x) |

### rules

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `rules.title_base_max_chars` | int | 50 | Max display chars at default title size |
| `rules.subtitle_max_chars` | int | 70 | Max display chars for subtitle |
| `rules.agenda_max_items` | int | 20 | Max agenda items supported |

### features

Features control slide generation behavior. **Structure flags** (cover/agenda/dividers/thanks/title_prefix) affect CoCo's spec.json design — when false, CoCo simply does not include those slides or enforce that format. **Style flags** (zebra/jp_period/auto_link/accent) are applied during build execution.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `features.cover_slide` | bool | true | Generate Cover slide |
| `features.agenda_slide` | bool | true | Generate Agenda slide |
| `features.section_dividers` | bool | true | Generate section divider slides |
| `features.thanks_slide` | bool | true | Generate Thanks slide |
| `features.title_section_prefix` | bool | true | Enforce `Section — Title` format |
| `features.table_zebra_stripes` | bool | true | Alternating row background colors |
| `features.jp_period_to_newline` | bool | true | Convert `。` to newline in table cells |
| `features.auto_link_snowflake_views` | bool | true | Auto-link Snowflake view names to docs |
| `features.body_accent_emphasis` | bool | true | Apply accent color to `**bold**` in body |
| `features.cover_date` | bool | true | Include date line on Cover slide |
| `features.subtitle_required` | bool | true | Require subtitle on all content slides |
| `features.diagram_slide` | bool | true | Enable diagram slide type (icon + arrow diagrams) |

### Auto-link Data (`config/snowflake_docs_links.json`)

When `features.auto_link_snowflake_views` is true, known Snowflake view/function names in body text are auto-linked to documentation.

The link data is stored in `config/snowflake_docs_links.json` with two sections:
- `account_usage_views` — SNOWFLAKE.ACCOUNT_USAGE views (comprehensive)
- `functions` — Cortex AI functions

To add new entries, edit the JSON file directly. Only names with 10+ characters are matched (shorter names are skipped to avoid false positives).

---

## Limitations

- **Page numbers not managed by API** — Enable once via UI (Insert → Slide numbers); auto-updates thereafter
- **Diagram icon insertion requires Apps Script** — The configured Apps Script Web App must be deployed and accessible. See `config/snowflake-gslides-config.yaml` diagram section for the URL.
- **Images in md are not processed** — `![alt](image.png)` in source md is ignored. If an image contains an architecture diagram you want on slides, describe it as text or ask explicitly to convert it.

## Trademark Notice

Third-party logos and icons (AWS, Azure, GCP, dbt, Kafka, Tableau, etc.) included in this skill's icon library are trademarks of their respective owners. When distributing slides containing these icons to customers or external parties, ensure your use complies with each vendor's brand guidelines. Use of third-party icons in customer-facing materials is at your own responsibility.

---
name: snowflake-gslides
description: "Auto-generate Snowflake-branded Google Slides from markdown or any text content. Use when: user mentions .gslides file, creating slides or presentations from markdown, text, or prompts. Triggers: .gslides, gslides, Google Slides, create slides, presentation, build slides, update slide, fix slide, rebuild slide, make slides from"
---

# Snowflake Google Slides Auto-Generation

Convert markdown content into Snowflake-branded Google Slides.

## Prerequisites

- `gcloud auth application-default login` completed (ADC authentication)
- Python 3.11+ / uv
- **Output Google Slides file must be based on the Snowflake template** — The template's "layouts" (master side) are required. When no gslides file is specified, `copy_template.py` auto-creates one from the template. When a gslides file is provided, it must already be template-based. Slides themselves can be all deleted, partially remaining, or all 73 sample slides intact. Layouts persist even when slides are deleted.

## Workflow

### Step 0: Input Format Handling

Determine the input type and ensure a slide-optimized md file exists:

| Input pattern | Action |
|---------------|--------|
| `.md` file specified | Proceed directly to Step 1. **Do NOT rewrite, summarize, or create a new md.** Use the provided md as-is regardless of size. **If a line range is specified (e.g., lines 47-292), use ONLY that range as the target content — do NOT read or process the full file.** For large md, apply "Large Input Handling" in Step 5 |
| Non-md file specified (.txt, .docx, .pdf, etc.) | Read the file → convert to slide-optimized md (see `references/slide-markdown-format.md`) → save as `.md` → ask user to confirm → proceed |
| No file specified, but content described in prompt | Generate slide-optimized md from prompt content → save as `.md` → ask user to confirm → proceed |
| No file specified, no content in prompt | Ask user: "What content should the slides contain?" |
| Diagram from prompt (explicit diagram/architecture request) | Extract entities → write spec.json (single diagram slide) → lint → build --append |
| Add element to existing slide ("add icon", "connect X to Y") | Identify target slide → write add.json → run add_elements.py → visual check |

**When generating md (non-md input or prompt only — NEVER for existing .md files):**
- Read `references/slide-markdown-format.md` for format rules
- Save generated md to the same directory as the .gslides file (or working directory)
- Ask user: "Generated md from your input. Please review and confirm: `<path>`"
- Only proceed after user confirms (user may edit the md before confirming)

### Step 1: Input Confirmation and Mode Selection

Receive from user:
1. **md file path** — Content to convert (full file or line range). Not required for Update mode. **If line range is specified (e.g., `lines 47-292`), read ONLY those lines and pass only that content to analyze_md.py (`--lines 47-292`) and spec generation. The line range IS the target scope.**
2. **gslides file path or URL** — Output Google Slides (optional). If a Google Slides URL is provided (e.g., `https://docs.google.com/presentation/d/<ID>/edit`), extract the `presentation_id` from the URL path. **Always use the explicitly provided URL/ID over any cached audit.json or working directory name.** Do NOT reuse a presentation_id from a previous session without confirming.

**If gslides file is not specified:**
1. Copy the template using `copy_template.py`:
   ```bash
   uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/copy_template.py --name "<presentation_name>" --folder-path "<path>"
   ```
   - `--name`: based on md file name (e.g., `monthly_report.md` → `monthly_report`) or date-based name
   - `--folder-path`: relative path from My Drive (e.g., `99.temp/20260513_test1`). Extracted from CWD: strip everything up to and including `マイドライブ/` (or `My Drive/`)
   - `--folder-id`: alternative — pass a known Drive folder ID directly
   - If folder not found (exit code 2): inform the user that Drive Desktop sync may be pending. Ask them to check sync status or provide a Drive folder URL. Do NOT create folders via API (may cause duplicates with pending sync).
   - If CWD is not on Google Drive and no md file is on Google Drive: ask the user for a Drive folder URL or name. Do NOT silently place in My Drive root.
2. Parse stdout JSON to get `presentation_id` and `url`
3. Create working directory: `mkdir -p /tmp/gslides_<pid8>/` (first 8 characters of presentation_id)
4. Report to user: "Created new presentation: `<URL>`"
5. Use Replace mode (new file, no existing slides)

**If gslides file is specified:**
Read the gslides file to obtain `doc_id` (presentation_id).

**Mode selection (context-dependent):**

Determine which modes to present based on user intent:

| User intent | Modes to present |
|-------------|-----------------|
| md full file or large range → create slides | Replace, Replace (keep), Append |
| Specific slide modification ("update slide 5", "fix the table on page 3") | Update |
| Ambiguous (could be either) | All 4 modes |

1. **Replace** — Delete all existing slides and create new ones (backup auto-created)
2. **Replace (keep existing)** — Keep existing slides, insert new slides at the beginning (backup auto-created)
3. **Append mode** — Keep existing slides, add slides at specified position (no deletion)
4. **Update mode** — Update specific slide(s) content in-place (old slide moved to end as skipped)

For append mode, confirm the following:

**Append mode design checklist (must verify all items):**

1. **New section or addition to existing section?**
   - **New section** → Include divider in spec.json (required)
   - **Addition to existing section** → divider not needed
2. **Determine insertion position (`--insert-after N`) — must always specify:**
   - Check `audit_template.py` output (existing slide list: slide number + layout name) and determine N:
     - **New section**: Before Thanks slide (= Thanks slide number - 1)
     - **Addition to existing section**: Last multi/code slide number in that section (before next divider or Thanks)
   - **Example**: Existing is `[1:Cover, 2:Agenda, 3:Divider, 4:Multi, 5:Multi, 6:Divider, 7:Multi, 8:Thanks]` and you want to add to section 1 (slides 3-5) → `--insert-after 5`
   - **If not specified, slides are added after Thanks = inappropriate position. Always specify.**
3. **Agenda update (`agenda_items`):**
   - If existing Agenda slide exists, **always include `agenda_items` at spec.json top level**
   - `agenda_items` must list **all items** to display on Agenda (including new section)
   - If not specified, Agenda remains unchanged (stale)
   - `agenda_items` only updates Agenda slide's BODY[1], no other slides are affected

For update mode:

**Update mode workflow:**
1. Run `audit_template.py` (Step 2) to get existing slide list with numbers, objectIds, and layout names
2. Identify which slide(s) to update (by number or objectId)
3. Create a `patch.json` with the updated slide spec (same format as spec.json, **must contain exactly 1 slide**). The slide `id` must differ from the original (e.g., append `_v2`)
4. Run `rebuild_slide.py` — old slide is moved after Thanks and marked as skipped (hidden in presentation mode)
5. Users can manually delete skipped slides from Google Slides UI when no longer needed

**Note:** Each rebuild requires a unique `id` never used before in the presentation (including skipped slides still present). Increment suffix: `_v2`, `_v3`, etc.

### Step 2: Template Audit

```bash
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/audit_template.py <presentation_id> --output /tmp/gslides_<pid8>/audit.json
```

Create the working directory first (if not already created in Step 1): `mkdir -p /tmp/gslides_<pid8>` (first 8 characters of presentation_id).

Use `recommendedLayouts` from the output to identify layout IDs.

### Step 3: Analyze MD Structure

```bash
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/analyze_md.py <md_file> --output /tmp/gslides_<pid8>/analysis.md
```

Read the output to understand:
- Total tables and code blocks (= minimum content slides)
- Per-section element counts (= slide allocation per section)
- Code blocks >25 lines (need trimming)
- Large/wide tables (need overflow consideration)
- **Estimated slides** and whether Phase split is required

Use this data for all subsequent design decisions in Step 5.

### Step 4: Read Config YAML

1. Read skill default: `<SKILL_DIR>/config/snowflake-gslides-config.yaml`
2. Check project directory for `snowflake-gslides-config.yaml` (same directory as md/gslides files)
3. If local exists: deep merge (local values override default, only specified keys are overridden)
4. If neither exists: ERROR — report to user
5. The merged config becomes the `config` section of spec.json
6. All subsequent design decisions use config values

**spec.json top-level structure:**
```json
{
  "config_version": 1,
  "config": { ... },
  "agenda_items": [],
  "slides": [...]
}
```

### Step 5: Slide Structure Design

**First: Determine output language from md content.** All slide text (titles, subtitles, body, table data) must use the same language as the md source. State the language before proceeding (e.g., "Output language: Japanese"). Never translate md content.

**IMPORTANT: All file creation (spec.json, part*.json, etc.) MUST use the `write` tool. Do NOT use bash heredoc — CJK content will be corrupted.**

**Features flags (from config.features):**
When a feature is `false`, the corresponding behavior is disabled:
- `cover_slide: false` → Do not generate a Cover slide
- `agenda_slide: false` → Do not generate an Agenda slide
- `section_dividers: false` → Do not generate divider slides between sections
- `thanks_slide: false` → Do not generate a Thanks slide
- `title_section_prefix: false` → Titles do not need `Section — Title` format
- `table_zebra_stripes: false` → Table rows use single background_color
- `jp_period_to_newline: false` → Do not convert 。 to newline in table cells
- `auto_link_snowflake_views: false` → Do not auto-link Snowflake view names
- `body_accent_emphasis: false` → **bold** uses bold only (no accent color)
- `cover_date: false` → Do not include date line on Cover slide
- `subtitle_required: false` → Subtitle is optional on content slides (no error if missing)
- `diagram_slide: false` → Do not generate diagram slides (icon + arrow diagrams disabled)

Analyze md content and design slide structure JSON (`spec.json`) following these rules.

**Read** `references/snowflake-template-layouts.md` for layout specs.
**Read** `references/slides-api-patterns.md` for spec.json schema.

**Agenda and divider rules:**
1. **Adopt md chapter structure as Agenda items by default**. Respect the author's intent — do not consolidate without permission. Chapter delimiter = the top-level heading in the md (`#` if only `#` exists, `##` if `##` exists, `---` or paragraph structure if no headings). When `#` is the document title and `##` marks chapters, use `##`
2. List section names in Agenda page items (Google Slides native numbered bullets auto-applied)
3. Place a divider before each section's slides (**divider title is required** = must match Agenda item name)
4. Place section slides after the divider
5. **Agenda item count limits** (font auto-adjusted by build_slides.py):
   - **≤10 items**: default agenda font size
   - **11–15 items**: auto-shrunk
   - **16–20 items**: auto-shrunk (max capacity)
   - **>`config.rules.agenda_max_items` items**: **Not supported**. Consolidate related sections. Report the consolidation to the user and suggest revising the md chapter structure
6. Consolidation is considered **only when >`config.rules.agenda_max_items` items**. If consolidated, always report to the user and suggest revising the md chapter structure

**Layout selection rules:**

**Cover slide:**
- Use `recommendedLayouts.cover` from audit.json. If multiple cover layouts exist, prefer **Cover 04** (`Data Cloud_1_1_3_2`) unless the existing presentation already uses a different cover layout (match existing style).
- title: Main title. Text box vertical alignment is BOTTOM (displays near slide center)
- subtitle: Report description (e.g., "Monthly Report — April 2026"). Do not include fixed text like "Snowflake Professional Services"
- date: **Must follow format `Snowflake | Month DD, YYYY`** (e.g., "Snowflake | April 28, 2026"). Always include day. Use the date from user context (e.g., report date, meeting date); if unclear, use today's date. Do not omit the day or use other formats

| md structure | layout | type |
|-----------|--------|------|
| Document title | cover | - |
| Table of contents | agenda | - (Google Slides native numbered bullets) |
| Section heading (top-level `##` or equivalent) | divider | - |
| Table-focused | multi | table |
| Bullet-focused | multi | bullets |
| Long-form text (paragraphs) | one_column | bullets |
| Table + bullets mixed | multi | table (bullets in body) |
| Code block | multi | code |
| **Table + code mixed** | **multi × multiple slides** | **Separate into table slide + code slide** |
| Final page | thanks | - |

**Important: 1 md section ≠ 1 slide.** If a single md section contains both a table and code block, **always split into separate slides** (table slide + code slide). Never omit code blocks.

**4 patterns for content slides:**
1. **Bullets only**: Title + subtitle (1 line) + body bullets
2. **With table**: Title + subtitle (1 line) + body bullets (table description 1+ lines) + table
3. **With code block**: Title + subtitle (1 line) + body bullets + syntax-highlighted code block
4. **With diagram**: Title + subtitle (1 line) + optional body bullets + diagram (icons + arrows)

**Slide structure design process:**

Design by **content element**, not by md section. Multiple slides from one md section is normal.

1. Scan entire md and **enumerate content elements** per section:
   - Bullets / description text → `type: "bullets"` candidate
   - Table (`| ... |`) → `type: "table"` candidate
   - Code block (` ```sql ``` ` etc.) → `type: "code"` candidate. **Exception**: If the code block contains arrow notation (→, ->, ASCII art flow) rather than executable code, treat it as a `type: "diagram"` candidate instead.
   - **Diagram candidate** — ALL of the following must be true:
     1. **Named components (2+)**: At least 2 named technologies/services/tools (e.g., Snowflake, S3, Tableau, dbt — not generic terms like "step" or "process")
     2. **Structural relationship**: A clear flow, parallel, containment (group), or comparison relationship between them
     3. **Non-linear structure OR 3+ components**: Branching, parallel, bidirectional, grouping, OR 3 or more named components (linear 2-node flow → use bullets instead)
     If all conditions are met → `type: "diagram"` candidate. If not → `type: "bullets"`
   - **Table content describing architecture patterns** (e.g., DAG structures, component relationships) → consider a **supplementary `type: "diagram"` slide** in addition to the table slide. Report the addition to the user.
2. **Design each element as an independent slide:**
   - 1 table → 1 table slide
   - 1 code block → 1 code slide
   - Table + code block → table slide + code slide = **2 slides**
   - 2 tables + 1 code block → table × 2 + code × 1 = **3 slides**
   - Bullets only (no table or code) → 1 bullets slide
   - **Architecture / data flow description → 1 diagram slide (check sections for diagram potential using the 3-condition rule above before defaulting to bullets)**
3. Related code blocks may be combined into 1 code slide (within `config.code_block.max_lines` lines)
4. **If a md section has code blocks, a `type: "code"` slide MUST be generated. Converting code to bullets or embedding in body with backticks is FORBIDDEN**
5. **Post-design self-check (required):**
   - Compare md code block count vs spec.json `type: "code"` slide count → no code blocks missing
   - Compare md table count vs spec.json `type: "table"` slide count → no tables missing
   - **Diagram opportunity check**: For each section with named component relationships (architecture, pipelines, integrations) — apply the 3-condition diagram rule. If conditions are met but no `type: "diagram"` slide exists, justify why bullets are better
   - If any are missing, state the reason explicitly (only intentional omissions allowed)
   - **Table header row check**: For every table slide, verify that `table.data[0]` contains **column titles** (short labels like "Item", "Description", "Status"), NOT data. `data[0]` is always rendered as bold white text on Snowflake Blue background. If the md table has no explicit header, add an appropriate header row. If `data[0]` contains long text, `**bold**`, `` `backtick` ``, or descriptions, it is data — insert a proper header row above it

**Required rules:**
- **Output language must match the md source language**. If md is in Japanese, all slide content (titles, subtitles, body, table data) must be in Japanese. If md is in English, output in English. Never translate the content
- Title and subtitle are **required on all content slides**
- **Title identifiability (CRITICAL)**: Every content slide's title **MUST** follow the format `Section Name — Slide-specific Title` with ` — ` (space + em dash + space) as separator. Examples: `WH Health Check — Cost Structure`, `Performance Optimization — Benchmark Results`. **Exception**: If a section has only 1 content slide, the title may be the exact Agenda item name without ` — ` (e.g., `Deliverables`). Titles that neither contain ` — ` nor match an Agenda item are rejected by lint
- **Title must fit in 1 line (`config.sizes.title` pt bold)**. Guideline: `config.rules.title_base_max_chars` * (24 / `config.sizes.title`) display chars (CJK count as 2). Newlines are forbidden (ERROR). If title cannot be shortened below the limit, set `titleSize: config.sizes.title_min` in spec.json (allows more chars). `config.sizes.title_min` is the minimum — do not go below. If still too long at min size, shorten the title text. lint adjusts the limit based on titleSize
- **Subtitle must be exactly 1 line** (goes into SUBTITLE placeholder), bold. Guideline: ~`config.rules.subtitle_max_chars` display chars max (CJK chars count as 2). Newlines are forbidden (ERROR). If too long, shorten and move details to body
- **Body content goes in body field** (placed as separate text box)
- Bullet lines start with `•` or `-` → converted to Google Slides native bullet format
- **Bullet granularity**: Do not drop information from md. Remove redundant expressions, make concise and clear. Omitting specific numbers, proper nouns, or conclusions is NOT acceptable
- **Preserve md markup**: `**text**`, `` `text` ``, `[text](url)` in the source md must be carried over into spec.json body and table data as-is. Do not strip bold/code/link markup when converting md to spec.json — the build script processes these markers into styled output
- **Abbreviations**: First use of abbreviations (WIF, SiS, DT, etc.) must include full form (e.g., "WIF (Workload Identity Federation)"). Subsequent uses may use abbreviation only
- **Slide splitting**: If content doesn't fit in 1 slide, **split into multiple slides rather than dropping necessary information**. Removing verbose/redundant text is OK, but if it still doesn't fit, split. Two patterns:
  - **Same title + page numbers**: Continuation (e.g., "WH Health Check Results (1/2)", "(2/2)")
  - **Same title + different subtitles**: Different perspectives (e.g., title "WH Health Check", subtitles "Cost Structure" and "Per-WH Summary")
- Body header lines are `config.sizes.body_header` pt bold (auto-detected, any non-bullet line matching either):
  - **Ends with `:`** — e.g., `Full Refresh:\n• DT definition query...` → "Full Refresh:" becomes header
  - **Starts with `#` to `####`** — e.g., `## VIEW Structure` → "VIEW Structure" becomes header (`#` auto-removed from display)
- `` `text` `` in body → Bold text. Known Snowflake view/function names (QUERY_HISTORY, AI_COMPLETE, etc.) auto-linked to docs
- `**text**` in body → `config.colors.accent` bold emphasis (same behavior for full-line or partial). Disabled when `config.features.body_accent_emphasis` is `false` (bold only, no accent color)
- `**text**` in table cells → bold only (no accent color). `**` markers are removed automatically
- `` `text` `` in table cells → Courier New (monospace) + bold. Backtick markers are removed automatically. Use for identifiers, code references, object names (e.g., warehouse names, function names)
- **Hyperlinks**: `[text](URL)` notation supported. Display text with embedded URL link. Works in both body and table cells. **Include `[text](URL)` format in spec.json body and table data.**
  - **Include actively**: Add links for Snowflake official docs, product pages, public technical references. When Snowflake feature names appear (Dynamic Tables, Cortex Search, WIF, etc.), embed `[feature](https://docs.snowflake.com/...)` format
  - **If md has links**: Include as-is in spec.json
  - **If md has no links**: When Snowflake features/services are mentioned, look up and add official doc URLs. Use the most specific page URL (deep path, not top page)
  - **Do not include**: Internal-only URLs (Snowforce cases, Lift tickets, internal Slack, internal GitLab) for customer-facing slides. OK for internal slides
- Table slides must have 1+ bullet lines describing the table before it
- **table.data[0] is always treated as the header row** (Snowflake Blue background + white text + bold). Even if the md table has no explicit header (e.g., definition list format), always add appropriate column title row as data[0] in spec.json. Never place data rows in the header position
- **Do not specify table.y** (auto-calculated from body bottom. Manual specification causes overflow)
- Table header is bold, `config.sizes.table_header_increment` pt larger font than body rows
- `#` columns should be narrow by default (controlled via columnWidths, EMU unit. e.g., `[500000, 3000000, 4700000]` — sum should approximately equal table width, default `config.table.default_w` EMU). If columnWidths is omitted, build_slides.py auto-calculates proportional widths based on cell content length
- Table zebra stripes auto-applied (odd/even alternating colors from `config.table`, white borders). Disabled when `config.features.table_zebra_stripes` is `false` (single background_color for all rows)
- **Table cell bullet formatting**: Markdown tables are single-line per cell, so multiple items are written without line breaks. When a cell contains multiple items that should be displayed as separate bullet points, insert `\n` between them in spec.json. The script auto-applies native bullet format to any data cell containing `\n` (header row excluded). When a cell's content consists of multiple sentences, prefer `\n` separation over joining into a single long string
- Japanese `。` in table cells → also auto-converted to newlines with bullet format (language-specific convenience). Disabled when `config.features.jp_period_to_newline` is `false`
- Table bullet indent: indentFirstLine=0.06in, indentStart=0.19in
- Evaluation symbols: use `⚪︎` (U+26AA, good) `△` (U+25B3, caution) `×` (U+00D7, issue). Do not use `○` (U+25CB) or other visually similar characters
- **Do not include md section numbers/references (§ symbols, section names) in slides**. md structure info is only for designing slide structure, not output to tables/text

**Code block rules:**
- **If md contains code blocks (` ```sql ``` ` etc.), a `type: "code"` slide MUST be generated.** Embedding code in body with backticks or summarizing as bullets is FORBIDDEN. Always use `type: "code"`
- Code over `config.code_block.max_lines` lines: extract key portions to fit within `config.code_block.max_lines` lines (slide itself must still be created)
- `type: "code"` and `type: "table"` cannot coexist (1 slide = 1 content type)
- **If table and code exist in same md section**: Create separate table slide and code slide. Never omit code
- **Multiple code blocks in one md section**: Combine related ones into 1 code slide, or split into separate slides if content differs
- Theme: GitHub Dark Default (background `config.colors.code_background`, left accent bar color by language from `config.code_block.accent_colors`: SQL=Snowflake Blue, Programming=Purple, Config=Gray, Other=Green)
- Font: `config.fonts.code` `config.sizes.code` pt bold
- Pygments tokenization → per-token syntax highlight colors applied
- Snowflake-specific keyword/function reclassification (FLATTEN, DYNAMIC TABLE, MAX_BY, etc.)
- Supported languages: sql, python, json, yaml, etc. (all Pygments-supported languages)

**Text volume guidelines:**
- Title: fits in 1 line (`config.sizes.title` pt bold)
- Subtitle: **must fit in 1 line** (`config.sizes.subtitle` pt)
- Table: rows × rowHeight should be ≤ 3,500,000 EMU (prevent page bottom overflow)

**Font size system:**
- Title: `config.sizes.title` pt (bold) / Cover: `config.sizes.cover_title` pt (bold, white) / Divider: `config.sizes.divider` pt / Agenda title: `config.sizes.agenda_title` pt / Agenda items: `config.sizes.agenda_items` pt (≤10), auto-shrunk (11–15), auto-shrunk (16–20)
- Subtitle: `config.sizes.subtitle` pt bold. **Must be 1 line**. Consistent across all slides / Cover: `config.sizes.cover_subtitle` pt bold
- Body: `config.sizes.body` pt (line spacing `config.layout.body_line_spacing`). Placed in separate text box from subtitle. Non-bullet lines ending with `:` or `#` headings → `config.sizes.body_header` pt bold (header, auto-detected)
- Table: `config.sizes.table_body` pt

**spec.json layoutId:** Use IDs from audit.json's `recommendedLayouts`.

**Layout calculation check (pre-validation):**

build_slides.py auto-checks before execution, but also consider during spec.json design:
- Page height: 5,143,500 EMU, bottom margin: `config.layout.page_bottom_margin` EMU → content bottom limit: **5,143,500 - `config.layout.page_bottom_margin`** EMU
- Body height estimate: lines × fontSize(pt) × 914400/72 × 1.5 + 20000. Note: CJK characters occupy ~2x width, causing more line wraps. build_slides.py accounts for this automatically
- Body to table gap: `config.layout.body_table_gap` EMU
- Body start Y: `config.layout.body_start_y` (below subtitle)
- Table start Y: body bottom + `config.layout.body_table_gap` if body exists, otherwise `config.layout.body_start_y`
- Table bottom: table_y + rows × rowHeight
- **Both body bottom and table bottom must be ≤ content bottom limit**

Write `spec.json` to the working directory: `/tmp/gslides_<pid8>/spec.json`. **Use the `write` tool to create the file directly. Do NOT use bash heredoc (`cat << EOF`) or Python heredoc (`python3 << 'EOF'`) — CJK/multibyte content in large JSON is corrupted by terminal buffering. This applies to all file creation: spec.json, part*.json, phase1_structure.md, etc.**

**CAUTION: Editing code.source in spec.json** — JSON string fields containing `\n` (literal newlines in code) can be corrupted by text editors that convert `\n` escape sequences to actual newlines. If code.source needs post-creation modification, use a Python script to read/modify/write the JSON programmatically rather than using text edit tools directly on the JSON file.

### Large Input Handling (50+ content slides ONLY)

**Do NOT use Phase split for less than 50 content slides.** Count only content slides (diagram, table, code, text/bullets) — exclude cover, agenda, dividers, and thanks. Example: 14 diagram + 2 table + 14 divider + cover + agenda + thanks = 16 content slides → no split needed. Only split when content slide count exceeds 50.

When the spec.json output is expected to be large (50+ content slides), split generation into 3 phases to maintain quality:

**Phase 1: Structure Design (MANDATORY file output)**
- Read the entire md and **count all content elements**: number of `##` sections, tables (`|...|`), code blocks (` ``` `), bullet sections
- Create a slide list: `id`, `layout`, `title`, `subtitle`, `type`, source line range
- Confirm Agenda items
- **Write to file**: `/tmp/gslides_<pid8>/phase1_structure.md` — this is REQUIRED before proceeding to Phase 2
- Include a **count verification** at the end of the file:
  ```
  ## Element Count
  - Sections: N
  - Tables in md: N → Table slides: N (must be ≥ md table count after reasonable merging)
  - Code blocks in md: N → Code slides: N (must be ≥ md code count after reasonable merging)
  - Estimated total content slides: N
  ```
- Do NOT proceed to Phase 2 until this file is written and counts are verified

**Phase 2: Part-by-part spec.json generation**
- Generate 15-20 slides per part file (target), up to 30 max when aligning with section boundaries. Follow Phase 1's structure strictly
- Part 1: `config_version` + `config` + `agenda_items` + `slides[0:N]`
- Part 2+: `{"slides": [...]}` only
- Write to: `/tmp/gslides_<pid8>/part1.json`, `part2.json`, ...
- Each part follows the Phase 1 structure exactly (titles, types, ids are already decided)

**Phase 3: Merge → lint → build**
```bash
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/merge_spec.py /tmp/gslides_<pid8>/part1.json /tmp/gslides_<pid8>/part2.json [...] --output /tmp/gslides_<pid8>/spec.json
```
Then run lint and build as normal on the merged spec.json.

**When to apply:** CoCo judges based on md complexity (section count, table/code count, total lines). Split boundaries must align with section boundaries (never split mid-section).

### Step 6: Slide Generation

**Full generation mode:**
```bash
# Delete existing and create new (backup always created)
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/build_slides.py <presentation_id> /tmp/gslides_<pid8>/spec.json --output /tmp/gslides_<pid8>/result.json

# Keep existing slides, insert new at beginning (backup always created)
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/build_slides.py <presentation_id> /tmp/gslides_<pid8>/spec.json --output /tmp/gslides_<pid8>/result.json --keep-existing
```

**Append mode (no deletion):**
```bash
# Append at end
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/build_slides.py <presentation_id> /tmp/gslides_<pid8>/spec.json --output /tmp/gslides_<pid8>/result.json --append

# Insert after slide 5
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/build_slides.py <presentation_id> /tmp/gslides_<pid8>/spec.json --output /tmp/gslides_<pid8>/result.json --append --insert-after 5
```

In append mode, include `agenda_items` at spec.json top level to auto-update existing Agenda slide (no other slides affected):
```json
{
  "agenda_items": ["Activity Summary", "WH Health Check", "Performance Optimization", "New Chapter"],
  "slides": [...]
}
```

**Update mode (single slide rebuild):**
```bash
# Update slide 4 with new content
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/rebuild_slide.py <presentation_id> --slide 4 --spec /tmp/gslides_<pid8>/patch.json --output /tmp/gslides_<pid8>/result.json

# Update by objectId
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/rebuild_slide.py <presentation_id> --slide sl_0101 --spec /tmp/gslides_<pid8>/patch.json --output /tmp/gslides_<pid8>/result.json
```

patch.json format is identical to spec.json but **must contain exactly 1 slide**. The slide `id` should differ from the original (e.g., append `_v2`).

**Pre-validation (required before build/rebuild):**
```bash
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/lint_spec.py /tmp/gslides_<pid8>/spec.json --audit /tmp/gslides_<pid8>/audit.json
```
Run URL check **in parallel** with lint (separate shell). Only needed on first lint run or when body URLs have changed:
```bash
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/check_urls.py /tmp/gslides_<pid8>/spec.json
```
This applies to BOTH `spec.json` (full build) AND `patch.json` (rebuild). Always lint before any build/rebuild. Fix any 404 URLs before building.

Note: `lint_spec.py` checks schema/rule compliance (field presence, type conflicts, layoutId validity, **diagram slide bounds including body-aware height check**). `build_slides.py` has its own pre-validation that checks EMU overflow. Both are complementary — lint catches structural issues before build catches layout issues. **Always run lint before the first build to avoid unnecessary API calls and hand-back cycles.**

**Lint retry rules:**
1. When lint reports ERRORs, fix **all** errors across all slides before re-running lint (do not fix one at a time).
2. For errors within the same slide, consider them holistically — fixing one may affect others (e.g., changing col to fix edge crossing may cause overflow).
3. **STOP after 3 total lint runs (initial + 2 retries). Do NOT run lint a 4th time.** Proceed to build regardless of remaining errors — `build_slides.py` has its own pre-validation and will block on critical issues. This limit is absolute — even if errors are still decreasing, stop.
4. Edge crossing errors (`[CROSSING]` prefix) do **not** block build — `build_slides.py` will proceed and print them as warnings.
5. Any slide with remaining errors after build **must** be verified via thumbnail check (Step 8). Do NOT skip thumbnail verification for these slides.

**If build reports BOTTOM overflow on a diagram slide:**
1. Do NOT re-run full build. Use `rebuild_slide.py` to fix only the problem slide.
2. Common fixes: reduce `rowSpan`, use smaller `iconSize`, shorten body text, or split into 2 slides.
3. Re-run lint on patched spec to confirm fix before rebuild.

**CRITICAL: NEVER re-run full build (build_slides.py) to fix a single slide issue.** Full builds delete ALL existing slides and recreate them — this wastes API calls (especially for diagram slides with Apps Script icon insertion) and creates unnecessary backups. Once a presentation is built successfully:
- **Any single-slide fix = rebuild_slide.py ONLY**
- **Full build is ONLY for initial creation or user-requested full regeneration**
- This rule applies to ALL slide types, not just diagrams

**Guardrails:**
- **Full generation mode:**
  - **Always creates backup** (`{filename}_bk{YYYYMMDD}_{nnn}`)
  - Default: delete existing slides and create new
  - `--keep-existing`: keep existing slides, insert new at beginning
  - Confirm with user before deciding replace vs keep-existing
- **Append mode:**
  - Never deletes existing slides
  - Only inserts at specified position
- **Update mode:**
  - Old slide moved after Thanks and marked as skipped (isSkipped=true)
  - New slide created at same position with updated content
  - No backup file created (old slide preserved in-file as skipped)
  - Users can delete skipped slides manually from Google Slides UI

**Script steps by mode:**

Replace / Replace(keep):
0. Create backup → 1. Delete existing (or keep) → 2. Create slides → 3. Fill content → 4. Hide empty placeholders → 5. Verify

Append:
1. Create slides at position → 2. Fill content → 3. Update Agenda (if agenda_items) → 4. Hide empty placeholders → 5. Verify

Update (rebuild_slide.py):
1. Move old slide after Thanks → 2. Set isSkipped=true → 3. Create new slide at original position → 4. Fill content → 5. Hide empty placeholders → 6. Verify

If no Thanks slide exists, old slide is moved to the end of the presentation.

### Step 7: Result Verification

Check result.json for issues. When reporting to user, **always include Google Slides URL**:

```
Done (XX slides). Please review: https://docs.google.com/presentation/d/<presentation_id>/edit
```

### Step 8: Diagram Visual Check (conditional)

**When to perform**: Required when lint had remaining errors (especially `[CROSSING]` edge crossing) that were not resolved before build. Optional when lint passed cleanly.

After successful build/rebuild of diagram slides with remaining lint errors, perform visual verification on the affected slides. **Read `references/diagram-visual-check.md` for detailed check criteria and fix patterns.**

1. Download thumbnails for slides with remaining errors (or all diagram slides if preferred):
```bash
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/download_thumbnails.py <presentation_id> <spec.json> --output-dir ./thumbnails [--slide-ids sl_0201 sl_0501]
```
This saves `<slide_id>.png` files and a `summary.json` with status per slide.

2. For each slide with remaining errors, check the **specific issue** that lint reported:
   - `[CROSSING]` edge crossing → verify arrows do not visually cross through nodes
   - Overflow errors → verify no elements are cut off at slide edges
   - Free node overlap → verify free nodes are not hidden behind groups
   - Also check: icons rendered (not gray placeholders), labels readable, arrows connecting correctly

3. Report check result per slide: `sl_XXXX: OK` or `sl_XXXX: NG — <issue description>`. **When in doubt, judge as NG** — false negatives (missed crossing) are worse than false positives.

4. If NG:
   - Fix the spec.json (adjust col/row, iconSize, labels)
   - Use `rebuild_slide.py` (NEVER full build) to regenerate only the problem slide
   - Re-check thumbnail after fix
   - **Maximum 2 thumbnail fix attempts per slide.** If the issue persists after 2 fixes, proceed with delivery but flag the slide: "Slides are complete. Note: slide `sl_XXXX` may have a visual issue (edge crossing / overlap). Please check and let me know if adjustment is needed."

## Tools

### copy_template.py

**Description**: Copy the Snowflake Slides template to a target Drive folder. Handles ADC authentication and folder path resolution.

```bash
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/copy_template.py --name "<name>" --folder-path "<relative_path>" [--output result.json]
```

| Argument | Description |
|----------|-------------|
| `--name` | Name for the new presentation (required) |
| `--folder-path` | Drive folder path relative to My Drive (e.g., `99.temp/project1`) |
| `--folder-id` | Direct Drive folder ID (alternative to --folder-path) |
| `--template-id` | Override template_id from config |
| `--output` | Save result JSON to file |

Exit codes: 0=success, 1=config error, 2=folder not found (sync pending).

### audit_template.py

**Description**: Audit Google Slides template layout and slide structure

**Usage:**
```bash
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/audit_template.py <presentation_id> --output audit.json
```

**Output**: Layout list, existing slide info, recommended layout mapping

### build_slides.py

**Description**: Build slides from JSON spec (with guardrails)

**Usage:**
```bash
# Full generation (replace)
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/build_slides.py <presentation_id> <spec.json> [--output result.json]

# Full generation (keep existing, prepend)
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/build_slides.py <presentation_id> <spec.json> --keep-existing [--output result.json]

# Append mode
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/build_slides.py <presentation_id> <spec.json> --append [--insert-after N] [--output result.json]
```

**Flags:**
- `--keep-existing`: Keep existing slides, prepend new slides (backup auto-created)
- `--append`: Append slides without deleting existing ones
- `--insert-after N`: Insert after slide N (1-indexed). Default: append at end

**Output**: Build result (slide count, overflow check, backup info)

### rebuild_slide.py

**Description**: Update a single slide's content in-place. Old slide is moved after Thanks and marked as skipped.

**Usage:**
```bash
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/rebuild_slide.py <presentation_id> --slide <N|objectId> --spec <patch.json> [--output result.json]
```

**Arguments:**
- `--slide`: Slide number (1-indexed) or objectId to update
- `--spec`: Patch JSON file (same format as spec.json, must contain exactly 1 slide)

**Behavior:**
1. Moves target slide after Thanks slide
2. Sets isSkipped=true on old slide
3. Creates new slide at original position
4. Fills content from patch spec

### lint_spec.py

**Description**: Validate spec.json / patch.json for rule compliance before building

**Usage:**
```bash
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/lint_spec.py <spec.json> [--audit audit.json]
```

**Checks:**
- Required fields (id, layout, layoutId)
- Duplicate slide id detection
- Slide id minimum length (5+ chars)
- Title and subtitle required on content slides (ERROR)
- Body field type validation (must be string, not list)
- Body contains code fence ` ``` ` (ERROR: should use type=code)
- Body contains md table syntax `|` (WARN: should use table.data)
- Nested markup detection (backtick inside `**bold**`)
- Subtitle is 1 line
- Title / subtitle length check (ERROR: title >`config.rules.title_base_max_chars` at `config.sizes.title` pt / adjusted at `config.sizes.title_min` pt, subtitle >`config.rules.subtitle_max_chars` display chars)
- Duplicate title detection (without (1/N) suffix)
- table + code not on same slide
- Content type required fields (table/code field presence)
- layoutId exists in audit.json
- Table column count consistency
- columnWidths: element count vs table columns, sum vs table width (EMU check), per-column minimum
- Table header row sanity (bold/backtick markers, newlines, avg length ratio vs data rows)
- Table cell unclosed markup markers (`**`, `` ` ``)
- Cover date format validation (`Snowflake | Month DD, YYYY`)
- Title format: `Section Name — Slide-specific Title` separator check (` — ` required, or exact Agenda item match for single-slide sections)
- Title / subtitle newline check (ERROR)
- Agenda item count (>`config.rules.agenda_max_items` ERROR, >15 WARNING)
- Agenda-Divider 1:1 consistency (item count and title match)

### check_urls.py

**Description**: Verify docs.snowflake.com URLs in spec.json are not broken (404). Run in parallel with lint.

```bash
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/check_urls.py <spec.json>
```

Extracts all `https://docs.snowflake.com/...` URLs from body and table cells, checks each via HTTP GET. Reports 404 (broken) and 301/302 (redirects). Exit code 1 if any broken URLs found.

### download_thumbnails.py

**Description**: Download LARGE (1600×900) PNG thumbnails for all diagram slides. Use for visual verification after build/rebuild.

```bash
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/download_thumbnails.py <presentation_id> <spec.json> [--output-dir ./thumbnails] [--slide-ids sl_0801_v2 sl_0901]
```

- Reads spec.json to find `type: "diagram"` slides
- Uses spec slide ID directly as Google Slides page objectId (build_slides.py sets objectId = spec id)
- Downloads thumbnails with automatic retry (default 2 retries per slide)
- Saves to `./thumbnails/<slide_id>.png` + `summary.json`
- All output is flushed immediately (no buffering issues with `uv run`)

### add_elements.py

**Description**: Add icons, groups, or edges to an existing slide without rebuild.

```bash
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/add_elements.py <presentation_id> --input <add.json> [--output result.json]
```

**add.json schema**:
```json
{
  "slideId": "sl_0101 or slide number (e.g. '4')",
  "elements": [
    {"type": "icon", "iconName": "api_gateway", "label": "API", "position": {"near": "s3", "direction": "right"}},
    {"type": "group", "label": "AWS", "color": "aws", "position": {"x": 50, "y": 100, "w": 200, "h": 150}},
    {"type": "edge", "from": "api_gateway", "to": "raw", "label": "load", "line": "elbow", "color": "dark_blue"}
  ]
}
```

**Position options**: `{"near": "<icon_name_or_label>", "direction": "right|left|below|above"}` or `{"x": <pt>, "y": <pt>}`. If omitted, auto-places in next available grid slot.

**Icon resolution**: Matches by image description (set by Apps Script) → node label → normalized fuzzy match.

### read_slide_elements.py

**Description**: Read existing slide elements (icons, groups, edges) and output as JSON. Use to inspect a slide before adding elements.

```bash
uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/read_slide_elements.py <presentation_id> --slide <slide_id_or_number> [--output elements.json]
```

## Stopping Points

- After generating md from non-md input → confirm with user before proceeding
- When CWD is not Google Drive → ask user for placement folder
- When mode is ambiguous (replace vs keep-existing) → confirm with user
- On lint/build errors → report to user with fix options

## Constraints

**Determining Action Mode** (when user requests diagram-related changes):
1. Does the user specify a **target slide** (number, id, or "this slide")?
   - YES + partial change ("add icon", "connect X to Y", "add group") → **Lightweight add** (`add_elements.py`)
   - YES + full change ("redo this diagram", "change layout") → **Rebuild** (`patch.json` + `rebuild_slide.py`)
   - NO → go to 2
2. Does the user want a **new diagram**?
   - YES + existing presentation → **Append mode** (spec.json with 1 diagram slide + `build --append`)
   - YES + no presentation → **New build** (spec.json + build)
   - NO → Ask "Which slide should I modify?"

**Do NOT delegate spec.json generation to subagents.** Always generate spec.json in the main agent. Subagents do not have access to this skill's rules and will produce non-compliant output that fails lint.

**NEVER create new Apps Script projects.** Use `audit_template.py` for slide/element information, `read_slide_elements.py` for element inspection, and `add_elements.py` for element addition. Do not open Script Editor or create container-bound scripts.

**Do NOT limit slide count or "extract key information" from md.** All information in the provided md must be reflected in slides. If the md produces 100+ slides, that is correct. Never pre-decide a target slide count and compress content to fit it. Use Large Input Handling (Phase 1-2-3) for large outputs.

## Output

Snowflake-branded Google Slides presentation.

**Post-generation guidance:**
1. Open in Google Slides and review all slides
2. Enable slide numbers: Insert → Slide numbers → Apply (one-time setup; native numbers auto-update thereafter)
3. Adjust layout/placement as needed

## Diagram Slides (type: "diagram")

Renders architecture/flow diagrams with icons, groups, and arrows directly on slides.

**IMPORTANT:** Before generating a diagram slide, ALWAYS read `references/diagram-patterns.md` for the full schema, 14 layout patterns, and color palettes.

**When to use proactively:**
- Content describes system components with connections
- Pipeline or data flow is being explained
- Multiple services mentioned in relation to each other
- Visual diagram would significantly improve comprehension over bullets alone
- **Process flow with 3+ sequential steps** (e.g., detect → compute → merge)
- **Comparison of two architectures or approaches** (Before/After, Pattern A vs B)
- **Concept flow explaining "how it works"** with 2+ named stages (e.g., "Ingest → Transform → Serve")

**Do NOT wait for the user to explicitly request a diagram.** If the content naturally maps to a visual architecture or flow, generate a diagram slide.

**Key constraints:**
- Mutual exclusion: diagram cannot coexist with table or code on same slide. Body (bullets above) is allowed **and encouraged** — include body bullets to explain the diagram context.
- **1-row diagrams (all nodes at same row) MUST have body bullets.** Single-row diagrams leave too much empty space; body text is required.
- iconSize: 40 (simple, 3-7 nodes), 30 (medium, groups), 20 (dense)
- All edge fields must be explicit (no defaults): from, to, label, line, startArrow, endArrow, color, dashed
- Node labels should be short (≤12 chars recommended). Longer labels auto-wrap to 2 lines at spaces. **Never shorten to ambiguous abbreviations** — write the full name and let auto-wrap handle it.
- Icon names from `config/index.json`. Aliases supported via `config/icon_aliases.json`.
- **Brand logo check**: When a node label contains a brand/product name (e.g., GitHub, Terraform, Docker, Kafka), always check the `logos` category in `index.json` — brand icons are there, not in the `snowflake/` category. Also check `icon_aliases.json` for shorthand aliases.
- **Flow direction: left-to-right is default.** Source at low col, destination at high col.
- **Slide bounds**: Builder auto-expands groups to fill available space (20–700pt width). Node grid limits: iconSize=40 max col=7/row=3, iconSize=30 max col=9/row=4, iconSize=20 max col=13/row=6. With body subtract ~2 rows. Lint warns if exceeded; builder clamps.
- **Body vs diagram vertical space tradeoff**: Body text and diagram share the slide's vertical space. When diagram needs 3+ rows, resolve in this priority order: (1) adjust col/row layout, (2) reduce iconSize if lint confirms smaller size fits, (3) shorten body text, (4) remove body. NEVER remove diagram nodes to fit — adjust layout and body first.
- **No duplicate edges between same node pair.** For bidirectional, use single edge with startArrow=arrow + endArrow=arrow.
- **Edge-crossing resolution (ordered strategies)**: If lint reports cross-node `[CROSSING]` error, fix in this priority order. Move to the next strategy ONLY when the previous still produces errors:
  1. **Move blocking node**: Change the blocking node's row or col so it is no longer between the two connected nodes.
  2. **Fan-in/out: distribute targets/sources across different rows**: When one node connects to multiple targets (fan-out) or multiple sources connect to one node (fan-in), place the multiple-side nodes at the **same col but different rows** (vertical stack). Never put fan-out targets on the same row as the hub — edges will cross intermediate nodes.
  3. **Swap node positions**: Exchange the crossing node's position with a non-blocking neighbor in the same group.
  4. **Rearrange group layout**: Change the layout within the group (e.g., 2-column to 1-column, redistribute rows).
  5. **Override edge routing (last resort, may cause false negative)**: Set `fromSide`/`toSide` to force a different connector path. **WARNING**: This may make lint pass but Google Slides renders connectors differently — the visual result may still show crossings. Always verify with thumbnail after build. Prefer node rearrangement (strategies 1-4) over routing overrides.
  6. **Merge similar nodes** (only when 3+ nodes of the same type exist): Combine into a single node with count label (e.g., "Raw Tables (3)"). Report the merge to the user.
  7. **Split into 2 slides**: Create overview + detail slides. Report the split to the user.
  8. **Report to user**: If none of the above resolves all crossings, report the specific crossing details and ask for guidance.
  **NEVER delete an edge.** Edges represent real data flows. Removing an edge to fix a layout problem = information loss = unacceptable.
- **Icon names use underscores** (e.g. `dynamic_table`, `api_gateway`). Hyphens are auto-converted but underscores preferred.
- **Fan-in/Fan-out**: Place sources/targets at the **same col** with consecutive rows (0,1,2,...) — do NOT skip rows, do NOT put them on the same row as the hub node. **Same col is critical**: if fan-out targets are at different cols, edges cross each other and intermediate nodes. Always align the multiple-side nodes vertically first, then adjust the hub node's col/row. Max fan-out per iconSize: 40→3, 30→4, 20→6 (subtract ~2 with body).
- **Entity-Edge Manifest (MANDATORY before writing diagram JSON)**: Before writing the diagram section of spec.json, perform these substeps in order:
  1. **Group list**: Extract deployment boundaries / environment labels from the md (e.g., `[Snowflake]`, `[AWS Cloud]`, `[On-Premise]`). Write them as a list. If the md defines a single group, there must be exactly 1 group — **do NOT split into sub-groups that the md does not define**. If no explicit group labels exist, infer from context (e.g., "all inside Snowflake" → 1 Snowflake group). Apply deduplication: if the same label appears multiple times, merge into one. Only create separate groups for explicitly different boundaries.
  2. **Entity list**: Extract ALL distinct entities/services/components from the source md section. Write them as a numbered list in your response.
  3. **Edge list**: For each data flow or connection described (explicitly or implicitly), write a from→to pair in your response.
  4. **Verify**: group count matches md structure, node count ≥ entity count, edge count ≥ flow count. If the diagram has N source entities feeding into a layer, there must be N edges (fan-in). Do NOT reduce edges to simplify layout.
  5. Only after the manifest is verified, proceed to write the diagram JSON. Every entity in the list must have a corresponding node. Every flow must have a corresponding edge. Every manifest group must have a corresponding diagram group.
  6. **Write `_manifest` field in spec.json**: Include the manifest as a `_manifest` field inside the diagram object. lint validates this field — missing or incomplete manifest = ERROR.
     - **`entities`**: Each entry MUST match a node's `id` or `label` (case/hyphen/underscore insensitive). Use the same string you write in the node's `label` field — not the icon name, not a group name, not an abbreviated concept name. Example: node label is "Ops Dashboard" with icon "streamlit" → entity is "Ops Dashboard" (not "Streamlit"). Write entities AFTER designing nodes, not before.
     - **`flows`**: Each flow is a **direct** from→to pair using **node IDs** (same as `edges[].from`/`to`). Multi-hop chains (A→B→C) are NOT supported — write each hop separately: A→B and B→C.
     ```json
     "diagram": {
       "_manifest": {
         "groups": ["AWS", "Snowflake"],
         "entities": ["S3", "RDS", "API", "RAW", "Silver DT", "Gold DT", "Streamlit", "BI"],
         "flows": [
           {"from": "s3", "to": "raw"},
           {"from": "rds", "to": "raw"},
           {"from": "api", "to": "raw"},
           {"from": "raw", "to": "silver_dt"},
           {"from": "silver_dt", "to": "gold_dt"},
           {"from": "gold_dt", "to": "streamlit"},
           {"from": "gold_dt", "to": "bi"}
         ]
       },
       "iconSize": 30,
       "groups": [...],
       "nodes": [...],
       "edges": [...]
     }
     ```
  **If layout cannot fit all entities**: Do NOT omit nodes. Instead: reduce iconSize → split into 2 slides → ask user. NEVER drop entities to fix layout.
- **Group fidelity (CRITICAL)**: Diagram groups MUST correspond to boundaries identified in the md. Do NOT invent group names that the md does not define or imply. If the md has a single `[Snowflake]` group, the diagram must have exactly 1 Snowflake group — do NOT split into sub-categories like "Unstructured Data" / "Structured Data" unless the md explicitly defines them. Sub-grouping is only allowed when the md explicitly defines sub-groups or the node count exceeds the single-group grid capacity (report the split to user).
- **colSpan/rowSpan auto-floor**: You may omit or set colSpan/rowSpan on groups — the layout engine auto-calculates the minimum from node positions. If you set a value, it is treated as a floor (engine takes the max of your value and the computed minimum).


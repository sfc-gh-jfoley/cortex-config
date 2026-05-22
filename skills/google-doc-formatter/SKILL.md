---
name: google-doc-formatter
description: "Convert markdown to a properly formatted Google Doc using block-based batchUpdate. Handles headers, tables (native), bullets, code blocks, page breaks. Updates use wipe-and-rebuild — never incremental edits. Triggers: format to google doc, push to google, export to google doc, make this a google doc, convert to google doc."
---

# Google Doc Formatter

Convert markdown into a professionally formatted Google Doc with native tables,
proper headings, and intelligent page breaks. Updates are always wipe-and-rebuild
to avoid corruption.

**This skill does NOT share documents.** It creates/updates and returns a URL.

**Default styling:**
- Headings: dark blue (#11567F), named styles (HEADING_1/2/3)
- Blank line inserted before every heading (except the first)
- Code blocks: Courier New 9pt, grey shading (#F5F5F5), indented, extra spacing below
- Tables: native Google Tables, header row bold (no background shading)
- Bullet/numbered lists: standard presets

---

## Related skills

- `snowflake-gslides` — for slide decks (≤12 bullet-heavy sections)

---

## Phase 0: Intake

Determine:

1. **Input** — file path or pasted markdown content
2. **Mode** — Create new doc, or update existing doc?
   - If user provides a doc URL/ID → update mode
   - Otherwise → create mode
3. **Doc title** — from first `# H1`, filename, or ask user

If output should be Slides instead: stop, tell user to use `$snowflake-gslides`.

---

## Phase 1: Parse Markdown → Block List

Parse the markdown into an ordered array of blocks:

```
blocks = [
  { type: "heading", level: 1, text: "Title" },
  { type: "paragraph", text: "Body with **bold** and *italic*." },
  { type: "list", style: "bullet", items: ["item 1", "item 2"] },
  { type: "list", style: "numbered", items: ["first", "second"] },
  { type: "code", language: "sql", text: "SELECT * FROM t;" },
  { type: "table", headers: ["Col A", "Col B"], rows: [["a", "b"], ["c", "d"]] },
  { type: "hr" },
]
```

**Parsing rules:**
- `# text` → heading (level from # count)
- Consecutive non-blank, non-special lines → paragraph (preserve inline **bold**, *italic*, `code`)
- `- item` or `* item` → bullet list (gather consecutive items)
- `1. item` → numbered list
- ` ``` ` fenced → code block
- `| col | col |` with separator row → table
- `---` alone on a line → horizontal rule

**Inline formatting within text blocks:**
- `**text**` → bold span
- `*text*` → italic span
- `` `text` `` → code span (Courier New)
- `[text](url)` → hyperlink

---

## Phase 2: Create or Clear Doc

**Create mode:**
```
create_document(title=<doc_title>)
→ save doc_id
```

**Update mode:**
```
get_document_structure(doc_id=<existing_id>)
→ find body end index
batch_update_document(doc_id, requests=[
  { deleteContentRange: { range: { startIndex: 1, endIndex: <end-1> } } }
])
```

Both modes produce a blank doc body ready for Phase 3.

---

## Phase 3: Compile batchUpdate from Blocks

Build one `batchUpdate` requests array that renders all blocks. Process in two stages:

### Stage 1: Compute content and indices

Walk blocks top-to-bottom. For each block, determine:
- The plain text to insert (including `\n` terminators)
- Its absolute startIndex and endIndex in the final document
- Any inline style spans (bold, italic, code) with their offsets

**Tables are special:** Do NOT insertText for tables. Instead, reserve their position
and use `insertTable` at that index. Table content goes into cells via separate
insertText requests targeting cell indices (discovered after table insertion).

**Page break rules — keep blocks together:**
- NEVER split a table across pages. Insert a page break BEFORE a table if it
  would start in the bottom 20% of a page (estimate ~50 lines per page at 11pt).
- NEVER split a heading from its first paragraph/list. A heading at the end of a
  page must move to the next page with its content.
- Insert `insertPageBreak` before sections that start with H1 or H2 (except the first one).

### Stage 2: Build requests array

Build requests in this order (process indices end-to-start to preserve positions):

1. **insertText** — all text content for non-table blocks
2. **insertTable** — for each table at its computed position
3. **insertText into table cells** — populate cell content (requires reading back cell indices via `get_document_structure` after table insertion)
4. **updateParagraphStyle** — heading levels (HEADING_1, HEADING_2, etc.)
5. **updateTextStyle** — bold, italic, code inline spans
6. **createParagraphBullets** — bullet and numbered lists
7. **updateTableCellStyle** — header row shading, alternating rows

**CRITICAL: Tables require a two-call approach:**
- First `batchUpdate`: insertText for all non-table content + insertTable for tables
- Then `get_document_structure` to discover table cell indices
- Second `batchUpdate`: populate table cells + apply all styling (headings, bold, bullets, table shading)

See `references/style-guide.md` for exact request formats.

### Stage 3: Send

```
batch_update_document(doc_id=<id>, requests=<compiled_array>)
```

If tables exist, send two calls as described above.

---

## Phase 4: Output

```
✓ Google Doc created/updated

Title:    <doc title>
URL:      https://docs.google.com/document/d/<id>/edit
Mode:     <Created / Updated>
```

---

## Update Workflow Summary

When the user says "update this doc" or provides a doc_id to modify:

1. `read_document(doc_id)` — pull current content
2. **Safety check:** Show the user what's currently in the doc (brief summary or first few lines). Warn:
   > "This will replace ALL content in the doc with the new markdown. Any manual edits made directly in Google Docs will be lost. Proceed?"
3. Only after confirmation:
   - Update the markdown source with requested changes
   - Create a **new blank doc** with `create_document(title=...)`
   - Run Phase 1 (parse) → Phase 3 (build batchUpdate) against the new doc
   - Return new URL (old doc can be trashed)
4. Phase 4: Return new URL

**Source of truth is always the markdown.** The Google Doc is a rendered output, not an editable source. If users need to preserve manual edits, they should incorporate those changes back into the markdown before re-rendering.

**Why create-new instead of wipe:** `deleteContentRange` cannot span across table structural elements. Clearing a doc with tables requires multiple sequential deletes between table boundaries — fragile and slow. Creating a fresh doc and rebuilding is simpler and guaranteed to work.

---

## Notes

- Uses `mcp__google-workspace` MCP tools. If unavailable, warn user.
- Nested lists in table cells are flattened to plain text (API limitation).
- Unicode/emoji preserved as-is.
- For very long documents (>100 blocks), break batchUpdate into chunks of 50 requests
  to avoid API limits. The MCP tool handles chunking automatically.

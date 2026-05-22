# Google Doc Formatting — Style Guide & Request Patterns

Reference for how blocks map to Google Docs API batchUpdate requests.

---

## Font Specifications

| Context | Font | Size | Weight |
|---------|------|------|--------|
| HEADING_1 | Google Sans (or Roboto) | 20pt | Bold |
| HEADING_2 | Google Sans (or Roboto) | 16pt | Bold |
| HEADING_3 | Google Sans (or Roboto) | 14pt | Bold |
| HEADING_4 | Google Sans (or Roboto) | 12pt | Bold |
| NORMAL_TEXT | Arial | 11pt | Regular |
| Inline code | Courier New | 10pt | Regular |
| Code block | Courier New | 10pt | Regular |
| Table header | Arial | 11pt | Bold |
| Table body | Arial | 11pt | Regular |

## Paragraph Spacing

```
HEADING_1: spaceAbove=0pt, spaceBelow=12pt
HEADING_2: spaceAbove=16pt, spaceBelow=8pt
HEADING_3: spaceAbove=12pt, spaceBelow=6pt
NORMAL_TEXT: spaceAbove=0pt, spaceBelow=8pt
Code block: spaceAbove=4pt, spaceBelow=8pt
```

## Snowflake Brand Colors

| Name | Hex | RGB (0-1) |
|------|-----|-----------|
| Snowflake Blue | #29B5E8 | 0.16, 0.71, 0.91 |
| Snowflake Dark | #11567F | 0.07, 0.34, 0.50 |
| Light Grey | #F3F3F3 | 0.95, 0.95, 0.95 |
| Border Grey | #CCCCCC | 0.80, 0.80, 0.80 |

Use Snowflake Blue for H2 color in customer-facing docs. Default black for internal.

---

## Request Patterns

### insertText

```json
{
  "insertText": {
    "location": { "index": <startIndex> },
    "text": "The text content\n"
  }
}
```

Every block's text MUST end with `\n`. Headings, paragraphs, list items — all terminate with newline.

### updateParagraphStyle (Headings)

```json
{
  "updateParagraphStyle": {
    "range": { "startIndex": <start>, "endIndex": <end> },
    "paragraphStyle": {
      "namedStyleType": "HEADING_2",
      "spaceAbove": { "magnitude": 16, "unit": "PT" },
      "spaceBelow": { "magnitude": 8, "unit": "PT" }
    },
    "fields": "namedStyleType,spaceAbove,spaceBelow"
  }
}
```

### updateTextStyle (Bold/Italic/Code)

```json
{
  "updateTextStyle": {
    "range": { "startIndex": <start>, "endIndex": <end> },
    "textStyle": { "bold": true },
    "fields": "bold"
  }
}
```

For inline code:
```json
{
  "updateTextStyle": {
    "range": { "startIndex": <start>, "endIndex": <end> },
    "textStyle": {
      "weightedFontFamily": { "fontFamily": "Courier New" },
      "fontSize": { "magnitude": 10, "unit": "PT" },
      "backgroundColor": { "color": { "rgbColor": { "red": 0.96, "green": 0.96, "blue": 0.96 } } }
    },
    "fields": "weightedFontFamily,fontSize,backgroundColor"
  }
}
```

### createParagraphBullets

```json
{
  "createParagraphBullets": {
    "range": { "startIndex": <start>, "endIndex": <end> },
    "bulletPreset": "BULLET_DISC_CIRCLE_SQUARE"
  }
}
```

For numbered lists use `"NUMBERED_DECIMAL_ALPHA_ROMAN"`.

Range must span ALL list items (from first item startIndex to last item endIndex).

### insertTable

```json
{
  "insertTable": {
    "location": { "index": <position> },
    "rows": <num_rows_including_header>,
    "columns": <num_cols>
  }
}
```

After inserting, call `get_document_structure` to discover cell indices, then populate cells with `insertText` targeting each cell's startIndex.

### Table Cell Styling (Header Row)

```json
{
  "updateTableCellStyle": {
    "tableStartLocation": { "index": <table_start_index> },
    "rowSpan": { "startRowIndex": 0, "endRowIndex": 1 },
    "columnSpan": { "startColumnIndex": 0, "endColumnIndex": <num_cols> },
    "tableCellStyle": {
      "backgroundColor": { "color": { "rgbColor": { "red": 0.95, "green": 0.95, "blue": 0.95 } } }
    },
    "fields": "backgroundColor"
  }
}
```

### Table Cell Styling (Alternating Rows)

Apply to even data rows (row index 2, 4, 6...):
```json
{
  "updateTableCellStyle": {
    "tableStartLocation": { "index": <table_start_index> },
    "rowSpan": { "startRowIndex": <row>, "endRowIndex": <row+1> },
    "columnSpan": { "startColumnIndex": 0, "endColumnIndex": <num_cols> },
    "tableCellStyle": {
      "backgroundColor": { "color": { "rgbColor": { "red": 0.976, "green": 0.976, "blue": 0.976 } } }
    },
    "fields": "backgroundColor"
  }
}
```

### Bold Text in Table Header Cells

After populating header cells with insertText, apply bold:
```json
{
  "updateTextStyle": {
    "range": { "startIndex": <cell_text_start>, "endIndex": <cell_text_end> },
    "textStyle": { "bold": true },
    "fields": "bold"
  }
}
```

### Code Block (Shaded Single-Cell Table)

Render code blocks as a 1x1 table with monospace content:

```json
[
  { "insertTable": { "location": { "index": <pos> }, "rows": 1, "columns": 1 } },
  // After get_document_structure to find cell index:
  { "insertText": { "location": { "index": <cell_start> }, "text": "<code content>" } },
  { "updateTextStyle": {
      "range": { "startIndex": <cell_start>, "endIndex": <cell_end> },
      "textStyle": { "weightedFontFamily": { "fontFamily": "Courier New" }, "fontSize": { "magnitude": 10, "unit": "PT" } },
      "fields": "weightedFontFamily,fontSize"
  }},
  { "updateTableCellStyle": {
      "tableStartLocation": { "index": <table_start> },
      "rowSpan": { "startRowIndex": 0, "endRowIndex": 1 },
      "columnSpan": { "startColumnIndex": 0, "endColumnIndex": 1 },
      "tableCellStyle": {
        "backgroundColor": { "color": { "rgbColor": { "red": 0.96, "green": 0.96, "blue": 0.96 } } },
        "contentAlignment": "TOP"
      },
      "fields": "backgroundColor,contentAlignment"
  }}
]
```

Set table border width to 0 for borderless appearance.

### Page Break

```json
{
  "insertPageBreak": {
    "location": { "index": <position> }
  }
}
```

### insertPageBreak — Keep-Together Rules

- Insert before any H1 or H2 (except the document's first heading)
- Insert before a table if estimated remaining page space < table height
  - Estimate: each text line ≈ 16pt, page body ≈ 680pt (letter minus margins)
  - Table height ≈ (rows × 20pt) + 10pt padding
- NEVER insert a page break between a heading and its first content block

### Horizontal Rule

```json
{
  "insertText": { "location": { "index": <pos> }, "text": "\n" },
  "updateParagraphStyle": {
    "range": { "startIndex": <pos>, "endIndex": <pos+1> },
    "paragraphStyle": {
      "borderBottom": {
        "color": { "color": { "rgbColor": { "red": 0.8, "green": 0.8, "blue": 0.8 } } },
        "width": { "magnitude": 1, "unit": "PT" },
        "dashStyle": "SOLID",
        "padding": { "magnitude": 4, "unit": "PT" }
      }
    },
    "fields": "borderBottom"
  }
}
```

### Hyperlink

```json
{
  "updateTextStyle": {
    "range": { "startIndex": <link_text_start>, "endIndex": <link_text_end> },
    "textStyle": { "link": { "url": "<url>" } },
    "fields": "link"
  }
}
```

Insert only the link text via insertText, then apply the link style.

### deleteContentRange (for wipe-and-rebuild)

```json
{
  "deleteContentRange": {
    "range": { "startIndex": 1, "endIndex": <body_end - 1> }
  }
}
```

Get `body_end` from `get_document_structure`. Index 1 is the start of body content (index 0 is the document root). Always delete to end-1 to preserve the trailing newline.

---

## Page Margins (default)

```
top: 72pt (1 inch)
bottom: 72pt
left: 72pt
right: 72pt
```

Page body height: ~680pt (letter 792pt minus 72pt top and 72pt bottom margins, minus header space).
Approximate lines per page: ~42 at 11pt with 8pt spacing.

# Slide Markdown Format

This document defines the optimal markdown format for the snowflake-gslides skill. When this skill generates markdown from non-md inputs or user prompts, it follows this format.

## Structure Rules

```
# Document Title              → Cover slide title

---

## Section Name               → Agenda item + Divider slide title

Content here                  → Content slides

---

## Next Section Name          → Next Agenda item + Divider

...
```

- `#` (H1) = Document title (becomes Cover slide title)
- `##` (H2) = Section headings (become Agenda items and Divider titles)
- `---` = Section separator (placed before each `##`)
- `###` (H3) = Subsections within a section (used for grouping, not separate slides)

## Content Elements

### Bullet Points

```markdown
- First point
- Second point with **emphasis**
- Point with `code reference`
```

### Tables

```markdown
| Header 1 | Header 2 | Header 3 |
|----------|----------|----------|
| Data 1   | Data 2   | Data 3   |
| Data 4   | Data 5   | Data 6   |
```

- Always include a header row with short column titles
- Use `**bold**` for emphasis in cells
- Use `` `backtick` `` for identifiers, object names, code references
- Use `[text](url)` for hyperlinks

### Code Blocks

````markdown
```sql
SELECT * FROM table WHERE condition;
```
````

- Always specify the language after the opening fence
- Keep under 25 lines (extract key portions if longer)
- Supported: sql, python, json, yaml, bash, and other Pygments-supported languages

### Paragraphs

Plain text paragraphs become bullet-based slides. Write concisely — each sentence or key point on its own line or as a bullet.

## Best Practices

| Practice | Good | Bad |
|----------|------|-----|
| Section structure | `## WH Health Check` | No headings, just paragraphs |
| Table headers | Short labels: `Item`, `Status` | Long sentences in header row |
| Code blocks | Fenced with language tag | Inline code in body for multi-line code |
| Information density | 3-7 bullets per topic | 20+ bullets without splitting |
| Emphasis | `**key conclusion**` | ALL CAPS or underlining |

## Conversion Rules (for non-md inputs)

When converting from other formats (.txt, .docx, .pdf, or user prompt):

1. Identify the document title → `#`
2. Identify logical sections → `##` with `---` separator
3. Convert tabular data → md table format (always add header row)
4. Convert code/queries → fenced code blocks with language tag
5. Convert numbered/bulleted lists → `-` bullets
6. Preserve specific numbers, proper nouns, conclusions — do not over-summarize
7. Keep the same language as the source (do not translate)

## Anti-patterns (avoid these)

- Sections without `##` heading (CoCo cannot determine Agenda items)
- Tables without header row (first row becomes header styling)
- Code embedded in paragraphs instead of fenced blocks
- Single massive section with all content (split into logical sections)
- More than 20 sections (Agenda cannot display >20 items)

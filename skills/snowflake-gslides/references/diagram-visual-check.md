# Diagram Visual Check Guide

After build/rebuild, retrieve the thumbnail of every diagram slide and verify visual quality.
This check is **mandatory** whenever one or more `type: "diagram"` slides exist.

---

## Thumbnail Retrieval

```python
thumb = svc.presentations().pages().getThumbnail(
    presentationId=pid,
    pageObjectId=slide_id,
    thumbnailProperties_thumbnailSize='LARGE'
).execute()
# thumb['contentUrl'] → 1600×900 PNG URL
# requests.get(thumb['contentUrl']).content → image bytes
```

Inspect the retrieved image against all check items below.

---

## Check Items (9 total)

### 1. Icon Rendering

Verify that icon nodes (`shape: "icon"`) display as colored images.

| State | Verdict | Appearance |
|-------|---------|------------|
| Normal | OK | Colored icon image at correct size and position |
| Fallback | **NG** | Gray rectangle + icon name text (6pt) |
| Missing | **NG** | Nothing at node position (only floating label) |

**Criteria**: Any fallback or missing icon = NG.

**Causes and fixes**:
| Cause | How to verify | Fix |
|-------|---------------|-----|
| apps_script_url is empty | Check diagram_cfg contents | Confirm yaml fallback in build_slides.py is working |
| Icon name does not exist | Check `resolve_icon_name()` return value | Add mapping to icon_aliases.json or correct the name |
| Apps Script timeout | Check stdout/result.json | Re-run (transient network issue) |
| Drive permission denied | Check Apps Script error response | Verify Drive folder sharing settings |

---

### 2. Slide Bounds (Horizontal)

All elements must fit within the slide width (0–720pt).

| State | Verdict | Appearance |
|-------|---------|------------|
| Normal | OK | All nodes, groups, and labels within slide edges |
| Right overflow | **NG** | Node or group border extends beyond slide right edge |
| Left-crammed | WARNING | Elements touching left edge with no margin |

**Criteria**: Any element's right edge exceeding the slide right edge = NG.

**Causes and fixes**:
| Cause | Calculation | Fix |
|-------|-------------|-----|
| Too many nodes in group (min-width exceeds space) | (max_col+1)×cell + padding×2 > available per-group width | Reduce node col values, use smaller iconSize, or split across rows |
| Free node conflict with group | Free node obstacle limits group expansion | Move free node to different row, or place inside a group |
| 3+ groups overflow | Sum of min-widths > 680pt | Use fewer groups per row, or reduce iconSize |

Note: The builder auto-expands groups to fill available width (20–700pt). Horizontal overflow is rare — it only occurs when content min-width exceeds the drawable area.

---

### 3. Slide Bounds (Vertical)

All elements must fit within the slide height (0–405pt).

| State | Verdict | Appearance |
|-------|---------|------------|
| Normal | OK | All elements above slide bottom edge |
| Bottom overflow | **NG** | Nodes, groups, or labels extend below slide bottom |
| Footer invasion | **NG** | Nodes overlapping footer (© line) area |

**Criteria**: Node bottom edge (icon + label height 14pt) exceeding 375pt = NG. This is the DRAW_BOTTOM boundary enforced by lint.

**Causes and fixes**:
| Cause | Calculation | Fix |
|-------|-------------|-----|
| Body + too many rows | start_y(170) + row×cell + icon + label > 405 | With body max rows: 40pt→2, 30pt→2, 20pt→4 |
| No body + too many rows | start_y(50) + row×cell + icon + label > 405 | No body max rows: 40pt→3, 30pt→4, 20pt→6 |
| Group rowSpan too large | start_y + row×cell + rowSpan×cell + padding > 405 | Reduce rowSpan or reduce iconSize |

---

### 4. Node Label Position and Readability

Labels below icons must display correctly.

| State | Verdict | Appearance |
|-------|---------|------------|
| Normal | OK | Label centered below icon, fully readable |
| Too far from icon | WARNING | Unnatural gap between icon and label |
| Text truncated | **NG** | Label text cut off (width insufficient) |
| Overlap with other elements | **NG** | Label overlaps adjacent node or arrow |

**Criteria**: Unreadable text or overlap = NG.

**Causes and fixes**:
| Cause | Fix |
|-------|-----|
| Label too long (>12 chars) | Shorten label text |
| Nodes too close together | Increase col spacing (min 1 cell between adjacent nodes) |
| CJK characters wider than estimated | Verify display_len calculation is applied |

---

### 5. Edge Label Position

Arrow labels must be positioned near the midpoint without overlapping.

| State | Verdict | Appearance |
|-------|---------|------------|
| Normal | OK | Label near arrow midpoint, not overlapping the line |
| Overlaps arrow | **NG** | Label text rendered on top of the arrow line |
| Overlaps node | **NG** | Label overlaps a node icon or node label |
| Position ambiguous | WARNING | Unclear which arrow the label belongs to |

**Criteria**: Overlap with arrow or node = NG.

**Causes and fixes**:
| Cause | Fix |
|-------|-----|
| Vertical connection (dy > dx) label placement | Rearrange nodes so dx > dy (horizontal flow) |
| Label too long | Shorten to ≤10 characters |
| Label at elbow bend point | Remove edge label or rearrange nodes |
| Label not needed | Set label to empty string `""` |

---

### 6. Arrow Connection Points and Routing

Arrows must connect to appropriate sides and follow natural paths.

| State | Verdict | Appearance |
|-------|---------|------------|
| Normal | OK | Left-to-right flow with right→left connections, elbows bend naturally |
| Label penetration | **NG** | Arrow passes through a node label (text below icon) |
| Unnatural detour | WARNING | Elbow takes an unnecessarily long path |
| Reverse connection | **NG** | Arrow connects from unexpected side (e.g., left-side exit going right) |

**Criteria**: Label penetration or reverse connection = NG.

**Causes and fixes**:
| Cause | Fix |
|-------|-----|
| Top-bottom flow + label in between | Switch to left-to-right layout (ensure dx > dy) |
| Auto-detection incorrect (cross-group) | Explicitly set fromSide/toSide |
| Multiple edges from same node | Reduce edges or split node into separate instances |

---

### 7. Group Containment

Group borders must fully contain their child nodes. Adjacent groups must have a visible gap (no touching, no overlapping).

**How to check**: For each pair of adjacent groups (horizontal or vertical), verify there is a clear empty space between them. Check not just the border lines, but also:
- Group labels (text above the group content)
- Node labels (text below the icons)
- Node icons themselves

If ANY element from group A visually overlaps or touches ANY element from group B, it is **NG**.

| State | Verdict | How to identify |
|-------|---------|-----------------|
| Normal | OK | Clear visible gap between all elements of adjacent groups |
| Node overflow | **NG** | A node icon or its label extends outside its parent group border |
| Group overlap | **NG** | Any element (border, group label, node icon, or node label) from one group visually overlaps or touches any element from an adjacent group |
| Excessive empty space | WARNING | Large unused area within group |

**Criteria**: If you see any overlap or touching between elements of different groups = **NG**. When in doubt, it is NG.

**Causes and fixes**:
| Cause | Fix |
|-------|-----|
| colSpan/rowSpan too small for nodes | Ensure max child col + 1 ≤ colSpan (nodes must fit within declared span) |
| Adjacent child groups too close | Next child col ≥ previous col + previous colSpan + 1 |
| Nested child exceeds parent | Builder auto-clamps children within parent; if clamp is too aggressive, increase parent rowSpan/colSpan |
| Vertical groups touching/overlapping | Builder auto push-down ensures gap; if still touching, reduce iconSize or rowSpan |
| Excessive empty space in group | Normal — builder auto-expands width. Reduce rowSpan if vertical space is excessive |

---

### 8. Spacing and Balance

Overall diagram placement should be balanced within the slide.

| State | Verdict | Appearance |
|-------|---------|------------|
| Normal | OK | Adequate margins on all sides, centered layout |
| Excessive bottom space | **NG (1-row)** | Single-row diagram with empty lower half |
| Left-biased | WARNING | Diagram clustered on left, large right gap |
| Top-crammed | WARNING | Diagram touching title/subtitle directly |

**Criteria**: 1-row without body = NG (rule violation). Others = WARNING.

**Causes and fixes**:
| Cause | Fix |
|-------|-----|
| 1-row without body | Add body text (mandatory rule for 1-row diagrams) |
| Auto-centering not applied | Check group col placement |
| Body-diagram gap too narrow | Verify +60000 EMU additional gap is applied |

---

### 9. Brand Group Logo

Groups with `color: "snowflake"/"aws"/"azure"/"gcp"` should display a brand logo.

| State | Verdict | Appearance |
|-------|---------|------------|
| Normal | OK | Brand logo (16pt) in top-left corner of group |
| Logo missing | WARNING | Brand-colored group without logo icon (fallback) |
| Logo misplaced | WARNING | Logo outside group border or at unexpected position |

**Criteria**: Logo depends on Apps Script, so WARNING only (no functional impact).

---

## Overall Verdict

| Result | Condition | Action |
|--------|-----------|--------|
| **PASS** | All items OK or WARNING only | Report completion to user |
| **FAIL** | One or more NG items | Fix via rebuild_slide.py → re-check |
| **CRITICAL** | All icons failed (Check 1 all NG) | Verify config/Apps Script setup before retrying |

---

## Fix Flow

```
NG detected
  ↓
Modify spec.json for the affected slide only
  ↓
Re-run lint_spec.py (verify bounds)
  ↓
Execute rebuild_slide.py for that slide only
  ↓
Retrieve thumbnail again → re-check
  ↓
PASS → done / NG → fix again (max 2 attempts)
  ↓
Still FAIL after 2 fixes → report to user for decision
```

---

## Prohibited Actions During Fixes

1. **NEVER re-run build_slides.py** — Do not recreate all slides for a single-slide issue
2. **NEVER modify working slides** — Do not change spec for slides that passed checks
3. **NEVER reduce iconSize without lint guidance** — If lint shows iconSize upgrade ERROR, the current size is correct. If nodes overflow, adjust col/row/colSpan first; reduce iconSize only when lint confirms the smaller size is needed (e.g., 3+ body rows)
4. **NEVER remove nodes** — Do not drop information from the source md. If content cannot fit, split into multiple slides

---

## When to Skip This Check

- No diagram slides in the presentation (all bullets/table/code)
- User explicitly requests "skip visual check"
- After 2nd retry where the same issue persists (report to user and stop)

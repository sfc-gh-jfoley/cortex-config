# Diagram Patterns Reference
**Edge crossing prevention**: lint checks actual pixel positions of elbow connector segments against all node bounding boxes. Crossing is an ERROR.

**Cross-Group Edge Safety Rule**: When drawing an edge from node A in group X to node B in a different group, do NOT place another node in group X on the same row as A in the direction of B. Move extra nodes to a different row.

```
NG: Group X has A(col=0,row=0)→Group Y, C(col=1,row=0) in Group X ← C blocks the edge path
OK: Group X has A(col=0,row=0)→Group Y, C(col=0,row=1) in Group X ← different row, no conflict
```

**Adjacency rule**: The same applies vertically. Do not place nodes on the same col between a vertical edge's from and to.

**Edge crossing check details**: lint computes pixel positions using the same layout engine as the builder (compute_layout), generates elbow connector segments (3 segments: horizontal→vertical→horizontal or vertical→horizontal→vertical), and checks each segment against every node's bounding box. Google Slides BENT connectors do NOT auto-avoid obstacles.
Guide for generating `type: "diagram"` slides. MUST read before generating any diagram slide.

## spec.json Schema

```json
{
  "id": "sl_arch_01",
  "layout": "multi",
  "layoutId": "g1ed82e8067d_0_5350",
  "title": "Pipeline Architecture",
  "subtitle": "Source to Dashboard flow",
  "type": "diagram",
  "diagram": {
    "iconSize": 40,
    "groups": [
      {"id": "g1", "label": "Snowflake", "color": "snowflake", "col": 0, "row": 0, "colSpan": 5, "rowSpan": 2}
    ],
    "nodes": [
      {"id": "n1", "icon": "table", "label": "RAW", "col": 0, "row": 0, "groupId": "g1"},
      {"id": "n2", "icon": "dynamic_tables", "label": "SILVER", "col": 2, "row": 0, "groupId": "g1"},
      {"id": "n3", "icon": "process_1", "label": "ETL", "col": 1, "row": 1, "groupId": "g1"}
    ],
    "edges": [
      {"from": "n1", "to": "n2", "label": "refresh", "line": "elbow", "startArrow": "none", "endArrow": "arrow", "color": "dark_blue", "dashed": false}
    ]
  }
}
```

## When to Use (Proactive)

Generate `type: "diagram"` when content describes:
- System components with connections (architecture)
- Pipeline or data flow (source -> transform -> destination)
- Multiple services in relation to each other
- Icon-based visual would significantly improve comprehension over bullets
- Process flow with 3+ sequential steps (e.g., "detect → compute → merge")
- Comparison of two architectures/approaches (use Before/After pattern)
- "How it works" concept explanation with distinct phases or stages

Do NOT wait for user to explicitly request a diagram.

## LLM Generation Checklist

Before outputting a diagram spec, verify:
1. Choose pattern (1-14) matching the content structure
2. Choose iconSize: 40 (simple ≤7 nodes), 30 (groups/medium), 20 (dense)
3. Pick icons from aliases or index.json (use underscores)
4. Verify col/row within max bounds for chosen iconSize
5. All edges have 8 explicit fields: from, to, label, line, startArrow, endArrow, color, dashed
6. Labels ≤ 12 chars recommended (longer OK — auto-wraps to 2 lines). Never shorten to ambiguous abbreviations
7. Flow direction: left-to-right (source at low col, dest at high col)
8. No reverse edge pairs (A→B and B→A); use bidirectional single edge instead
9. Nested groups: child.col + child.colSpan + 1 ≤ next child.col
10. Total content fits slide (720×405pt)

## Flow Direction

**Respect the md's flow direction first.** If the md describes a vertical flow (top→bottom), use top-to-bottom layout. If horizontal (A → B → C), use left-to-right. Forcing a direction change (e.g., vertical md → horizontal layout) is the #1 cause of edge crossing issues.

**Decision flow:**
1. Check the md's flow direction (vertical or horizontal)
2. If vertical: count the number of stages
   - Fits in max row for iconSize=20 (6 rows without body, 3-4 with body) → **use top-to-bottom layout**
   - Does not fit → **convert to left-to-right** (max col=13 for iconSize=20)
3. If horizontal: use left-to-right (default)

**Left-to-right layout** (default for horizontal flows):
- Source nodes at lower col values, destination at higher col values
- Arrows auto-connect right→left (most natural)
- Labels below icons never overlap with horizontal arrows

**Top-to-bottom layout** (for vertical flows):
- Source nodes at lower row values, destination at higher row values
- Use when md explicitly shows vertical flow (stacked items, top→bottom arrows)
- Advantage: fan-out branches can spread horizontally without crossing

### Group fidelity

**Groups must reflect the md's structure, not LLM interpretation.**

- When the same environment label appears multiple times, **merge into one group**
- When the md defines a single group (e.g., `[Snowflake]`), create exactly 1 group — do NOT split into sub-categories
- Do NOT invent group names absent from the md (e.g., "Unstructured Data", "Structured Data" when md only says `[Snowflake]`)
- Create separate groups **only** when the md explicitly indicates different boundaries:
  - Different regions: `[AWS - us-east-1]` vs `[AWS - eu-west-1]`
  - Different VPCs: `[VPC A]` vs `[VPC B]`
  - Different accounts: `[Production Account]` vs `[Dev Account]`

## Field Reference

### diagram.iconSize
- `40`: Simple diagrams, 3-7 nodes (default)
- `30`: Medium complexity, groups, 5-12 nodes
- `20`: Dense diagrams, many nodes in groups

**Decision table** (choose the FIRST matching row):

| Condition | body あり | body なし |
|-----------|----------|----------|
| Nested groups (parent + child) | 20 | 20 or 30 |
| 3+ groups side-by-side on same row | 20 | 20 |
| Fan-in/out 4 sources/targets | 20 | 30 |
| Fan-in/out 5+ sources/targets | 20 | 20 |
| Has groups, 5-10 nodes | 30 | 30 |
| Total nodes > 10 | 20 | 20 or 30 |
| No groups, ≤7 nodes | 40 | 40 |

**Lint override rule**: lint checks whether all nodes AND group rowSpans fit at a larger iconSize. If lint reports `iconSize=N but all nodes fit with iconSize=M`, use iconSize=M. This takes priority over the table above. The lint check already accounts for body height and rowSpan constraints, so it will not suggest an iconSize that causes rowSpan overflow.

When in doubt, use `30` — it works for most real diagrams with groups.

### body あり時の group rowSpan 目安

| iconSize | cell (pt) | max rowSpan (body 3-4行) | max rowSpan (body なし) |
|----------|-----------|-------------------------|------------------------|
| 40       | 90        | 1-2                     | 3                      |
| 30       | 70        | 2                       | 4                      |
| 20       | 50        | 3-4                     | 6                      |

※ lint は body テキスト量に基づいて動的に計算するため、上記は目安。lint が rowSpan ERROR を出した場合はその値に従う。

### diagram.groups[]
| Field | Required | Description |
|-------|----------|-------------|
| id | yes | Unique group identifier |
| label | yes | Display label (brand groups show logo instead) |
| color | yes | Color name from palette |
| col | yes | Grid column position (global, or relative to parent) |
| row | yes | Grid row position (global, or relative to parent) |
| colSpan | yes | Width in grid cells. For top-level groups: also serves as proportional ratio when multiple groups share a row. Builder auto-expands to fill available space. Must be >= 1. |
| rowSpan | yes | Height in grid cells. Builder uses max(declared height, content height) then clamps at slide bottom. |
| parentGroupId | no | Nest inside another group (max 1 level). Child is clamped within parent bounds. |

### Slide Bounds (CRITICAL)
Slide is 720×405pt. Drawable area: x=20–700pt, y=start_y–375pt (DRAW_BOTTOM).

**Auto-expand behavior**: Top-level groups automatically expand horizontally to fill the drawable area (20–700pt). The builder handles this; you do NOT need to calculate exact pixel widths. Just set `col` for sort order and `colSpan` for proportional ratio.

- Single group on a row: expands to full width (respecting free node obstacles)
- Multiple groups on same row: split proportionally by their `colSpan` values with 20pt gaps
- `col` field for top-level groups = sort order (lower col renders left)
- `colSpan` = relative weight for proportional split (e.g. colSpan 3 vs 2 → 60%/40%). Also serves as minimum capacity: node col values must be < colSpan.
- Min-width guarantee: groups never shrink below what their content nodes require

**Vertical content-fit**: Group height is the maximum of the declared rowSpan-based height and the deepest node row + padding. Height expands to fit content but never stretches beyond what is needed. Groups are clamped at DRAW_BOTTOM (375pt).

**Nested groups**: Automatically repositioned and clamped within parent's expanded inner area. Keep child content reasonable; the builder handles overflow by clamping width/height to a minimum of 1 cell.

**Vertical overlap forbidden**: Top-level groups must NOT have partially overlapping vertical ranges (row + rowSpan). Groups with identical `row` AND `rowSpan` are allowed (same horizontal band = side-by-side). Lint will ERROR on partial overlap. Use different row positions for vertically stacked groups.

Max grid capacity (for node placement within groups):
- iconSize=40 (cell=90): max col index=7, max row index=3
- iconSize=30 (cell=70): max col index=9, max row index=4
- iconSize=20 (cell=50): max col index=13, max row index=6

### Free Node Placement Rules

Free nodes (no `groupId`) are automatically avoided by groups during auto-expand. The layout engine reserves space for free nodes so groups do not overlap them.

**Safe patterns**:
1. Place to the right of groups: use a col value larger than the group's node content. The group will stop expanding before the free node.
2. Place below all groups: `row ≥ max(group row + group rowSpan)` for all groups
3. Place above all groups: `row < min(group row) - 1`
4. Place to the left of groups: use col=0 for free node and start group content at col≥2. The group's left edge expands leftward but stops before the free node. **Important**: the group's `col` position must leave enough gap (≥1 cell) from the free node. If overlap persists, wrap the free node in a small single-node group — groups respect each other's boundaries.

**Limitations**:
- Free node between two side-by-side groups may not have enough space if both groups need their min-width. In this case, move the free node to a row below the groups, or wrap it in a single-node group.
- If a free node at col=0 overlaps with a group that auto-expands leftward, the safest fix is to place the free node inside its own group (groupId with only that node). Groups do not overlap each other.

### diagram.nodes[]
| Field | Required | Description |
|-------|----------|-------------|
| id | yes | Unique node identifier |
| icon | yes | Icon name (use underscores). Search config/icon_aliases.json first. Use Generic Icons only when no specific icon exists. |
| label | yes | Text below icon |
| col | yes | Column within group (relative) or global |
| row | yes | Row within group (relative) or global |
| groupId | no | Parent group id (relative coords) |
| offsetX | no | Fine-tune X position (pt) |
| offsetY | no | Fine-tune Y position (pt) |

### diagram.edges[]
| Field | Required | Description |
|-------|----------|-------------|
| from | yes | Source node id |
| to | yes | Target node id |
| label | yes | Text on arrow (empty string for none) |
| line | yes | elbow / straight / curved |
| startArrow | yes | arrow / none |
| endArrow | yes | arrow / none |
| color | yes | dark_blue / gray / accent |
| dashed | yes | true / false |
| fromSide | no | Override: top/right/bottom/left |
| toSide | no | Override: top/right/bottom/left |

## Group Color Palette

### Brand (white bg, logo icon auto-inserted)
| Name | Border | Use when |
|------|--------|----------|
| snowflake | #29B5E8 | Snowflake icons inside |
| aws | #FF9900 | AWS service icons inside |
| azure | #0078D4 | Azure service icons inside |
| gcp | #4285F4 | Google Cloud icons inside |

### Default
| Name | Border | Use when |
|------|--------|----------|
| default | #333333 | No brand association |

### Semantic (ultra-light bg, text label)
| Name | Border | Use when |
|------|--------|----------|
| gray | #999999 | Generic zone/layer |
| green | #4CAF50 | Production/success |
| coral | #D32F2F | Warning/error |
| purple | #7B1FA2 | Analytics/AI |
| teal | #00897B | Network/infra |
| amber | #F57F17 | Staging/dev |
| bronze | #CD7F32 | Bronze/raw data layer |
| silver | #78909C | Silver/curated layer |
| gold | #F9A825 | Gold/consumption layer |

## Edge Style Guide

### line
- `elbow`: Standard right-angle connectors. Use for most cases.
- `straight`: Direct line. Use when nodes are in same row/col with no obstacles.
- `curved`: Organic curve. Rarely used.

### startArrow / endArrow
- One-way flow: `none` -> `arrow`
- Bidirectional: `arrow` -> `arrow`
- Association (no direction): `none` -> `none`

### dashed
- `false`: Normal connection/flow
- `true`: Optional, dependency, async

### color
- `dark_blue`: Main flow (default choice)
- `gray`: Secondary/auxiliary connection
- `accent`: Highlight, error path

## Grid Capacity

These limits apply equally to grouped nodes (inside a group with rowSpan) and free nodes (groups=[]). Body text reduces available diagram height regardless of whether groups are used.

### iconSize: 40 (cell=90pt, gap=50pt)
- Horizontal: max col index=7 (cols 0-7 = up to 8 nodes)
- Vertical: max row index=3 (no body) / **max row index=2 (with body)**

### iconSize: 30 (cell=70pt, gap=40pt)
- Horizontal: max col index=9 (cols 0-9 = up to 10 nodes)
- Vertical: max row index=4 (no body) / **max row index=2 (with body)**
- Inside 2 groups: 4 nodes wide, 3 rows

### iconSize: 20 (cell=50pt, gap=30pt)
- Horizontal: max col index=13 (cols 0-13 = up to 14 nodes)
- Vertical: max row index=6 (no body) / **max row index=4 (with body)**
- Inside 2 groups: 7 nodes wide, 5 rows

**CRITICAL: "with body" means the slide has a `body` field. Body text takes ~120pt, reducing available diagram height significantly. Always account for this when choosing row count.**

**Group rowSpan limits are dynamic** — lint calculates the maximum rowSpan based on actual body height and iconSize. If lint reports a rowSpan ERROR, it will suggest the correct iconSize to use. Do not rely on fixed tables; trust the lint output.

## Layout Patterns

### Pattern 1: Linear Flow
```
[icon] -> [icon] -> [icon]
```
Use: Simple pipeline, ETL flow. iconSize=40, all row=0.

### Pattern 2: Two-group
```
+-- AWS --+     +-- Snowflake ------+
| [S3]    | --> | [table] -> [DT]   |
+----------+    +-------------------+
```
Use: Cross-cloud data movement. iconSize=30, 2 groups.
Rule: If an intermediate service has an icon (e.g. Snowpipe, Kafka), place it as a node between groups—not as an edge label. Edge labels are for verbs/actions only (e.g. "load", "sync"), not for service names.

### Pattern 3: Hub and Spoke
```
         [icon]
           ^
[icon] <- [hub] -> [icon]
           v
         [icon]
```
Use: Central service distributing/receiving. iconSize=40, center at col=2/row=1.
Symmetry rule: If spokes are equal count left/right, place them at matching rows. If equal count top/bottom, place at matching cols. Example: 2 left spokes at row=0,row=2 → 2 right spokes also at row=0,row=2.

**Hub placement**: Always place the Hub node inside a group (not as a free node). Free node Hubs will overlap with auto-expanded groups. If groups are not needed, use flat layout (no groups at all).

### Pattern 4: Layered (Left-to-Right)
```
col 0:       col 3:        col 6:       col 8:
[S3]         [table]       [DT]         [dashboard]
[RDS]        [table]       [DT]
[API]
 Source       Bronze        Silver        Consume
```
Use: Medallion architecture, data layers. iconSize=30. Flow is left-to-right.
Each layer occupies a column group. Nodes at same column = same layer.
Edges auto-connect right→left. Use rows to stack multiple nodes in same layer.
**rowSpan sizing**: Set each group's rowSpan = max(node row within group) + 1. Do NOT set all groups to the same rowSpan for visual uniformity — the builder auto-adjusts heights proportionally.

### Pattern 5: Icon Gallery
```
[icon1] [icon2] [icon3] [icon4]
 label   label   label   label
```
Use: Feature overview, service catalog. iconSize=40, edges=[].
Multi-row gallery: Use consecutive rows (0, 1, 2…). Do NOT skip rows. Col spacing (0, 2, 4) is acceptable for visual breathing room.

### Pattern 6: Nested Groups (Grouped Layers)
```
+-- Snowflake (outer) --------------------------+
|  +-- Bronze --+  +-- Silver --+  +-- Gold --+ |
|  | [table]    |  | [DT]       |  | [DT]     | |
|  | [table]    |  | [DT]       |  | [Dash]   | |
|  +------------+  +------------+  +----------+ |
+------------------------------------------------+
```
Use: Medallion in single platform, nested environment.
iconSize=30. Parent group first in array, children use `parentGroupId`.
Nesting limited to 1 level. Children use col/row relative to parent.
**Rule: Parent rowSpan MUST be > max child rowSpan.** (e.g. children rowSpan=2 → parent rowSpan≥3). This ensures labels and padding fit within the parent boundary.

```json
"groups": [
  {"id": "sf", "label": "Snowflake", "color": "snowflake", "col": 0, "row": 0, "colSpan": 6, "rowSpan": 3},
  {"id": "bronze", "label": "Bronze", "color": "bronze", "col": 0, "row": 0, "colSpan": 1, "rowSpan": 2, "parentGroupId": "sf"},
  {"id": "silver", "label": "Silver", "color": "silver", "col": 2, "row": 0, "colSpan": 1, "rowSpan": 2, "parentGroupId": "sf"},
  {"id": "gold", "label": "Gold", "color": "gold", "col": 4, "row": 0, "colSpan": 1, "rowSpan": 2, "parentGroupId": "sf"}
]
```
Child group spacing: next child col = prev.col + prev.colSpan + 1 (gap of 1 cell between children).

### Pattern 7: Before/After
```
+-- Before --+     +-- After ----------+
| [A] -> [B] |     | [A] -> [C] -> [B] |
+-------------+    +--------------------+
```
Use: Migration, improvement proposal. 2 groups side by side.

### Pattern 8: Fan-in
```
[S3]     ─┐
[RDS]    ─┼─→ [DT] → [Dashboard]
[Kinesis] ─┘
```
Use: Data aggregation, ETL consolidation. iconSize=40.
Sources at col=0, rows=0/1/2 (consecutive, no gaps). Target at col=3, row=1 (middle).
Keep rows consecutive (0,1,2 not 0,2,4) to avoid exceeding slide height.
For 4+ sources with body: use iconSize=20 (max row index=4 with body). 3 sources with body: iconSize=40 or 30.

**Multiple sources/targets in a group:** Stack nodes perpendicular to the flow direction. Left-to-right flow (default) → vertical stack (same col, different rows). Top-to-bottom flow → horizontal stack (same row, different cols). This prevents edges from crossing intermediate nodes.

### Pattern 9: Fan-out
```
              ┌─→ [icon]
[icon] → [hub]┼─→ [icon]
              └─→ [icon]
```
Use: Distribution, event broadcasting. iconSize=40.
Hub at col=0, row=1. Targets at col=3, rows=0/1/2.
For 4+ targets with body: use iconSize=20 (max row=4 with body, allowing rows 0-4=5 targets). 3 targets with body: iconSize=40 or 30. Place ALL targets in the same col at consecutive rows—never split to a separate col.

### Pattern 10: Bidirectional
```
[icon] <-> [icon] <-> [icon]
```
Use: Sync, replication. startArrow=arrow, endArrow=arrow.

IMPORTANT: Do NOT create two separate edges (A→B and B→A) between the same nodes.
Use a single edge with `startArrow: "arrow", endArrow: "arrow"` instead.
Multiple edges from same connection point overlap and become unreadable.

**Adjacency rule:** Edges MUST connect adjacent nodes only. Never draw an edge that crosses over an intermediate node on the same row or col. If A is at col=0 and C is at col=4 with B at col=2 (same row), do NOT create edge A→C. Instead route through B (A→B, B→C) or move C to a different row.

### Pattern 11: Multi-group Pipeline
```
+- Source -+   +- Transform -+   +- Serve -+
| [icon]   | > | [icon]->[icon]| > | [icon]  |
+-----------+  +--------------+   +----------+
```
Use: 3+ stage pipeline, microservices.

### Pattern 12: Matrix
```
       Col_A   Col_B   Col_C
Row_1: [icon]  [icon]  [icon]
Row_2: [icon]  [icon]  [icon]
```
Use: Feature comparison visual, role-permission matrix. edges=[].

### Pattern 13: Nested Groups
```
+-- VPC -------------------------+
|  +- Public -+ +- Private ----+ |
|  | [ALB]    | | [EC2] [RDS]  | |
|  +----------+ +--------------+ |
+--------------------------------+
```
Use: Network topology, security zones. Nested group = smaller colSpan/rowSpan inside outer group grid.
Connect subnet nodes with edges based on data/traffic flow (e.g. ALB→App, App→DB). Do not leave infrastructure nodes orphaned if they participate in the architecture flow.

### Pattern 14: Timeline Flow
```
[icon] -> [icon] -> [icon] -> [icon]
 T=0       T+1h     T+2h      T+24h
```
Use: Scheduled refresh, time-based processing.

### Cross-Group Edge Crossing Avoidance

When edges connect nodes across two groups (e.g., Diagnosis → Fixes), crossing is common if both groups have multiple nodes. Rules:

1. **Align source and target vertically**: If check_A leads to fix_A, place both at the same row. This makes the edge horizontal and avoids crossing other nodes.
2. **Simplify many-to-many edges**: If N checks map to M fixes, don't draw N×M edges. Draw each check to its direct fix only (same row or nearest). Describe other relationships in body text.
3. **Prefer horizontal flow over diagonal**: Source at lower col, target at higher col, same row → straight horizontal edge with no crossing risk.
4. **If crossing is unavoidable after 2 lint attempts**: Simplify the diagram structure (merge nodes, reduce edges) rather than endlessly adjusting col/row.
5. **Overlapping reverse edges**: When two edges travel the same line segment in opposite directions (e.g., `A→C` downward and `B→A` upward share the same vertical path), they visually merge into a bidirectional arrow. Fix: add `fromSide` or `toSide` to one edge to reroute it (e.g., `toSide: "left"` makes the arrow arrive from the side instead of straight up/down).

## Icon Selection

### Rules

- **Always search `config/icon_aliases.json` and `config/index.json`** for icon names. Do NOT rely on memory alone.
- If a specific brand/service icon exists, use it. Lint will warn if you use a generic icon when a specific one is available.
- Aliases supported (e.g. "s3" → "amazon_simple_storage_service", "redshift" → "amazon_redshift")
- Categories: snowflake, logos, general, aws, azure, fabric
- Use the most specific icon (e.g. "dynamic_tables" not "table" for DT)
- Use underscores in names (e.g. "dynamic_tables" not "dynamic-table")
- **`icon` value MUST be an English icon name** from icons_list.json or icon_aliases.json. Never use translated/localized words (e.g. use "application" not "アプリ").
- **Every node requires an `icon` field.**
- **Avoid reusing the same icon for conceptually different services** on one slide.
- **Exception**: Cortex products now have individual icons: `cortex_analyst` (chart+AI), `cortex_agent` (robot+AI), `ai_function` (Fx+AI), `universal_search` (Cortex Search). Use `snowflake_cortex` only for the platform as a whole.

### Generic Icons (fallback when no brand icon exists)

| Category | Icon | Use for |
|----------|------|---------|
| Server / Compute | `server` | On-prem server, VM, API server |
| Database | `database` | Generic/unknown DB |
| Processing / ETL | `process_1` | ETL job, batch, transformation |
| Application | `application` | Web app, SaaS, business system |
| Abstract block | `cube` | Unknown / catch-all |
| Cloud | `cloud` | Cloud service, external SaaS |
| Internet | `globe` | Web, external connection |
| Data / File | `data` | Data source, CSV, JSON |
| Function / Logic | `function` | UDF, Lambda, script |
| Layer / Stack | `layers` | Multi-stage, abstract layer |
| Storage | `hard_drive`, `storage` | Disk, S3, Blob |
| Sync / CDC | `refresh` | CDC, sync, update |
| Microservices | `services` | Service mesh, API group |
| Container | `container` | Docker, containerized app |
| User | `user_1` | End user, persona, actor |
| Team | `users` | Team, department, group |
| Security | `security` | Auth, encryption |
| Pipeline | `pipe` | Data pipeline, ingestion |
| Notification | `email` | Email, alert delivery |
| Defense | `shield` | Firewall, governance |
| Monitoring | `monitor` | Dashboard, observability |
| Mobile | `mobile` | Mobile app, device |
| Alert | `bell` | Alert, event notification |

## Canonical Example: Snowflake Data Pipeline

```json
{
  "iconSize": 30,
  "groups": [
    {"id": "aws", "label": "AWS", "color": "aws", "col": 0, "row": 0, "colSpan": 1, "rowSpan": 2},
    {"id": "sf", "label": "Snowflake", "color": "snowflake", "col": 1, "row": 0, "colSpan": 5, "rowSpan": 2}
  ],
  "nodes": [
    {"id": "s3", "icon": "s3", "label": "S3", "col": 0, "row": 0, "groupId": "aws"},
    {"id": "raw", "icon": "table", "label": "RAW", "col": 0, "row": 0, "groupId": "sf"},
    {"id": "silver", "icon": "dynamic_tables", "label": "SILVER", "col": 2, "row": 0, "groupId": "sf"},
    {"id": "gold", "icon": "dynamic_tables", "label": "GOLD", "col": 3, "row": 0, "groupId": "sf"},
    {"id": "app", "icon": "streamlit", "label": "Streamlit", "col": 4, "row": 0, "groupId": "sf"}
  ],
  "edges": [
    {"from": "s3", "to": "raw", "label": "load", "line": "elbow", "startArrow": "none", "endArrow": "arrow", "color": "dark_blue", "dashed": false},
    {"from": "raw", "to": "silver", "label": "clean", "line": "elbow", "startArrow": "none", "endArrow": "arrow", "color": "dark_blue", "dashed": false},
    {"from": "silver", "to": "gold", "label": "agg", "line": "elbow", "startArrow": "none", "endArrow": "arrow", "color": "dark_blue", "dashed": false},
    {"from": "gold", "to": "app", "label": "serve", "line": "elbow", "startArrow": "none", "endArrow": "arrow", "color": "dark_blue", "dashed": false}
  ]
}
```

## Mutual Exclusion

- diagram CANNOT coexist with table or code on the same slide
- diagram CAN coexist with body (bullets above, diagram below)
- **Diagram slides SHOULD include body bullets** when the md source has explanatory text. The body provides context; the diagram provides visual. Use both together for maximum comprehension.
- **1-row diagrams (all nodes at same row) MUST have body bullets.** A single-row diagram leaves too much empty space below; body text is required to fill the slide and provide explanation.

## Node Labels

- Keep labels short (≤12 display chars recommended). Labels auto-wrap to 2 lines at spaces if they exceed icon width. **Never shorten to ambiguous abbreviations** (e.g., "Snowpipe Str" is NG — write "Snowpipe Streaming" and let it auto-wrap). When a label exceeds 12 chars, prefer the full name over a meaningless truncation.
- **UPPER_SNAKE_CASE** (e.g., RAW_EVENTS, AGG_MONTHLY) renders poorly at small iconSize. Convert to human-readable Title Case: "Raw Events", "Monthly Agg", "Clean Users".
- Use object names or service names (e.g. "Raw Data", "Silver DT", "S3"). Prefer Title Case over UPPER_SNAKE_CASE for readability.
- **Node labels = nouns (objects/services). Edge labels = verbs (actions/processes).** Never put process names (e.g. "検出", "Calculate", "Merge") as node labels. Instead, use objects as nodes and actions as edge labels between them.

### Node vs Edge Decision Flow

1. Does this concept have a **deployed, running entity** (server, service, table, queue)? → **Node** with specific icon
2. Is it a **process/action** (detect, transform, aggregate, sync)?
   - Does it run as an independent service (e.g. Airflow, CodePipeline, ETL server)? → **Node** (use service icon)
   - Is it just an action between two entities? → **Edge label** (not a node)
3. For generic processing steps that ARE independent components, use:
   - `process_1` (gear icon) — general transformation/processing
   - `refresh` (circular arrows) — sync/refresh/update cycle
   - `process` (radial arrows) — distribution/fan-out processing
   - `aggregate` (converging arrows + text bar) — aggregation (note: has fixed "AGGREGATE" text)

## Edge Labels

- Edge labels should match the language of the md source
- Technical terms (e.g. "CDC", "ETL", "refresh") may remain in English regardless of source language
- Keep edge labels short (≤10 chars recommended)

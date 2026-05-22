"""Shared layout computation for diagrams.

Used by diagram_builder.py (rendering) and lint_spec.py (validation).
"""
from collections import defaultdict

PT = 12700

DIAGRAM_GRID = {
    40: {"size": 40, "gap": 50, "cell": 90},
    30: {"size": 30, "gap": 40, "cell": 70},
    20: {"size": 20, "gap": 30, "cell": 50},
}

DIAGRAM_FONT_SIZES = {
    40: {"label": 8, "group_label": 9, "edge_label": 7},
    30: {"label": 7, "group_label": 8, "edge_label": 6},
    20: {"label": 6, "group_label": 7, "edge_label": 5},
}

DRAW_LEFT = 20
DRAW_RIGHT = 700
DRAW_BOTTOM = 375
GROUP_GAP = 20
CONNECTION_SITE = {"top": 0, "left": 1, "bottom": 2, "right": 3}


def auto_connection_sites(dx, dy):
    if dx == 0 and dy == 0:
        return 3, 1
    if abs(dx) >= abs(dy):
        if dx > 0:
            return 3, 1
        else:
            return 1, 3
    else:
        if dy > 0:
            return 2, 0
        else:
            return 0, 2


def compute_layout(diagram_spec, diagram_cfg=None, start_y_emu=None):
    """Compute pixel positions for all groups and nodes.

    Args:
        diagram_spec: the "diagram" dict from spec.json
        diagram_cfg: config.diagram section (optional)
        start_y_emu: Y position in EMU where diagram starts (optional, default 1140000)

    Returns:
        dict with keys: group_positions, node_positions, icon_size, cell, fonts,
                        content_x_pt, start_y_pt, free_node_positions,
                        padding_x, padding_y, child_padding_y, padding_bottom
    """
    if diagram_cfg is None:
        diagram_cfg = {}
    if start_y_emu is None:
        start_y_emu = 1140000

    icon_size = diagram_spec.get("iconSize", diagram_cfg.get("default_icon_size", 40))
    grid = DIAGRAM_GRID.get(icon_size, DIAGRAM_GRID[40])
    fonts = DIAGRAM_FONT_SIZES.get(icon_size, DIAGRAM_FONT_SIZES[40])
    cell = grid["cell"]

    slide_width_pt = 720
    start_y_pt = start_y_emu / PT
    padding_x = 20
    padding_y = 30
    padding_bottom = 10
    child_padding_y = 20

    groups = diagram_spec.get("groups", [])
    nodes = diagram_spec.get("nodes", [])

    groups = [g for g in groups if g.get("id")]
    nodes = [n for n in nodes if n.get("id")]

    for g in groups:
        gid = g["id"]
        g_nodes = [n for n in nodes if n.get("groupId") == gid]
        child_groups = [g2 for g2 in groups if g2.get("parentGroupId") == gid]
        auto_cs = 1
        auto_rs = 1
        if g_nodes:
            auto_cs = max(auto_cs, max(n.get("col", 0) for n in g_nodes) + 1)
            auto_rs = max(auto_rs, max(n.get("row", 0) for n in g_nodes) + 1)
        for cg in child_groups:
            cg_right = cg.get("col", 0) + cg.get("colSpan", 2)
            cg_bottom = cg.get("row", 0) + cg.get("rowSpan", 2)
            auto_cs = max(auto_cs, cg_right)
            auto_rs = max(auto_rs, cg_bottom)
        g["colSpan"] = max(g.get("colSpan", 1), auto_cs)
        g["rowSpan"] = max(g.get("rowSpan", 1), auto_rs)

    all_cols = [n.get("col", 0) for n in nodes if not n.get("groupId")]
    if groups:
        for g in groups:
            g_nodes = [n for n in nodes if n.get("groupId") == g["id"]]
            for n in g_nodes:
                all_cols.append(g.get("col", 0) + n.get("col", 0))
    max_col = max(all_cols) if all_cols else 0
    total_content_w = max_col * cell + icon_size
    if groups:
        max_group_right = max((g.get("col", 0) * cell + g.get("colSpan", 2) * cell + padding_x * 2) for g in groups)
        total_content_w = max(total_content_w, max_group_right)
    content_x_pt = max(37, (slide_width_pt - total_content_w) / 2)

    group_positions = {}

    def _group_depth(g):
        return 0 if not g.get("parentGroupId") else 1

    sorted_groups = sorted(groups, key=_group_depth)

    for g in sorted_groups:
        gid = g["id"]
        g_col = g.get("col", 0)
        g_row = g.get("row", 0)
        g_colspan = g.get("colSpan", 2)
        g_rowspan = g.get("rowSpan", 2)
        parent_id = g.get("parentGroupId")

        if parent_id and parent_id in group_positions:
            pp = group_positions[parent_id]
            gx = pp["x"] + padding_x + g_col * cell
            gy = pp["y"] + padding_y + g_row * cell
            gw = g_colspan * cell + padding_x * 2
            gh = g_rowspan * cell + child_padding_y + padding_bottom
        else:
            gx = content_x_pt + g_col * cell
            gy = start_y_pt + g_row * cell
            gw = g_colspan * cell + padding_x * 2
            gh = g_rowspan * cell + padding_y + padding_bottom

        group_positions[gid] = {"x": gx, "y": gy, "w": gw, "h": gh}

    row_groups = defaultdict(list)
    for g in groups:
        if not g.get("parentGroupId"):
            row_groups[g.get("row", 0)].append(g)

    free_node_positions = []
    free_base_x = DRAW_LEFT if groups else content_x_pt
    for n in nodes:
        if not n.get("groupId"):
            nx = free_base_x + n.get("col", 0) * cell + n.get("offsetX", 0)
            ny = start_y_pt + n.get("row", 0) * cell + n.get("offsetY", 0)
            free_node_positions.append({"x": nx, "right": nx + icon_size, "y": ny, "bottom": ny + icon_size})

    for row_idx, rg_list in row_groups.items():
        if len(rg_list) == 1:
            g = rg_list[0]
            gp = group_positions[g["id"]]
            g_top = gp["y"]
            g_bot = gp["y"] + gp["h"]
            g_nodes = [n for n in nodes if n.get("groupId") == g["id"]]
            g_max_col = max((n.get("col", 0) for n in g_nodes), default=0)
            g_min_w = (g_max_col + 1) * cell + padding_x * 2
            overlapping_free = [fp for fp in free_node_positions if fp["bottom"] > g_top and fp["y"] < g_bot]
            free_right = [fp for fp in overlapping_free if fp["x"] >= DRAW_LEFT + g_min_w]
            free_left = [fp for fp in overlapping_free if fp["right"] <= DRAW_LEFT + g_min_w and fp not in free_right]
            right_limit = min(fp["x"] for fp in free_right) - GROUP_GAP if free_right else DRAW_RIGHT
            left_limit = max(fp["right"] for fp in free_left) + GROUP_GAP if free_left else DRAW_LEFT
            gp["x"] = left_limit
            gp["w"] = max(cell, right_limit - left_limit)
        else:
            total_spans = sum(g2.get("colSpan", 2) for g2 in rg_list)
            sorted_rg = sorted(rg_list, key=lambda x: x.get("col", 0))
            min_widths = []
            for g2 in sorted_rg:
                g_nodes = [n for n in nodes if n.get("groupId") == g2["id"]]
                if g_nodes:
                    max_ncol = max(n.get("col", 0) for n in g_nodes)
                    min_widths.append((max_ncol + 1) * cell + padding_x * 2)
                else:
                    min_widths.append(cell + padding_x * 2)
            total_min = sum(min_widths)

            g_top = min(group_positions[g2["id"]]["y"] for g2 in rg_list)
            g_bot = max(group_positions[g2["id"]]["y"] + group_positions[g2["id"]]["h"] for g2 in rg_list)
            overlapping_free = [fp for fp in free_node_positions if fp["bottom"] > g_top and fp["y"] < g_bot]

            left_limit = DRAW_LEFT
            right_limit = DRAW_RIGHT
            total_min_right = DRAW_LEFT + total_min + GROUP_GAP * (len(rg_list) - 1)
            for fp in overlapping_free:
                if fp["x"] >= total_min_right:
                    right_limit = min(right_limit, fp["x"] - GROUP_GAP)
                elif fp["right"] <= total_min_right:
                    left_limit = max(left_limit, fp["right"] + GROUP_GAP)

            available_w = right_limit - left_limit - GROUP_GAP * (len(rg_list) - 1)
            current_x = left_limit
            for idx, g2 in enumerate(sorted_rg):
                gp = group_positions[g2["id"]]
                if total_min >= available_w:
                    prop_w = min_widths[idx]
                else:
                    ratio = g2.get("colSpan", 2) / max(total_spans, 1)
                    prop_w = max(available_w * ratio, min_widths[idx])
                gp["x"] = current_x
                gp["w"] = prop_w
                current_x += prop_w + GROUP_GAP

    if groups:
        content_x_pt = DRAW_LEFT

    child_group_ids = {g["id"]: g.get("parentGroupId") for g in groups if g.get("parentGroupId")}
    top_level_groups = [g for g in groups if not g.get("parentGroupId")]
    top_level_y_sorted = sorted(top_level_groups, key=lambda g: g.get("row", 0))

    for idx, g in enumerate(top_level_y_sorted):
        gp = group_positions[g["id"]]
        if idx > 0:
            prev_g = top_level_y_sorted[idx - 1]
            prev_gp = group_positions[prev_g["id"]]
            if prev_g.get("row", 0) < g.get("row", 0):
                min_y = prev_gp["y"] + prev_gp["h"] + GROUP_GAP
                if gp["y"] < min_y:
                    gp["y"] = min_y

    for idx, g in enumerate(top_level_y_sorted):
        if g.get("parentGroupId"):
            continue
        gp = group_positions[g["id"]]
        descendant_ids = [g["id"]] + [cid for cid, pid in child_group_ids.items() if pid == g["id"]]
        g_nodes = [n for n in nodes if n.get("groupId") in descendant_ids]
        if g_nodes:
            direct_nodes = [n for n in g_nodes if n.get("groupId") == g["id"]]
            max_node_row = max((n.get("row", 0) for n in direct_nodes), default=0)
            content_h = (max_node_row + 1) * cell + padding_y + 20
            for cg_id in descendant_ids[1:]:
                if cg_id in group_positions:
                    cg_def = next((x for x in groups if x["id"] == cg_id), {})
                    cg_row = cg_def.get("row", 0)
                    cg_rowspan = cg_def.get("rowSpan", 2)
                    child_bottom = (cg_row + cg_rowspan) * cell + padding_y + padding_bottom
                    content_h = max(content_h, child_bottom)
            gp["h"] = max(gp["h"], content_h)
        next_groups = [g2 for g2 in top_level_y_sorted[idx+1:] if g2.get("row", 0) > g.get("row", 0)]
        if next_groups:
            next_gp = group_positions[next_groups[0]["id"]]
            max_h = next_gp["y"] - gp["y"] - GROUP_GAP
        else:
            max_h = DRAW_BOTTOM - gp["y"]
        free_below = [fp for fp in free_node_positions
                      if fp["y"] >= gp["y"] + gp["h"]
                      and fp["right"] > gp["x"] and fp["x"] < gp["x"] + gp["w"]]
        if free_below:
            max_h = min(max_h, min(fp["y"] for fp in free_below) - gp["y"] - GROUP_GAP)
        gp["h"] = max(cell, max_h)

    child_groups_by_parent = defaultdict(list)
    for g in groups:
        pid = g.get("parentGroupId")
        if pid and pid in group_positions:
            child_groups_by_parent[pid].append(g)

    for pid, children in child_groups_by_parent.items():
        pp = group_positions[pid]
        inner_left = pp["x"] + padding_x
        inner_right = pp["x"] + pp["w"] - padding_x
        inner_top = pp["y"] + padding_y
        inner_bottom = pp["y"] + pp["h"] - padding_bottom
        inner_w = inner_right - inner_left

        child_ids = {c["id"] for c in children}
        parent_free_nodes = []
        for n in nodes:
            if n.get("groupId") == pid:
                nx = pp["x"] + padding_x + n.get("col", 0) * cell
                ny = pp["y"] + padding_y + n.get("row", 0) * cell
                parent_free_nodes.append({"x": nx, "right": nx + icon_size, "y": ny, "bottom": ny + icon_size})

        row_children = defaultdict(list)
        for c in children:
            row_children[c.get("row", 0)].append(c)

        for row_idx, rc_list in row_children.items():
            total_spans = sum(c.get("colSpan", 2) for c in rc_list)
            gap = GROUP_GAP
            avail_w = inner_w - gap * (len(rc_list) - 1)
            current_x = inner_left
            for c in sorted(rc_list, key=lambda x: x.get("col", 0)):
                cp = group_positions[c["id"]]
                ratio = c.get("colSpan", 2) / max(total_spans, 1)
                cp["x"] = current_x
                cp["w"] = max(cell, avail_w * ratio)
                current_x += cp["w"] + gap

        children_sorted_by_row = sorted(children, key=lambda c: c.get("row", 0))
        for idx, c in enumerate(children_sorted_by_row):
            cp = group_positions[c["id"]]
            cp["y"] = inner_top + c.get("row", 0) * cell
            next_in_col = [c2 for c2 in children_sorted_by_row[idx+1:] if c2.get("row", 0) > c.get("row", 0)]
            if next_in_col:
                next_y = inner_top + next_in_col[0].get("row", 0) * cell
                bottom_limit = next_y - GROUP_GAP
            else:
                bottom_limit = inner_bottom
            pfn_below = [pf for pf in parent_free_nodes
                         if pf["y"] >= cp["y"] + cell
                         and pf["right"] > cp["x"] and pf["x"] < cp["x"] + cp["w"]]
            if pfn_below:
                bottom_limit = min(bottom_limit, min(pf["y"] for pf in pfn_below) - GROUP_GAP)
            cp["h"] = max(cell, bottom_limit - cp["y"])

    for gid, gp in group_positions.items():
        gp["x"] = max(DRAW_LEFT, gp["x"])
        gp["w"] = max(cell, min(gp["w"], DRAW_RIGHT - gp["x"]))
        gp["y"] = max(start_y_pt, gp["y"])
        gp["h"] = max(cell, min(gp["h"], DRAW_BOTTOM - gp["y"]))

    node_positions = {}
    group_by_id = {g["id"]: g for g in groups}
    for n in nodes:
        nid = n["id"]
        n_col = n.get("col", 0)
        n_row = n.get("row", 0)
        offset_x = n.get("offsetX", 0)
        offset_y = n.get("offsetY", 0)

        gid = n.get("groupId")
        if gid and gid in group_positions:
            gp = group_positions[gid]
            g_def = group_by_id.get(gid, {})
            py = child_padding_y if g_def.get("parentGroupId") else padding_y
            nx = gp["x"] + padding_x + n_col * cell + offset_x
            ny = gp["y"] + py + n_row * cell + offset_y
        else:
            nx = content_x_pt + n_col * cell + offset_x
            ny = start_y_pt + n_row * cell + offset_y

        node_positions[nid] = {"x": nx, "y": ny}

    return {
        "group_positions": group_positions,
        "node_positions": node_positions,
        "icon_size": icon_size,
        "cell": cell,
        "fonts": fonts,
        "content_x_pt": content_x_pt,
        "start_y_pt": start_y_pt,
        "free_node_positions": free_node_positions,
        "padding_x": padding_x,
        "padding_y": padding_y,
        "child_padding_y": child_padding_y,
        "padding_bottom": padding_bottom,
    }


def edge_segments(from_pos, to_pos, icon_size, from_side=None, to_side=None):
    """Generate elbow edge segments for crossing detection.

    Returns list of ((x1,y1),(x2,y2)) segments.
    """
    dx = to_pos["x"] - from_pos["x"]
    dy = to_pos["y"] - from_pos["y"]

    auto_from, auto_to = auto_connection_sites(dx, dy)
    fs = CONNECTION_SITE.get(from_side, auto_from) if from_side else auto_from
    ts = CONNECTION_SITE.get(to_side, auto_to) if to_side else auto_to

    exit_points = {
        0: (from_pos["x"] + icon_size / 2, from_pos["y"]),
        1: (from_pos["x"], from_pos["y"] + icon_size / 2),
        2: (from_pos["x"] + icon_size / 2, from_pos["y"] + icon_size),
        3: (from_pos["x"] + icon_size, from_pos["y"] + icon_size / 2),
    }
    entry_points = {
        0: (to_pos["x"] + icon_size / 2, to_pos["y"]),
        1: (to_pos["x"], to_pos["y"] + icon_size / 2),
        2: (to_pos["x"] + icon_size / 2, to_pos["y"] + icon_size),
        3: (to_pos["x"] + icon_size, to_pos["y"] + icon_size / 2),
    }

    fx, fy = exit_points[fs]
    tx, ty = entry_points[ts]

    if fx == tx and fy == ty:
        return []

    if fy == ty:
        return [((fx, fy), (tx, ty))]
    if fx == tx:
        return [((fx, fy), (tx, ty))]

    mid_x = (fx + tx) / 2
    mid_y = (fy + ty) / 2

    if fs in (1, 3):
        return [
            ((fx, fy), (mid_x, fy)),
            ((mid_x, fy), (mid_x, ty)),
            ((mid_x, ty), (tx, ty)),
        ]
    else:
        return [
            ((fx, fy), (fx, mid_y)),
            ((fx, mid_y), (tx, mid_y)),
            ((tx, mid_y), (tx, ty)),
        ]


def seg_intersects_rect(seg, rect):
    """Check if a horizontal or vertical segment intersects a rectangle.

    Uses strict inequality (<, not <=) so touching edges don't count.
    Zero-length segments are ignored.
    """
    (sx, sy), (ex, ey) = seg
    rx1, ry1, rx2, ry2 = rect

    if abs(sx - ex) < 0.1 and abs(sy - ey) < 0.1:
        return False

    if abs(sy - ey) < 0.1:
        if ry1 < sy < ry2:
            min_x, max_x = min(sx, ex), max(sx, ex)
            if min_x < rx2 and max_x > rx1:
                return True
    elif abs(sx - ex) < 0.1:
        if rx1 < sx < rx2:
            min_y, max_y = min(sy, ey), max(sy, ey)
            if min_y < ry2 and max_y > ry1:
                return True
    return False

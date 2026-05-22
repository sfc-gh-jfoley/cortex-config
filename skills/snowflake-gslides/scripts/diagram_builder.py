"""Diagram builder for Google Slides.

Renders architecture/flow diagrams with icons, groups, and arrows.
Called from build_slides.py when type="diagram".
"""
from utils import resolve_icon_name, call_icon_inserter, batch, display_len, is_valid_icon
from diagram_layout import compute_layout, auto_connection_sites, CONNECTION_SITE

PT = 12700  # 1pt in EMU

GROUP_COLORS = {
    "snowflake": {"bg": "#FFFFFF", "border": "#29B5E8", "logo": "snowflake"},
    "aws":       {"bg": "#FFFFFF", "border": "#FF9900", "logo": "aws"},
    "azure":     {"bg": "#FFFFFF", "border": "#0078D4", "logo": "azure"},
    "gcp":       {"bg": "#FFFFFF", "border": "#4285F4", "logo": "gcp"},
    "default":   {"bg": "#FFFFFF", "border": "#333333"},
    "gray":      {"bg": "#FAFAFA", "border": "#999999", "label_color": "#555555"},
    "green":     {"bg": "#F6FBF6", "border": "#4CAF50"},
    "coral":     {"bg": "#FDF6F6", "border": "#D32F2F"},
    "purple":    {"bg": "#F8F5FD", "border": "#7B1FA2"},
    "teal":      {"bg": "#F4FAFA", "border": "#00897B"},
    "amber":     {"bg": "#FDFAF3", "border": "#F57F17"},
    "bronze":    {"bg": "#FDF8F3", "border": "#CD7F32"},
    "silver":    {"bg": "#FAFAFA", "border": "#78909C"},
    "gold":      {"bg": "#FFFDF5", "border": "#F9A825"},
}


EDGE_COLORS = {
    "dark_blue": "#11567F",
    "gray": "#999999",
    "accent": "#D45B90",
}

ARROW_MAP = {"arrow": "FILL_ARROW", "none": "NONE"}


def _hex_to_rgb(h):
    h = h.lstrip("#")
    return {"red": int(h[0:2], 16) / 255, "green": int(h[2:4], 16) / 255, "blue": int(h[4:6], 16) / 255}


def build_diagram(builder, sid, diagram_spec, start_y_emu, diagram_cfg, creds):
    """Build a diagram on a slide.
    
    Args:
        builder: SlideBuilder instance
        sid: slide object ID
        diagram_spec: the "diagram" dict from spec.json
        start_y_emu: Y position in EMU where diagram starts (below body if any)
        diagram_cfg: config.diagram section
        creds: google auth credentials for Apps Script calls
    """
    layout = compute_layout(diagram_spec, diagram_cfg, start_y_emu)
    group_positions = layout["group_positions"]
    node_positions_layout = layout["node_positions"]
    icon_size = layout["icon_size"]
    cell = layout["cell"]
    fonts = layout["fonts"]

    apps_script_url = diagram_cfg.get("apps_script_url", "")
    logo_size = 16

    groups = diagram_spec.get("groups", [])
    nodes = diagram_spec.get("nodes", [])
    edges = diagram_spec.get("edges", [])
    groups = [g for g in groups if g.get("id")]
    nodes = [n for n in nodes if n.get("id")]

    def _group_depth(g):
        return 0 if not g.get("parentGroupId") else 1
    sorted_groups = sorted(groups, key=_group_depth)

    # --- Draw groups (parent-first for z-order) ---
    reqs = []
    has_nested = any(g.get("parentGroupId") for g in groups)
    for g in sorted_groups:
        gid = g["id"]
        gp = group_positions[gid]
        color_name = g.get("color", "default")
        gc = GROUP_COLORS.get(color_name, GROUP_COLORS["default"])
        box_id = f"{sid}_g_{gid}"
        is_child = bool(g.get("parentGroupId"))
        use_bg = has_nested and not is_child

        reqs.append({"createShape": {"objectId": box_id, "shapeType": "RECTANGLE", "elementProperties": {
            "pageObjectId": sid,
            "size": {"width": {"magnitude": int(gp["w"] * PT), "unit": "EMU"}, "height": {"magnitude": int(gp["h"] * PT), "unit": "EMU"}},
            "transform": {"scaleX": 1, "scaleY": 1, "translateX": int(gp["x"] * PT), "translateY": int(gp["y"] * PT), "unit": "EMU"},
        }}})
        if use_bg:
            reqs.append({"updateShapeProperties": {"objectId": box_id, "shapeProperties": {
                "shapeBackgroundFill": {"solidFill": {"color": {"rgbColor": _hex_to_rgb(gc["bg"])}}},
                "outline": {"outlineFill": {"solidFill": {"color": {"rgbColor": _hex_to_rgb(gc["border"])}}}, "weight": {"magnitude": 1, "unit": "PT"}},
            }, "fields": "shapeBackgroundFill.solidFill.color,outline.outlineFill.solidFill.color,outline.weight"}})
        elif is_child:
            reqs.append({"updateShapeProperties": {"objectId": box_id, "shapeProperties": {
                "shapeBackgroundFill": {"solidFill": {"color": {"rgbColor": _hex_to_rgb("#FFFFFF")}}},
                "outline": {"outlineFill": {"solidFill": {"color": {"rgbColor": _hex_to_rgb(gc["border"])}}}, "weight": {"magnitude": 1, "unit": "PT"}},
            }, "fields": "shapeBackgroundFill.solidFill.color,outline.outlineFill.solidFill.color,outline.weight"}})
        else:
            reqs.append({"updateShapeProperties": {"objectId": box_id, "shapeProperties": {
                "shapeBackgroundFill": {"solidFill": {"color": {"rgbColor": _hex_to_rgb("#FFFFFF")}, "alpha": 0}},
                "outline": {"outlineFill": {"solidFill": {"color": {"rgbColor": _hex_to_rgb(gc["border"])}}}, "weight": {"magnitude": 1, "unit": "PT"}},
            }, "fields": "shapeBackgroundFill,outline.outlineFill.solidFill.color,outline.weight"}})

        # Semantic groups: text label
        if "logo" not in gc and g.get("label"):
            lbl_id = f"{sid}_gl_{gid}"
            reqs.append({"createShape": {"objectId": lbl_id, "shapeType": "TEXT_BOX", "elementProperties": {
                "pageObjectId": sid,
                "size": {"width": {"magnitude": int(100 * PT), "unit": "EMU"}, "height": {"magnitude": int(16 * PT), "unit": "EMU"}},
                "transform": {"scaleX": 1, "scaleY": 1, "translateX": int((gp["x"] + 3) * PT), "translateY": int((gp["y"] + 2) * PT), "unit": "EMU"},
            }}})
            reqs.append({"insertText": {"objectId": lbl_id, "text": g["label"]}})
            reqs.append({"updateTextStyle": {"objectId": lbl_id, "style": {
                "fontFamily": "Arial", "fontSize": {"magnitude": fonts["group_label"], "unit": "PT"}, "bold": True,
                "foregroundColor": {"opaqueColor": {"rgbColor": _hex_to_rgb(gc.get("label_color", gc["border"]))}},
            }, "textRange": {"type": "ALL"}, "fields": "fontFamily,fontSize,bold,foregroundColor"}})
            reqs.append({"updateShapeProperties": {"objectId": lbl_id, "shapeProperties": {"contentAlignment": "MIDDLE"}, "fields": "contentAlignment"}})

    if reqs:
        batch(builder.svc, builder.pid, reqs)

    # --- Insert brand logos via Apps Script ---
    logo_items = []
    for g in groups:
        gc = GROUP_COLORS.get(g.get("color", "default"), {})
        if "logo" in gc:
            gp = group_positions[g["id"]]
            logo_items.append({
                "iconName": gc["logo"],
                "x": gp["x"] + 8,
                "y": gp["y"] + 4,
                "width": logo_size,
                "height": logo_size,
            })

    if logo_items and apps_script_url and creds:
        call_icon_inserter(creds, apps_script_url, builder.pid, sid, logo_items)

    # --- Node positions from layout (add col/row for compatibility) ---
    node_positions = {}
    for n in nodes:
        nid = n["id"]
        if nid in node_positions_layout:
            pos = node_positions_layout[nid]
            node_positions[nid] = {"x": pos["x"], "y": pos["y"], "col": n.get("col", 0), "row": n.get("row", 0)}

    # --- Insert icon nodes via Apps Script ---
    for n in nodes:
        if n.get("shape") in ("box", "rect") and not n.get("icon"):
            label_text = n.get("label", "")
            resolved = resolve_icon_name(label_text)
            n["icon"] = resolved if is_valid_icon(label_text) else "cube"
            n.pop("shape", None)

    icon_nodes = [n for n in nodes if n.get("shape", "icon") == "icon"]
    icon_items = []
    for n in icon_nodes:
        nid = n["id"]
        pos = node_positions[nid]
        resolved_name = resolve_icon_name(n.get("icon", ""))
        icon_items.append({
            "iconName": resolved_name,
            "x": pos["x"],
            "y": pos["y"],
            "width": icon_size,
            "height": icon_size,
        })

    icon_results = []
    if icon_items and apps_script_url and creds:
        icon_results = call_icon_inserter(creds, apps_script_url, builder.pid, sid, icon_items)

    if icon_items and not icon_results:
        icon_results = [{"iconName": item.get("iconName", ""), "error": "no_service"} for item in icon_items]

    # Map icon names to objectIds for connector attachment
    icon_object_ids = {}
    for i, n in enumerate(icon_nodes):
        if i < len(icon_results) and "objectId" in icon_results[i]:
            icon_object_ids[n["id"]] = icon_results[i]["objectId"]

    # --- Draw placeholder for failed icons ---
    reqs_ph = []
    for i, n in enumerate(icon_nodes):
        if i < len(icon_results) and "error" in icon_results[i]:
            nid = n["id"]
            pos = node_positions[nid]
            ph_id = f"{sid}_ph_{nid}"
            reqs_ph.append({"createShape": {"objectId": ph_id, "shapeType": "RECTANGLE", "elementProperties": {
                "pageObjectId": sid,
                "size": {"width": {"magnitude": int(icon_size * PT), "unit": "EMU"}, "height": {"magnitude": int(icon_size * PT), "unit": "EMU"}},
                "transform": {"scaleX": 1, "scaleY": 1, "translateX": int(pos["x"] * PT), "translateY": int(pos["y"] * PT), "unit": "EMU"},
            }}})
            reqs_ph.append({"updateShapeProperties": {"objectId": ph_id, "shapeProperties": {
                "shapeBackgroundFill": {"solidFill": {"color": {"rgbColor": _hex_to_rgb("#F0F0F0")}}},
                "outline": {"outlineFill": {"solidFill": {"color": {"rgbColor": _hex_to_rgb("#CCCCCC")}}}, "weight": {"magnitude": 1, "unit": "PT"}},
            }, "fields": "shapeBackgroundFill.solidFill.color,outline.outlineFill.solidFill.color,outline.weight"}})
            reqs_ph.append({"insertText": {"objectId": ph_id, "text": n.get("icon", "?")}})
            reqs_ph.append({"updateTextStyle": {"objectId": ph_id, "style": {
                "fontFamily": "Arial", "fontSize": {"magnitude": 6, "unit": "PT"},
                "foregroundColor": {"opaqueColor": {"rgbColor": _hex_to_rgb("#999999")}},
            }, "textRange": {"type": "ALL"}, "fields": "fontFamily,fontSize,foregroundColor"}})
            icon_object_ids[nid] = ph_id

    if reqs_ph:
        batch(builder.svc, builder.pid, reqs_ph)

    # --- Draw node labels ---
    label_object_ids = {}  # node_id -> label textbox objectId
    reqs_lbl = []
    for n in nodes:
        label = n.get("label", "")
        if not label:
            continue
        nid = n["id"]
        pos = node_positions[nid]
        label_w = cell
        label_x = pos["x"] + icon_size / 2 - label_w / 2
        label_y = pos["y"] + icon_size + 2
        label_h = fonts["label"] * 2 + 5
        lbl_id = f"{sid}_nl_{nid}"
        label_object_ids[nid] = lbl_id

        reqs_lbl.append({"createShape": {"objectId": lbl_id, "shapeType": "TEXT_BOX", "elementProperties": {
            "pageObjectId": sid,
            "size": {"width": {"magnitude": int(label_w * PT), "unit": "EMU"}, "height": {"magnitude": int(label_h * PT), "unit": "EMU"}},
            "transform": {"scaleX": 1, "scaleY": 1, "translateX": int(label_x * PT), "translateY": int(label_y * PT), "unit": "EMU"},
        }}})
        reqs_lbl.append({"insertText": {"objectId": lbl_id, "text": label}})
        reqs_lbl.append({"updateTextStyle": {"objectId": lbl_id, "style": {
            "fontFamily": "Arial", "fontSize": {"magnitude": fonts["label"], "unit": "PT"},
        }, "textRange": {"type": "ALL"}, "fields": "fontFamily,fontSize"}})
        reqs_lbl.append({"updateParagraphStyle": {"objectId": lbl_id, "style": {"alignment": "CENTER"}, "textRange": {"type": "ALL"}, "fields": "alignment"}})
        reqs_lbl.append({"updateShapeProperties": {"objectId": lbl_id, "shapeProperties": {"contentAlignment": "MIDDLE"}, "fields": "contentAlignment"}})

    if reqs_lbl:
        batch(builder.svc, builder.pid, reqs_lbl)

    # --- Draw edges ---
    reqs_edge = []
    for ei, e in enumerate(edges):
        from_id = e.get("from", "")
        to_id = e.get("to", "")
        if from_id not in node_positions or to_id not in node_positions:
            continue

        from_pos = node_positions[from_id]
        to_pos = node_positions[to_id]
        default_color = diagram_cfg.get("default_edge_color", "dark_blue")
        default_arrow = diagram_cfg.get("default_edge_arrow", "arrow")
        edge_color = EDGE_COLORS.get(e.get("color", default_color), EDGE_COLORS["dark_blue"])
        line_cat = "BENT" if e.get("line", "elbow") == "elbow" else "STRAIGHT"
        if e.get("line") == "curved":
            line_cat = "CURVED"
        end_arrow = ARROW_MAP.get(e.get("endArrow", default_arrow), "FILL_ARROW")
        start_arrow = ARROW_MAP.get(e.get("startArrow", "none"), "NONE")
        dashed = e.get("dashed", False)

        edge_id = f"{sid}_e_{ei}"
        reqs_edge.append({"createLine": {"objectId": edge_id, "lineCategory": line_cat, "elementProperties": {
            "pageObjectId": sid,
            "size": {"width": {"magnitude": int(abs(to_pos["x"] - from_pos["x"]) * PT) or 1, "unit": "EMU"},
                     "height": {"magnitude": int(abs(to_pos["y"] - from_pos["y"]) * PT) or 1, "unit": "EMU"}},
            "transform": {"scaleX": 1, "scaleY": 1,
                          "translateX": int(min(from_pos["x"], to_pos["x"]) * PT),
                          "translateY": int(min(from_pos["y"], to_pos["y"]) * PT), "unit": "EMU"},
        }}})

        # Connect to objects if available
        from_obj = icon_object_ids.get(from_id)
        to_obj = icon_object_ids.get(to_id)
        if from_obj and to_obj:
            auto_from, auto_to = auto_connection_sites(
                to_pos["x"] - from_pos["x"], to_pos["y"] - from_pos["y"]
            )
            from_site = CONNECTION_SITE.get(e.get("fromSide"), auto_from) if "fromSide" in e else auto_from
            to_site = CONNECTION_SITE.get(e.get("toSide"), auto_to) if "toSide" in e else auto_to
            actual_from_obj = from_obj
            actual_to_obj = to_obj
            if from_site == 2 and from_id in label_object_ids:
                actual_from_obj = label_object_ids[from_id]
            if to_site == 2 and to_id in label_object_ids:
                actual_to_obj = label_object_ids[to_id]
            reqs_edge.append({"updateLineProperties": {"objectId": edge_id, "lineProperties": {
                "startConnection": {"connectedObjectId": actual_from_obj, "connectionSiteIndex": from_site},
                "endConnection": {"connectedObjectId": actual_to_obj, "connectionSiteIndex": to_site},
            }, "fields": "startConnection,endConnection"}})

        line_props = {
            "endArrow": end_arrow,
            "startArrow": start_arrow,
            "lineFill": {"solidFill": {"color": {"rgbColor": _hex_to_rgb(edge_color)}}},
        }
        fields = "endArrow,startArrow,lineFill.solidFill.color"
        if dashed:
            line_props["dashStyle"] = "DASH"
            fields += ",dashStyle"
        reqs_edge.append({"updateLineProperties": {"objectId": edge_id, "lineProperties": line_props, "fields": fields}})

    if reqs_edge:
        batch(builder.svc, builder.pid, reqs_edge)

    # --- Draw edge labels ---
    from collections import Counter
    from_counts = Counter(e.get("from", "") for e in edges if e.get("label"))
    to_counts = Counter(e.get("to", "") for e in edges if e.get("label"))

    reqs_el = []
    for ei, e in enumerate(edges):
        label = e.get("label", "")
        if not label:
            continue
        from_id = e.get("from", "")
        to_id = e.get("to", "")
        if from_id not in node_positions or to_id not in node_positions:
            continue

        from_pos = node_positions[from_id]
        to_pos = node_positions[to_id]
        edge_color = EDGE_COLORS.get(e.get("color", "dark_blue"), EDGE_COLORS["dark_blue"])

        mid_x = (from_pos["x"] + to_pos["x"]) / 2 + icon_size / 2
        mid_y = (from_pos["y"] + to_pos["y"]) / 2 + icon_size / 2

        dc = to_pos["x"] - from_pos["x"]
        dr = to_pos["y"] - from_pos["y"]
        line_type = e.get("line", "elbow")
        is_fan_out = from_counts.get(from_id, 0) > 1
        is_fan_in = to_counts.get(to_id, 0) > 1
        if line_type == "elbow" and dr != 0 and (is_fan_out or is_fan_in):
            if is_fan_out:
                if abs(dc) >= abs(dr):
                    mid_x = to_pos["x"] - dc / 4 + icon_size / 2
                    mid_y = to_pos["y"] + icon_size / 2
                else:
                    mid_x = to_pos["x"] + icon_size / 2
                    mid_y = to_pos["y"] - dr / 4 + icon_size / 2
            elif is_fan_in:
                if abs(dc) >= abs(dr):
                    mid_x = from_pos["x"] + dc / 4 + icon_size / 2
                    mid_y = from_pos["y"] + icon_size / 2
                else:
                    mid_x = from_pos["x"] + icon_size / 2
                    mid_y = from_pos["y"] + dr / 4 + icon_size / 2
            else:
                if abs(dc) >= abs(dr):
                    mid_x = from_pos["x"] + dc / 4 + icon_size / 2
                    mid_y = from_pos["y"] + icon_size / 2
                else:
                    mid_x = from_pos["x"] + icon_size / 2
                    mid_y = from_pos["y"] + dr / 4 + icon_size / 2
        label_w = display_len(label) * 7 + 10
        edge_label_offset = fonts["edge_label"] + 8
        if abs(dc) >= abs(dr):
            lx = mid_x - label_w / 2
            ly = mid_y - edge_label_offset
        else:
            lx = mid_x + edge_label_offset / 2
            ly = mid_y - edge_label_offset / 2

        el_id = f"{sid}_el_{ei}"
        reqs_el.append({"createShape": {"objectId": el_id, "shapeType": "TEXT_BOX", "elementProperties": {
            "pageObjectId": sid,
            "size": {"width": {"magnitude": int(label_w * PT), "unit": "EMU"}, "height": {"magnitude": int(14 * PT), "unit": "EMU"}},
            "transform": {"scaleX": 1, "scaleY": 1, "translateX": int(lx * PT), "translateY": int(ly * PT), "unit": "EMU"},
        }}})
        reqs_el.append({"insertText": {"objectId": el_id, "text": label}})
        reqs_el.append({"updateTextStyle": {"objectId": el_id, "style": {
            "fontFamily": "Arial", "fontSize": {"magnitude": fonts["edge_label"], "unit": "PT"},
            "foregroundColor": {"opaqueColor": {"rgbColor": _hex_to_rgb("#333333")}},
        }, "textRange": {"type": "ALL"}, "fields": "fontFamily,fontSize,foregroundColor"}})
        reqs_el.append({"updateParagraphStyle": {"objectId": el_id, "style": {"alignment": "CENTER"}, "textRange": {"type": "ALL"}, "fields": "alignment"}})
        reqs_el.append({"updateShapeProperties": {"objectId": el_id, "shapeProperties": {"contentAlignment": "MIDDLE"}, "fields": "contentAlignment"}})

    if reqs_el:
        batch(builder.svc, builder.pid, reqs_el)

    print(f"  Diagram: {len(groups)} groups, {len(nodes)} nodes, {len(edges)} edges")

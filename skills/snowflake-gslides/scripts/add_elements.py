#!/usr/bin/env python3
"""Add elements (icons, groups, edges) to an existing slide.

Usage:
    python add_elements.py <presentation_id> --input add.json [--output result.json]

add.json schema:
{
  "slideId": "sl_p04_diag",
  "elements": [
    {"type": "icon", "iconName": "api_gateway", "label": "API", "position": {"near": "s3", "direction": "right"}},
    {"type": "icon", "iconName": "lambda", "label": "Lambda", "position": {"x": 300, "y": 200}},
    {"type": "group", "label": "AWS", "color": "aws", "position": {"x": 50, "y": 100, "w": 200, "h": 150}},
    {"type": "edge", "from": "api_gateway", "to": "raw", "label": "load", "line": "elbow", "color": "dark_blue"}
  ]
}
"""
import argparse, json
from pathlib import Path
import google.auth, google.auth.transport.requests
from googleapiclient.discovery import build
from read_slide_elements import read_elements, _norm, DIAGRAM_GRID
from utils import call_icon_inserter, display_len, resolve_icon_name, is_valid_icon

PT = 12700

GROUP_COLORS = {
    "snowflake": {"bg": "#FFFFFF", "border": "#29B5E8"},
    "aws": {"bg": "#FFFFFF", "border": "#FF9900"},
    "azure": {"bg": "#FFFFFF", "border": "#0078D4"},
    "gcp": {"bg": "#FFFFFF", "border": "#4285F4"},
    "default": {"bg": "#FFFFFF", "border": "#333333"},
    "gray": {"bg": "#FAFAFA", "border": "#999999"},
    "green": {"bg": "#F6FBF6", "border": "#4CAF50"},
    "coral": {"bg": "#FDF6F6", "border": "#D32F2F"},
    "purple": {"bg": "#F8F5FD", "border": "#7B1FA2"},
    "teal": {"bg": "#F4FAFA", "border": "#00897B"},
    "amber": {"bg": "#FDFAF3", "border": "#F57F17"},
    "bronze": {"bg": "#FDF8F3", "border": "#CD7F32"},
    "silver": {"bg": "#FAFAFA", "border": "#78909C"},
    "gold": {"bg": "#FFFDF5", "border": "#F9A825"},
}

EDGE_COLORS = {"dark_blue": "#11567F", "gray": "#999999", "accent": "#D45B90"}


def _hex_to_rgb(h):
    h = h.lstrip("#")
    return {"red": int(h[0:2], 16) / 255, "green": int(h[2:4], 16) / 255, "blue": int(h[4:6], 16) / 255}


def _find_icon(icons, name):
    name_n = _norm(name)
    for ic in icons:
        if _norm(ic.get("description", "")) == name_n:
            return ic
    for ic in icons:
        if _norm(ic.get("name", "")) == name_n:
            return ic
    for ic in icons:
        if _norm(ic.get("label", "")) == name_n:
            return ic
    return None


def _resolve_position(pos, icons, icon_size, grid_info):
    if "x" in pos and "y" in pos:
        return pos["x"], pos["y"]

    if "near" in pos:
        ref = _find_icon(icons, pos["near"])
        if not ref:
            return None, None
        direction = pos.get("direction", "right")
        cell = grid_info["cell"] if grid_info else icon_size + 30
        if direction == "right":
            return ref["x"] + cell, ref["y"]
        elif direction == "left":
            return ref["x"] - cell, ref["y"]
        elif direction == "below":
            return ref["x"], ref["y"] + cell
        elif direction == "above":
            return ref["x"], ref["y"] - cell
        else:
            return ref["x"] + cell, ref["y"]

    if grid_info and icons:
        cell = grid_info["cell"]
        origin_x = grid_info["originX"]
        origin_y = grid_info["originY"]
        occupied = set()
        for ic in icons:
            col = round((ic["x"] - origin_x) / cell)
            row = round((ic["y"] - origin_y) / cell)
            occupied.add((col, row))
        max_col = max(c for c, r in occupied) if occupied else 0
        max_row = max(r for c, r in occupied) if occupied else 0
        for row in range(max_row + 2):
            for col in range(max_col + 2):
                if (col, row) not in occupied:
                    return origin_x + col * cell, origin_y + row * cell
    return 100, 100


def add_elements(presentation_id, input_data):
    slide_ref = input_data["slideId"]
    elements = input_data.get("elements", [])

    slide_info = read_elements(presentation_id, slide_ref)
    if "error" in slide_info:
        return {"error": slide_info["error"]}

    slide_id = slide_info["slideId"]
    icons = slide_info.get("icons", [])
    icon_size = slide_info.get("iconSize") or 40
    grid_info = slide_info.get("grid")
    cell = DIAGRAM_GRID.get(icon_size, DIAGRAM_GRID[40])["cell"]

    creds, _ = google.auth.default(scopes=[
        "https://www.googleapis.com/auth/presentations",
        "https://www.googleapis.com/auth/drive",
    ])
    creds.refresh(google.auth.transport.requests.Request())
    svc = build("slides", "v1", credentials=creds)

    results = []
    added_icons = []

    for elem in elements:
        etype = elem.get("type", "")

        if etype == "icon":
            icon_name = resolve_icon_name(elem.get("iconName", ""))
            if not is_valid_icon(icon_name):
                results.append({"type": "icon", "iconName": icon_name, "error": f"Icon '{elem.get('iconName', '')}' (resolved: '{icon_name}') not found in icons_list. Check icon name or aliases."})
                continue
            label = elem.get("label", "")
            pos = elem.get("position", {})
            x, y = _resolve_position(pos, icons + added_icons, icon_size, grid_info)
            if x is None:
                results.append({"type": "icon", "iconName": icon_name, "error": f"Cannot resolve position (near '{pos.get('near')}' not found)"})
                continue


            icon_results = call_icon_inserter(creds, _get_apps_script_url(), presentation_id, slide_id, [
                {"iconName": icon_name, "x": x, "y": y, "width": icon_size, "height": icon_size}
            ])
            if icon_results and "objectId" in icon_results[0]:
                obj_id = icon_results[0]["objectId"]
                added_icons.append({"name": icon_name, "objectId": obj_id, "x": x, "y": y, "w": icon_size, "h": icon_size, "label": label, "description": icon_name})

                if label:
                    label_w = cell
                    label_x = x + icon_size / 2 - label_w / 2
                    label_y = y + icon_size + 2
                    label_h = 13
                    lbl_id = f"add_lbl_{len(results)}"
                    reqs = [
                        {"createShape": {"objectId": lbl_id, "shapeType": "TEXT_BOX", "elementProperties": {
                            "pageObjectId": slide_id,
                            "size": {"width": {"magnitude": int(label_w * PT), "unit": "EMU"}, "height": {"magnitude": int(label_h * PT), "unit": "EMU"}},
                            "transform": {"scaleX": 1, "scaleY": 1, "translateX": int(label_x * PT), "translateY": int(label_y * PT), "unit": "EMU"},
                        }}},
                        {"insertText": {"objectId": lbl_id, "text": label}},
                        {"updateTextStyle": {"objectId": lbl_id, "style": {
                            "fontFamily": "Arial", "fontSize": {"magnitude": {20: 6, 30: 7, 40: 8}.get(icon_size, 8), "unit": "PT"},
                        }, "textRange": {"type": "ALL"}, "fields": "fontFamily,fontSize"}},
                        {"updateParagraphStyle": {"objectId": lbl_id, "style": {"alignment": "CENTER"}, "textRange": {"type": "ALL"}, "fields": "alignment"}},
                        {"updateShapeProperties": {"objectId": lbl_id, "shapeProperties": {"contentAlignment": "MIDDLE"}, "fields": "contentAlignment"}},
                    ]
                    svc.presentations().batchUpdate(presentationId=presentation_id, body={"requests": reqs}).execute()

                results.append({"type": "icon", "iconName": icon_name, "objectId": obj_id, "x": x, "y": y})
            else:
                error = icon_results[0].get("error", "unknown") if icon_results else "no response"
                results.append({"type": "icon", "iconName": icon_name, "error": error})

        elif etype == "group":
            label = elem.get("label", "")
            color_name = elem.get("color", "default")
            pos = elem.get("position", {})
            x = pos.get("x", 50)
            y = pos.get("y", 100)
            w = pos.get("w", 200)
            h = pos.get("h", 150)
            gc = GROUP_COLORS.get(color_name, GROUP_COLORS["default"])

            box_id = f"add_grp_{len(results)}"
            reqs = [
                {"createShape": {"objectId": box_id, "shapeType": "RECTANGLE", "elementProperties": {
                    "pageObjectId": slide_id,
                    "size": {"width": {"magnitude": int(w * PT), "unit": "EMU"}, "height": {"magnitude": int(h * PT), "unit": "EMU"}},
                    "transform": {"scaleX": 1, "scaleY": 1, "translateX": int(x * PT), "translateY": int(y * PT), "unit": "EMU"},
                }}},
                {"updateShapeProperties": {"objectId": box_id, "shapeProperties": {
                    "shapeBackgroundFill": {"solidFill": {"color": {"rgbColor": _hex_to_rgb(gc["bg"])}, "alpha": 0}},
                    "outline": {"outlineFill": {"solidFill": {"color": {"rgbColor": _hex_to_rgb(gc["border"])}}}, "weight": {"magnitude": 1, "unit": "PT"}},
                }, "fields": "shapeBackgroundFill,outline.outlineFill.solidFill.color,outline.weight"}},
                {"updatePageElementZOrder": {"pageElementObjectId": box_id, "operation": "SEND_TO_BACK"}},
            ]

            if label:
                lbl_id = f"add_grplbl_{len(results)}"
                reqs.append({"createShape": {"objectId": lbl_id, "shapeType": "TEXT_BOX", "elementProperties": {
                    "pageObjectId": slide_id,
                    "size": {"width": {"magnitude": int(100 * PT), "unit": "EMU"}, "height": {"magnitude": int(16 * PT), "unit": "EMU"}},
                    "transform": {"scaleX": 1, "scaleY": 1, "translateX": int((x + 3) * PT), "translateY": int((y + 2) * PT), "unit": "EMU"},
                }}})
                reqs.append({"insertText": {"objectId": lbl_id, "text": label}})
                reqs.append({"updateTextStyle": {"objectId": lbl_id, "style": {
                    "fontFamily": "Arial", "fontSize": {"magnitude": {20: 7, 30: 8, 40: 9}.get(icon_size, 8), "unit": "PT"}, "bold": True,
                    "foregroundColor": {"opaqueColor": {"rgbColor": _hex_to_rgb(gc["border"])}},
                }, "textRange": {"type": "ALL"}, "fields": "fontFamily,fontSize,bold,foregroundColor"}})

            svc.presentations().batchUpdate(presentationId=presentation_id, body={"requests": reqs}).execute()
            results.append({"type": "group", "label": label, "objectId": box_id, "x": x, "y": y, "w": w, "h": h})

        elif etype == "edge":
            from_name = elem.get("from", "")
            to_name = elem.get("to", "")
            all_icons = icons + added_icons
            from_icon = _find_icon(all_icons, from_name)
            to_icon = _find_icon(all_icons, to_name)

            if not from_icon:
                results.append({"type": "edge", "error": f"from node '{from_name}' not found on slide"})
                continue
            if not to_icon:
                results.append({"type": "edge", "error": f"to node '{to_name}' not found on slide"})
                continue

            from_obj = from_icon["objectId"]
            to_obj = to_icon["objectId"]
            dx = to_icon["x"] - from_icon["x"]
            dy = to_icon["y"] - from_icon["y"]

            if abs(dx) >= abs(dy):
                from_site = 3 if dx > 0 else 1
                to_site = 1 if dx > 0 else 3
            else:
                from_site = 2 if dy > 0 else 0
                to_site = 0 if dy > 0 else 2

            line_cat = "BENT" if elem.get("line", "elbow") == "elbow" else "STRAIGHT"
            edge_color = EDGE_COLORS.get(elem.get("color", "dark_blue"), EDGE_COLORS["dark_blue"])

            edge_id = f"add_edge_{len(results)}"
            reqs = [
                {"createLine": {"objectId": edge_id, "lineCategory": line_cat, "elementProperties": {
                    "pageObjectId": slide_id,
                    "size": {"width": {"magnitude": max(1, int(abs(dx) * PT)), "unit": "EMU"},
                             "height": {"magnitude": max(1, int(abs(dy) * PT)), "unit": "EMU"}},
                    "transform": {"scaleX": 1, "scaleY": 1,
                                  "translateX": int(min(from_icon["x"], to_icon["x"]) * PT),
                                  "translateY": int(min(from_icon["y"], to_icon["y"]) * PT), "unit": "EMU"},
                }}},
                {"updateLineProperties": {"objectId": edge_id, "lineProperties": {
                    "startConnection": {"connectedObjectId": from_obj, "connectionSiteIndex": from_site},
                    "endConnection": {"connectedObjectId": to_obj, "connectionSiteIndex": to_site},
                }, "fields": "startConnection,endConnection"}},
                {"updateLineProperties": {"objectId": edge_id, "lineProperties": {
                    "endArrow": "FILL_ARROW",
                    "lineFill": {"solidFill": {"color": {"rgbColor": _hex_to_rgb(edge_color)}}},
                }, "fields": "endArrow,lineFill.solidFill.color"}},
            ]
            svc.presentations().batchUpdate(presentationId=presentation_id, body={"requests": reqs}).execute()

            edge_label = elem.get("label", "")
            if edge_label:
                mid_x = (from_icon["x"] + to_icon["x"]) / 2 + icon_size / 2
                mid_y = (from_icon["y"] + to_icon["y"]) / 2 + icon_size / 2
                lw = display_len(edge_label) * 7 + 10
                el_id = f"add_elbl_{len(results)}"
                lbl_reqs = [
                    {"createShape": {"objectId": el_id, "shapeType": "TEXT_BOX", "elementProperties": {
                        "pageObjectId": slide_id,
                        "size": {"width": {"magnitude": int(lw * PT), "unit": "EMU"}, "height": {"magnitude": int(14 * PT), "unit": "EMU"}},
                        "transform": {"scaleX": 1, "scaleY": 1, "translateX": int((mid_x - lw / 2) * PT), "translateY": int((mid_y - ({20: 5, 30: 6, 40: 7}.get(icon_size, 6) + 8)) * PT), "unit": "EMU"},
                    }}},
                    {"insertText": {"objectId": el_id, "text": edge_label}},
                    {"updateTextStyle": {"objectId": el_id, "style": {
                        "fontFamily": "Arial", "fontSize": {"magnitude": {20: 5, 30: 6, 40: 7}.get(icon_size, 6), "unit": "PT"},
                        "foregroundColor": {"opaqueColor": {"rgbColor": _hex_to_rgb("#333333")}},
                    }, "textRange": {"type": "ALL"}, "fields": "fontFamily,fontSize,foregroundColor"}},
                    {"updateParagraphStyle": {"objectId": el_id, "style": {"alignment": "CENTER"}, "textRange": {"type": "ALL"}, "fields": "alignment"}},
                ]
                svc.presentations().batchUpdate(presentationId=presentation_id, body={"requests": lbl_reqs}).execute()

            results.append({"type": "edge", "from": from_name, "to": to_name, "objectId": edge_id})

    return {"slideId": slide_id, "added": len(results), "results": results}


def _get_apps_script_url():
    config_path = Path(__file__).parent.parent / "config" / "snowflake-gslides-config.yaml"
    if config_path.exists():
        import re
        text = config_path.read_text()
        m = re.search(r'apps_script_url:\s*"([^"]+)"', text)
        if m:
            return m.group(1)
    return ""


def main():
    parser = argparse.ArgumentParser(description="Add elements to a slide")
    parser.add_argument("presentation_id")
    parser.add_argument("--input", required=True, help="Input JSON file with elements to add")
    parser.add_argument("--output", help="Output JSON result file")
    args = parser.parse_args()

    with open(args.input, "r", encoding="utf-8") as f:
        input_data = json.load(f)

    result = add_elements(args.presentation_id, input_data)

    output = json.dumps(result, indent=2, ensure_ascii=False)
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"Result written to {args.output}")
    else:
        print(output)

    added = result.get("added", 0)
    errors = sum(1 for r in result.get("results", []) if "error" in r)
    print(f"  Added: {added - errors}, Errors: {errors}")
    if errors:
        for r in result.get("results", []):
            if "error" in r:
                print(f"    - {r['type']}: {r['error']}")


if __name__ == "__main__":
    main()

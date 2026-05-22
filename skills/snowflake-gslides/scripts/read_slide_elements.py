#!/usr/bin/env python3
"""Read existing slide elements (icons, groups, edges) and output as JSON.

Usage:
    python read_slide_elements.py <presentation_id> --slide <slide_id_or_number>
    python read_slide_elements.py <presentation_id> --slide 4
    python read_slide_elements.py <presentation_id> --slide sl_p04_diag
"""
import argparse, json
from pathlib import Path
import google.auth, google.auth.transport.requests
from googleapiclient.discovery import build

PT = 12700

DIAGRAM_GRID = {
    40: {"size": 40, "gap": 50, "cell": 90},
    30: {"size": 30, "gap": 40, "cell": 70},
    20: {"size": 20, "gap": 30, "cell": 50},
}


def _norm(s):
    return s.lower().replace("-", "_").replace(" ", "_").replace("\n", "_")


def get_services():
    creds, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/presentations.readonly"]
    )
    creds.refresh(google.auth.transport.requests.Request())
    svc = build("slides", "v1", credentials=creds)
    return svc, creds


def read_elements(presentation_id, slide_ref):
    svc, _ = get_services()
    pres = svc.presentations().get(presentationId=presentation_id).execute()

    slide = None
    for i, s in enumerate(pres.get("slides", [])):
        if slide_ref == s["objectId"] or slide_ref == str(i + 1):
            slide = s
            break
    if not slide:
        for i, s in enumerate(pres.get("slides", [])):
            if slide_ref.isdigit() and int(slide_ref) == i + 1:
                slide = s
                break

    if not slide:
        return {"error": f"Slide '{slide_ref}' not found"}

    elements = slide.get("pageElements", [])

    images = []
    shapes = []
    lines = []
    text_boxes = []

    for el in elements:
        obj_id = el["objectId"]
        transform = el.get("transform", {})
        size = el.get("size", {})
        x = transform.get("translateX", 0) / PT
        y = transform.get("translateY", 0) / PT
        w = size.get("width", {}).get("magnitude", 0) / PT * transform.get("scaleX", 1)
        h = size.get("height", {}).get("magnitude", 0) / PT * transform.get("scaleY", 1)

        if "image" in el:
            desc = el.get("description", "")
            images.append({"objectId": obj_id, "description": desc, "x": round(x, 1), "y": round(y, 1), "w": round(w, 1), "h": round(h, 1)})
        elif "shape" in el:
            shape = el["shape"]
            shape_type = shape.get("shapeType", "")
            text_content = ""
            for te in shape.get("text", {}).get("textElements", []):
                if "textRun" in te:
                    text_content += te["textRun"]["content"]
            text_content = text_content.strip()

            if shape_type == "RECTANGLE":
                outline = shape.get("shapeProperties", {}).get("outline", {})
                border_color = outline.get("outlineFill", {}).get("solidFill", {}).get("color", {}).get("rgbColor", {})
                shapes.append({"objectId": obj_id, "type": "rectangle", "x": round(x, 1), "y": round(y, 1), "w": round(w, 1), "h": round(h, 1), "text": text_content, "borderColor": border_color})
            elif shape_type == "TEXT_BOX":
                text_boxes.append({"objectId": obj_id, "text": text_content, "x": round(x, 1), "y": round(y, 1), "w": round(w, 1), "h": round(h, 1)})
        elif "line" in el:
            line = el["line"]
            line_type = line.get("lineCategory", "")
            start_conn = line.get("lineProperties", {}).get("startConnection", {})
            end_conn = line.get("lineProperties", {}).get("endConnection", {})
            lines.append({
                "objectId": obj_id,
                "lineCategory": line_type,
                "startConnection": start_conn.get("connectedObjectId", ""),
                "endConnection": end_conn.get("connectedObjectId", ""),
                "x": round(x, 1), "y": round(y, 1), "w": round(w, 1), "h": round(h, 1),
            })

    icon_size = None
    if images:
        widths = [img["w"] for img in images]
        common_w = max(set(widths), key=widths.count)
        for sz in DIAGRAM_GRID:
            if abs(common_w - sz) < 3:
                icon_size = sz
                break
        if not icon_size:
            icon_size = round(common_w)

    icons = []
    for img in images:
        label = ""
        for tb in text_boxes:
            if abs(tb["x"] + tb["w"] / 2 - (img["x"] + img["w"] / 2)) < 15 and 0 < tb["y"] - (img["y"] + img["h"]) < 20:
                label = tb["text"]
                break
        name = img["description"] if img["description"] else _norm(label) if label else ""
        icons.append({
            "name": name,
            "objectId": img["objectId"],
            "x": img["x"],
            "y": img["y"],
            "w": img["w"],
            "h": img["h"],
            "label": label,
            "description": img["description"],
        })

    groups = []
    for sh in shapes:
        if sh["w"] > (icon_size or 40) * 1.5 and sh["h"] > (icon_size or 40) * 1.5:
            label = sh["text"]
            if not label:
                for tb in text_boxes:
                    if sh["x"] < tb["x"] < sh["x"] + sh["w"] and sh["y"] < tb["y"] < sh["y"] + 20:
                        label = tb["text"]
                        break
            groups.append({
                "objectId": sh["objectId"],
                "x": sh["x"],
                "y": sh["y"],
                "w": sh["w"],
                "h": sh["h"],
                "label": label,
            })

    edges = []
    for ln in lines:
        from_icon = ""
        to_icon = ""
        for ic in icons:
            if ic["objectId"] == ln["startConnection"]:
                from_icon = ic["name"] or ic["label"]
            if ic["objectId"] == ln["endConnection"]:
                to_icon = ic["name"] or ic["label"]
        edge_label = ""
        mid_x = ln["x"] + ln["w"] / 2
        mid_y = ln["y"] + ln["h"] / 2
        for tb in text_boxes:
            if abs(tb["x"] + tb["w"] / 2 - mid_x) < 30 and abs(tb["y"] + tb["h"] / 2 - mid_y) < 30:
                edge_label = tb["text"]
                break
        edges.append({
            "objectId": ln["objectId"],
            "from": from_icon,
            "to": to_icon,
            "fromObjectId": ln["startConnection"],
            "toObjectId": ln["endConnection"],
            "label": edge_label,
            "lineCategory": ln["lineCategory"],
        })

    grid_info = None
    if icon_size and len(icons) >= 2:
        cell = DIAGRAM_GRID.get(icon_size, {}).get("cell", icon_size + 50)
        xs = sorted(set(round(ic["x"]) for ic in icons))
        ys = sorted(set(round(ic["y"]) for ic in icons))
        origin_x = xs[0] if xs else 0
        origin_y = ys[0] if ys else 0
        grid_info = {"iconSize": icon_size, "cell": cell, "originX": origin_x, "originY": origin_y}

    return {
        "slideId": slide["objectId"],
        "slideIndex": next(i for i, s in enumerate(pres["slides"]) if s["objectId"] == slide["objectId"]),
        "iconSize": icon_size,
        "grid": grid_info,
        "icons": icons,
        "groups": groups,
        "edges": edges,
        "rawImages": len(images),
        "rawShapes": len(shapes),
        "rawLines": len(lines),
        "rawTextBoxes": len(text_boxes),
    }


def main():
    parser = argparse.ArgumentParser(description="Read slide elements")
    parser.add_argument("presentation_id")
    parser.add_argument("--slide", required=True, help="Slide objectId or 1-based number")
    parser.add_argument("--output", help="Output JSON file path")
    args = parser.parse_args()

    result = read_elements(args.presentation_id, args.slide)

    output = json.dumps(result, indent=2, ensure_ascii=False)
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"Elements written to {args.output}")
        print(f"  Icons: {len(result.get('icons', []))}, Groups: {len(result.get('groups', []))}, Edges: {len(result.get('edges', []))}")
    else:
        print(output)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Audit a Snowflake-template Google Slides presentation.
Outputs layout info, existing slides, and icon slide candidates as JSON.

Usage:
    python audit_template.py <presentation_id> [--output audit.json]
"""
import argparse, json, sys
from googleapiclient.discovery import build
import google.auth, google.auth.transport.requests


def get_service():
    creds, _ = google.auth.default(
        scopes=["https://www.googleapis.com/auth/presentations.readonly"]
    )
    creds.refresh(google.auth.transport.requests.Request())
    return build("slides", "v1", credentials=creds)


def audit(presentation_id: str) -> dict:
    svc = get_service()
    pres = svc.presentations().get(presentationId=presentation_id).execute()

    pw = pres["pageSize"]["width"]["magnitude"]
    ph = pres["pageSize"]["height"]["magnitude"]

    layouts = []
    for l in pres.get("layouts", []):
        lid = l["objectId"]
        props = l.get("layoutProperties", {})
        phs = []
        for el in l.get("pageElements", []):
            p = el.get("shape", {}).get("placeholder", {})
            if p:
                phs.append({"type": p.get("type", "?"), "index": p.get("index", 0)})
        layouts.append({
            "id": lid,
            "displayName": props.get("displayName", ""),
            "name": props.get("name", ""),
            "placeholders": phs,
        })

    slides_info = []
    icon_slides = []
    for i, s in enumerate(pres.get("slides", [])):
        sid = s["objectId"]
        lid = s.get("slideProperties", {}).get("layoutObjectId", "")
        els = s.get("pageElements", [])
        groups = sum(1 for e in els if e.get("elementGroup"))
        texts = []
        for e in els:
            sh = e.get("shape", {})
            t = ""
            for te in sh.get("text", {}).get("textElements", []):
                if "textRun" in te:
                    t += te["textRun"]["content"]
            t = t.strip()
            if t:
                texts.append(t[:60])

        info = {
            "index": i,
            "objectId": sid,
            "layoutId": lid,
            "elementCount": len(els),
            "groupCount": groups,
            "sampleTexts": texts[:3],
        }
        slides_info.append(info)
        if len(els) >= 20 and groups >= 5:
            icon_slides.append(info)

    layout_map = {l["id"]: l["displayName"] for l in layouts}
    recommended = {}
    for l in layouts:
        dn = l["displayName"].lower()
        phtypes = [p["type"] for p in l["placeholders"]]
        if "cover" in dn:
            recommended.setdefault("cover", []).append(l["id"])
        elif "agenda" in dn:
            recommended.setdefault("agenda", []).append(l["id"])
        elif "divider" in dn:
            recommended.setdefault("divider", []).append(l["id"])
        elif "thank" in dn:
            recommended.setdefault("thanks", []).append(l["id"])
        elif "blank" in dn:
            recommended.setdefault("blank", []).append(l["id"])
        elif "multi" in dn and "TITLE" in phtypes:
            recommended.setdefault("multi", []).append(l["id"])
        elif "one column" in dn:
            recommended.setdefault("one_column", []).append(l["id"])
        elif "two column" in dn:
            recommended.setdefault("two_column", []).append(l["id"])

    return {
        "presentationId": presentation_id,
        "pageSize": {"width": pw, "height": ph, "widthInches": round(pw / 914400, 1), "heightInches": round(ph / 914400, 1)},
        "layoutCount": len(layouts),
        "layouts": layouts,
        "slideCount": len(slides_info),
        "slides": slides_info,
        "iconSlides": icon_slides,
        "recommendedLayouts": recommended,
        "layoutDisplayNames": layout_map,
    }


def main():
    parser = argparse.ArgumentParser(description="Audit Snowflake-template Google Slides")
    parser.add_argument("presentation_id", help="Google Slides presentation ID")
    parser.add_argument("--output", "-o", help="Output JSON file (default: stdout)")
    args = parser.parse_args()

    result = audit(args.presentation_id)

    if args.output:
        with open(args.output, "w") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        print(f"Audit written to {args.output}")
        print(f"  Layouts: {result['layoutCount']}, Slides: {result['slideCount']}, Icon slides: {len(result['iconSlides'])}")
    else:
        json.dump(result, sys.stdout, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    main()

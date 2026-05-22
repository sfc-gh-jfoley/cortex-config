#!/usr/bin/env python3
"""Rebuild (update) a single slide's content in-place.

The old slide is moved after the Thanks slide and marked as skipped (hidden in presentation mode).
A new slide is created at the original position with updated content.

Usage:
    python rebuild_slide.py <presentation_id> --slide <N|objectId> --spec <patch.json> [--output result.json]
"""
import argparse, json, sys
from utils import get_services_with_creds, batch
from build_slides import (
    SlideBuilder, fill_slides, validate_spec,
)


def find_thanks_index(pres):
    layouts = {l["objectId"]: l.get("layoutProperties", {}).get("displayName", "").lower()
               for l in pres.get("layouts", [])}
    for i, slide in enumerate(pres.get("slides", [])):
        lid = slide.get("slideProperties", {}).get("layoutObjectId", "")
        if "thank" in layouts.get(lid, ""):
            return i
    return len(pres.get("slides", [])) - 1


def find_slide_index(pres, target):
    slides = pres.get("slides", [])
    if target.isdigit():
        idx = int(target) - 1
        if 0 <= idx < len(slides):
            return idx
        print(f"ERROR: Slide number {target} out of range (1-{len(slides)})")
        sys.exit(2)
    for i, s in enumerate(slides):
        if s["objectId"] == target:
            return i
    print(f"ERROR: Slide with objectId '{target}' not found")
    sys.exit(2)


def rebuild(svc, drive_svc, pid, target, spec, creds=None):
    config = spec.get("config", {})
    b = SlideBuilder(svc, drive_svc, pid, config)
    b._creds = creds
    b.refresh()

    slide_idx = find_slide_index(b.pres, target)
    old_slide = b.pres["slides"][slide_idx]
    old_id = old_slide["objectId"]
    thanks_idx = find_thanks_index(b.pres)

    print(f"Target: slide {slide_idx + 1} (objectId={old_id})")

    total_slides = len(b.pres["slides"])
    if slide_idx <= thanks_idx:
        move_to = thanks_idx + 1
    else:
        move_to = total_slides
    print(f"Step 1: Moving old slide to position {move_to + 1} (after Thanks)...")
    batch(svc, pid, [{
        "updateSlidesPosition": {
            "slideObjectIds": [old_id],
            "insertionIndex": move_to,
        }
    }])

    print("Step 2: Marking old slide as skipped...")
    batch(svc, pid, [{
        "updateSlideProperties": {
            "objectId": old_id,
            "slideProperties": {"isSkipped": True},
            "fields": "isSkipped",
        }
    }])

    slides = spec["slides"]
    new_slide = slides[0]
    print(f"Step 3: Creating new slide at position {slide_idx + 1}...")
    batch(svc, pid, [{
        "createSlide": {
            "objectId": new_slide["id"],
            "insertionIndex": slide_idx,
            "slideLayoutReference": {"layoutId": new_slide["layoutId"]},
        }
    }])

    print("Step 4: Filling content...")
    ph_map = b.get_phs()
    fill_slides(b, slides, ph_map)
    b.flush()

    print("Step 5: Hiding empty placeholders on new slide...")
    b.refresh()
    reqs = []
    for slide in b.pres["slides"]:
        if slide["objectId"] != new_slide["id"]:
            continue
        for el in slide.get("pageElements", []):
            ph = el.get("shape", {}).get("placeholder")
            if not ph:
                continue
            if ph.get("type") == "SLIDE_NUMBER":
                continue
            t = ""
            for te in el.get("shape", {}).get("text", {}).get("textElements", []):
                if "textRun" in te:
                    t += te["textRun"]["content"]
            if not t.strip():
                reqs.append({
                    "updatePageElementTransform": {
                        "objectId": el["objectId"],
                        "applyMode": "ABSOLUTE",
                        "transform": {
                            "scaleX": 0.01, "scaleY": 0.01,
                            "translateX": 20000000, "translateY": 20000000,
                            "unit": "EMU",
                        },
                    }
                })
    if reqs:
        batch(svc, pid, reqs, 50)
    print(f"  Hidden {len(reqs)} empty placeholders")

    print("Step 6: Verifying...")
    result = b.verify()
    print(f"  Slides: {result['slideCount']}, Issues: {len(result['issues'])}")
    for iss in result["issues"]:
        print(f"    - {iss}")

    skipped = [s for s in result["slides"] if s["objectId"] == old_id]
    print(f"\n  Old slide ({old_id}) moved to position {skipped[0]['index'] if skipped else '?'} (skipped)")
    print(f"  New slide ({new_slide['id']}) at position {slide_idx + 1}")

    if result["issues"]:
        print(f"\nWARNING: {len(result['issues'])} issues found")
    else:
        print("\nDONE - No issues!")

    return result


def main():
    parser = argparse.ArgumentParser(description="Rebuild a single slide in-place")
    parser.add_argument("presentation_id", help="Google Slides presentation ID")
    parser.add_argument("--slide", required=True, help="Slide number (1-indexed) or objectId")
    parser.add_argument("--spec", required=True, help="Patch JSON file (single slide spec)")
    parser.add_argument("--output", "-o", help="Output verification JSON")
    parser.add_argument("--clean", action="store_true", help="Delete all skipped slides before rebuild")
    args = parser.parse_args()

    with open(args.spec) as f:
        try:
            spec = json.load(f)
        except json.JSONDecodeError as e:
            print(f"ERROR: Failed to parse spec JSON: {e}")
            sys.exit(3)

    print("Pre-validation...")
    from lint_spec import lint
    lint_errors, lint_warnings = lint(spec)
    if lint_errors:
        print(f"LINT ERRORS ({len(lint_errors)}):")
        for e in lint_errors:
            print(f"  ERROR: {e}")
        print("Fix lint errors before rebuilding.")
        sys.exit(5)
    if lint_warnings:
        for w in lint_warnings:
            print(f"  LINT WARNING: {w}")

    vw = validate_spec(spec)
    slides = spec.get("slides", [])
    if len(slides) != 1:
        print(f"ERROR: patch.json must contain exactly 1 slide (found {len(slides)})")
        sys.exit(2)
    if vw:
        errors = [w for w in vw if "auto-shrunk" not in w]
        for w in vw:
            print(f"  WARNING: {w}")
        if errors:
            print(f"  {len(errors)} unrecoverable layout issue(s). Split overflowing slides (do NOT truncate/drop content).")
            sys.exit(4)
        print(f"  {len(vw)} issue(s) auto-corrected. Continuing...")
    else:
        print("  OK")

    svc, drive_svc, creds = get_services_with_creds()

    if args.clean:
        print("Cleaning skipped slides...")
        pres = svc.presentations().get(presentationId=args.presentation_id).execute()
        skipped_ids = [
            s["objectId"] for s in pres.get("slides", [])
            if s.get("slideProperties", {}).get("isSkipped")
        ]
        if skipped_ids:
            batch(svc, args.presentation_id, [{"deleteObject": {"objectId": sid}} for sid in skipped_ids])
            print(f"  Deleted {len(skipped_ids)} skipped slide(s)")
        else:
            print("  No skipped slides found")

    result = rebuild(svc, drive_svc, args.presentation_id, args.slide, spec, creds=creds)

    if args.output:
        with open(args.output, "w") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

    sys.exit(1 if result["issues"] else 0)


if __name__ == "__main__":
    main()

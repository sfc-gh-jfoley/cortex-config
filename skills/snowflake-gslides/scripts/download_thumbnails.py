#!/usr/bin/env python3
"""Download thumbnails for diagram slides from a Google Slides presentation.

Usage:
    python download_thumbnails.py <presentation_id> <spec.json> [--output-dir DIR]
    python download_thumbnails.py <presentation_id> <spec.json> --slide-ids sl_0801_v2 sl_0901

Downloads LARGE (1600x900) PNG thumbnails for all type="diagram" slides.
Saves to output-dir (default: ./thumbnails/) as <slide_id>.png.
Prints JSON summary to stdout for easy parsing.
"""
import argparse, json, time
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import URLError

from utils import get_services


def get_diagram_slides(spec):
    slides = spec.get("slides", [])
    return [(s["id"], s.get("title", "")) for s in slides if s.get("type") == "diagram"]


def download_thumbnails(pid, spec_path, output_dir, retries=2, slide_ids=None):
    spec = json.loads(Path(spec_path).read_text(encoding="utf-8"))
    if slide_ids:
        all_slides = {s["id"]: s.get("title", "") for s in spec.get("slides", [])}
        diagram_slides = [(sid, all_slides.get(sid, "")) for sid in slide_ids]
    else:
        diagram_slides = get_diagram_slides(spec)

    if not diagram_slides:
        print("No diagram slides found.", flush=True)
        return []

    svc, _ = get_services()

    slide_id_to_obj_id = {s_id: s_id for s_id, _ in diagram_slides}

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    results = []
    total = len(diagram_slides)
    for idx, (s_id, title) in enumerate(diagram_slides, 1):
        obj_id = slide_id_to_obj_id.get(s_id)
        if not obj_id:
            print(f"  [{idx}/{total}] {s_id}: SKIP (object_id not found)", flush=True)
            results.append({"slide_id": s_id, "title": title, "status": "skip", "path": None})
            continue

        for attempt in range(retries + 1):
            try:
                thumb = svc.presentations().pages().getThumbnail(
                    presentationId=pid,
                    pageObjectId=obj_id,
                    thumbnailProperties_thumbnailSize='LARGE'
                ).execute()
                url = thumb["contentUrl"]
                req = Request(url)
                req.add_header("User-Agent", "snowflake-gslides-thumbnail/1.0")
                img_data = urlopen(req, timeout=15).read()
                dest = out / f"{s_id}.png"
                dest.write_bytes(img_data)
                print(f"  [{idx}/{total}] {s_id}: OK → {dest}", flush=True)
                results.append({"slide_id": s_id, "title": title, "status": "ok", "path": str(dest)})
                break
            except (URLError, OSError, KeyError, Exception) as e:
                if attempt < retries:
                    time.sleep(1)
                    continue
                print(f"  [{idx}/{total}] {s_id}: FAIL ({e})", flush=True)
                results.append({"slide_id": s_id, "title": title, "status": "fail", "path": None, "error": str(e)})

    ok_count = sum(1 for r in results if r["status"] == "ok")
    print(f"\nDone: {ok_count}/{total} thumbnails downloaded to {out}/", flush=True)

    summary = {"total": total, "ok": ok_count, "thumbnails": results}
    summary_path = out / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    return results


def main():
    parser = argparse.ArgumentParser(description="Download diagram slide thumbnails")
    parser.add_argument("presentation_id", help="Google Slides presentation ID")
    parser.add_argument("spec", help="Path to spec.json")
    parser.add_argument("--output-dir", default="./thumbnails", help="Output directory (default: ./thumbnails)")
    parser.add_argument("--retries", type=int, default=2, help="Retry count per slide (default: 2)")
    parser.add_argument("--slide-ids", nargs="+", help="Specific slide IDs to download (overrides spec diagram detection)")
    args = parser.parse_args()

    results = download_thumbnails(args.presentation_id, args.spec, args.output_dir, args.retries, args.slide_ids)
    fail_count = sum(1 for r in results if r["status"] == "fail")
    raise SystemExit(1 if fail_count else 0)


if __name__ == "__main__":
    main()

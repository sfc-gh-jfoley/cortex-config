#!/usr/bin/env python3
"""Check docs.snowflake.com URLs in spec.json for broken links (404)."""
import argparse, json, re
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.request import urlopen, Request
from urllib.error import HTTPError, URLError

URL_RE = re.compile(r'https://docs\.snowflake\.com/[^\s\)\]"\'>]+[^\s\)\]"\'>.,;:!?]')


def extract_urls(spec):
    urls = set()
    slides = spec.get("slides", []) if isinstance(spec, dict) else spec
    for slide in slides:
        body = slide.get("body", "")
        urls.update(URL_RE.findall(body))
        for row in slide.get("table", {}).get("rows", []):
            for cell in row:
                urls.update(URL_RE.findall(str(cell)))
        for row in slide.get("table", {}).get("data", []):
            for cell in row:
                urls.update(URL_RE.findall(str(cell)))
    return sorted(urls)


def check_url(url):
    try:
        req = Request(url, method="GET")
        req.add_header("User-Agent", "snowflake-gslides-url-checker/1.0")
        resp = urlopen(req, timeout=10)
        code = resp.getcode()
        final_url = resp.geturl()
        if final_url.rstrip("/") != url.rstrip("/"):
            return url, code, "redirect", final_url
        return url, code, "ok", None
    except HTTPError as e:
        hint = None
        if e.code == 404:
            try:
                body = e.read().decode("utf-8", errors="ignore")
                m = re.search(r'href="(https://docs\.snowflake\.com/[^"]+)"', body)
                if m:
                    hint = m.group(1)
            except Exception:
                pass
        return url, e.code, "error", hint
    except (URLError, OSError) as e:
        return url, 0, "network_error", str(e)


def main():
    parser = argparse.ArgumentParser(description="Check Snowflake doc URLs in spec.json")
    parser.add_argument("spec", help="Path to spec.json")
    args = parser.parse_args()

    with open(args.spec, encoding="utf-8") as f:
        spec = json.load(f)

    urls = extract_urls(spec)
    if not urls:
        print("No docs.snowflake.com URLs found.")
        return

    print(f"Checking {len(urls)} URL(s)...\n")
    broken = []
    redirects = []

    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {pool.submit(check_url, u): u for u in urls}
        for fut in as_completed(futures):
            url, code, status, extra = fut.result()
            if status == "ok":
                print(f"  ✓ {url}")
            elif status == "redirect":
                print(f"  ⟳ {url} → {extra}")
                redirects.append((url, extra))
            elif status == "error":
                print(f"  ✗ {url} ({code})")
                if extra:
                    print(f"    → Did you mean: {extra}")
                broken.append((url, code, extra))
            else:
                print(f"  ? {url} (network error: {extra})")

    print()
    if broken:
        print(f"ERROR: {len(broken)} broken URL(s). Fix in spec.json before building:")
        for url, code, hint in broken:
            msg = f"  - {url} ({code})"
            if hint:
                msg += f"  →  {hint}"
            print(msg)
    if redirects:
        print(f"INFO: {len(redirects)} redirect(s) (consider updating to final URL):")
        for url, final in redirects:
            print(f"  - {url}  →  {final}")
    if not broken and not redirects:
        print("All URLs OK.")

    raise SystemExit(1 if broken else 0)


if __name__ == "__main__":
    main()

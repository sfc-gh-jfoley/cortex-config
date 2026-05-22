#!/usr/bin/env python3
"""Shared utilities for snowflake-gslides scripts."""
import json, re
from pathlib import Path
from googleapiclient.discovery import build
import google.auth, google.auth.transport.requests


def get_services():
    creds, _ = google.auth.default(
        scopes=[
            "https://www.googleapis.com/auth/presentations",
            "https://www.googleapis.com/auth/drive",
        ]
    )
    creds.refresh(google.auth.transport.requests.Request())
    slides_svc = build("slides", "v1", credentials=creds)
    drive_svc = build("drive", "v3", credentials=creds)
    return slides_svc, drive_svc


def get_services_with_creds():
    creds, _ = google.auth.default(
        scopes=[
            "https://www.googleapis.com/auth/presentations",
            "https://www.googleapis.com/auth/drive",
        ]
    )
    creds.refresh(google.auth.transport.requests.Request())
    slides_svc = build("slides", "v1", credentials=creds)
    drive_svc = build("drive", "v3", credentials=creds)
    return slides_svc, drive_svc, creds


def batch(svc, pid, reqs, chunk_size=80):
    for i in range(0, len(reqs), chunk_size):
        svc.presentations().batchUpdate(
            presentationId=pid, body={"requests": reqs[i : i + chunk_size]}
        ).execute()


def parse_md_links(text):
    """Parse [text](url) in markdown. Returns (plain_text, [(start, end, url), ...])."""
    links = []
    result = []
    pos = 0
    for m in re.finditer(r'\[([^\]]+)\]\(([^)]+)\)', text):
        result.append(text[pos:m.start()])
        link_start = sum(len(s) for s in result)
        link_text = m.group(1)
        link_url = m.group(2)
        result.append(link_text)
        link_end = link_start + len(link_text)
        links.append((link_start, link_end, link_url))
        pos = m.end()
    result.append(text[pos:])
    return "".join(result), links


def display_len(text):
    """CJK-aware display width calculation."""
    w = 0
    for ch in text:
        if '\u3000' <= ch <= '\u9fff' or '\uf900' <= ch <= '\ufaff' or '\uff00' <= ch <= '\uffef' or '\uac00' <= ch <= '\ud7af':
            w += 2
        else:
            w += 1
    return max(w, 1)


def estimate_body_h(body_text, body_fs, body_w=8200000):
    """Estimate body text box height in EMU."""
    clean_body = body_text.replace("**", "").replace("`", "")
    clean_body = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', clean_body)
    clean_body = re.sub(r'^#{1,4}\s+', '', clean_body, flags=re.MULTILINE)
    lines = clean_body.split("\n")
    char_w_emu = int(body_fs * 914400 / 72 * 0.55)
    chars_per_line = max(body_w // max(char_w_emu, 1), 1)
    line_h = int(body_fs * 914400 / 72 * 1.5)
    total_lines = 0
    for line in lines:
        stripped = line.strip()
        dl = display_len(stripped)
        wrapped = max(1, -(-dl // chars_per_line))
        total_lines += wrapped
    return total_lines * line_h + 20000


_aliases_cache = None
_icons_list_cache = None


def _load_aliases():
    global _aliases_cache
    if _aliases_cache is None:
        p = Path(__file__).parent.parent / "config" / "icon_aliases.json"
        if p.exists():
            with open(p) as f:
                _aliases_cache = json.load(f)
        else:
            _aliases_cache = {}
    return _aliases_cache


def _load_icons_list():
    global _icons_list_cache
    if _icons_list_cache is None:
        p = Path(__file__).parent.parent / "config" / "icons_list.json"
        if p.exists():
            with open(p) as f:
                data = json.load(f)
            if isinstance(data, dict):
                all_icons = set()
                for icons in data.values():
                    all_icons.update(icons)
                _icons_list_cache = all_icons
            else:
                _icons_list_cache = set(data)
        else:
            _icons_list_cache = set()
    return _icons_list_cache


def resolve_icon_name(name):
    """Resolve icon alias to canonical name. Returns resolved name or original if not found."""
    if not name:
        return ""
    aliases = _load_aliases()
    icons = _load_icons_list()
    normalized = name.lower().replace("-", "_").replace(" ", "_").replace("\n", "_")
    resolved = aliases.get(normalized, aliases.get(name, normalized))
    if resolved in icons:
        return resolved
    if normalized in icons:
        return normalized
    if name in icons:
        return name
    # Substring match: find icon whose name ends with the normalized term
    candidates = [i for i in icons if i.endswith("_" + normalized) or i == normalized]
    if len(candidates) == 1:
        return candidates[0]
    return resolved


def is_valid_icon(name):
    """Check if icon name (after resolve) exists in icons_list."""
    resolved = resolve_icon_name(name)
    icons = _load_icons_list()
    return resolved in icons


def call_icon_inserter(creds, apps_script_url, presentation_id, slide_id, items):
    """Call Apps Script to insert icons. Returns list of {iconName, objectId|error}."""
    if not creds or not items:
        return [{"iconName": item.get("iconName", ""), "error": "no_credentials"} for item in (items or [])]
    import requests as req_lib
    headers = {
        "Authorization": f"Bearer {creds.token}",
        "Content-Type": "application/json",
    }
    payload = {
        "presentationId": presentation_id,
        "slideId": slide_id,
        "items": items,
    }
    for attempt in range(2):
        try:
            resp = req_lib.post(apps_script_url, json=payload, headers=headers, timeout=30)
            if resp.status_code == 401:
                creds.refresh(google.auth.transport.requests.Request())
                headers["Authorization"] = f"Bearer {creds.token}"
                continue
            data = resp.json()
            return data.get("results", [])
        except Exception as e:
            if attempt == 0:
                continue
            return [{"iconName": item.get("iconName", ""), "error": str(e)} for item in items]
    return [{"iconName": item.get("iconName", ""), "error": "auth_failed"} for item in items]

#!/usr/bin/env python3
"""Firewall scan for telemetry-to-lab.

Builds a deny list from <labdir>/internal/ and scans customer-facing files for leaks.
Exit 0 = clean, 1 = hits found, 2 = usage/setup error. Stdlib only.
"""
import json
import re
import sys
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
ALLOW_FILE = SKILL_ROOT / "references" / "allow.txt"

IDENT_RE = re.compile(r"\b[A-Za-z][A-Za-z0-9_$]*(?:\.[A-Za-z0-9_$\"]+){1,2}\b|\b[A-Z][A-Z0-9_$]{3,}\b")
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
PHRASES = [
    r"\bwe\s+(saw|noticed|observed|found)\b",
    r"\byour\s+(account|failures|jobs|queries|warehouses?)\b",
    r"\bin\s+your\s+environment\b",
    r"\btelemetry\b",
    r"\bsnowhouse\b",
    r"\bbased\s+on\s+your\s+usage\b",
]
CUSTOMER_FACING_GLOBS = ["*-lab-intake.md", "data_spec.yaml", "data_spec.yml", "remap.md"]
GENERIC_SUFFIXES = {"CORP", "CORPORATION", "INC", "LLC", "LTD", "COMPANY", "GROUP", "HOLDINGS",
                    "GLOBAL", "THE", "AND", "INTERNATIONAL", "SERVICES"}


def load_allow():
    if not ALLOW_FILE.exists():
        return set()
    out = set()
    for line in ALLOW_FILE.read_text().splitlines():
        tok = line.split("#", 1)[0].strip()
        if tok:
            out.add(tok.upper())
    return out


def walk_strings(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield str(k)
            yield from walk_strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from walk_strings(v)
    elif obj is not None:
        yield str(obj)


def build_deny(internal: Path, allow: set):
    deny = set()
    acct_path = internal / "account.json"
    if acct_path.exists():
        acct = json.loads(acct_path.read_text())
        cust = acct.get("customer", "")
        if cust:
            deny.add(cust.upper())
            # brand tokens keep inner punctuation (Acme&Co, Foo-Bar); alnum tokens catch the rest
            for tok in re.split(r"[\s()\[\],/]+", cust):
                tok = tok.strip(".-")
                if len(tok) >= 3 and tok.upper() not in GENERIC_SUFFIXES:
                    deny.add(tok.upper())
            for tok in re.split(r"[^A-Za-z0-9]+", cust):
                if len(tok) >= 3 and tok.upper() not in GENERIC_SUFFIXES:
                    deny.add(tok.upper())
        for key in ("account_name", "account_alias"):
            if acct.get(key):
                deny.add(str(acct[key]).upper())
        if acct.get("account_id"):
            deny.add(str(acct["account_id"]))
        for wh in (acct.get("warehouse_classes") or {}):
            deny.add(wh.upper())
    extra = internal / "deny_extra.txt"
    if extra.exists():
        deny |= {l.strip().upper() for l in extra.read_text().splitlines() if l.strip()}
    texts = []
    for name in ("findings.json", "intents.json", "selection.json"):
        p = internal / name
        if p.exists():
            try:
                texts.extend(walk_strings(json.loads(p.read_text())))
            except json.JSONDecodeError:
                texts.append(p.read_text())
    em = internal / "evidence_map.md"
    if em.exists():
        texts.append(em.read_text())
    for t in texts:
        for m in IDENT_RE.findall(t):
            tok = m.upper().replace('"', "")
            if "." in tok:
                deny.add(tok)
                deny.update(part for part in tok.split(".") if len(part) >= 4)
            else:
                deny.add(tok)
        for m in EMAIL_RE.findall(t):
            deny.add(m.upper())
    return {d for d in deny if d and d not in allow}


def lab_owned_names(labdir: Path):
    """Archetype, column and starter names defined by the lab's own data spec are never leaks."""
    owned = set()
    for spec in (labdir / "data_spec.yaml", labdir / "data_spec.yml"):
        if spec.exists():
            for m in re.finditer(r"\bname:\s*['\"]?([A-Za-z][A-Za-z0-9_]*)", spec.read_text()):
                owned.add(m.group(1).upper())
    return owned


def scan(labdir: Path):
    internal = labdir / "internal"
    if not internal.is_dir():
        print(f"error: {internal} not found", file=sys.stderr)
        return 2
    allow = load_allow() | lab_owned_names(labdir)
    deny = build_deny(internal, allow)
    files = sorted({p for g in CUSTOMER_FACING_GLOBS for p in labdir.glob(g)})
    if not files:
        print("error: no customer-facing files found", file=sys.stderr)
        return 2
    hits = []
    deny_res = [(d, re.compile(r"(?<![A-Za-z0-9_])" + re.escape(d) + r"(?![A-Za-z0-9_])", re.I)) for d in deny]
    phrase_res = [re.compile(p, re.I) for p in PHRASES]
    for f in files:
        for n, line in enumerate(f.read_text().splitlines(), 1):
            for d, rx in deny_res:
                if rx.search(line):
                    hits.append((f.name, n, "identifier", d))
            for rx in phrase_res:
                m = rx.search(line)
                if m:
                    hits.append((f.name, n, "phrase", m.group(0)))
            for m in EMAIL_RE.findall(line):
                hits.append((f.name, n, "email", m))
    if hits:
        for h in hits:
            print(f"{h[0]}:{h[1]}: [{h[2]}] {h[3]}")
        print(f"FAIL: {len(hits)} hit(s) across {len(files)} file(s); deny list size {len(deny)}")
        return 1
    print(f"PASS: {len(files)} file(s) clean; deny list size {len(deny)}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: firewall_scan.py <labdir>", file=sys.stderr)
        sys.exit(2)
    sys.exit(scan(Path(sys.argv[1]).expanduser()))

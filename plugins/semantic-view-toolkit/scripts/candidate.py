#!/usr/bin/env python3
"""Candidate-copy contract helper for semantic-view-toolkit.

Every skill that changes a semantic view works on a uniquely named candidate copy,
never the production view. This script owns naming, the production guard, DDL
rewriting, and the run manifest that cleanup relies on.

Usage:
  python candidate.py new-run
  python candidate.py name --source DB.SCH.SV --kind {gepa,cand,mat} --run RUN [--gen N --idx N]
  python candidate.py guard --source DB.SCH.SV --target DB.SCH.NAME
  python candidate.py rewrite-ddl --source DB.SCH.SV --candidate DB.SCH.NAME [--manifest M] < ddl.sql
  python candidate.py vqr-diff ORIGINAL.sql MUTATED.sql
  python candidate.py register MANIFEST --run RUN --source FQN --candidate FQN [--parent FQN] [--ddl-file F]
  python candidate.py set-status MANIFEST --candidate FQN --status STATUS
  python candidate.py cleanup-plan MANIFEST --run RUN
"""
import argparse
import hashlib
import json
import re
import secrets
import sys
from pathlib import Path

IDENT = re.compile(r"^[A-Z_][A-Z0-9_$]*$")
MAX_IDENT = 255
KINDS = ("gepa", "cand", "mat")
STATUSES = ("created", "evaluated", "winner", "promoted", "discarded", "failed")
DROPPABLE = {"created", "evaluated", "discarded", "failed"}
RUN_RE = re.compile(r"^R[0-9A-F]{6}$")
HEADER = re.compile(
    r"^\s*CREATE\s+(?:OR\s+(?:REPLACE|ALTER)\s+)?SEMANTIC\s+VIEW\s+(?:IF\s+NOT\s+EXISTS\s+)?"
    r"(?P<name>(?:\"[^\"]+\"|[A-Za-z_][\w$]*)(?:\s*\.\s*(?:\"[^\"]+\"|[A-Za-z_][\w$]*)){0,2})",
    re.IGNORECASE,
)
CANDIDATE_RE = re.compile(r"__(?:GEPA__R[0-9A-F]{6}__G\d+__C\d+|CAND__R[0-9A-F]{6}|MAT__R[0-9A-F]{6})$")
SUFFIX_RE = re.compile(r"^__(?:GEPA__R[0-9A-F]{6}__G\d+__C\d+|CAND__R[0-9A-F]{6}|MAT__R[0-9A-F]{6})$")
RUN_IN_NAME = re.compile(r"__(?:GEPA|CAND|MAT)__(R[0-9A-F]{6})")


class ContractError(Exception):
    pass


def mask_non_code(sql):
    """Return sql with string, quoted-identifier and comment contents blanked (same length).

    Delimiters of strings stay so structure is visible; comments become spaces.
    """
    out, i, n = [], 0, len(sql)
    while i < n:
        ch = sql[i]
        two = sql[i:i + 2]
        if two == "--":
            j = sql.find("\n", i)
            j = n if j == -1 else j
            out.append(" " * (j - i))
            i = j
        elif two == "/*":
            j = sql.find("*/", i + 2)
            j = n if j == -1 else j + 2
            out.append(" " * (j - i))
            i = j
        elif two == "$$":
            j = sql.find("$$", i + 2)
            j = n if j == -1 else j + 2
            out.append("$$" + "x" * max(0, j - i - 4) + ("$$" if j - i >= 4 else ""))
            i = j
        elif ch in ("'", '"'):
            j = i + 1
            while j < n:
                if sql[j] == "\\" and ch == "'":
                    j += 2
                    continue
                if sql[j] == ch:
                    if j + 1 < n and sql[j + 1] == ch:
                        j += 2
                        continue
                    break
                j += 1
            j = min(j, n - 1)
            out.append(ch + "x" * (j - i - 1) + ch)
            i = j + 1
        else:
            out.append(ch)
            i += 1
    return "".join(out)[:n].ljust(n)


def assert_single_statement(ddl):
    """Reject DDL with anything but whitespace or comments after the first top-level semicolon."""
    masked = mask_non_code(ddl)
    cut = masked.find(";")
    if cut != -1 and masked[cut + 1:].strip():
        raise ContractError("DDL contains more than one statement; exactly one CREATE SEMANTIC VIEW is allowed")


def extract_vqrs(ddl):
    """Map verified-query name -> whitespace-normalized text from the AI_VERIFIED_QUERIES clause."""
    masked = mask_non_code(ddl)
    match = re.search(r"AI_VERIFIED_QUERIES\s*\(", masked, re.IGNORECASE)
    if not match:
        return {}
    start, depth, i = match.end(), 1, match.end()
    entries, last = [], start
    while i < len(masked) and depth:
        ch = masked[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                break
        elif ch == "," and depth == 1:
            entries.append(ddl[last:i])
            last = i + 1
        i += 1
    entries.append(ddl[last:i])
    result = {}
    for entry in entries:
        text = " ".join(entry.split())
        head = re.match(r"([A-Za-z_][\w$]*)\s+AS\b", text, re.IGNORECASE)
        if head:
            result[head.group(1).upper()] = text
    return result


def vqr_diff(original_ddl, mutated_ddl):
    before, after = extract_vqrs(original_ddl), extract_vqrs(mutated_ddl)
    return {
        "added": sorted(set(after) - set(before)),
        "removed": sorted(set(before) - set(after)),
        "changed": sorted(k for k in set(before) & set(after) if before[k] != after[k]),
    }


def split_fqn(fqn):
    parts = [p.strip() for p in fqn.split(".")]
    if len(parts) != 3 or not all(parts):
        raise ContractError(f"expected DATABASE.SCHEMA.NAME, got {fqn!r}")
    parts = [p.upper() for p in parts]
    for part in parts:
        if not IDENT.match(part):
            raise ContractError(f"unsupported identifier {part!r}; use unquoted names")
    return parts


def new_run():
    return "R" + secrets.token_hex(3).upper()


def build_name(source, kind, run, gen=None, idx=None, manifest=None):
    if kind not in KINDS:
        raise ContractError(f"kind must be one of {KINDS}")
    if not RUN_RE.match(run):
        raise ContractError(f"run id must look like R1A2B3C, got {run!r}")
    db, schema, name = split_fqn(source)
    if kind == "gepa":
        if gen is None or idx is None or gen < 1 or idx < 1:
            raise ContractError("gepa names need --gen >= 1 and --idx >= 1")
        suffix = f"__GEPA__{run}__G{gen}__C{idx}"
    elif kind == "cand":
        suffix = f"__CAND__{run}"
    else:
        suffix = f"__MAT__{run}"
    if CANDIDATE_RE.search(name) and not is_adopted(manifest, source):
        raise ContractError("source is already a candidate; derive candidates from the production view "
                            "(or from a candidate recorded as promoted in the manifest)")
    candidate = name + suffix
    if len(candidate) > MAX_IDENT:
        raise ContractError(f"candidate name exceeds {MAX_IDENT} characters")
    result = f"{db}.{schema}.{candidate}"
    check_guard(source, result, manifest)
    return result


def is_adopted(manifest, fqn):
    """True when the manifest records fqn as promoted (a retargeted candidate now used as production)."""
    if not manifest:
        return False
    return any(e["candidate"] == fqn and e["status"] == "promoted" for e in load_manifest(manifest)["entries"])


def suffix_of(source_name, target_name):
    if not target_name.startswith(source_name):
        return None
    suffix = target_name[len(source_name):]
    return suffix if SUFFIX_RE.match(suffix) else None


def check_guard(source, target, manifest=None):
    src, tgt = split_fqn(source), split_fqn(target)
    if src == tgt:
        raise ContractError("target equals the production view; refusing")
    if tgt[:2] != src[:2]:
        raise ContractError("candidate must live in the same database and schema as its source")
    if suffix_of(src[2], tgt[2]) is None:
        raise ContractError(f"{target} is not a candidate name of {source}; refusing to modify it")
    if is_adopted(manifest, target):
        raise ContractError(f"{target} was promoted and is in use as production; refusing to modify it")


def rewrite_ddl(ddl, source, candidate, manifest=None):
    check_guard(source, candidate, manifest)
    assert_single_statement(ddl)
    match = HEADER.match(ddl)
    if not match:
        raise ContractError("DDL does not start with CREATE [OR ...] SEMANTIC VIEW <name>")
    parts = [p.strip() for p in match.group("name").split(".")]
    found = [p if p.startswith('"') else p.upper() for p in parts]
    found = [p.strip('"') if p.startswith('"') else p for p in found]
    src = split_fqn(source)
    own = found[-1] == src[2]
    sibling = suffix_of(src[2], found[-1]) is not None
    scope = {3: found[:2] == src[:2], 2: found[0] == src[1], 1: True}[len(found)]
    if not (own or sibling) or not scope:
        raise ContractError(f"DDL header names {match.group('name')!r}, expected {source} or one of its candidates")
    return "CREATE SEMANTIC VIEW " + candidate + ddl[match.end():]


def load_manifest(path):
    p = Path(path)
    if not p.exists():
        return {"entries": []}
    data = json.loads(p.read_text())
    if not isinstance(data.get("entries"), list):
        raise ContractError("manifest is malformed")
    return data


def save_manifest(path, data):
    Path(path).write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def register(path, run, source, candidate, parent=None, ddl_text=None):
    check_guard(source, candidate)
    if parent:
        check_guard(source, parent)
    data = load_manifest(path)
    if any(e["candidate"] == candidate for e in data["entries"]):
        raise ContractError(f"{candidate} already registered")
    data["entries"].append({
        "run": run, "source": source, "candidate": candidate, "parent": parent,
        "ddl_sha256": hashlib.sha256(ddl_text.encode()).hexdigest() if ddl_text else None,
        "status": "created",
    })
    save_manifest(path, data)
    return data["entries"][-1]


def set_status(path, candidate, status):
    if status not in STATUSES:
        raise ContractError(f"status must be one of {STATUSES}")
    data = load_manifest(path)
    for entry in data["entries"]:
        if entry["candidate"] == candidate:
            entry["status"] = status
            save_manifest(path, data)
            return entry
    raise ContractError(f"{candidate} not in manifest")


def cleanup_plan(path, run):
    data = load_manifest(path)
    drops, kept = [], []
    for entry in data["entries"]:
        if entry["run"] != run:
            continue
        check_guard(entry["source"], entry["candidate"])
        in_name = RUN_IN_NAME.search(entry["candidate"].rsplit(".", 1)[-1])
        if not in_name or in_name.group(1) != entry["run"]:
            raise ContractError(f"{entry['candidate']} does not carry run id {entry['run']}; refusing")
        if entry["status"] in DROPPABLE:
            drops.append(f"DROP SEMANTIC VIEW IF EXISTS {entry['candidate']};")
        else:
            kept.append({"candidate": entry["candidate"], "status": entry["status"]})
    return {"run": run, "drop_statements": drops, "kept": kept}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("new-run")
    p = sub.add_parser("name")
    p.add_argument("--source", required=True)
    p.add_argument("--kind", required=True, choices=KINDS)
    p.add_argument("--run", required=True)
    p.add_argument("--gen", type=int)
    p.add_argument("--idx", type=int)
    p.add_argument("--manifest", help="allow a promoted candidate in this manifest as the source")
    p = sub.add_parser("guard")
    p.add_argument("--source", required=True)
    p.add_argument("--target", required=True)
    p.add_argument("--manifest")
    p = sub.add_parser("rewrite-ddl")
    p.add_argument("--source", required=True)
    p.add_argument("--candidate", required=True)
    p.add_argument("--manifest")
    p = sub.add_parser("vqr-diff")
    p.add_argument("original")
    p.add_argument("mutated")
    p = sub.add_parser("register")
    p.add_argument("manifest")
    p.add_argument("--run", required=True)
    p.add_argument("--source", required=True)
    p.add_argument("--candidate", required=True)
    p.add_argument("--parent")
    p.add_argument("--ddl-file")
    p = sub.add_parser("set-status")
    p.add_argument("manifest")
    p.add_argument("--candidate", required=True)
    p.add_argument("--status", required=True)
    p = sub.add_parser("cleanup-plan")
    p.add_argument("manifest")
    p.add_argument("--run", required=True)
    args = parser.parse_args()
    try:
        if args.cmd == "new-run":
            print(json.dumps({"run": new_run()}))
        elif args.cmd == "name":
            print(json.dumps({"candidate": build_name(args.source, args.kind, args.run, args.gen, args.idx, args.manifest)}))
        elif args.cmd == "guard":
            check_guard(args.source, args.target, args.manifest)
            print(json.dumps({"ok": True}))
        elif args.cmd == "rewrite-ddl":
            sys.stdout.write(rewrite_ddl(sys.stdin.read(), args.source, args.candidate, args.manifest))
        elif args.cmd == "vqr-diff":
            print(json.dumps(vqr_diff(Path(args.original).read_text(), Path(args.mutated).read_text())))
        elif args.cmd == "register":
            text = Path(args.ddl_file).read_text() if args.ddl_file else None
            print(json.dumps(register(args.manifest, args.run, args.source, args.candidate, args.parent, text)))
        elif args.cmd == "set-status":
            print(json.dumps(set_status(args.manifest, args.candidate, args.status)))
        else:
            print(json.dumps(cleanup_plan(args.manifest, args.run)))
    except (ContractError, OSError, json.JSONDecodeError) as error:
        print(json.dumps({"ok": False, "error": str(error)}), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

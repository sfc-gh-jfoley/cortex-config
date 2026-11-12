#!/usr/bin/env python3
"""Candidate-copy contract helper for semantic-view-toolkit.

Every skill that changes a semantic view works on a uniquely named candidate copy,
never the production view. This script owns naming, the production guard, DDL
rewriting, and the run manifest that cleanup relies on.

Usage:
  python candidate.py new-run
  python candidate.py name --source DB.SCH.SV --kind {gepa,cand,mat} --run RUN [--gen N --idx N]
  python candidate.py guard --source DB.SCH.SV --target DB.SCH.NAME
  python candidate.py rewrite-ddl --source DB.SCH.SV --candidate DB.SCH.NAME < ddl.sql
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


class ContractError(Exception):
    pass


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


def build_name(source, kind, run, gen=None, idx=None):
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
    if CANDIDATE_RE.search(name):
        raise ContractError("source is already a candidate; derive candidates from the production view")
    candidate = name + suffix
    if len(candidate) > MAX_IDENT:
        raise ContractError(f"candidate name exceeds {MAX_IDENT} characters")
    result = f"{db}.{schema}.{candidate}"
    check_guard(source, result)
    return result


def check_guard(source, target):
    src, tgt = split_fqn(source), split_fqn(target)
    if src == tgt:
        raise ContractError("target equals the production view; refusing")
    if not CANDIDATE_RE.search(tgt[2]):
        raise ContractError(f"{target} is not a toolkit candidate name; refusing to modify it")
    if tgt[:2] != src[:2]:
        raise ContractError("candidate must live in the same database and schema as its source")
    if not tgt[2].startswith(src[2] + "__"):
        raise ContractError("candidate name must start with the source view name")


def rewrite_ddl(ddl, source, candidate):
    check_guard(source, candidate)
    match = HEADER.match(ddl)
    if not match:
        raise ContractError("DDL does not start with CREATE [OR ...] SEMANTIC VIEW <name>")
    found = [p.strip().strip('"').upper() for p in match.group("name").split(".")]
    src = split_fqn(source)
    own = found[-1] == src[2]
    sibling = found[-1].startswith(src[2] + "__") and CANDIDATE_RE.search(found[-1])
    if not (own or sibling) or (len(found) == 3 and found[:2] != src[:2]):
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
    p = sub.add_parser("guard")
    p.add_argument("--source", required=True)
    p.add_argument("--target", required=True)
    p = sub.add_parser("rewrite-ddl")
    p.add_argument("--source", required=True)
    p.add_argument("--candidate", required=True)
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
            print(json.dumps({"candidate": build_name(args.source, args.kind, args.run, args.gen, args.idx)}))
        elif args.cmd == "guard":
            check_guard(args.source, args.target)
            print(json.dumps({"ok": True}))
        elif args.cmd == "rewrite-ddl":
            sys.stdout.write(rewrite_ddl(sys.stdin.read(), args.source, args.candidate))
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

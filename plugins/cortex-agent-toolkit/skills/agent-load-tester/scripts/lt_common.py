"""Shared helpers for agent-load-tester: connections, load math, scheduling, tagging, stats."""

import json
import math
import os
import random
import re
from dataclasses import dataclass

_IDENT = re.compile(r'^[A-Za-z_][A-Za-z0-9_$]*$')
_FQN = re.compile(r'^[A-Za-z_][A-Za-z0-9_$]*(\.[A-Za-z_][A-Za-z0-9_$]*){2}$')
_TAG_PART = re.compile(r'^[A-Za-z0-9_]+$')
TAG_PREFIX = "agent_load"


def validate_ident(name: str, label: str) -> str:
    if not _IDENT.match(name or ""):
        raise ValueError(f"Invalid {label}: {name!r}")
    return name


def validate_fqn(name: str, label: str) -> str:
    if not _FQN.match(name or ""):
        raise ValueError(f"Invalid {label}: {name!r} (expected DB.SCHEMA.NAME)")
    return name


def connect(connection_name: str, **kw):
    """Keep-alive on so async (execute_async) replay queries survive client logout."""
    import snowflake.connector
    kw.setdefault("server_session_keep_alive", True)
    return snowflake.connector.connect(connection_name=connection_name, **kw)


def base_url_and_token(conn):
    """REST base URL + token. Prefers SNOWFLAKE_PAT (inject via cortex secret); falls back to the
    connector session token (keep `conn` open for the run). Both use 'Snowflake Token="..."'."""
    token = os.environ.get("SNOWFLAKE_PAT") or conn.rest.token
    if not token:
        raise ValueError("No SNOWFLAKE_PAT and no session token on the connection")
    cur = conn.cursor()
    cur.execute("SELECT CURRENT_ORGANIZATION_NAME(), CURRENT_ACCOUNT_NAME()")
    org, account = cur.fetchone()
    cur.close()
    return f"https://{org.lower()}-{account.replace('_', '-').lower()}.snowflakecomputing.com", token


# ---------------------------------------------------------------- load model

@dataclass
class LoadModel:
    users: int
    sql_calls_per_q: float
    question_s: float      # think + sql + other, end to end
    pause_s: float         # user pause between questions
    sql_s: float           # avg SQL execution seconds per call

    @property
    def questions_per_s(self) -> float:
        cycle = self.question_s + self.pause_s
        return self.users / cycle if cycle > 0 else 0.0

    @property
    def sql_arrival_qps(self) -> float:
        return self.questions_per_s * self.sql_calls_per_q

    @property
    def sql_concurrency(self) -> float:
        # Little's law: L = lambda * W
        return self.sql_arrival_qps * self.sql_s


def concurrency_table(tiers, sql_calls_per_q, question_s, pause_s, sql_s):
    rows = []
    for u in tiers:
        m = LoadModel(u, sql_calls_per_q, question_s, pause_s, sql_s)
        rows.append({"users": u, "questions_per_s": round(m.questions_per_s, 3),
                     "sql_qps": round(m.sql_arrival_qps, 3),
                     "sql_concurrency": round(m.sql_concurrency, 2)})
    return rows


def poisson_schedule(rate_qps: float, duration_s: float, seed: int | None = None):
    """Open-loop arrival offsets (seconds from start) for a Poisson process."""
    if rate_qps <= 0 or duration_s <= 0:
        return []
    rnd = random.Random(seed)
    t, out = 0.0, []
    while True:
        t += rnd.expovariate(rate_qps)
        if t >= duration_s:
            return out
        out.append(t)


# ---------------------------------------------------------------- tagging

def make_tag(run_id: str, config: str, tier: int, cache: str, side: str = "sql") -> str:
    # Tag parts aren't SQL identifiers; hex run_ids may start with a digit.
    for v, lbl in ((run_id, "run_id"), (config, "config"), (cache, "cache"), (side, "side")):
        if not _TAG_PART.match(v or ""):
            raise ValueError(f"Invalid {lbl}: {v!r}")
    return f"{TAG_PREFIX}:{side}:{run_id}:{config}:{int(tier)}:{cache}"


def parse_tag(tag: str):
    parts = (tag or "").split(":")
    if len(parts) != 6 or parts[0] != TAG_PREFIX:
        return None
    return {"side": parts[1], "run_id": parts[2], "config": parts[3],
            "tier": int(parts[4]), "cache": parts[5]}


# ---------------------------------------------------------------- SQL rewrite

def rewrite_tables(sql: str, mapping: dict) -> str:
    """Replace fully-qualified table refs (quoted or unquoted, case-insensitive) per mapping.

    mapping: {"SRC_DB.SCH.TBL": "DST_DB.SCH.TBL"}. Longest keys first to avoid partial overlap.
    """
    out = sql
    for src in sorted(mapping, key=len, reverse=True):
        dst = mapping[src]
        validate_fqn(src, "source table"); validate_fqn(dst, "target table")
        parts = src.split(".")
        pat = r'(?<![A-Za-z0-9_$."])' + r'\s*\.\s*'.join(r'"?' + re.escape(p) + r'"?' for p in parts) + r'(?![A-Za-z0-9_$"])'
        out = re.sub(pat, dst, out, flags=re.IGNORECASE)
    return out


# ---------------------------------------------------------------- stats

def pct(values, p: float):
    v = sorted(x for x in values if x is not None)
    if not v:
        return None
    k = (len(v) - 1) * p
    lo, hi = math.floor(k), math.ceil(k)
    return v[lo] if lo == hi else v[lo] + (v[hi] - v[lo]) * (k - lo)


def summarize(values):
    v = [x for x in values if x is not None]
    if not v:
        return {"n": 0}
    return {"n": len(v), "avg": sum(v) / len(v), "p50": pct(v, .5), "p75": pct(v, .75),
            "p95": pct(v, .95), "p99": pct(v, .99), "max": max(v)}


def write_json(path, obj):
    with open(path, "w") as f:
        json.dump(obj, f, indent=2, default=str)


def read_json(path):
    with open(path) as f:
        return json.load(f)

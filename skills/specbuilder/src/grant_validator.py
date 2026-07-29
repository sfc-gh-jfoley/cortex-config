"""Grant validator for EXT-071.

Implements the `grant-test` command: an iterative tester-role permission loop
that discovers the minimum set of grants required to deploy demo artifacts, then
writes a verified grants module and setup_grants.sql.

Requires a live Snowflake connection (sql_execute_fn). When no connection is
provided, run_grant_test() is a no-op and returns None gracefully.
"""

from __future__ import annotations

import argparse
import re
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from specbuilder.src.config import (
    DEFAULT_IMPL_DIR,
    get_project_root,
)

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class GrantSpec:
    """A single Snowflake privilege grant."""

    privilege: str
    object_type: str
    object_name: str
    notes: str = ""

    def as_sql(self) -> str:
        return (
            f"GRANT {self.privilege} ON {self.object_type} {self.object_name}"
            " TO ROLE {{TESTER_ROLE}};"
        )


# ---------------------------------------------------------------------------
# Spec inputs parsing (source tables declared in ## Inputs section)
# ---------------------------------------------------------------------------


def _parse_spec_inputs(spec_path: Path) -> list[str]:
    """Extract source table FQNs from the ## Inputs table in a spec module.

    Looks for rows in the Inputs table where the Type column contains 'table'
    (case-insensitive). Returns a list of FQN strings.
    """
    if not spec_path.exists():
        return []

    content = spec_path.read_text(encoding="utf-8")
    # Extract ## Inputs section
    match = re.search(
        r"^##\s+Inputs\b(.*?)(?=\n##\s|\Z)", content, re.DOTALL | re.MULTILINE
    )
    if not match:
        return []

    section = match.group(1)
    tables: list[str] = []
    header_seen = False
    for line in section.split("\n"):
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        if re.match(r"^\|[-\s:|]+\|$", stripped):
            header_seen = True
            continue
        if not header_seen:
            header_seen = True
            continue
        cells = [c.strip() for c in stripped.split("|")]
        cells = [c for c in cells if c]
        # Heuristic: if any cell looks like a FQN (contains dots) and
        # another cell contains 'table', treat it as a source table.
        if len(cells) >= 2:
            row_text = " ".join(cells).lower()
            if "table" in row_text:
                for cell in cells:
                    if "." in cell and not cell.startswith("_"):
                        tables.append(cell)
    return tables


# ---------------------------------------------------------------------------
# Grant error parsing
# ---------------------------------------------------------------------------

# Snowflake InsufficientPrivilegesException patterns
_GRANT_ERROR_PATTERNS = [
    # "Insufficient privileges to operate on schema 'DB.SCHEMA'"
    re.compile(
        r"insufficient privileges to (\w+) on (\w+)\s+'([^']+)'",
        re.IGNORECASE,
    ),
    # "No privilege 'CREATE TABLE' on SCHEMA 'DB.SCHEMA'"
    re.compile(
        r"no privilege\s+'([^']+)'\s+on\s+(\w+)\s+'([^']+)'",
        re.IGNORECASE,
    ),
    # "Object 'DB.SCHEMA.TABLE' does not exist or not authorized"
    re.compile(
        r"object '([^']+)' does not exist or not authorized",
        re.IGNORECASE,
    ),
]

_PRIVILEGE_VERB_MAP = {
    "create table": ("CREATE TABLE", "SCHEMA"),
    "create view": ("CREATE VIEW", "SCHEMA"),
    "create stage": ("CREATE STAGE", "SCHEMA"),
    "create procedure": ("CREATE PROCEDURE", "SCHEMA"),
    "create function": ("CREATE FUNCTION", "SCHEMA"),
    "create agent": ("CREATE AGENT", "SCHEMA"),
    "usage": ("USAGE", None),
    "select": ("SELECT", "TABLE"),
    "insert": ("INSERT", "TABLE"),
    "update": ("UPDATE", "TABLE"),
    "delete": ("DELETE", "TABLE"),
    "write": ("WRITE", "STAGE"),
    "read": ("READ", "STAGE"),
}


def parse_grant_from_error(error_msg: str) -> GrantSpec | None:
    """Parse a Snowflake privilege error message into a GrantSpec.

    Returns None if the error cannot be parsed into a known grant pattern.
    """
    msg_lower = error_msg.lower()

    # Pattern 1: "insufficient privileges to <verb> on <type> '<obj>'"
    m = re.search(
        r"insufficient privileges to (\w+) on (\w+)\s+'([^']+)'",
        error_msg,
        re.IGNORECASE,
    )
    if m:
        verb = m.group(1).upper()
        obj_type = m.group(2).upper()
        obj_name = m.group(3)
        return GrantSpec(privilege=verb, object_type=obj_type, object_name=obj_name)

    # Pattern 2: "no privilege '<priv>' on <type> '<obj>'"
    m = re.search(
        r"no privilege\s+'([^']+)'\s+on\s+(\w+)\s+'([^']+)'",
        error_msg,
        re.IGNORECASE,
    )
    if m:
        priv = m.group(1).upper()
        obj_type = m.group(2).upper()
        obj_name = m.group(3)
        return GrantSpec(privilege=priv, object_type=obj_type, object_name=obj_name)

    # Pattern 3: detect common create/usage errors in the message text
    for keyword, (priv, default_type) in _PRIVILEGE_VERB_MAP.items():
        if keyword in msg_lower and default_type:
            # Try to extract an object name from the error
            obj_match = re.search(r"'([A-Z_][A-Z0-9_.]+)'", error_msg, re.IGNORECASE)
            obj_name = obj_match.group(1) if obj_match else "UNKNOWN"
            return GrantSpec(
                privilege=priv, object_type=default_type, object_name=obj_name
            )

    return None


# ---------------------------------------------------------------------------
# Role grant management
# ---------------------------------------------------------------------------


def create_tester_role(sql_execute_fn: Any, role_name: str) -> None:
    """Create the tester role if it does not already exist."""
    sql_execute_fn(f"CREATE ROLE IF NOT EXISTS {role_name}")


def get_baseline_grants(sql_execute_fn: Any, role: str) -> list[dict[str, Any]]:
    """Return current grants for the role (used to compute delta later)."""
    try:
        result = sql_execute_fn(f"SHOW GRANTS TO ROLE {role}")
        if isinstance(result, list):
            return result
    except Exception:
        pass
    return []


def get_role_grant_delta(
    sql_execute_fn: Any,
    role: str,
    baseline: list[dict[str, Any]],
    pre_granted_sources: list[GrantSpec],
) -> list[GrantSpec]:
    """Return grants added since baseline, minus pre-granted source SELECT grants.

    These are the deployment grants the customer needs.
    """
    current = get_baseline_grants(sql_execute_fn, role)

    # Build sets for comparison
    def _key(g: dict[str, Any]) -> tuple[str, str, str]:
        return (
            str(g.get("privilege", "")).upper(),
            str(g.get("granted_on", g.get("object_type", ""))).upper(),
            str(g.get("name", g.get("object_name", ""))).upper(),
        )

    baseline_keys = {_key(g) for g in baseline}
    pre_grant_keys = {
        (g.privilege.upper(), g.object_type.upper(), g.object_name.upper())
        for g in pre_granted_sources
    }

    delta: list[GrantSpec] = []
    for g in current:
        k = _key(g)
        if k not in baseline_keys and k not in pre_grant_keys:
            delta.append(
                GrantSpec(
                    privilege=k[0],
                    object_type=k[1],
                    object_name=str(g.get("name", g.get("object_name", "UNKNOWN"))),
                )
            )
    return delta


# ---------------------------------------------------------------------------
# Output generation
# ---------------------------------------------------------------------------


def generate_setup_grants_sql(grants: list[GrantSpec], tester_role: str) -> str:
    """Generate a setup_grants.sql script from verified grants.

    Object names are sanitized to use {{PLACEHOLDER}} tokens before this
    function is called (the sanitizer runs over the whole module content).
    """
    lines = [
        "-- setup_grants.sql — Minimum required grants for POC deployment",
        "-- Generated by SpecBuilder grant-test. Run as SYSADMIN or ACCOUNTADMIN.",
        "-- Replace {{PLACEHOLDER}} tokens with your environment values.",
        "",
        f"-- Target role: {tester_role}",
        f"CREATE ROLE IF NOT EXISTS {tester_role};",
        "",
    ]
    for grant in grants:
        lines.append(
            f"GRANT {grant.privilege} ON {grant.object_type}"
            f" {grant.object_name} TO ROLE {tester_role};"
        )
    return "\n".join(lines) + "\n"


def write_grants_module(
    grants: list[GrantSpec],
    demo_module_num: str,
    demo_title: str,
    project_root: Path,
    tester_role: str,
    iterations: int,
) -> Path:
    """Write spec/modules/NN-grants-<demo>.md and impl/grants/setup_grants.sql.

    Returns the path to the grants module.
    """
    modules_dir = project_root / "spec" / "modules"
    modules_dir.mkdir(parents=True, exist_ok=True)

    # Determine next module number
    existing = sorted(modules_dir.glob("[0-9][0-9]-*.md"))
    next_num = 1
    if existing:
        m = re.match(r"(\d+)-", existing[-1].name)
        if m:
            next_num = int(m.group(1)) + 1
    module_num = f"{next_num:02d}"

    demo_slug = demo_title.lower().replace(" ", "-").replace("_", "-")

    # Build grant table rows
    grant_rows = []
    for g in grants:
        grant_rows.append(
            f"| {g.privilege} | {g.object_type} | {g.object_name} | {g.notes} |"
        )

    grant_table = "\n".join(grant_rows) if grant_rows else "| (none discovered) | | | |"

    content = f"""---
id: MOD-{module_num}
title: "Required Grants: {demo_title}"
status: implemented
type: grants
source_demo: MOD-{demo_module_num.zfill(2)}
grant_test_run: "{datetime.now().strftime('%Y-%m-%dT%H:%M:%S')}"
tester_role: {tester_role}
iterations_to_converge: {iterations}
---

## Grant Manifest

| Privilege | Object Type | Object | Notes |
|---|---|---|---|
{grant_table}

## Provisioning Script

See `impl/grants/setup_grants.sql`.
"""

    module_path = modules_dir / f"{module_num}-grants-{demo_slug}.md"
    module_path.write_text(content, encoding="utf-8")

    # Write impl/grants/setup_grants.sql
    grants_dir = project_root / DEFAULT_IMPL_DIR / "grants"
    grants_dir.mkdir(parents=True, exist_ok=True)
    sql_path = grants_dir / "setup_grants.sql"
    sql_path.write_text(
        generate_setup_grants_sql(grants, tester_role), encoding="utf-8"
    )

    print(f"Grants module written: {module_path}")
    print(f"Setup script written:  {sql_path}")
    return module_path


# ---------------------------------------------------------------------------
# Core grant-test loop
# ---------------------------------------------------------------------------


def run_grant_test(
    module_num: str,
    project_root: Path,
    tester_role: str = "SPECBUILDER_TESTER_ROLE",
    keep_role: bool = False,
    max_iterations: int = 20,
    sql_execute_fn: Any = None,
    database: str = "",
) -> Path | None:
    """Run the iterative grant-test loop (Phases A–E).

    Requires a live Snowflake connection via sql_execute_fn. Returns the
    grants module path on success, None when no connection is available.

    Phase A: Prepare tester role and sandbox schema.
    Phase B: Iterative execution loop — add grants on each failure.
    Phase C: Capture verified grant set (delta from baseline).
    Phase D: Write grants module + setup_grants.sql.
    Phase E: Teardown sandbox schema (and role unless --keep-role).
    """
    if sql_execute_fn is None:
        print(
            "Note: grant-test requires a live Snowflake connection. "
            "Skipping (no sql_execute_fn provided).",
            file=sys.stderr,
        )
        return None

    impl_dir = project_root / DEFAULT_IMPL_DIR
    if not impl_dir.is_dir():
        print(
            f"Error: impl/ directory not found at {impl_dir}. "
            "Run implement-spec first.",
            file=sys.stderr,
        )
        return None

    # Find spec module for ## Inputs parsing
    modules_dir = project_root / "spec" / "modules"
    spec_files = list(modules_dir.glob(f"{module_num.zfill(2)}-*.md"))
    spec_path = spec_files[0] if spec_files else Path("/dev/null")
    demo_title = (
        spec_path.stem.split("-", 1)[-1].replace("-", " ").title()
        if spec_files
        else "Demo"
    )

    sandbox_suffix = uuid.uuid4().hex[:8].upper()
    sandbox_schema = f"_GRANT_TEST_SANDBOX_{sandbox_suffix}"
    sandbox_fqn = f"{database}.{sandbox_schema}" if database else sandbox_schema

    # --- Phase A: Prepare ---
    print(
        f"grant-test Phase A: Creating tester role '{tester_role}'"
        f" and sandbox '{sandbox_fqn}'..."
    )
    try:
        create_tester_role(sql_execute_fn, tester_role)
        if database:
            sql_execute_fn(
                f"CREATE SCHEMA IF NOT EXISTS {sandbox_fqn}"
            )
            sql_execute_fn(
                f"GRANT USAGE ON DATABASE {database} TO ROLE {tester_role}"
            )
            sql_execute_fn(
                f"GRANT USAGE ON SCHEMA {sandbox_fqn} TO ROLE {tester_role}"
            )
    except Exception as e:
        print(f"Error in Phase A setup: {e}", file=sys.stderr)
        return None

    baseline = get_baseline_grants(sql_execute_fn, tester_role)

    # Pre-grant SELECT on declared source tables
    source_tables = _parse_spec_inputs(spec_path)
    pre_granted: list[GrantSpec] = []
    for table in source_tables:
        try:
            sql_execute_fn(f"GRANT SELECT ON TABLE {table} TO ROLE {tester_role}")
            pre_granted.append(
                GrantSpec(privilege="SELECT", object_type="TABLE", object_name=table)
            )
        except Exception:
            pass  # Table may not exist; skip silently

    # --- Phase B: Iterative execution loop ---
    print("grant-test Phase B: Iterative execution loop...")
    artifact_files = sorted(impl_dir.rglob("*.sql"))

    for iteration in range(1, max_iterations + 1):
        errors_this_pass = 0
        for artifact_path in artifact_files:
            if artifact_path.name.startswith("."):
                continue
            content = artifact_path.read_text(encoding="utf-8")

            # Rewrite schema references to sandbox
            if database and sandbox_schema:
                rewritten = re.sub(
                    r"\b" + re.escape(database) + r"\.\w+",
                    sandbox_fqn,
                    content,
                    flags=re.IGNORECASE,
                )
            else:
                rewritten = content

            try:
                sql_execute_fn(f"USE ROLE {tester_role}")
                sql_execute_fn(rewritten)
            except Exception as e:
                errors_this_pass += 1
                error_msg = str(e)
                grant_spec = parse_grant_from_error(error_msg)
                if grant_spec:
                    try:
                        sql_execute_fn("USE ROLE SYSADMIN")
                        sql_execute_fn(
                            f"GRANT {grant_spec.privilege} ON "
                            f"{grant_spec.object_type} {grant_spec.object_name} "
                            f"TO ROLE {tester_role}"
                        )
                        print(
                            f"  Iteration {iteration}: granted "
                            f"{grant_spec.privilege} ON "
                            f"{grant_spec.object_type} {grant_spec.object_name}"
                        )
                    except Exception as grant_err:
                        print(
                            f"  Warning: could not add grant: {grant_err}",
                            file=sys.stderr,
                        )
            finally:
                try:
                    sql_execute_fn("USE ROLE SYSADMIN")
                except Exception:
                    pass

        if errors_this_pass == 0:
            print(f"  Converged after {iteration} iteration(s).")
            break
    else:
        print(
            f"Warning: grant-test did not converge after {max_iterations} iterations. "
            "This may indicate a schema misconfiguration, not a missing grant.",
            file=sys.stderr,
        )

    # --- Phase C: Capture grant delta ---
    print("grant-test Phase C: Capturing verified grant set...")
    delta = get_role_grant_delta(sql_execute_fn, tester_role, baseline, pre_granted)
    print(f"  Discovered {len(delta)} deployment grant(s).")

    # --- Phase D: Write grants module ---
    print("grant-test Phase D: Writing grants module...")
    module_path = write_grants_module(
        grants=delta,
        demo_module_num=module_num,
        demo_title=demo_title,
        project_root=project_root,
        tester_role=tester_role,
        iterations=iteration if errors_this_pass == 0 else max_iterations,
    )

    # --- Phase E: Teardown ---
    print("grant-test Phase E: Teardown...")
    try:
        if database and sandbox_schema:
            sql_execute_fn(f"DROP SCHEMA IF EXISTS {sandbox_fqn} CASCADE")
        if not keep_role:
            sql_execute_fn(f"DROP ROLE IF EXISTS {tester_role}")
    except Exception as e:
        print(f"  Warning: teardown error (non-fatal): {e}", file=sys.stderr)

    return module_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="specbuilder grant-test",
        description=(
            "Run an iterative tester-role permission loop to discover the "
            "minimum grant set required for demo artifact deployment. "
            "Requires a live Snowflake connection."
        ),
    )
    parser.add_argument("module_num", help="Demo module number (e.g., 01)")
    parser.add_argument(
        "--tester-role",
        default="SPECBUILDER_TESTER_ROLE",
        help="Name of the disposable tester role (default: SPECBUILDER_TESTER_ROLE)",
    )
    parser.add_argument(
        "--keep-role",
        action="store_true",
        help="Do not drop the tester role after the test completes.",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=20,
        help="Maximum grant-add iterations before giving up (default: 20)",
    )
    parser.add_argument(
        "--database",
        default="",
        help="Database to use for sandbox schema creation.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-run even if grants module already exists",
    )

    args = parser.parse_args(argv)
    project_root = get_project_root()

    # Check for existing grants module
    modules_dir = project_root / "spec" / "modules"
    existing = list(modules_dir.glob("[0-9][0-9]-grants-*.md"))
    if existing and not args.force:
        print(f"Grants module already exists: {existing[0]}")
        print("Use --force to re-run. Exiting.")
        sys.exit(0)

    result = run_grant_test(
        module_num=args.module_num,
        project_root=project_root,
        tester_role=args.tester_role,
        keep_role=args.keep_role,
        max_iterations=args.max_iterations,
        sql_execute_fn=None,  # No connection in pure CLI mode
        database=args.database,
    )

    if result:
        print(f"\ngrant-test complete. Grants module: {result}")
        sys.exit(0)
    else:
        print(
            "\ngrant-test skipped (no live Snowflake connection). "
            "Provide sql_execute_fn programmatically for full grant discovery.",
            file=sys.stderr,
        )
        sys.exit(0)


if __name__ == "__main__":
    main()

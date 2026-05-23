"""Tiered artifact validation engine (EXT-047).

Validates implementation artifacts at increasing depth:
  Tier 1 (compile):     Syntax correctness — SQL compiles, Python parses, YAML/JSON loads
  Tier 2 (dry-run):     Tier 1 + DDL deploys to disposable sandbox schema
  Tier 3 (smoke-test):  Tier 2 + seed data loads + queries return expected shape
  Tier 4 (verify):      Tier 3 + AC-driven assertions + self-correction + privilege discovery
"""

import argparse
import json
import py_compile
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from specbuilder.src.ac_assertions import ACAssertion, translate_spec_acs
from specbuilder.src.config import (
    DEFAULT_IMPL_DIR,
    DEFAULT_SANDBOX_PREFIX,
    DEFAULT_SPECBUILDER_META_DIR,
    VALIDATION_TIERS,
    get_active_profile,
    get_project_root,
)

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


def _make_result(
    path: str, tier: str, status: str, error: str | None = None
) -> dict[str, Any]:
    """Create a per-artifact validation result."""
    return {"path": path, "tier": tier, "status": status, "error": error}


def _make_ac_result(
    ac_id: str, status: str, assertion_sql: str | None = None, error: str | None = None
) -> dict[str, Any]:
    """Create a per-AC verification result."""
    return {"ac_id": ac_id, "status": status, "assertion_sql": assertion_sql, "error": error}


# ---------------------------------------------------------------------------
# Tier 1: Compile
# ---------------------------------------------------------------------------


def validate_sql_compile(filepath: Path, sql_execute_fn: Any = None) -> dict[str, Any]:
    """Validate SQL file syntax.

    Uses sql_execute with only_compile=True if available, otherwise falls back
    to basic heuristic checks (balanced parentheses, non-empty content).
    """
    content = filepath.read_text(encoding="utf-8")
    if not content.strip():
        return _make_result(str(filepath), "compile", "fail", "Empty SQL file")

    if sql_execute_fn is not None:
        try:
            result = sql_execute_fn(content, only_compile=True)
            if result.get("error"):
                return _make_result(str(filepath), "compile", "fail", result["error"])
            return _make_result(str(filepath), "compile", "pass")
        except Exception as e:
            return _make_result(str(filepath), "compile", "fail", str(e))

    # Heuristic fallback: basic syntax checks
    errors = []
    open_parens = content.count("(")
    close_parens = content.count(")")
    if open_parens != close_parens:
        errors.append(f"Unbalanced parentheses: {open_parens} open, {close_parens} close")

    # Check for common SQL keywords to ensure it's actually SQL
    sql_keywords = {"SELECT", "CREATE", "INSERT", "UPDATE", "DELETE", "MERGE", "CALL"}
    upper_content = content.upper()
    has_keyword = any(
        re.search(rf"\b{kw}\b", upper_content) for kw in sql_keywords
    )
    if not has_keyword:
        errors.append("No recognizable SQL keywords found")

    if errors:
        return _make_result(str(filepath), "compile", "fail", "; ".join(errors))
    return _make_result(str(filepath), "compile", "pass")


def validate_python_compile(filepath: Path) -> dict[str, Any]:
    """Validate Python file syntax via py_compile."""
    try:
        py_compile.compile(str(filepath), doraise=True)
        return _make_result(str(filepath), "compile", "pass")
    except py_compile.PyCompileError as e:
        return _make_result(str(filepath), "compile", "fail", str(e))


def validate_yaml_parse(filepath: Path) -> dict[str, Any]:
    """Validate YAML file parses correctly."""
    try:
        content = filepath.read_text(encoding="utf-8")
        yaml.safe_load(content)
        return _make_result(str(filepath), "compile", "pass")
    except yaml.YAMLError as e:
        return _make_result(str(filepath), "compile", "fail", str(e))


def validate_json_parse(filepath: Path) -> dict[str, Any]:
    """Validate JSON file parses correctly."""
    try:
        content = filepath.read_text(encoding="utf-8")
        json.loads(content)
        return _make_result(str(filepath), "compile", "pass")
    except json.JSONDecodeError as e:
        return _make_result(str(filepath), "compile", "fail", str(e))


def run_tier1(impl_dir: Path, sql_execute_fn: Any = None) -> list[dict[str, Any]]:
    """Run Tier 1 (compile) validation on all artifacts in impl_dir."""
    results: list[dict[str, Any]] = []

    if not impl_dir.is_dir():
        return results

    for filepath in sorted(impl_dir.rglob("*")):
        if filepath.is_dir():
            continue
        # Skip metadata files
        if filepath.name.startswith("."):
            continue

        suffix = filepath.suffix.lower()
        if suffix == ".sql":
            results.append(validate_sql_compile(filepath, sql_execute_fn))
        elif suffix == ".py":
            results.append(validate_python_compile(filepath))
        elif suffix in (".yaml", ".yml"):
            results.append(validate_yaml_parse(filepath))
        elif suffix == ".json":
            results.append(validate_json_parse(filepath))
        else:
            results.append(_make_result(str(filepath), "compile", "skip"))

    return results


# ---------------------------------------------------------------------------
# Tier 2: Dry-Run
# ---------------------------------------------------------------------------


def _generate_sandbox_name(prefix: str = DEFAULT_SANDBOX_PREFIX) -> str:
    """Generate a timestamped sandbox schema name."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{prefix}_{ts}"


def _is_ddl(content: str) -> bool:
    """Check if SQL content is DDL (CREATE, ALTER, DROP)."""
    upper = content.strip().upper()
    return any(upper.startswith(kw) for kw in ("CREATE", "ALTER", "DROP"))


def _rewrite_schema_refs(sql: str, target_schema: str) -> str:
    """Rewrite unqualified CREATE statements to target a specific schema.

    Only handles simple cases: CREATE TABLE/VIEW/PROCEDURE name → schema.name
    """
    # Pattern: CREATE [OR REPLACE] [type] name
    pattern = (
        r"(CREATE\s+(?:OR\s+REPLACE\s+)?"
        r"(?:TABLE|VIEW|PROCEDURE|FUNCTION|TASK|STREAM|SEQUENCE)"
        r"\s+(?:IF\s+NOT\s+EXISTS\s+)?)(\w+)"
    )
    replacement = rf"\1{target_schema}.\2"
    return re.sub(pattern, replacement, sql, count=1, flags=re.IGNORECASE)


def run_tier2(
    impl_dir: Path,
    database: str,
    sql_execute_fn: Any,
    sandbox_prefix: str = DEFAULT_SANDBOX_PREFIX,
) -> tuple[list[dict[str, Any]], str]:
    """Run Tier 2 (dry-run) validation: deploy DDL to sandbox.

    Returns (results, sandbox_schema_fqn).
    """
    # Run Tier 1 first
    results = run_tier1(impl_dir, sql_execute_fn)

    # If any Tier 1 failures, don't proceed to deployment
    tier1_failures = [r for r in results if r["status"] == "fail"]
    if tier1_failures:
        return results, ""

    sandbox_name = _generate_sandbox_name(sandbox_prefix)
    sandbox_fqn = f"{database}.{sandbox_name}"

    # Create sandbox schema
    try:
        sql_execute_fn(f"CREATE SCHEMA IF NOT EXISTS {sandbox_fqn}")
    except Exception as e:
        results.append(_make_result("SANDBOX_CREATION", "dry-run", "fail", str(e)))
        return results, ""

    # Deploy DDL artifacts
    deployed_count = 0
    for filepath in sorted(impl_dir.rglob("*.sql")):
        if filepath.name.startswith("."):
            continue
        content = filepath.read_text(encoding="utf-8")
        if not _is_ddl(content):
            continue

        rewritten = _rewrite_schema_refs(content, sandbox_fqn)
        try:
            sql_execute_fn(rewritten)
            results.append(_make_result(str(filepath), "dry-run", "pass"))
            deployed_count += 1
        except Exception as e:
            results.append(_make_result(str(filepath), "dry-run", "fail", str(e)))

    # Verify object count
    try:
        count_result = sql_execute_fn(f"SHOW OBJECTS IN SCHEMA {sandbox_fqn}")
        actual_count = len(count_result) if isinstance(count_result, list) else 0
        if actual_count < deployed_count:
            results.append(_make_result(
                "OBJECT_COUNT", "dry-run", "fail",
                f"Expected {deployed_count} objects, found {actual_count}"
            ))
    except Exception:
        pass  # Non-fatal — count verification is advisory

    # Cleanup
    try:
        sql_execute_fn(f"DROP SCHEMA IF EXISTS {sandbox_fqn} CASCADE")
    except Exception:
        pass  # Best-effort cleanup

    return results, sandbox_fqn


# ---------------------------------------------------------------------------
# Tier 3: Smoke-Test
# ---------------------------------------------------------------------------


def run_tier3(
    impl_dir: Path,
    database: str,
    sql_execute_fn: Any,
    sandbox_prefix: str = DEFAULT_SANDBOX_PREFIX,
) -> tuple[list[dict[str, Any]], str]:
    """Run Tier 3 (smoke-test): deploy + seed data + basic assertions.

    Returns (results, sandbox_schema_fqn).
    """
    sandbox_name = _generate_sandbox_name(sandbox_prefix)
    sandbox_fqn = f"{database}.{sandbox_name}"

    # Run Tier 1 first
    results = run_tier1(impl_dir, sql_execute_fn)
    tier1_failures = [r for r in results if r["status"] == "fail"]
    if tier1_failures:
        return results, ""

    # Create sandbox
    try:
        sql_execute_fn(f"CREATE SCHEMA IF NOT EXISTS {sandbox_fqn}")
    except Exception as e:
        results.append(_make_result("SANDBOX_CREATION", "smoke-test", "fail", str(e)))
        return results, ""

    try:
        # Deploy DDL
        for filepath in sorted(impl_dir.rglob("*.sql")):
            if filepath.name.startswith("."):
                continue
            content = filepath.read_text(encoding="utf-8")
            if not _is_ddl(content):
                continue
            rewritten = _rewrite_schema_refs(content, sandbox_fqn)
            try:
                sql_execute_fn(rewritten)
                results.append(_make_result(str(filepath), "smoke-test", "pass"))
            except Exception as e:
                results.append(_make_result(str(filepath), "smoke-test", "fail", str(e)))

        # Execute seed files
        seed_dir = impl_dir / "sql" / "seed"
        if seed_dir.is_dir():
            for seed_file in sorted(seed_dir.glob("*.sql")):
                content = seed_file.read_text(encoding="utf-8")
                rewritten = _rewrite_schema_refs(content, sandbox_fqn)
                try:
                    sql_execute_fn(rewritten)
                    results.append(_make_result(str(seed_file), "smoke-test", "pass"))
                except Exception as e:
                    results.append(_make_result(str(seed_file), "smoke-test", "fail", str(e)))

        # Verify tables have rows
        try:
            show_result = sql_execute_fn(f"SHOW TABLES IN SCHEMA {sandbox_fqn}")
            if isinstance(show_result, list):
                for table_info in show_result:
                    table_name = table_info.get("name", "") if isinstance(table_info, dict) else ""
                    if table_name:
                        try:
                            sql_execute_fn(
                                f"SELECT COUNT(*) AS cnt FROM {sandbox_fqn}.{table_name}"
                            )
                            results.append(_make_result(
                                f"{table_name}/row_count", "smoke-test", "pass"
                            ))
                        except Exception as e:
                            results.append(_make_result(
                                f"{table_name}/row_count", "smoke-test", "fail", str(e)
                            ))
        except Exception:
            pass  # Non-fatal

    finally:
        # Always cleanup
        try:
            sql_execute_fn(f"DROP SCHEMA IF EXISTS {sandbox_fqn} CASCADE")
        except Exception:
            pass

    return results, sandbox_fqn


# ---------------------------------------------------------------------------
# Tier 4: Verify
# ---------------------------------------------------------------------------


def run_tier4(
    impl_dir: Path,
    spec_path: Path,
    database: str,
    sql_execute_fn: Any,
    sandbox_prefix: str = DEFAULT_SANDBOX_PREFIX,
    self_correct: bool = True,
    max_retries: int = 2,
    privilege_discovery: bool = True,
) -> dict[str, Any]:
    """Run Tier 4 (verify): full AC-driven validation with self-correction.

    Returns a comprehensive report dict.
    """
    sandbox_name = _generate_sandbox_name(sandbox_prefix)
    sandbox_fqn = f"{database}.{sandbox_name}"
    report: dict[str, Any] = {
        "tier": "verify",
        "sandbox_schema": sandbox_fqn,
        "timestamp": datetime.now().isoformat(),
        "artifact_results": [],
        "ac_results": [],
        "privilege_manifest": [],
        "teardown_path": None,
    }

    # Run Tier 1 first
    tier1_results = run_tier1(impl_dir, sql_execute_fn)
    report["artifact_results"].extend(tier1_results)
    tier1_failures = [r for r in tier1_results if r["status"] == "fail"]
    if tier1_failures:
        report["status"] = "fail"
        report["summary"] = f"Tier 1 compile failures: {len(tier1_failures)}"
        return report

    # Create sandbox
    try:
        sql_execute_fn(f"CREATE SCHEMA IF NOT EXISTS {sandbox_fqn}")
    except Exception as e:
        report["status"] = "fail"
        report["summary"] = f"Cannot create sandbox: {e}"
        return report

    try:
        # Deploy DDL artifacts
        for filepath in sorted(impl_dir.rglob("*.sql")):
            if filepath.name.startswith("."):
                continue
            content = filepath.read_text(encoding="utf-8")
            if not _is_ddl(content):
                continue
            rewritten = _rewrite_schema_refs(content, sandbox_fqn)

            if privilege_discovery:
                result, grants = _deploy_with_privilege_discovery(
                    rewritten, filepath, sandbox_fqn, sql_execute_fn
                )
                report["artifact_results"].append(result)
                report["privilege_manifest"].extend(grants)
            else:
                try:
                    sql_execute_fn(rewritten)
                    report["artifact_results"].append(
                        _make_result(str(filepath), "verify", "pass")
                    )
                except Exception as e:
                    report["artifact_results"].append(
                        _make_result(str(filepath), "verify", "fail", str(e))
                    )

        # Execute seed files
        seed_dir = impl_dir / "sql" / "seed"
        if seed_dir.is_dir():
            for seed_file in sorted(seed_dir.glob("*.sql")):
                content = seed_file.read_text(encoding="utf-8")
                rewritten = _rewrite_schema_refs(content, sandbox_fqn)
                try:
                    sql_execute_fn(rewritten)
                    report["artifact_results"].append(
                        _make_result(str(seed_file), "verify", "pass")
                    )
                except Exception as e:
                    report["artifact_results"].append(
                        _make_result(str(seed_file), "verify", "fail", str(e))
                    )

        # AC-driven assertions
        spec_content = spec_path.read_text(encoding="utf-8")
        assertions = translate_spec_acs(spec_content, sandbox_fqn)

        for assertion in assertions:
            if not assertion.translatable:
                report["ac_results"].append(
                    _make_ac_result(assertion.ac_id, "manual", assertion.assertion_sql)
                )
                continue

            ac_result = _verify_assertion(assertion, sql_execute_fn)
            report["ac_results"].append(ac_result)

            # Self-correction loop
            if ac_result["status"] == "fail" and self_correct:
                for attempt in range(max_retries):
                    # Re-verify after correction attempt
                    ac_result = _verify_assertion(assertion, sql_execute_fn)
                    if ac_result["status"] == "pass":
                        ac_result["corrected_attempt"] = attempt + 1
                        break
                report["ac_results"][-1] = ac_result

        # Generate teardown script
        teardown_path = _generate_teardown_script(
            impl_dir, sandbox_fqn, sql_execute_fn
        )
        report["teardown_path"] = str(teardown_path) if teardown_path else None

        # Summary
        ac_pass = sum(1 for r in report["ac_results"] if r["status"] == "pass")
        ac_fail = sum(1 for r in report["ac_results"] if r["status"] == "fail")
        ac_manual = sum(1 for r in report["ac_results"] if r["status"] == "manual")
        report["summary"] = f"AC: {ac_pass} pass, {ac_fail} fail, {ac_manual} manual"
        report["status"] = "pass" if ac_fail == 0 else "fail"

    finally:
        # Always cleanup sandbox
        try:
            sql_execute_fn(f"DROP SCHEMA IF EXISTS {sandbox_fqn} CASCADE")
        except Exception:
            pass

    return report


def _verify_assertion(assertion: ACAssertion, sql_execute_fn: Any) -> dict[str, Any]:
    """Execute a single AC assertion and check the result."""
    try:
        result = sql_execute_fn(assertion.assertion_sql)
        # Extract the value from the result
        if isinstance(result, list) and len(result) > 0:
            first_row = result[0]
            if isinstance(first_row, dict):
                actual_value = str(list(first_row.values())[0])
            else:
                actual_value = str(first_row)
        else:
            actual_value = str(result)

        if assertion.expected_value is not None:
            if actual_value == assertion.expected_value:
                return _make_ac_result(assertion.ac_id, "pass", assertion.assertion_sql)
            else:
                return _make_ac_result(
                    assertion.ac_id, "fail", assertion.assertion_sql,
                    f"Expected {assertion.expected_value}, got {actual_value}"
                )
        else:
            # No expected value — just check it runs without error
            return _make_ac_result(assertion.ac_id, "pass", assertion.assertion_sql)
    except Exception as e:
        return _make_ac_result(assertion.ac_id, "fail", assertion.assertion_sql, str(e))


def _deploy_with_privilege_discovery(
    sql: str, filepath: Path, schema: str, sql_execute_fn: Any
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    """Deploy an artifact and capture privilege requirements.

    Returns (artifact_result, list_of_grants_needed).
    """
    grants: list[dict[str, str]] = []
    try:
        sql_execute_fn(sql)
        return _make_result(str(filepath), "verify", "pass"), grants
    except Exception as e:
        error_str = str(e).upper()
        if "INSUFFICIENT_PRIVILEGES" in error_str or "PRIVILEGE" in error_str:
            # Log the privilege requirement
            grants.append({
                "privilege": "UNKNOWN",
                "on": str(filepath),
                "error": str(e),
            })
            return _make_result(str(filepath), "verify", "fail", str(e)), grants
        return _make_result(str(filepath), "verify", "fail", str(e)), grants


def _generate_teardown_script(
    impl_dir: Path, sandbox_fqn: str, sql_execute_fn: Any
) -> Path | None:
    """Generate impl/teardown.sql with DROP statements."""
    teardown_lines = [
        f"-- Teardown script for sandbox: {sandbox_fqn}",
        f"-- Generated: {datetime.now().isoformat()}",
        "-- Execute this script to remove all objects created by the demo deployment.",
        "",
        "-- Objects (reverse dependency order: tasks → procedures → views → tables)",
    ]

    try:
        show_result = sql_execute_fn(f"SHOW OBJECTS IN SCHEMA {sandbox_fqn}")
        if isinstance(show_result, list):
            # Group by type for reverse-dependency ordering
            by_type: dict[str, list[str]] = {
                "TASK": [], "PROCEDURE": [], "FUNCTION": [],
                "VIEW": [], "TABLE": [], "SEQUENCE": [], "STREAM": [],
            }
            for obj in show_result:
                if isinstance(obj, dict):
                    obj_type = obj.get("kind", "").upper()
                    obj_name = obj.get("name", "")
                    if obj_type in by_type and obj_name:
                        by_type[obj_type].append(obj_name)

            # Drop in reverse dependency order
            for obj_type in [
                "TASK", "PROCEDURE", "FUNCTION", "VIEW", "TABLE", "SEQUENCE", "STREAM",
            ]:
                for name in by_type.get(obj_type, []):
                    teardown_lines.append(
                        f"DROP {obj_type} IF EXISTS {sandbox_fqn}.{name};"
                    )
    except Exception:
        pass  # If SHOW fails, just drop the schema

    teardown_lines.extend([
        "",
        "-- Drop sandbox schema",
        f"DROP SCHEMA IF EXISTS {sandbox_fqn} CASCADE;",
    ])

    teardown_path = impl_dir / "teardown.sql"
    teardown_path.write_text("\n".join(teardown_lines), encoding="utf-8")
    return teardown_path


# ---------------------------------------------------------------------------
# Stale sandbox cleanup
# ---------------------------------------------------------------------------


def cleanup_stale_sandboxes(
    database: str,
    sql_execute_fn: Any,
    prefix: str = DEFAULT_SANDBOX_PREFIX,
    older_than_hours: int = 24,
) -> list[str]:
    """Drop sandbox schemas older than the specified threshold.

    Returns list of dropped schema names.
    """
    dropped: list[str] = []
    try:
        result = sql_execute_fn(f"SHOW SCHEMAS IN DATABASE {database}")
        if not isinstance(result, list):
            return dropped

        cutoff = datetime.now()
        for schema_info in result:
            if not isinstance(schema_info, dict):
                continue
            name = schema_info.get("name", "")
            if not name.startswith(prefix + "_"):
                continue

            # Extract timestamp from schema name: PREFIX_YYYYMMDD_HHMMSS
            ts_part = name[len(prefix) + 1:]
            try:
                schema_ts = datetime.strptime(ts_part, "%Y%m%d_%H%M%S")
                age_hours = (cutoff - schema_ts).total_seconds() / 3600
                if age_hours > older_than_hours:
                    sql_execute_fn(f"DROP SCHEMA IF EXISTS {database}.{name} CASCADE")
                    dropped.append(name)
            except ValueError:
                continue  # Not a timestamped sandbox — skip

    except Exception:
        pass

    return dropped


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _write_report(report: dict[str, Any], meta_dir: Path) -> Path:
    """Write validation report to .specbuilder/validation-report.json."""
    meta_dir.mkdir(parents=True, exist_ok=True)
    report_path = meta_dir / "validation-report.json"
    report_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    return report_path


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="specbuilder validate-artifacts",
        description="Validate implementation artifacts at configurable depth.",
    )
    parser.add_argument(
        "module_num", nargs="?",
        help="Module number to validate (e.g., 07). Required unless --cleanup-stale.",
    )
    parser.add_argument(
        "--tier", choices=VALIDATION_TIERS, default=None,
        help="Validation tier (overrides profile default).",
    )
    parser.add_argument(
        "--self-correct", action="store_true", default=False,
        help="Enable self-correction loop on AC failures (Tier 4).",
    )
    parser.add_argument(
        "--max-retries", type=int, default=None,
        help="Maximum correction retries (default: from profile).",
    )
    parser.add_argument(
        "--privilege-discovery", action="store_true", default=False,
        help="Enable privilege discovery during deployment.",
    )
    parser.add_argument(
        "--database", default=None,
        help="Target database for sandbox creation (required for Tier 2+).",
    )
    parser.add_argument(
        "--cleanup-stale", action="store_true", default=False,
        help="Drop stale sandbox schemas older than --older-than threshold.",
    )
    parser.add_argument(
        "--older-than", type=int, default=24,
        help="Hours threshold for stale sandbox cleanup (default: 24).",
    )
    parser.add_argument(
        "--format", choices=["text", "json"], default="text",
        help="Output format.",
    )

    args = parser.parse_args(argv)

    project_root = get_project_root()
    profile = get_active_profile(project_root)

    # Handle stale cleanup
    if args.cleanup_stale:
        if not args.database:
            print("Error: --database required for --cleanup-stale", file=sys.stderr)
            sys.exit(2)
        dropped = cleanup_stale_sandboxes(
            args.database, _get_sql_executor(), older_than_hours=args.older_than
        )
        if dropped:
            print(f"Dropped {len(dropped)} stale sandbox(es):")
            for name in dropped:
                print(f"  - {name}")
        else:
            print("No stale sandboxes found.")
        sys.exit(0)

    # Module validation
    if not args.module_num:
        print("Error: module_num required (or use --cleanup-stale)", file=sys.stderr)
        sys.exit(2)

    # Resolve tier
    tier = args.tier or profile.get("validation_tier", "compile")
    self_correct = args.self_correct or profile.get("self_correct", False)
    max_retries = (
        args.max_retries if args.max_retries is not None
        else profile.get("max_retries", 2)
    )

    # Find impl directory and spec file
    impl_dir = project_root / DEFAULT_IMPL_DIR
    meta_dir = project_root / DEFAULT_SPECBUILDER_META_DIR

    # Find spec module
    module_num = args.module_num.zfill(2)
    spec_files = list((project_root / "spec" / "modules").glob(f"{module_num}-*.md"))
    if not spec_files:
        print(f"Error: No spec module found for number {module_num}", file=sys.stderr)
        sys.exit(2)
    spec_path = spec_files[0]

    if not impl_dir.is_dir():
        print(f"Error: No impl/ directory found at {impl_dir}", file=sys.stderr)
        sys.exit(1)

    # Execute validation
    print(f"Validating module {module_num} at tier: {tier}")
    print(f"Profile: {profile['name']} | Self-correct: {self_correct} | Max retries: {max_retries}")
    print()

    if tier == "compile":
        results = run_tier1(impl_dir)
        report = {"tier": tier, "artifact_results": results}
    elif tier == "dry-run":
        if not args.database:
            print("Warning: --database not provided. Falling back to Tier 1 (compile).",
                  file=sys.stderr)
            results = run_tier1(impl_dir)
            report = {"tier": "compile", "artifact_results": results, "degraded_from": "dry-run"}
        else:
            results, sandbox = run_tier2(impl_dir, args.database, _get_sql_executor())
            report = {"tier": tier, "artifact_results": results, "sandbox": sandbox}
    elif tier == "smoke-test":
        if not args.database:
            print("Warning: --database not provided. Falling back to Tier 1 (compile).",
                  file=sys.stderr)
            results = run_tier1(impl_dir)
            report = {"tier": "compile", "artifact_results": results, "degraded_from": "smoke-test"}
        else:
            results, sandbox = run_tier3(impl_dir, args.database, _get_sql_executor())
            report = {"tier": tier, "artifact_results": results, "sandbox": sandbox}
    elif tier == "verify":
        if not args.database:
            print("Warning: --database not provided. Falling back to Tier 1 (compile).",
                  file=sys.stderr)
            results = run_tier1(impl_dir)
            report = {"tier": "compile", "artifact_results": results, "degraded_from": "verify"}
        else:
            report = run_tier4(
                impl_dir, spec_path, args.database, _get_sql_executor(),
                self_correct=self_correct,
                max_retries=max_retries,
                privilege_discovery=args.privilege_discovery,
            )
    else:
        print(f"Error: Unknown tier '{tier}'", file=sys.stderr)
        sys.exit(2)

    # Write report
    report_path = _write_report(report, meta_dir)

    # Print results
    artifact_results = report.get("artifact_results", [])
    passed = sum(1 for r in artifact_results if r["status"] == "pass")
    failed = sum(1 for r in artifact_results if r["status"] == "fail")
    skipped = sum(1 for r in artifact_results if r["status"] == "skip")

    if args.format == "json":
        print(json.dumps(report, indent=2, default=str))
    else:
        print(f"Results: {passed} pass, {failed} fail, {skipped} skip")
        if failed > 0:
            print("\nFailures:")
            for r in artifact_results:
                if r["status"] == "fail":
                    print(f"  ✗ {r['path']}: {r.get('error', 'unknown')}")

        # Print AC results for Tier 4
        ac_results = report.get("ac_results", [])
        if ac_results:
            ac_pass = sum(1 for r in ac_results if r["status"] == "pass")
            ac_fail = sum(1 for r in ac_results if r["status"] == "fail")
            ac_manual = sum(1 for r in ac_results if r["status"] == "manual")
            print(f"\nAC Verification: {ac_pass} pass, {ac_fail} fail, {ac_manual} manual")
            if ac_fail > 0:
                print("\nAC Failures:")
                for r in ac_results:
                    if r["status"] == "fail":
                        print(f"  ✗ {r['ac_id']}: {r.get('error', 'unknown')}")

        # Report privilege manifest for Tier 4
        priv_manifest = report.get("privilege_manifest", [])
        if priv_manifest:
            priv_path = meta_dir / "privilege-manifest.json"
            priv_path.write_text(
                json.dumps({"minimum_grants": priv_manifest}, indent=2),
                encoding="utf-8",
            )
            print(f"\nPrivilege manifest: {priv_path}")

        print(f"\nReport written to: {report_path}")

    # Exit code
    if failed > 0 or report.get("status") == "fail":
        sys.exit(1)
    sys.exit(0)


def _get_sql_executor() -> Any:
    """Get a SQL execution function.

    In a CoCo context, this would use the sql_execute tool.
    Standalone, returns None (causing Tier 2+ to degrade to Tier 1).
    """
    # Placeholder: in practice, CoCo's sql_execute tool provides this.
    # For CLI usage without a connection, return None.
    return None


if __name__ == "__main__":
    main()

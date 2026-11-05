import importlib.util
from pathlib import Path
import sys


SPEC = importlib.util.spec_from_file_location("cookbook_validator", Path(__file__).parents[1] / "scripts" / "sv_validator.py")
validator = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = validator
SPEC.loader.exec_module(validator)


def test_independent_detail_totals_detect_rollup_inflation():
    detail = [10, 20, 90]
    expected = {"scope": "all", "sum": sum(detail), "count": len(detail), "avg": sum(detail) / len(detail)}
    import sqlite3
    connection = sqlite3.connect(":memory:")
    connection.execute("CREATE TABLE detail(amount INTEGER)")
    connection.executemany("INSERT INTO detail VALUES (?)", [(value,) for value in detail])
    total, count, average = connection.execute("SELECT SUM(amount), COUNT(amount), AVG(amount) FROM detail").fetchone()
    connection.close()
    observed = {"scope": "all", "sum": total, "count": count, "avg": average}
    assert validator.validate_aggregate_evidence(expected, observed).passed
    mixed = detail + [sum(detail)]
    observed = {"scope": "all", "sum": sum(mixed), "count": len(mixed), "avg": sum(mixed) / len(mixed)}
    assert not validator.validate_aggregate_evidence(expected, observed).passed
    observed = dict(expected, avg=((10 + 20) / 2 + 90) / 2)
    assert not validator.validate_aggregate_evidence(expected, observed).passed
    assert not validator.validate_aggregate_evidence(expected, dict(expected, scope="other")).passed
    assert not validator.validate_aggregate_evidence(expected, {}).passed


def test_description_lint_rejects_name_only_and_accepts_meaning():
    class Context:
        facts = []
        dimensions = []
        metrics = [{"table": "orders", "col_name": "net_revenue", "comment": "net revenue"}]
    assert not validator._check_description_quality(Context()).passed
    Context.metrics[0]["comment"] = "USD revenue after refunds per order, excluding tax."
    assert validator._check_description_quality(Context()).passed


def test_numeric_evidence_fails_closed():
    valid = {"scope": "all", "sum": 0, "count": 1, "avg": 0}
    for key, value in [("sum", None), ("avg", float("inf")), ("sum", float("nan")), ("count", True), ("count", 1.0), ("scope", "")]:
        invalid = dict(valid, **{key: value})
        assert not validator.validate_aggregate_evidence(invalid, invalid).passed


def test_forward_chain_safe_reverse_chain_warns():
    class Context:
        relationships = [{"left_table": "detail", "right_table": "bridge"}, {"left_table": "bridge", "right_table": "parent"}]
        metrics = [{"table": "detail"}]
        dimensions = [{"table": "parent"}]
    assert validator._check_fan_trap_warning(Context()).passed
    Context.metrics = [{"table": "parent"}]
    Context.dimensions = [{"table": "detail"}]
    assert not validator._check_fan_trap_warning(Context()).passed


def test_tolerance_is_bounded_and_count_exact():
    expected = {"scope": "all", "sum": 1.0, "count": 2, "avg": 0.5}
    observed = dict(expected, sum=1.00001)
    assert not validator.validate_aggregate_evidence(expected, observed).passed
    assert validator.validate_aggregate_evidence(expected, observed, abs_tol=0.001).passed
    assert not validator.validate_aggregate_evidence(expected, dict(observed, count=3), abs_tol=100).passed
    for tolerance in (-1, float("inf"), float("nan"), True):
        assert not validator.validate_aggregate_evidence(expected, expected, rel_tol=tolerance).passed


def test_parsed_avg_description_contradiction():
    ddl = "CREATE SEMANTIC VIEW db.sc.test TABLES (orders AS db.sc.orders PRIMARY KEY (id)) METRICS (orders.amount AS AVG(orders.amount) COMMENT = 'Total amount');"
    result = next(item for item in validator.validate_ddl(ddl) if item.name == "description_quality")
    assert not result.passed
    assert "AVG described as total" in result.message


def test_cli_evidence_dispatch(monkeypatch):
    import io
    import json
    import builtins
    expected = {"scope": "all", "sum": 120, "count": 3, "avg": 40}
    monkeypatch.setattr(validator, "validate_file", lambda path: [])
    monkeypatch.setattr(sys, "argv", ["sv_validator.py", "fixture.sql", "evidence.json"])
    for observed, status in [(expected, 0), (dict(expected, sum=240), 1), ({}, 1)]:
        payload = json.dumps({"expected": expected, "observed": observed})
        monkeypatch.setattr(builtins, "open", lambda *args, **kwargs: io.StringIO(payload))
        assert validator._cli_main() == status

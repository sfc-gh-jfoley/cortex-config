import importlib.util
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1] / "skills" / "sv-coverage-checker" / "sv_coverage_checker.py"
spec = importlib.util.spec_from_file_location("sv_coverage_checker", MODULE)
cc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cc)


class FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def collect(self):
        return self._rows


class FakeSession:
    """Returns canned GET_DDL text and canned EXPLAIN rows keyed by SQL text."""

    def __init__(self, ddl="", explains=None, gt_rows=None):
        self.ddl = ddl
        self.explains = explains or {}
        self.gt_rows = gt_rows or []

    def sql(self, text):
        if text.startswith("SELECT GET_DDL"):
            return FakeResult([(self.ddl,)])
        if text.startswith("SELECT QUESTION_ID"):
            return FakeResult(self.gt_rows)
        if text.startswith("EXPLAIN USING TABULAR "):
            return FakeResult(self.explains[text[len("EXPLAIN USING TABULAR "):]])
        raise AssertionError(text)


def scan(fqn, alias, cols):
    return {"operation": "TableScan", "objects": fqn, "alias": alias, "expressions": cols}


def join(expr):
    return {"operation": "InnerJoin", "objects": None, "alias": None, "expressions": expr}


DDL = """create semantic view V
  tables (
    orders as DB.S.ORDERS,
    customers as DB.S.CUSTOMERS primary key (customer_id),
    DB.S.LINES comment = 'a, b (c'
  )
  relationships (
    orders_to_customers as orders (customer_id) references customers,
    lines_to_orders as lines (order_id) references orders (order_id)
  )
  dimensions (
    orders.month as DATE_TRUNC('month', order_date) comment = 'x, y',
    customers.name as COALESCE(first_name, last_name)
  )
  metrics (
    orders.total as SUM(amount)
  )
"""


def test_table_without_primary_key_is_registered():
    sv = cc.sv_manifest_parser(FakeSession(DDL), "DB.S.V")
    assert sv["alias_map"]["ORDERS"] == "DB.S.ORDERS"
    assert sv["alias_map"]["LINES"] == "DB.S.LINES"
    assert "DB.S.ORDERS" in sv["registered_fqns"]


def test_references_without_column_list_resolves_to_primary_key():
    sv = cc.sv_manifest_parser(FakeSession(DDL), "DB.S.V")
    assert frozenset({"ORDERS.CUSTOMER_ID", "CUSTOMERS.CUSTOMER_ID"}) in sv["relationships"]
    assert not sv["parse_warnings"]


def test_references_without_column_list_and_no_pk_warns():
    ddl = DDL.replace("customers as DB.S.CUSTOMERS primary key (customer_id)", "customers as DB.S.CUSTOMERS")
    sv = cc.sv_manifest_parser(FakeSession(ddl), "DB.S.V")
    assert any("referenced columns unknown" in w for w in sv["parse_warnings"])


def test_references_with_column_list_still_parsed():
    sv = cc.sv_manifest_parser(FakeSession(DDL), "DB.S.V")
    assert frozenset({"LINES.ORDER_ID", "ORDERS.ORDER_ID"}) in sv["relationships"]


def test_commas_inside_expressions_keep_all_columns():
    sv = cc.sv_manifest_parser(FakeSession(DDL), "DB.S.V")
    assert "ORDERS.MONTH" in sv["exposed_cols"]
    assert "ORDERS.ORDER_DATE" in sv["source_cols"]
    assert "CUSTOMERS.FIRST_NAME" in sv["source_cols"]
    assert "CUSTOMERS.LAST_NAME" in sv["source_cols"]


def test_split_top_level_respects_quotes_and_parens():
    assert cc._split_top_level("a, f(b, c), 'x, y', \"p,q\"") == ["a", " f(b, c)", " 'x, y'", ' "p,q"']


def test_alias_collision_across_questions_is_keyed_by_fqn():
    sv = cc.sv_manifest_parser(FakeSession(DDL), "DB.S.V")
    q1 = "SELECT * FROM orders o"
    q2 = "SELECT * FROM customers o"
    explains = {
        q1: [scan("DB.S.ORDERS", "O", "AMOUNT")],
        q2: [scan("DB.S.CUSTOMERS", "O", "SECRET_COL")],
    }
    session = FakeSession(DDL, explains, [{"QUESTION_ID": "1", "SQL_TEXT": q1}, {"QUESTION_ID": "2", "SQL_TEXT": q2}])
    out = cc.sv_coverage_checker(session, "DB.S.GT", "DB.S.V")
    cols = {(g["physical_table"], g["element"]) for g in out["gaps"] if g["gap_type"] == "COLUMN_NOT_EXPOSED"}
    assert cols == {("DB.S.CUSTOMERS", "SECRET_COL")}
    verdicts = {v["question_id"]: v["status"] for v in out["verdicts"]}
    assert verdicts == {"1": "ANSWERABLE", "2": "NOT_ANSWERABLE"}


def test_return_shape_and_no_validate_data_parameter():
    session = FakeSession(DDL, {}, [{"QUESTION_ID": "1", "SQL_TEXT": ""}])
    out = cc.sv_coverage_checker(session, "DB.S.GT", "DB.S.V")
    assert set(out) == {"checker_version", "gaps", "verdicts", "summary", "warnings"}
    assert out["verdicts"][0]["status"] == "SKIPPED"
    assert {"unknown", "explain_failed", "skipped"} <= set(out["summary"])
    assert "validate_data" not in cc.sv_coverage_checker.__code__.co_varnames[:4]

"""Failing tests for sv_coverage_checker.py — TDD red phase.

These tests FAIL (ImportError) until sv_coverage_checker.py is implemented.
Run: pytest tests/test_sv_coverage_checker.py -v

Modules under test (all in skills/sv-coverage-checker/sv_coverage_checker.py):
  explain_parser(session, sql_text) -> dict
  sv_manifest_parser(session, sv_name) -> dict
  gap_differ(workload_manifest, sv_manifest) -> (gaps, verdicts)

Known limitation (C2, from plan review): column-level checks compare TableScan
physical column names against exposed_cols logical names. Computed facts/dimensions
(e.g. REVENUE as SUM(L_EXTENDEDPRICE)) will produce false COLUMN_NOT_EXPOSED for
the underlying physical columns. Tests here use direct (non-computed) columns to
avoid false positives in the clean-pass test.
"""
import os
import sys

import pytest
from unittest.mock import MagicMock

# Locate implementation relative to this file: ../skills/sv-coverage-checker/
_SKILL_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "skills", "sv-coverage-checker")
)
sys.path.insert(0, _SKILL_DIR)

from sv_coverage_checker import explain_parser, sv_manifest_parser, gap_differ, sv_coverage_checker  # noqa: E402


# ── Shared fixtures ────────────────────────────────────────────────────────────

class ExplainRow:
    """Row stub that supports both attribute and dict-style string-key access,
    matching the Snowpark Row objects returned by session.sql(...).collect()."""

    __slots__ = (
        "step", "id", "parentOperators", "operation", "objects",
        "alias", "expressions", "partitionsTotal", "partitionsAssigned", "bytesAssigned",
    )

    def __init__(self, step, id, parentOperators, operation, objects,
                 alias, expressions, partitionsTotal, partitionsAssigned, bytesAssigned):
        self.step = step
        self.id = id
        self.parentOperators = parentOperators
        self.operation = operation
        self.objects = objects
        self.alias = alias
        self.expressions = expressions
        self.partitionsTotal = partitionsTotal
        self.partitionsAssigned = partitionsAssigned
        self.bytesAssigned = bytesAssigned

    def __getitem__(self, key):
        return getattr(self, key)


def _explain_row(
    operation,
    objects=None,
    alias=None,
    expressions=None,
    step=1,
    id=1,
    parentOperators="[0]",
):
    return ExplainRow(
        step=step, id=id, parentOperators=parentOperators,
        operation=operation, objects=objects, alias=alias,
        expressions=expressions,
        partitionsTotal=None, partitionsAssigned=None, bytesAssigned=None,
    )


def _global_stats_row():
    """step=None / id=None — must be ignored by the parser."""
    return ExplainRow(
        step=None, id=None, parentOperators=None, operation="GlobalStats",
        objects=None, alias=None, expressions=None,
        partitionsTotal=1000, partitionsAssigned=500, bytesAssigned=204800,
    )


def _mock_explain_session(rows):
    session = MagicMock()
    session.sql.return_value.collect.return_value = rows
    return session


class _DDLRow:
    """Minimal row stub: row[0] returns the DDL text."""
    def __init__(self, text):
        self._text = text

    def __getitem__(self, i):
        return self._text


def _mock_ddl_session(ddl_text):
    session = MagicMock()
    session.sql.return_value.collect.return_value = [_DDLRow(ddl_text)]
    return session


# ── Module 1: explain_parser ───────────────────────────────────────────────────

class TestExplainParser:

    def test_single_table_query(self):
        """TableScan row → tables=[fqn], join_keys=[], columns populated, alias_to_fqn set."""
        rows = [
            _global_stats_row(),
            _explain_row(
                operation="TableScan",
                objects="DEMO_DB.PUBLIC.ORDERS",
                alias="O",
                expressions="O_ORDERKEY, O_CUSTKEY, O_TOTALPRICE",
            ),
        ]
        result = explain_parser(_mock_explain_session(rows), "SELECT * FROM ORDERS O")

        assert "DEMO_DB.PUBLIC.ORDERS" in result["tables"]
        assert result["join_keys"] == set()
        assert set(result["columns"]["O"]) >= {"O_ORDERKEY", "O_CUSTKEY", "O_TOTALPRICE"}
        assert result["alias_to_fqn"] == {"O": "DEMO_DB.PUBLIC.ORDERS"}

    def test_inner_join_keys_extracted(self):
        """InnerJoin 'joinKey: (A.col = B.col)' → join_keys contains the pair."""
        rows = [
            _global_stats_row(),
            _explain_row("TableScan", objects="DEMO_DB.PUBLIC.ORDERS",   alias="O", expressions="O_ORDERKEY, O_CUSTKEY"),
            _explain_row("TableScan", objects="DEMO_DB.PUBLIC.CUSTOMER", alias="C", expressions="C_CUSTKEY, C_NAME"),
            _explain_row("InnerJoin", expressions="joinKey: (O.O_CUSTKEY = C.C_CUSTKEY)"),
        ]
        result = explain_parser(_mock_explain_session(rows), "SELECT * FROM ORDERS O JOIN CUSTOMER C ON O.O_CUSTKEY = C.C_CUSTKEY")

        assert len(result["join_keys"]) >= 1
        pairs_as_frozensets = [frozenset(pair) for pair in result["join_keys"]]
        assert frozenset({"O.O_CUSTKEY", "C.C_CUSTKEY"}) in pairs_as_frozensets

    def test_left_join_keys_extracted(self):
        """LeftOuterJoin rows must also yield join_keys — not silently dropped (C1 fix).

        The plan initially filtered only on 'InnerJoin'; this test forces the
        implementation to handle any operation name containing 'Join'.
        """
        rows = [
            _global_stats_row(),
            _explain_row("TableScan", objects="DEMO_DB.PUBLIC.ORDERS",   alias="O", expressions="O_ORDERKEY"),
            _explain_row("TableScan", objects="DEMO_DB.PUBLIC.CUSTOMER", alias="C", expressions="C_CUSTKEY"),
            _explain_row("LeftOuterJoin", expressions="joinKey: (O.O_CUSTKEY = C.C_CUSTKEY)"),
        ]
        result = explain_parser(_mock_explain_session(rows), "SELECT * FROM ORDERS O LEFT JOIN CUSTOMER C ON O.O_CUSTKEY = C.C_CUSTKEY")

        pairs_as_frozensets = [frozenset(pair) for pair in result["join_keys"]]
        assert frozenset({"O.O_CUSTKEY", "C.C_CUSTKEY"}) in pairs_as_frozensets, (
            "LeftOuterJoin join keys must be captured — filter on 'Join' in operation name, not exact 'InnerJoin'"
        )

    def test_filter_columns_included(self):
        """Filter expression column references are captured in the columns dict."""
        rows = [
            _global_stats_row(),
            _explain_row("TableScan", objects="DEMO_DB.PUBLIC.ORDERS", alias="O", expressions="O_ORDERKEY, O_TOTALPRICE"),
            _explain_row("Filter",    expressions="O.O_ORDERSTATUS = 'O'"),
        ]
        result = explain_parser(_mock_explain_session(rows), "SELECT O_ORDERKEY FROM ORDERS O WHERE O_ORDERSTATUS = 'O'")

        assert "O_ORDERSTATUS" in result["columns"]["O"]

    def test_global_stats_row_skipped(self):
        """GlobalStats row (step=None) must not pollute tables, columns, or join_keys."""
        rows = [
            _global_stats_row(),
            _explain_row("TableScan", objects="DEMO_DB.PUBLIC.ORDERS", alias="O", expressions="O_ORDERKEY"),
        ]
        result = explain_parser(_mock_explain_session(rows), "SELECT O_ORDERKEY FROM ORDERS")

        assert None not in result["tables"]
        assert len(result["tables"]) == 1
        assert result["join_keys"] == set()


# ── Module 2: sv_manifest_parser ──────────────────────────────────────────────

_DDL_ALIASED_TABLE = """\
CREATE OR REPLACE SEMANTIC VIEW DEMO_DB.PUBLIC.TEST_SV AS
tables (
    FCT_TXN as DB.SCHEMA.FCT_STORE_TRANSACTION_ITEM primary key (TXN_ID)
)
relationships (
)
facts (
)
dimensions (
)
metrics (
)
;"""

_DDL_UNALIASED_TABLE = """\
CREATE OR REPLACE SEMANTIC VIEW DEMO_DB.PUBLIC.TEST_SV AS
tables (
    DB.SCHEMA.ORDERS primary key (ORDER_ID)
)
relationships (
)
facts (
)
dimensions (
)
metrics (
)
;"""

_DDL_RELATIONSHIP = """\
CREATE OR REPLACE SEMANTIC VIEW DEMO_DB.PUBLIC.TEST_SV AS
tables (
    FCT_TXN as DB.SCHEMA.FCT_STORE_TRANSACTION_ITEM primary key (TXN_ID),
    DIM_ACCT as DB.SCHEMA.DIM_ACCOUNT primary key (ACCT_ID)
)
relationships (
    acct_rel as FCT_TXN(ACCT_ID) references DIM_ACCT(ACCT_ID)
)
facts (
)
dimensions (
)
metrics (
)
;"""

_DDL_EXPOSED_COLS = """\
CREATE OR REPLACE SEMANTIC VIEW DEMO_DB.PUBLIC.TEST_SV AS
tables (
    FCT_TXN as DB.SCHEMA.FCT_STORE_TRANSACTION_ITEM primary key (TXN_ID)
)
relationships (
)
facts (
    FCT_TXN.REVENUE as SUM(SALES_USD)
)
dimensions (
    FCT_TXN.TXN_DATE as TXN_DATE
)
metrics (
)
;"""


class TestSvManifestParser:

    def test_aliased_table_parsing(self):
        """'FCT_TXN as DB.SCHEMA.FCT_STORE_TRANSACTION_ITEM' → alias_map["FCT_TXN"] = fqn."""
        result = sv_manifest_parser(_mock_ddl_session(_DDL_ALIASED_TABLE), "DEMO_DB.PUBLIC.TEST_SV")

        assert "DB.SCHEMA.FCT_STORE_TRANSACTION_ITEM" in result["registered_fqns"]
        assert result["alias_map"]["FCT_TXN"] == "DB.SCHEMA.FCT_STORE_TRANSACTION_ITEM"

    def test_unaliased_table_alias_is_last_segment(self):
        """'DB.SCHEMA.ORDERS primary key (...)' → alias_map key is 'ORDERS' (last FQN segment).

        NOT the full FQN — facts/dimensions reference the last segment (e.g. ORDERS.O_ORDERKEY)
        so the logical alias must be the bare table name. (M2 from plan review.)
        """
        result = sv_manifest_parser(_mock_ddl_session(_DDL_UNALIASED_TABLE), "DEMO_DB.PUBLIC.TEST_SV")

        assert "DB.SCHEMA.ORDERS" in result["registered_fqns"]
        assert result["alias_map"]["ORDERS"] == "DB.SCHEMA.ORDERS", (
            "Unaliased table: logical alias must be bare name 'ORDERS', not full FQN"
        )
        # Full FQN must NOT be used as alias key (would break column-level lookups)
        assert "DB.SCHEMA.ORDERS" not in result["alias_map"]

    def test_relationship_parsed_as_frozenset(self):
        """'acct_rel as FCT_TXN(ACCT_ID) references DIM_ACCT(ACCT_ID)' → frozenset in relationships."""
        result = sv_manifest_parser(_mock_ddl_session(_DDL_RELATIONSHIP), "DEMO_DB.PUBLIC.TEST_SV")

        expected = frozenset({"FCT_TXN.ACCT_ID", "DIM_ACCT.ACCT_ID"})
        assert expected in result["relationships"], (
            f"Expected {expected!r} in relationships; got {result['relationships']!r}"
        )

    def test_facts_and_dimensions_in_exposed_cols(self):
        """Facts and dimensions appear as 'alias.col_name' in exposed_cols."""
        result = sv_manifest_parser(_mock_ddl_session(_DDL_EXPOSED_COLS), "DEMO_DB.PUBLIC.TEST_SV")

        assert "FCT_TXN.REVENUE"   in result["exposed_cols"]
        assert "FCT_TXN.TXN_DATE"  in result["exposed_cols"]


# ── Module 3: gap_differ ───────────────────────────────────────────────────────

def _sv(registered_fqns=(), alias_map=None, relationships=(), exposed_cols=()):
    am = dict(alias_map or {})
    return {
        "registered_fqns": set(registered_fqns),
        "alias_map":        am,
        "fqn_to_alias":     {v: k for k, v in am.items()},
        "relationships":    set(relationships),
        "exposed_cols":     set(exposed_cols),
        "source_cols":      set(),
    }


def _workload(tables, join_keys, columns, alias_to_fqn, question_id="Q1"):
    """Build a single-question workload manifest."""
    cols = {alias: set(c) for alias, c in columns.items()}
    return {
        "tables":       set(tables),
        "join_keys":    set(tuple(p) for p in join_keys),
        "columns":      cols,
        "alias_to_fqn": dict(alias_to_fqn),
        "per_question": {
            question_id: {
                "tables":       set(tables),
                "join_keys":    set(tuple(p) for p in join_keys),
                "columns":      cols,
                "alias_to_fqn": dict(alias_to_fqn),
            }
        },
    }


class TestGapDiffer:

    def test_table_not_registered(self):
        """Table in workload absent from SV → TABLE_NOT_REGISTERED gap, Q1=NOT_ANSWERABLE."""
        workload = _workload(
            tables=["DB.SCHEMA.DIM_DEVICE_TYPE"],
            join_keys=[],
            columns={"DDT": ["DEVICE_NAME"]},
            alias_to_fqn={"DDT": "DB.SCHEMA.DIM_DEVICE_TYPE"},
        )
        sv = _sv()  # empty

        gaps, verdicts = gap_differ(workload, sv)

        gap_types = {g["gap_type"] for g in gaps}
        assert "TABLE_NOT_REGISTERED" in gap_types

        tbl_gaps = [g for g in gaps if g["gap_type"] == "TABLE_NOT_REGISTERED"]
        assert any(g["physical_table"] == "DB.SCHEMA.DIM_DEVICE_TYPE" for g in tbl_gaps)

        verdict_map = {v["question_id"]: v["status"] for v in verdicts}
        assert verdict_map["Q1"] == "NOT_ANSWERABLE"

    def test_column_not_exposed(self):
        """Column in workload absent from SV exposed_cols → COLUMN_NOT_EXPOSED gap, Q1=NOT_ANSWERABLE.

        Uses a direct (non-computed) column to avoid false-positive from C2 limitation.
        """
        workload = _workload(
            tables=["DB.SCHEMA.FCT_TXN"],
            join_keys=[],
            columns={"FCT": ["DISCOUNT_AMT"]},
            alias_to_fqn={"FCT": "DB.SCHEMA.FCT_TXN"},
        )
        sv = _sv(
            registered_fqns=["DB.SCHEMA.FCT_TXN"],
            alias_map={"FCT": "DB.SCHEMA.FCT_TXN"},
            exposed_cols=["FCT.REVENUE", "FCT.TXN_DATE"],  # DISCOUNT_AMT absent
        )

        gaps, verdicts = gap_differ(workload, sv)

        col_gaps = [g for g in gaps if g["gap_type"] == "COLUMN_NOT_EXPOSED"]
        assert len(col_gaps) >= 1
        assert any(
            g.get("physical_table") == "DB.SCHEMA.FCT_TXN" and g.get("element") == "DISCOUNT_AMT"
            for g in col_gaps
        )

        verdict_map = {v["question_id"]: v["status"] for v in verdicts}
        assert verdict_map["Q1"] == "NOT_ANSWERABLE"

    def test_relationship_missing(self):
        """Join pair absent from SV relationships → RELATIONSHIP_MISSING gap, Q1=NOT_ANSWERABLE.

        Tables and columns are fully registered to isolate the relationship gap.
        """
        workload = _workload(
            tables=["DB.SCHEMA.FCT_TXN", "DB.SCHEMA.DIM_ACCT"],
            join_keys=[("FCT.TXN_ID", "DIM.TXN_ID")],
            columns={"FCT": ["TXN_ID"], "DIM": ["TXN_ID"]},
            alias_to_fqn={"FCT": "DB.SCHEMA.FCT_TXN", "DIM": "DB.SCHEMA.DIM_ACCT"},
        )
        sv = _sv(
            registered_fqns=["DB.SCHEMA.FCT_TXN", "DB.SCHEMA.DIM_ACCT"],
            alias_map={"FCT": "DB.SCHEMA.FCT_TXN", "DIM": "DB.SCHEMA.DIM_ACCT"},
            exposed_cols=["FCT.TXN_ID", "DIM.TXN_ID"],
            relationships=[],  # the pair is NOT registered
        )

        gaps, verdicts = gap_differ(workload, sv)

        rel_gaps = [g for g in gaps if g["gap_type"] == "RELATIONSHIP_MISSING"]
        assert len(rel_gaps) >= 1
        # element must reference both column sides of the join
        assert any("TXN_ID" in g.get("element", "") for g in rel_gaps)

        verdict_map = {v["question_id"]: v["status"] for v in verdicts}
        assert verdict_map["Q1"] == "NOT_ANSWERABLE"

    def test_clean_pass_all_answerable(self):
        """Workload fully covered by SV → gaps=[], Q1=ANSWERABLE.

        Uses only direct columns (no computed expressions) to avoid C2 false positives.
        """
        workload = _workload(
            tables=["DB.SCHEMA.FCT_TXN", "DB.SCHEMA.DIM_ACCT"],
            join_keys=[("FCT.ACCT_ID", "DIM.ACCT_ID")],
            columns={"FCT": ["REVENUE", "TXN_DATE"], "DIM": ["COUNTRY"]},
            alias_to_fqn={"FCT": "DB.SCHEMA.FCT_TXN", "DIM": "DB.SCHEMA.DIM_ACCT"},
        )
        sv = _sv(
            registered_fqns=["DB.SCHEMA.FCT_TXN", "DB.SCHEMA.DIM_ACCT"],
            alias_map={"FCT": "DB.SCHEMA.FCT_TXN", "DIM": "DB.SCHEMA.DIM_ACCT"},
            exposed_cols=["FCT.REVENUE", "FCT.TXN_DATE", "DIM.COUNTRY"],
            relationships=[frozenset({"FCT.ACCT_ID", "DIM.ACCT_ID"})],
        )

        gaps, verdicts = gap_differ(workload, sv)

        assert gaps == [], f"Expected no gaps; got: {gaps}"
        verdict_map = {v["question_id"]: v["status"] for v in verdicts}
        assert verdict_map["Q1"] == "ANSWERABLE"


# ── warnings[] — unrecognized EXPLAIN operations ───────────────────────────────

class TestExplainParserWarnings:

    def test_unrecognized_op_produces_warning(self):
        """An EXPLAIN row with an unrecognized operation emits a warning and does not crash."""
        rows = [
            _global_stats_row(),
            _explain_row("TableScan", objects="DEMO_DB.PUBLIC.ORDERS", alias="O", expressions="O_ORDERKEY"),
            _explain_row("LateralJoin", expressions=None),
        ]
        result = explain_parser(_mock_explain_session(rows), "SELECT O_ORDERKEY FROM ORDERS, LATERAL ...")

        assert isinstance(result["warnings"], list)
        assert len(result["warnings"]) >= 1
        assert any("LateralJoin" in w for w in result["warnings"]), (
            f"Expected a warning mentioning 'LateralJoin'; got: {result['warnings']}"
        )
        # Must still parse the TableScan correctly — not crash on the unknown op
        assert "DEMO_DB.PUBLIC.ORDERS" in result["tables"]


# ── sv_coverage_checker: NULL/empty SQL_TEXT → SKIPPED ────────────────────────

class _GTRow:
    """Minimal GT table row stub supporting string-key dict access."""
    def __init__(self, question_id, sql_text):
        self._data = {'QUESTION_ID': question_id, 'SQL_TEXT': sql_text}

    def __getitem__(self, key):
        return self._data[key]


class TestSvCoverageCheckerSkipped:

    def test_null_sql_text_produces_skipped_verdict(self):
        """A GT row with NULL SQL_TEXT must emit SKIPPED (not ANSWERABLE) and summary.skipped=1."""
        session = MagicMock()
        session.sql.return_value.collect.side_effect = [
            [_GTRow('Q1', None)],          # SELECT QUESTION_ID, SQL_TEXT FROM ...
            [_DDLRow(_DDL_UNALIASED_TABLE)],  # SELECT GET_DDL(...) in sv_manifest_parser
        ]

        result = sv_coverage_checker(session, 'MOCK_GT_TABLE', 'DEMO_DB.PUBLIC.TEST_SV')

        verdict_map = {v['question_id']: v['status'] for v in result['verdicts']}
        assert verdict_map.get('Q1') == 'SKIPPED', (
            f"Expected SKIPPED for NULL SQL_TEXT; got {verdict_map.get('Q1')!r}"
        )
        assert result['summary']['skipped'] == 1
        assert result['summary']['answerable'] == 0
        assert result['summary']['not_answerable'] == 0

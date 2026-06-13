"""T3 tests: sv_manifest_parser hardening — TDD red → green.

Tests cover:
  - parse_error returned (not raised) when GET_DDL fails
  - single-column relationship → frozenset in relationships + directed pair in relationship_pairs
  - composite (multi-column) relationship → multiple frozensets + composite flag
  - exposed_cols populated from dimensions block
  - _unquote applied to alias tokens in tables block
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from sv_coverage_checker import sv_manifest_parser


# --- helpers ---

class FakeSession:
    def __init__(self, ddl):
        self._ddl = ddl

    def sql(self, q):
        ddl = self._ddl
        class R:
            def collect(self):
                return [[ddl]]
        return R()


class FailSession:
    def sql(self, q):
        class R:
            def collect(self):
                raise RuntimeError("Object does not exist")
        return R()


SINGLE_REL_DDL = """
CREATE SEMANTIC VIEW sv TEST (
  tables (
    DB.SCH.ORDERS primary key (ID),
    items as DB.SCH.ITEMS primary key (ITEM_ID)
  )
  relationships (
    r1 as ORDERS(ID) references items(ORDER_ID)
  )
  dimensions (
    ORDERS.STATUS as order_status
  )
)
"""

COMPOSITE_REL_DDL = """
CREATE SEMANTIC VIEW sv TEST (
  tables (
    DB.SCH.A primary key (ID),
    B as DB.SCH.B primary key (BID)
  )
  relationships (
    r1 as A(col1, col2) references B(col3, col4)
  )
  dimensions (A.STATUS as status)
)
"""

QUOTED_ALIAS_DDL = """
CREATE SEMANTIC VIEW sv TEST (
  tables (
    "MyAlias" as DB.SCH.ORDERS primary key (ID)
  )
  relationships (
  )
  dimensions (
    "MyAlias".STATUS as status
  )
)
"""


# --- parse_error on failure ---

def test_parse_error_on_failure():
    result = sv_manifest_parser(FailSession(), 'MYDB.MYSCH.NONEXISTENT')
    assert 'parse_error' in result, "Must return parse_error key on GET_DDL failure"
    assert result['registered_fqns'] == set()
    assert result['alias_map'] == {}
    assert result['relationships'] == set()
    assert result['relationship_pairs'] == []


def test_parse_error_not_raised():
    """Must not raise — caller gets a dict back."""
    result = sv_manifest_parser(FailSession(), 'MYDB.MYSCH.NONEXISTENT')
    assert isinstance(result, dict)


# --- single-column relationship ---

def test_single_relationship_frozenset():
    m = sv_manifest_parser(FakeSession(SINGLE_REL_DDL), 'x')
    assert 'parse_error' not in m
    assert frozenset({'ORDERS.ID', 'ITEMS.ORDER_ID'}) in m['relationships']


def test_single_relationship_pairs_present():
    m = sv_manifest_parser(FakeSession(SINGLE_REL_DDL), 'x')
    assert 'relationship_pairs' in m
    assert len(m['relationship_pairs']) == 1


def test_single_relationship_pairs_direction():
    m = sv_manifest_parser(FakeSession(SINGLE_REL_DDL), 'x')
    p = m['relationship_pairs'][0]
    assert p['from'] == 'ORDERS'
    assert p['to'] == 'ITEMS'
    assert p['from_cols'] == ['ID']
    assert p['to_cols'] == ['ORDER_ID']
    assert p['composite'] is False


# --- composite (multi-column) relationship ---

def test_composite_relationship_produces_two_frozensets():
    m = sv_manifest_parser(FakeSession(COMPOSITE_REL_DDL), 'x')
    assert frozenset({'A.COL1', 'B.COL3'}) in m['relationships']
    assert frozenset({'A.COL2', 'B.COL4'}) in m['relationships']


def test_composite_relationship_pairs_single_entry():
    m = sv_manifest_parser(FakeSession(COMPOSITE_REL_DDL), 'x')
    assert len(m['relationship_pairs']) == 1


def test_composite_relationship_pairs_composite_flag():
    m = sv_manifest_parser(FakeSession(COMPOSITE_REL_DDL), 'x')
    p = m['relationship_pairs'][0]
    assert p['composite'] is True
    assert p['from_cols'] == ['COL1', 'COL2']
    assert p['to_cols'] == ['COL3', 'COL4']


# --- exposed_cols populated ---

def test_exposed_cols_populated():
    m = sv_manifest_parser(FakeSession(SINGLE_REL_DDL), 'x')
    assert 'ORDERS.STATUS' in m['exposed_cols']


# --- return dict has all required keys on success ---

def test_success_return_keys():
    m = sv_manifest_parser(FakeSession(SINGLE_REL_DDL), 'x')
    for key in ('registered_fqns', 'alias_map', 'fqn_to_alias', 'relationships',
                'relationship_pairs', 'exposed_cols', 'source_cols'):
        assert key in m, f"Missing key: {key}"
    assert 'parse_error' not in m


# --- parse_warnings key exists on success ---

def test_parse_warnings_key_present_on_success():
    m = sv_manifest_parser(FakeSession(SINGLE_REL_DDL), 'x')
    assert 'parse_warnings' in m
    assert isinstance(m['parse_warnings'], list)


def test_quoted_alias_in_dimensions():
    m = sv_manifest_parser(FakeSession(QUOTED_ALIAS_DDL), 'x')
    assert 'MYALIAS.STATUS' in m['exposed_cols'], f"exposed_cols={m['exposed_cols']}"

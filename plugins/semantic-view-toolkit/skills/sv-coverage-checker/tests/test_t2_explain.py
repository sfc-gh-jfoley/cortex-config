import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from sv_coverage_checker import _unquote, _parse_col_list, _parse_join_keys, explain_parser

def test_unquote_bare():
    assert _unquote('MY_COL') == 'MY_COL'

def test_unquote_quoted():
    assert _unquote('"My_Col"') == 'MY_COL'

def test_unquote_lowercase_bare():
    assert _unquote('my_col') == 'MY_COL'

def test_parse_col_list_quoted():
    result = _parse_col_list('"My_Col", BARE_COL')
    assert 'MY_COL' in result and 'BARE_COL' in result

def test_parse_join_keys_equi():
    pairs, unparsed = _parse_join_keys('joinKey: (t1.id = t2.order_id)')
    assert len(pairs) == 1
    assert pairs[0] == ('T1.ID', 'T2.ORDER_ID')
    assert unparsed == []

def test_parse_join_keys_non_equi():
    pairs, unparsed = _parse_join_keys('joinKey: (t1.start_date <= t2.end_date)')
    assert pairs == []
    assert len(unparsed) == 1
    assert 'non-equi' in unparsed[0]

def test_parse_join_keys_quoted():
    pairs, unparsed = _parse_join_keys('joinKey: ("T1"."ID" = "T2"."ORDER_ID")')
    assert len(pairs) == 1
    assert pairs[0] == ('T1.ID', 'T2.ORDER_ID')

class _FakeRow:
    def __init__(self, **kw): self.__dict__.update(kw)
    def __getitem__(self, k): return self.__dict__[k]

class _FakeSession:
    """Raises on EXPLAIN call."""
    def sql(self, q):
        raise RuntimeError("SQL compilation error: invalid syntax")
    def collect(self): return []

def test_explain_parser_explain_failed():
    class S:
        def sql(self, q):
            class R:
                def collect(self_inner): raise RuntimeError("bad sql")
            return R()
    result = explain_parser(S(), "SELECT 1/0 FROM nowhere")
    assert result['explain_failed'] is True
    assert 'explain_error' in result
    assert result['tables'] == set()


def test_explain_parser_lateral_join_unhandled():
    """LateralJoin op must emit UNHANDLED_JOIN_TYPE, not UNRECOGNIZED_EXPLAIN_OP."""
    class FakeRow:
        def __init__(self, **kw): self.__dict__.update(kw)
        def __getitem__(self, k): return self.__dict__[k]

    class FakeSession:
        def sql(self, q):
            class R:
                def collect(self_inner):
                    return [
                        FakeRow(operation='TableScan', objects='DB.SCH.A', alias='A', expressions='ID'),
                        FakeRow(operation='LateralJoin', objects='', alias='', expressions=''),
                    ]
            return R()

    result = explain_parser(FakeSession(), "SELECT A.ID FROM DB.SCH.A, LATERAL FLATTEN(...)")
    codes = [w['code'] for w in result['warnings']]
    assert 'UNHANDLED_JOIN_TYPE' in codes, f"Expected UNHANDLED_JOIN_TYPE, got: {codes}"
    assert 'UNRECOGNIZED_EXPLAIN_OP' not in codes


def test_explain_parser_zero_tables_extracted():
    """EXPLAIN plan with no TableScan rows must emit ZERO_TABLES_EXTRACTED warning."""
    class FakeRow:
        def __init__(self, **kw): self.__dict__.update(kw)
        def __getitem__(self, k): return self.__dict__[k]

    class FakeSession:
        def sql(self, q):
            class R:
                def collect(self_inner):
                    return [FakeRow(operation='Result', objects='', alias='', expressions='1')]
            return R()

    result = explain_parser(FakeSession(), "SELECT 1")
    codes = [w['code'] for w in result['warnings']]
    assert 'ZERO_TABLES_EXTRACTED' in codes, f"Expected ZERO_TABLES_EXTRACTED, got: {codes}"


def test_explain_parser_non_equi_join_warning():
    """Non-equi joinKey expression through explain_parser must produce UNHANDLED_JOIN_TYPE."""
    class FakeRow:
        def __init__(self, **kw): self.__dict__.update(kw)
        def __getitem__(self, k): return self.__dict__[k]

    class FakeSession:
        def sql(self, q):
            class R:
                def collect(self_inner):
                    return [
                        FakeRow(operation='TableScan', objects='DB.SCH.A', alias='A', expressions='ID'),
                        FakeRow(operation='TableScan', objects='DB.SCH.B', alias='B', expressions='START_DATE'),
                        FakeRow(operation='InnerJoin', objects='', alias='',
                                expressions='joinKey: (A.START_DATE <= B.END_DATE)'),
                    ]
            return R()

    result = explain_parser(FakeSession(), "SELECT * FROM DB.SCH.A JOIN DB.SCH.B ON A.START_DATE <= B.END_DATE")
    codes = [w['code'] for w in result['warnings']]
    assert 'UNHANDLED_JOIN_TYPE' in codes, f"Expected UNHANDLED_JOIN_TYPE in warnings, got: {codes}"

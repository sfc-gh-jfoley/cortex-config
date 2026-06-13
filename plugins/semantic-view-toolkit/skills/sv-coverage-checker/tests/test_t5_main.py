import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from sv_coverage_checker import sv_coverage_checker, CHECKER_VERSION

class FakeRow:
    def __init__(self, **kw): self.__dict__.update(kw)
    def __getitem__(self, k): return self.__dict__[k]

def make_session(gt_rows, explain_rows, ddl):
    class FakeResult:
        def __init__(self, rows): self._rows = rows
        def collect(self): return self._rows
    class FakeSession:
        def sql(self, q):
            q_up = q.strip().upper()
            if q_up.startswith('SELECT QUESTION_ID'):
                return FakeResult(gt_rows)
            elif q_up.startswith('EXPLAIN'):
                return FakeResult(explain_rows)
            elif 'GET_DDL' in q_up:
                return FakeResult([[ddl]])
            return FakeResult([])
    return FakeSession()

MINIMAL_DDL = """
CREATE SEMANTIC VIEW V (
  tables (DB.SCH.T primary key (ID))
  relationships ()
  dimensions (T.NAME as name)
)
"""

def _make_explain_row(op, objects='', alias='', expressions=''):
    return FakeRow(operation=op, objects=objects, alias=alias, expressions=expressions)

def test_checker_version_in_output():
    sess = make_session([], [], MINIMAL_DDL)
    result = sv_coverage_checker(sess, 'DB.SCH.GT', 'DB.SCH.V')
    assert result['checker_version'] == CHECKER_VERSION

def test_summary_has_unknown_and_explain_failed_keys():
    sess = make_session([], [], MINIMAL_DDL)
    result = sv_coverage_checker(sess, 'DB.SCH.GT', 'DB.SCH.V')
    assert 'unknown' in result['summary']
    assert 'explain_failed' in result['summary']

def test_skipped_on_empty_sql():
    gt = [FakeRow(QUESTION_ID='q1', SQL_TEXT='')]
    sess = make_session(gt, [], MINIMAL_DDL)
    result = sv_coverage_checker(sess, 'DB.SCH.GT', 'DB.SCH.V')
    assert result['summary']['skipped'] == 1
    v = next(v for v in result['verdicts'] if v['question_id'] == 'q1')
    assert v['status'] == 'SKIPPED'

def test_explain_failed_verdict_does_not_crash_others():
    gt = [
        FakeRow(QUESTION_ID='q_bad', SQL_TEXT='SELECT boom FROM nowhere'),
        FakeRow(QUESTION_ID='q_skip', SQL_TEXT=''),
    ]
    class BoomSession:
        def sql(self, q):
            class R:
                def collect(self_inner):
                    q_up = q.strip().upper()
                    if q_up.startswith('EXPLAIN'):
                        raise RuntimeError("compilation error")
                    if 'GET_DDL' in q_up:
                        return [[MINIMAL_DDL]]
                    if q_up.startswith('SELECT QUESTION_ID'):
                        return gt
                    return []
            return R()
    result = sv_coverage_checker(BoomSession(), 'DB.SCH.GT', 'DB.SCH.V')
    statuses = {v['question_id']: v['status'] for v in result['verdicts']}
    assert statuses['q_bad'] == 'EXPLAIN_FAILED'
    assert statuses['q_skip'] == 'SKIPPED'
    assert result['summary']['explain_failed'] == 1

def test_every_verdict_has_warnings_and_confidence():
    gt = [FakeRow(QUESTION_ID='q1', SQL_TEXT='SELECT 1')]
    explain = [_make_explain_row('TableScan', 'DB.SCH.T', 'T', 'ID')]
    sess = make_session(gt, explain, MINIMAL_DDL)
    result = sv_coverage_checker(sess, 'DB.SCH.GT', 'DB.SCH.V')
    for v in result['verdicts']:
        assert 'warnings' in v, f"verdict {v['question_id']} missing 'warnings'"
        assert 'confidence' in v, f"verdict {v['question_id']} missing 'confidence'"

def test_sv_parse_error_in_global_warnings():
    gt = [FakeRow(QUESTION_ID='q1', SQL_TEXT='')]
    class FailDDLSession:
        def sql(self, q):
            class R:
                def collect(self_inner):
                    if 'GET_DDL' in q.upper():
                        raise RuntimeError("SV does not exist")
                    if 'QUESTION_ID' in q.upper():
                        return gt
                    return []
            return R()
    result = sv_coverage_checker(FailDDLSession(), 'DB.SCH.GT', 'DB.SCH.NOEXIST')
    assert any('SV_PARSE_ERROR' in w or 'parse' in w.lower() for w in result['warnings'])

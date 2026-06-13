import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from sv_coverage_checker import _warn, _is_blocking, _classify_verdict, _PARSE_BLOCKING, CHECKER_VERSION

def test_checker_version():
    assert CHECKER_VERSION == "2.0.0"

def test_warn_structure():
    w = _warn('UNHANDLED_JOIN_TYPE', 'some message')
    assert w == {'code': 'UNHANDLED_JOIN_TYPE', 'message': 'some message'}

def test_is_blocking_true():
    assert _is_blocking(_warn('UNHANDLED_JOIN_TYPE', 'x')) is True

def test_is_blocking_false():
    assert _is_blocking(_warn('INFO', 'x')) is False

def test_classify_explain_failed():
    v = _classify_verdict('q1', {'explain_failed': True, 'explain_error': 'bad sql', 'warnings': []}, [])
    assert v['status'] == 'EXPLAIN_FAILED'
    assert v['confidence'] is None

def test_classify_not_answerable_high_confidence():
    gaps = [{'gap_type': 'TABLE_NOT_REGISTERED', 'detail': 'x', 'physical_table': 'T', 'element': None}]
    v = _classify_verdict('q1', {'explain_failed': False, 'warnings': []}, gaps)
    assert v['status'] == 'NOT_ANSWERABLE'
    assert v['confidence'] == 'high'

def test_classify_not_answerable_low_confidence_with_blocking_warning():
    gaps = [{'gap_type': 'TABLE_NOT_REGISTERED', 'detail': 'x', 'physical_table': 'T', 'element': None}]
    w = {'explain_failed': False, 'warnings': [_warn('UNHANDLED_JOIN_TYPE', 'lateral join')]}
    v = _classify_verdict('q1', w, gaps)
    assert v['status'] == 'NOT_ANSWERABLE'
    assert v['confidence'] == 'low'

def test_classify_unknown():
    w = {'explain_failed': False, 'warnings': [_warn('ZERO_TABLES_EXTRACTED', 'no tables')]}
    v = _classify_verdict('q1', w, [])
    assert v['status'] == 'UNKNOWN'
    assert v['failure_mode'] == 'ZERO_TABLES_EXTRACTED'

def test_classify_answerable():
    v = _classify_verdict('q1', {'explain_failed': False, 'warnings': []}, [])
    assert v['status'] == 'ANSWERABLE'
    assert v['confidence'] == 'high'
    assert v['warnings'] == []

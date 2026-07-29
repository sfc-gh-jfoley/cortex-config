import sys, os, pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from sv_coverage_checker import sv_coverage_checker, _sanitize_err

class _NullSession:
    def sql(self, q):
        class R:
            def collect(self): return []
        return R()

def test_gt_table_injection_rejected():
    with pytest.raises(ValueError, match="gt_table"):
        sv_coverage_checker(_NullSession(), "real_table UNION SELECT 1", "DB.SCH.SV")

def test_sv_name_injection_rejected():
    with pytest.raises(ValueError, match="sv_name"):
        sv_coverage_checker(_NullSession(), "DB.SCH.GT", "x') UNION SELECT 1 --")

def test_valid_identifiers_pass_validation():
    # Should NOT raise ValueError for identifier validation
    try:
        sv_coverage_checker(_NullSession(), "DB.SCH.GT", "DB.SCH.SV")
    except ValueError as e:
        assert "gt_table" not in str(e) and "sv_name" not in str(e)

def test_sanitize_err_redacts_fqn():
    msg = "Object 'MY_DB.MY_SCHEMA.MY_TABLE' does not exist."
    sanitized = _sanitize_err(msg)
    assert 'MY_DB' not in sanitized
    assert '<object>' in sanitized

def test_sanitize_err_leaves_plain_msg():
    msg = "SQL compilation error: invalid syntax"
    assert _sanitize_err(msg) == msg

def test_row_count_guard():
    class BigTableSession:
        def sql(self, q):
            class R:
                def collect(self_inner):
                    if 'QUESTION_ID' in q.upper():
                        class FakeRow:
                            def __getitem__(self, k):
                                return 'q1' if k == 'QUESTION_ID' else ''
                        return [FakeRow() for _ in range(501)]
                    return []
            return R()
    with pytest.raises(ValueError, match="501 rows"):
        sv_coverage_checker(BigTableSession(), "DB.SCH.GT", "DB.SCH.SV")

def test_deploy_sql_has_execute_as_caller():
    deploy_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'sv_coverage_checker_deploy.sql')
    with open(deploy_path) as f:
        content = f.read().upper()
    assert 'EXECUTE AS CALLER' in content

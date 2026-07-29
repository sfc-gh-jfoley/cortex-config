import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from sv_coverage_checker import gap_differ

SV = {
    'registered_fqns': {'DB.SCH.ORDERS', 'DB.SCH.ITEMS'},
    'fqn_to_alias': {'DB.SCH.ORDERS': 'ORDERS', 'DB.SCH.ITEMS': 'ITEMS'},
    'relationships': {frozenset({'ORDERS.ID', 'ITEMS.ORDER_ID'})},
    'relationship_pairs': [],
    'exposed_cols': {'ORDERS.STATUS', 'ITEMS.NAME'},
    'source_cols': {'ORDERS.CUSTOMER_ID'},
}

def test_gap_differ_returns_list():
    result = gap_differ({'tables': set(), 'join_keys': set(), 'columns': {}, 'alias_to_fqn': {}}, SV)
    assert isinstance(result, list)

def test_table_not_registered():
    wl = {
        'tables': {'DB.SCH.UNKNOWN'},
        'join_keys': set(),
        'columns': {},
        'alias_to_fqn': {'U': 'DB.SCH.UNKNOWN'},
    }
    gaps = gap_differ(wl, SV)
    assert any(g['gap_type'] == 'TABLE_NOT_REGISTERED' for g in gaps)

def test_no_column_not_exposed_for_rel_endpoint():
    # ORDERS.ID is a rel endpoint — should NOT produce COLUMN_NOT_EXPOSED
    wl = {
        'tables': {'DB.SCH.ORDERS'},
        'join_keys': set(),
        'columns': {'ORDERS_ALIAS': {'ID'}},
        'alias_to_fqn': {'ORDERS_ALIAS': 'DB.SCH.ORDERS'},
    }
    gaps = gap_differ(wl, SV)
    col_gaps = [g for g in gaps if g['gap_type'] == 'COLUMN_NOT_EXPOSED' and g['element'] == 'ID']
    assert col_gaps == []

def test_relationship_missing():
    wl = {
        'tables': {'DB.SCH.ORDERS', 'DB.SCH.ITEMS'},
        'join_keys': {frozenset({'ORDERS.FOO', 'ITEMS.BAR'})},
        'columns': {},
        'alias_to_fqn': {'ORDERS': 'DB.SCH.ORDERS', 'ITEMS': 'DB.SCH.ITEMS'},
    }
    gaps = gap_differ(wl, SV)
    assert any(g['gap_type'] == 'RELATIONSHIP_MISSING' for g in gaps)

def test_compute_verdicts_removed():
    import sv_coverage_checker
    assert not hasattr(sv_coverage_checker, '_compute_verdicts'), \
        "_compute_verdicts should be removed in T4"

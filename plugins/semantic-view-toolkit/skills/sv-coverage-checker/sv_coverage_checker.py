import re
from collections import defaultdict
try:
    from snowflake.snowpark import Session
except ImportError:
    Session = object  # type stub for local testing without snowpark installed

CHECKER_VERSION = "2.0.0"

# MEDIUM-1: error message sanitizer — redacts FQN-shaped tokens before surfacing to callers
_FQN_RE = re.compile(r"'[^']*\.[^']*'")

def _sanitize_err(msg: str) -> str:
    """Redact FQN-shaped tokens from exception messages before surfacing to callers."""
    return _FQN_RE.sub("'<object>'", str(msg))


_PARSE_BLOCKING = frozenset({
    'UNRECOGNIZED_EXPLAIN_OP',
    'UNHANDLED_JOIN_TYPE',
    'JOIN_NO_KEY_EXTRACTED',
    'ZERO_TABLES_EXTRACTED',
    'UNRESOLVED_JOIN_ALIAS',
})


def _warn(code: str, message: str) -> dict:
    return {'code': code, 'message': message}


def _is_blocking(w: dict) -> bool:
    return w['code'] in _PARSE_BLOCKING


def _classify_verdict(q_id: str, workload: dict, gaps: list) -> dict:
    """Classify a single question verdict. Priority: EXPLAIN_FAILED > NOT_ANSWERABLE > UNKNOWN > ANSWERABLE."""
    warnings = workload.get('warnings', [])
    warn_messages = [w['message'] if isinstance(w, dict) else w for w in warnings]

    if workload.get('explain_failed'):
        return {
            'question_id': q_id,
            'status': 'EXPLAIN_FAILED',
            'failure_mode': 'EXPLAIN_ERROR',
            'gap_detail': workload.get('explain_error', 'EXPLAIN call failed'),
            'warnings': warn_messages,
            'confidence': None,
        }

    if gaps:
        blocking = [w for w in warnings if isinstance(w, dict) and _is_blocking(w)]
        return {
            'question_id': q_id,
            'status': 'NOT_ANSWERABLE',
            'failure_mode': gaps[0]['gap_type'],
            'gap_detail': gaps[0]['detail'],
            'warnings': warn_messages,
            'confidence': 'low' if blocking else 'high',
        }

    blocking = [w for w in warnings if isinstance(w, dict) and _is_blocking(w)]
    if blocking:
        return {
            'question_id': q_id,
            'status': 'UNKNOWN',
            'failure_mode': blocking[0]['code'],
            'gap_detail': blocking[0]['message'],
            'warnings': warn_messages,
            'confidence': 'low',
        }

    return {
        'question_id': q_id,
        'status': 'ANSWERABLE',
        'failure_mode': None,
        'gap_detail': None,
        'warnings': warn_messages,
        'confidence': 'high',
    }


def _extract_block(ddl: str, block_name: str) -> str:
    """Extract content inside block_name(...) using paren-depth counting."""
    pattern = re.compile(rf'\b{block_name}\s*\(', re.IGNORECASE)
    m = pattern.search(ddl)
    if not m:
        return ''
    start = m.end()
    depth = 1
    i = start
    while i < len(ddl) and depth > 0:
        if ddl[i] == '(':
            depth += 1
        elif ddl[i] == ')':
            depth -= 1
        i += 1
    return ddl[start:i - 1]


def _unquote(identifier: str) -> str:
    """Strip double-quotes from a quoted Snowflake identifier and uppercase it."""
    s = identifier.strip()
    if s.startswith('"') and s.endswith('"') and len(s) > 2:
        return s[1:-1].upper()
    return s.upper()


def _parse_col_list(expr: str) -> list:
    if not expr:
        return []
    return [_unquote(c) for c in expr.split(',') if c.strip()]


def _parse_join_keys(expr: str) -> tuple:
    """Return ([(left_ref, right_ref), ...], [unparsed_fragment_strings])."""
    pairs = []
    unparsed = []
    matched_spans = []

    # Standard equi-join: joinKey: (alias.col = alias.col) — handles quoted identifiers
    _EQUI = re.compile(
        r'joinKey:\s*\(("?\w+"?)\.("?\w+"?)\s*=\s*("?\w+"?)\.("?\w+"?)\)',
        re.IGNORECASE
    )
    for m in _EQUI.finditer(expr):
        matched_spans.append((m.start(), m.end()))
        pairs.append((
            f"{_unquote(m.group(1))}.{_unquote(m.group(2))}",
            f"{_unquote(m.group(3))}.{_unquote(m.group(4))}",
        ))

    # Non-equi: joinKey with inequality operators
    _NON_EQUI = re.compile(
        r'joinKey:\s*\([^)]*(?:>=|<=|<>|!=|(?<!=)>(?!=)|(?<!=)<(?!=)|BETWEEN|LIKE)[^)]*\)',
        re.IGNORECASE
    )
    for m in _NON_EQUI.finditer(expr):
        if not any(s <= m.start() < e for s, e in matched_spans):
            unparsed.append(f"non-equi join condition: {m.group(0)[:120]}")

    # Catch any remaining unparsed joinKey fragments
    for m in re.finditer(r'joinKey:\s*\([^)]{0,200}\)', expr, re.IGNORECASE):
        if not any(s <= m.start() < e for s, e in matched_spans):
            raw = m.group(0)
            if not any(op in raw.upper() for op in ['>=', '<=', '<>', '!=', 'BETWEEN', 'LIKE']):
                unparsed.append(f"unrecognized joinKey pattern: {raw[:120]}")

    return pairs, unparsed


def _parse_expr_cols(expr: str) -> list:
    """Extract (alias, col) pairs from Filter/Result/Project expressions."""
    result = []
    for m in re.finditer(r'\b("?\w+"?)\."?(\w+)"?\b', expr):
        result.append((_unquote(m.group(1)), _unquote(m.group(2))))
    return result


def _extract_expr_column_tokens(expr: str) -> list:
    """Extract bare column name tokens from a SQL expression (RHS of AS in DIMS/FACTS/METRICS).
    Strips function names, operators, literals. Returns uppercase identifiers that look like column names.
    """
    expr = re.sub(r"'[^']*'", '', expr)
    tokens = []
    for m in re.finditer(r'\b([A-Z_][A-Z0-9_]*)\b(?!\s*\()', expr.upper()):
        tok = m.group(1)
        skip = {'AS', 'AND', 'OR', 'NOT', 'NULL', 'TRUE', 'FALSE', 'IS', 'IN',
                'WHEN', 'THEN', 'ELSE', 'END', 'CASE', 'CAST', 'DESC', 'ASC'}
        if tok not in skip and not tok.isdigit():
            tokens.append(tok)
    return tokens


_HANDLED_JOIN_RE = re.compile(
    r'^(inner|left(\s+outer)?|right(\s+outer)?|full(\s+outer)?|cross|semi|anti)\s*join$',
    re.IGNORECASE
)
_UNHANDLED_JOIN_RE = re.compile(
    r'\b(lateral|natural|asof|range|positional)', re.IGNORECASE
)
_KNOWN_OPS = frozenset({
    '', 'GlobalStats', 'Limit', 'Sort', 'SortWithLimit', 'Aggregate',
    'Result', 'Filter', 'TableScan', 'JoinFilter', 'Values', 'Window',
    'UnionAll', 'Except', 'Intersect', 'Flatten', 'WithClause',
    'WithReference', 'Project',
})


def explain_parser(session: Session, sql_text: str) -> dict:
    """Run EXPLAIN USING TABULAR and extract workload requirements."""
    _empty = {'explain_failed': False, 'tables': set(), 'join_keys': set(), 'columns': {}, 'alias_to_fqn': {}, 'warnings': []}
    sql_text = sql_text.strip()
    if not sql_text:
        return _empty

    try:
        rows = session.sql(f"EXPLAIN USING TABULAR {sql_text}").collect()
    except Exception as exc:
        return {
            'explain_failed': True,
            'explain_error': _sanitize_err(exc),
            'tables': set(),
            'join_keys': set(),
            'columns': {},
            'alias_to_fqn': {},
            'warnings': [],
        }

    alias_to_fqn = {}
    join_keys = set()
    columns = defaultdict(set)
    warnings = []

    for row in rows:
        op = row['operation'] or ''
        if op == 'TableScan':
            fqn = _unquote(row['objects'] or '') if row['objects'] else ''
            alias = _unquote(row['alias'] or '') if row['alias'] else ''
            if not alias and fqn:
                alias = fqn.split('.')[-1]
            if fqn and alias:
                alias_to_fqn[alias] = fqn
            for col in _parse_col_list(row['expressions'] or ''):
                if alias:
                    columns[alias].add(col)
        elif 'join' in op.lower() and op.lower() != 'joinfilter':
            expr = row['expressions'] or ''
            if _UNHANDLED_JOIN_RE.search(op):
                warnings.append(_warn('UNHANDLED_JOIN_TYPE',
                    f"Unhandled join type '{op}' — join/column requirements may be incomplete"))
            elif _HANDLED_JOIN_RE.match(op):
                pairs, unparsed = _parse_join_keys(expr)
                for pair in pairs:
                    join_keys.add(frozenset(pair))
                for fragment in unparsed:
                    warnings.append(_warn('UNHANDLED_JOIN_TYPE', fragment))
                if not pairs and expr:
                    warnings.append(_warn('JOIN_NO_KEY_EXTRACTED',
                        f"No equi-join key extracted from '{op}' expression: {expr[:120]}"))
            else:
                warnings.append(_warn('UNRECOGNIZED_EXPLAIN_OP',
                    f"Unrecognized join operation '{op}' — join/column requirements may be incomplete"))
        elif op in ('Filter', 'Result', 'Project'):
            for alias, col in _parse_expr_cols(row['expressions'] or ''):
                if alias:
                    columns[alias].add(col)
        elif op not in _KNOWN_OPS:
            warnings.append(_warn('UNRECOGNIZED_EXPLAIN_OP',
                f"Unrecognized EXPLAIN operation '{op}' — join/column requirements may be incomplete"))

    if not alias_to_fqn:
        warnings.append(_warn('ZERO_TABLES_EXTRACTED',
            "EXPLAIN plan contained no TableScan rows — SQL may use temp objects, session variables, or CTEs that hide physical table references"))

    for jk in join_keys:
        for part in jk:
            alias = part.split('.')[0]
            if alias not in alias_to_fqn:
                warnings.append(_warn('UNRESOLVED_JOIN_ALIAS',
                    f"Join key alias '{alias}' not found in TableScan alias map"))

    return {
        'explain_failed': False,
        'tables': set(alias_to_fqn.values()),
        'join_keys': join_keys,
        'columns': dict(columns),
        'alias_to_fqn': alias_to_fqn,
        'warnings': warnings,
    }


def sv_manifest_parser(session: Session, sv_name: str) -> dict:
    """Parse GET_DDL output for a semantic view into a structured manifest."""
    try:
        # HIGH-2: escape single quotes to prevent injection via sv_name
        sv_name_safe = sv_name.replace("'", "''")
        ddl = session.sql(f"SELECT GET_DDL('SEMANTIC_VIEW', '{sv_name_safe}')").collect()[0][0]
    except Exception as exc:
        return {
            'registered_fqns': set(), 'alias_map': {}, 'fqn_to_alias': {},
            'relationships': set(), 'relationship_pairs': [],
            'exposed_cols': set(), 'source_cols': set(),
            'parse_warnings': [],
            'parse_error': _sanitize_err(exc),
        }

    # --- Tables block ---
    tables_block = _extract_block(ddl, 'tables')
    alias_map = {}  # logical_alias → physical_fqn (uppercase)

    for m in re.finditer(
        r'(?:("?\w+"?)\s+as\s+)?([\w."]+)\s+primary\s+key',
        tables_block, re.IGNORECASE
    ):
        alias_token = m.group(1)
        fqn = m.group(2).replace('"', '').upper()
        if alias_token:
            logical = _unquote(alias_token)
        else:
            # M2 fix: unaliased → last segment as logical alias
            logical = fqn.split('.')[-1]
        alias_map[logical] = fqn

    registered_fqns = set(alias_map.values())
    fqn_to_alias = {v: k for k, v in alias_map.items()}

    # --- Relationships block ---
    rel_block = _extract_block(ddl, 'relationships')
    relationships = set()
    relationship_pairs = []
    parse_warnings = []

    for m in re.finditer(
        r'(?:\w+\s+as\s+)?("?\w+"?)\s*\(([^)]+)\)\s+references\s+("?\w+"?)\s*\(([^)]+)\)',
        rel_block, re.IGNORECASE
    ):
        from_alias = _unquote(m.group(1))
        from_cols  = [c.strip().upper() for c in m.group(2).split(',')]
        to_alias   = _unquote(m.group(3))
        to_cols    = [c.strip().upper() for c in m.group(4).split(',')]

        # frozenset per column pair for backward-compat gap_differ lookup
        for fc, tc in zip(from_cols, to_cols):
            relationships.add(frozenset({f"{from_alias}.{fc}", f"{to_alias}.{tc}"}))

        relationship_pairs.append({
            'from': from_alias,
            'from_cols': from_cols,
            'to': to_alias,
            'to_cols': to_cols,
            'composite': len(from_cols) > 1,
        })

    # Warn on any rel_block fragments that look like relationship entries but didn't match
    for frag in re.finditer(r'\b\w+\s+as\s+\w+[^,\n]{0,200}', rel_block, re.IGNORECASE):
        raw = frag.group(0)
        if 'references' in raw.lower() and not re.search(
            r'(?:\w+\s+as\s+)?"?\w+"?\s*\([^)]+\)\s+references\s+"?\w+"?\s*\([^)]+\)',
            raw, re.IGNORECASE
        ):
            parse_warnings.append(f"unmatched relationship fragment: {raw[:120]}")

    # --- Dimensions, Facts, Metrics blocks ---
    exposed_cols = set()   # logical_alias.col_name (LHS of 'as')
    source_cols = set()    # logical_alias.physical_col (tokens from RHS expression)

    for block_name in ('dimensions', 'facts', 'metrics'):
        block = _extract_block(ddl, block_name)
        if not block:
            continue
        for m in re.finditer(
            r'("?\w+"?)\.(\w+)\s+as\s+([^,\n]+)',
            block, re.IGNORECASE
        ):
            sv_alias = _unquote(m.group(1))
            col_name = m.group(2).upper()
            expr = m.group(3).strip()
            exposed_cols.add(f"{sv_alias}.{col_name}")
            # C2 fix: index physical column tokens from the RHS expression
            for tok in _extract_expr_column_tokens(expr):
                source_cols.add(f"{sv_alias}.{tok}")

    return {
        'registered_fqns': registered_fqns,
        'alias_map': alias_map,
        'fqn_to_alias': fqn_to_alias,
        'relationships': relationships,
        'relationship_pairs': relationship_pairs,
        'exposed_cols': exposed_cols,
        'source_cols': source_cols,
        'parse_warnings': parse_warnings,
    }


def gap_differ(workload: dict, sv: dict) -> list:
    """Diff workload manifest against SV manifest. Returns gaps list."""
    gaps = []
    fqn_to_alias = sv['fqn_to_alias']

    # --- TABLE_NOT_REGISTERED ---
    for fqn in workload['tables']:
        if fqn not in sv['registered_fqns']:
            gaps.append({
                'gap_type': 'TABLE_NOT_REGISTERED',
                'physical_table': fqn,
                'element': None,
                'detail': f'{fqn} used in GT SQL but not registered in SV TABLES block',
            })

    # Build relationship endpoint set — columns used as FK/PK join keys in SV relationships.
    # These appear in EXPLAIN plans due to joins but are "handled" by the relationship itself,
    # not by explicit DIMENSIONS exposure. Suppress COLUMN_NOT_EXPOSED for these.
    rel_endpoints: set = set()
    for rel_pair in sv['relationships']:
        for endpoint in rel_pair:
            rel_endpoints.add(endpoint)

    # --- COLUMN_NOT_EXPOSED ---
    for q_alias, cols in workload['columns'].items():
        fqn = workload['alias_to_fqn'].get(q_alias)
        if not fqn:
            continue
        sv_alias = fqn_to_alias.get(fqn)
        if not sv_alias:
            continue  # TABLE_NOT_REGISTERED already covers this
        for col in cols:
            logical_ref = f"{sv_alias}.{col}"
            if (logical_ref not in sv['exposed_cols'] and
                    logical_ref not in sv['source_cols'] and
                    logical_ref not in rel_endpoints):
                gaps.append({
                    'gap_type': 'COLUMN_NOT_EXPOSED',
                    'physical_table': fqn,
                    'element': col,
                    'detail': f'{fqn}.{col} referenced in GT SQL but not exposed in SV DIMENSIONS/FACTS/METRICS',
                })

    # --- RELATIONSHIP_MISSING ---
    for jk_frozenset in workload['join_keys']:
        parts = list(jk_frozenset)
        resolved = []
        for part in parts:
            q_alias, col = part.split('.', 1)
            fqn = workload['alias_to_fqn'].get(q_alias)
            sv_alias = fqn_to_alias.get(fqn) if fqn else None
            resolved.append(f"{sv_alias}.{col}" if sv_alias else None)
        if None not in resolved:
            sv_pair = frozenset(resolved)
            if sv_pair not in sv['relationships']:
                gaps.append({
                    'gap_type': 'RELATIONSHIP_MISSING',
                    'physical_table': None,
                    'element': ' = '.join(sorted(sv_pair)),
                    'detail': 'JOIN condition in GT SQL has no corresponding RELATIONSHIPS entry in SV',
                })

    return gaps


def sv_coverage_checker(session: Session, gt_table: str, sv_name: str,
                        validate_data: bool = False) -> dict:
    """
    Main entry point. Expects gt_table to have columns (QUESTION_ID, SQL_TEXT).
    Returns VARIANT with keys: checker_version, gaps[], verdicts[], summary{}, warnings[].

    validate_data (optional, default False):
        When True, execute each SQL_TEXT against actual data (LIMIT 3) and attach
        the top rows to each verdict as 'actual_top_rows'. Useful for GT data validation:
        confirms structural ANSWERABLE verdict with grounded data results.
    """
    # HIGH-1: validate identifiers before any session call
    _IDENT_RE = re.compile(r'^[\w]+(?:\.[\w]+){0,2}$')
    if not _IDENT_RE.match(gt_table):
        raise ValueError(f"gt_table must be a plain identifier (got: {gt_table!r})")
    if not _IDENT_RE.match(sv_name):
        raise ValueError(f"sv_name must be a plain identifier (got: {sv_name!r})")

    rows = session.sql(f"SELECT QUESTION_ID, SQL_TEXT FROM {gt_table}").collect()

    # MEDIUM-2: guard against oversized GT tables
    _MAX_ROWS = 500
    if len(rows) > _MAX_ROWS:
        raise ValueError(
            f"GT table has {len(rows)} rows; limit is {_MAX_ROWS}. "
            f"Split into batches or raise limit by changing _MAX_ROWS."
        )

    per_question = {}
    all_warnings = []
    skipped_ids = set()
    actual_data: dict = {}  # q_id → list of row dicts (populated when validate_data=True)

    for row in rows:
        q_id = str(row['QUESTION_ID'])
        sql = (row['SQL_TEXT'] or '').strip()
        if not sql:
            skipped_ids.add(q_id)
            continue
        try:
            w = explain_parser(session, sql)
        except Exception as exc:
            w = {
                'explain_failed': True,
                'explain_error': _sanitize_err(exc),
                'tables': set(),
                'join_keys': set(),
                'columns': {},
                'alias_to_fqn': {},
                'warnings': [],
            }
        per_question[q_id] = w
        if not w.get('explain_failed'):
            all_warnings.extend(w.get('warnings', []))

        if validate_data and not w.get('explain_failed'):
            try:
                data_rows = session.sql(f"{sql} LIMIT 3").collect()
                actual_data[q_id] = [r.as_dict() for r in data_rows]
            except Exception as exc:
                actual_data[q_id] = [{'_error': _sanitize_err(exc)}]

    # Build global workload from non-failed questions only
    global_workload = {
        'tables': set(), 'join_keys': set(),
        'columns': defaultdict(set), 'alias_to_fqn': {},
    }
    for w in per_question.values():
        if w.get('explain_failed'):
            continue
        global_workload['tables'].update(w['tables'])
        global_workload['join_keys'].update(w['join_keys'])
        for alias, cols in w['columns'].items():
            global_workload['columns'][alias].update(cols)
        global_workload['alias_to_fqn'].update(w['alias_to_fqn'])
    global_workload['columns'] = dict(global_workload['columns'])

    sv = sv_manifest_parser(session, sv_name)
    if 'parse_error' in sv:
        all_warnings.append(_warn('SV_PARSE_ERROR', f"SV manifest parse failed: {sv['parse_error']}"))

    gaps = gap_differ(global_workload, sv)

    verdicts = []
    for q_id in skipped_ids:
        verdicts.append({
            'question_id': q_id,
            'status': 'SKIPPED',
            'failure_mode': None,
            'gap_detail': 'SQL_TEXT is NULL or empty',
            'warnings': [],
            'confidence': None,
        })

    for q_id, w in per_question.items():
        if w.get('explain_failed'):
            v = _classify_verdict(q_id, w, [])
        else:
            q_gaps = gap_differ(w, sv)
            v = _classify_verdict(q_id, w, q_gaps)
        if validate_data and q_id in actual_data:
            v['actual_top_rows'] = actual_data[q_id]
        verdicts.append(v)

    summary = {
        'total_questions': len(verdicts),
        'answerable': sum(1 for v in verdicts if v['status'] == 'ANSWERABLE'),
        'not_answerable': sum(1 for v in verdicts if v['status'] == 'NOT_ANSWERABLE'),
        'unknown': sum(1 for v in verdicts if v['status'] == 'UNKNOWN'),
        'explain_failed': sum(1 for v in verdicts if v['status'] == 'EXPLAIN_FAILED'),
        'skipped': len(skipped_ids),
        'unique_gaps': len(gaps),
        'validate_data': validate_data,
    }

    # C3 fix: return dict (Snowpark auto-converts to VARIANT), do NOT use json.dumps()
    return {
        'checker_version': CHECKER_VERSION,
        'gaps': gaps,
        'verdicts': verdicts,
        'summary': summary,
        'warnings': [w['message'] for w in all_warnings],
    }

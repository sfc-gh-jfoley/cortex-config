"""
Tests for vqr-eval-health Check 8 (subquery SQL detection) and the phase 11
subquery context classifier (MISSING_TABLE_CANDIDATES vs SUBQUERY_FILTER_CANDIDATES).

Run: python -m pytest tests/test_vqr_subquery_checks.py -v
"""

from __future__ import annotations

import re
from typing import Any


# ---------------------------------------------------------------------------
# Check 8 — exact implementation from references/vqr-eval-health.md
# ---------------------------------------------------------------------------

def check_vqr_subqueries(vqr_list: list[dict]) -> list[dict]:
    """Detect VQR SQL containing subqueries (nested SELECT statements)."""
    issues = []
    for vqr in vqr_list:
        sql = vqr["sql"]
        select_count = len(re.findall(r"\bSELECT\b", sql, re.IGNORECASE))
        if select_count > 1:
            issues.append({
                "vqr": vqr["name"],
                "issue": "contains subquery — Analyst cannot generate subquery-based SQL",
                "fix": "rewrite without subquery, or add the filtering table as an SV relationship",
            })
    return issues


# ---------------------------------------------------------------------------
# Phase 11 subquery context classifier
# Implements the distinction described in 11_audit_scan.md point 1:
#   FROM/JOIN table refs  → MISSING_TABLE_CANDIDATES
#   WHERE subquery refs only → SUBQUERY_FILTER_CANDIDATES
#
# Uses depth tracking so that FROM/JOIN inside a (SELECT ...) block is
# classified as a subquery reference, not a top-level join reference.
# ---------------------------------------------------------------------------

def classify_table_references(
    query_text: str,
    sv_tables: set[str],
) -> dict[str, set[str]]:
    """
    Depth-aware FROM/JOIN classifier.

    Returns:
      join_candidates:      tables in top-level FROM/JOIN, not already in the SV
      subquery_candidates:  tables that appear only inside (SELECT ...) blocks
    """
    q = query_text.upper()
    sv_upper = {t.upper() for t in sv_tables}

    top_level: set[str] = set()
    in_subquery: set[str] = set()

    depth = 0
    # Track which open-paren depths opened a SELECT subquery
    select_at_depth: set[int] = set()

    i = 0
    n = len(q)

    while i < n:
        c = q[i]

        if c == "(":
            depth += 1
            # Peek past whitespace — is the next token SELECT?
            j = i + 1
            while j < n and q[j] in " \t\n\r":
                j += 1
            if re.match(r"SELECT\b", q[j:]):
                select_at_depth.add(depth)
            i += 1

        elif c == ")":
            select_at_depth.discard(depth)
            depth -= 1
            i += 1

        else:
            # Attempt a FROM/JOIN match only at a word boundary
            if i == 0 or not (q[i - 1].isalpha() or q[i - 1] == "_"):
                m = re.match(r"(?:FROM|JOIN)\s+([\w.]+)", q[i:])
                if m:
                    tbl = m.group(1)
                    if tbl not in sv_upper:
                        if select_at_depth:  # inside any SELECT subquery block
                            in_subquery.add(tbl)
                        else:
                            top_level.add(tbl)
                    i += m.end()
                    continue
            i += 1

    return {
        "join_candidates": top_level,
        "subquery_candidates": in_subquery - top_level,
    }


# ===========================================================================
# Tests — Check 8
# ===========================================================================

class TestCheck8SubqueryDetection:

    # --- clean VQRs (should produce no issues) ---

    def test_clean_simple_aggregate(self):
        vqrs = [{"name": "total_rev", "sql": "SELECT SUM(amount) AS total_revenue FROM __orders WHERE year = 2024"}]
        assert check_vqr_subqueries(vqrs) == []

    def test_clean_group_by_dimension(self):
        vqrs = [{"name": "rev_by_region", "sql": "SELECT region, SUM(amount) AS revenue FROM __orders GROUP BY region"}]
        assert check_vqr_subqueries(vqrs) == []

    def test_clean_with_where_and_having(self):
        vqrs = [{"name": "top_cust", "sql": "SELECT cust_id, SUM(amount) FROM __orders WHERE year = 2024 GROUP BY cust_id HAVING SUM(amount) > 1000"}]
        assert check_vqr_subqueries(vqrs) == []

    def test_clean_multi_metric_single_select(self):
        vqrs = [{"name": "multi", "sql": "SELECT SUM(amount) AS revenue, COUNT(*) AS order_count FROM __orders"}]
        assert check_vqr_subqueries(vqrs) == []

    def test_clean_join_two_sv_tables(self):
        # A VQR that JOINs tables already in the SV — still one outermost SELECT
        vqrs = [{"name": "joined", "sql": "SELECT o.region, SUM(o.amount) FROM __orders o JOIN __customers c ON o.cust_id = c.cust_id GROUP BY o.region"}]
        assert check_vqr_subqueries(vqrs) == []

    def test_multiple_clean_vqrs_all_pass(self):
        vqrs = [
            {"name": "v1", "sql": "SELECT SUM(amount) FROM __orders"},
            {"name": "v2", "sql": "SELECT region, COUNT(*) FROM __orders GROUP BY region"},
        ]
        assert check_vqr_subqueries(vqrs) == []

    # --- subquery VQRs (should be flagged) ---

    def test_where_in_subquery(self):
        sql = "SELECT SUM(amount) FROM __orders WHERE cust_id IN (SELECT cust_id FROM __customers WHERE region = 'EAST')"
        issues = check_vqr_subqueries([{"name": "in_subquery", "sql": sql}])
        assert len(issues) == 1
        assert issues[0]["vqr"] == "in_subquery"

    def test_where_not_in_subquery(self):
        sql = "SELECT SUM(amount) FROM __orders WHERE cust_id NOT IN (SELECT cust_id FROM __customers WHERE region = 'WEST')"
        issues = check_vqr_subqueries([{"name": "not_in_subquery", "sql": sql}])
        assert len(issues) == 1

    def test_where_exists_subquery(self):
        sql = "SELECT region, SUM(amount) FROM __orders o WHERE EXISTS (SELECT 1 FROM __customers c WHERE c.cust_id = o.cust_id) GROUP BY region"
        issues = check_vqr_subqueries([{"name": "exists_subquery", "sql": sql}])
        assert len(issues) == 1

    def test_scalar_subquery_equality(self):
        sql = "SELECT SUM(amount) FROM __orders WHERE cust_id = (SELECT MIN(cust_id) FROM __customers)"
        issues = check_vqr_subqueries([{"name": "scalar_eq", "sql": sql}])
        assert len(issues) == 1

    def test_scalar_subquery_comparison(self):
        sql = "SELECT SUM(amount) FROM __orders WHERE amount > (SELECT AVG(amount) FROM __orders)"
        issues = check_vqr_subqueries([{"name": "scalar_gt", "sql": sql}])
        assert len(issues) == 1

    def test_semantic_view_as_subquery_target(self):
        # Subquery itself is a SEMANTIC_VIEW() query
        sql = (
            "SELECT * FROM SEMANTIC_VIEW(sv_orders DIMENSIONS d_cust_id METRICS m_total "
            "WHERE d_cust_id IN (SELECT * FROM SEMANTIC_VIEW(sv_customers DIMENSIONS d_cust_id WHERE d_region = 'EAST')))"
        )
        issues = check_vqr_subqueries([{"name": "sv_subquery", "sql": sql}])
        assert len(issues) == 1

    def test_case_insensitive_select_keyword(self):
        sql = "select sum(amount) from __orders where cust_id in (select cust_id from __customers)"
        issues = check_vqr_subqueries([{"name": "lower_case", "sql": sql}])
        assert len(issues) == 1

    def test_union_all_also_flagged(self):
        # UNION ALL is also a rule-5 violation (complex SQL); flagging it is correct
        sql = "SELECT SUM(amount) FROM __orders WHERE year = 2024 UNION ALL SELECT SUM(amount) FROM __orders WHERE year = 2023"
        issues = check_vqr_subqueries([{"name": "union_vqr", "sql": sql}])
        assert len(issues) == 1

    def test_only_flagged_vqr_reported(self):
        vqrs = [
            {"name": "clean", "sql": "SELECT SUM(amount) FROM __orders"},
            {"name": "bad", "sql": "SELECT SUM(amount) FROM __orders WHERE cust_id IN (SELECT cust_id FROM __customers)"},
        ]
        issues = check_vqr_subqueries(vqrs)
        assert len(issues) == 1
        assert issues[0]["vqr"] == "bad"

    def test_multiple_subquery_vqrs_all_flagged(self):
        vqrs = [
            {"name": "v1", "sql": "SELECT SUM(a) FROM __t WHERE id IN (SELECT id FROM __lookup1)"},
            {"name": "v2", "sql": "SELECT SUM(b) FROM __t WHERE id IN (SELECT id FROM __lookup2)"},
        ]
        issues = check_vqr_subqueries(vqrs)
        assert len(issues) == 2
        assert {i["vqr"] for i in issues} == {"v1", "v2"}

    def test_issue_contains_fix_guidance(self):
        sql = "SELECT SUM(amount) FROM __orders WHERE cust_id IN (SELECT cust_id FROM __customers)"
        issues = check_vqr_subqueries([{"name": "q", "sql": sql}])
        assert "relationship" in issues[0]["fix"].lower()

    def test_empty_vqr_list(self):
        assert check_vqr_subqueries([]) == []


# ===========================================================================
# Tests — Phase 11 subquery context classifier
# ===========================================================================

SV_TABLES = {"ORDERS", "ORDER_ITEMS"}


class TestSubqueryContextClassifier:

    def test_from_clause_table_is_join_candidate(self):
        query = "SELECT o.id, c.name FROM ORDERS o JOIN CUSTOMERS c ON o.cust_id = c.cust_id"
        result = classify_table_references(query, SV_TABLES)
        assert "CUSTOMERS" in result["join_candidates"]
        assert "CUSTOMERS" not in result["subquery_candidates"]

    def test_join_clause_table_is_join_candidate(self):
        query = "SELECT * FROM ORDERS o INNER JOIN SEGMENTS s ON o.seg_id = s.id"
        result = classify_table_references(query, SV_TABLES)
        assert "SEGMENTS" in result["join_candidates"]
        assert "SEGMENTS" not in result["subquery_candidates"]

    def test_subquery_only_table_is_filter_candidate(self):
        query = "SELECT SUM(amount) FROM ORDERS WHERE cust_id IN (SELECT cust_id FROM CUSTOMERS WHERE region = 'EAST')"
        result = classify_table_references(query, SV_TABLES)
        assert "CUSTOMERS" not in result["join_candidates"]
        assert "CUSTOMERS" in result["subquery_candidates"]

    def test_exists_subquery_only_table_is_filter_candidate(self):
        query = "SELECT id FROM ORDERS WHERE EXISTS (SELECT 1 FROM BLACKLIST WHERE BLACKLIST.id = ORDERS.id)"
        result = classify_table_references(query, SV_TABLES)
        assert "BLACKLIST" in result["subquery_candidates"]
        assert "BLACKLIST" not in result["join_candidates"]

    def test_table_in_both_from_and_subquery_is_join_candidate(self):
        # Explicit JOIN + also used inside a WHERE subquery — should be join candidate only
        query = "SELECT * FROM ORDERS o JOIN CUSTOMERS c ON o.cust_id = c.cust_id WHERE o.cust_id IN (SELECT cust_id FROM CUSTOMERS WHERE active = 1)"
        result = classify_table_references(query, SV_TABLES)
        assert "CUSTOMERS" in result["join_candidates"]
        assert "CUSTOMERS" not in result["subquery_candidates"]

    def test_sv_tables_not_returned_as_candidates(self):
        # Tables already in the SV should not appear in either candidate set
        query = "SELECT * FROM ORDERS WHERE id IN (SELECT id FROM ORDER_ITEMS WHERE qty > 0)"
        result = classify_table_references(query, SV_TABLES)
        assert "ORDERS" not in result["join_candidates"]
        assert "ORDER_ITEMS" not in result["subquery_candidates"]

    def test_no_external_tables(self):
        query = "SELECT SUM(amount) FROM ORDERS GROUP BY region"
        result = classify_table_references(query, SV_TABLES)
        assert result["join_candidates"] == set()
        assert result["subquery_candidates"] == set()

    def test_multiple_external_tables_mixed_contexts(self):
        query = (
            "SELECT o.region, SUM(o.amount) "
            "FROM ORDERS o "
            "JOIN PRODUCTS p ON o.prod_id = p.id "
            "WHERE o.cust_id IN (SELECT cust_id FROM CUSTOMERS WHERE tier = 'gold') "
            "GROUP BY o.region"
        )
        result = classify_table_references(query, SV_TABLES)
        assert "PRODUCTS" in result["join_candidates"]
        assert "CUSTOMERS" in result["subquery_candidates"]
        assert "CUSTOMERS" not in result["join_candidates"]
        assert "PRODUCTS" not in result["subquery_candidates"]


# ===========================================================================
# Integration: round-trip the detection logic against the exact examples
# from the documentation page
# ===========================================================================

class TestDocExamples:
    """Verify detection against the exact SQL patterns from the Snowflake docs page."""

    DOC_VALID_EXAMPLES = [
        # WHERE IN — raw table
        "SELECT * FROM SEMANTIC_VIEW(sv_orders DIMENSIONS ord.d_cust_id METRICS ord.m_total WHERE ord.d_cust_id IN (SELECT cust_id FROM t_customers))",
        # WHERE NOT IN
        "SELECT * FROM SEMANTIC_VIEW(sv_orders DIMENSIONS ord.d_cust_id WHERE d_cust_id NOT IN (SELECT cust_id FROM t_customers WHERE region = 'WEST'))",
        # Scalar subquery
        "SELECT * FROM SEMANTIC_VIEW(sv_orders DIMENSIONS ord.d_cust_id WHERE d_cust_id = (SELECT MIN(cust_id) FROM t_customers))",
        # Nested SV subquery
        "SELECT * FROM SEMANTIC_VIEW(sv_orders DIMENSIONS ord.d_cust_id METRICS ord.m_total WHERE ord.d_cust_id IN (SELECT * FROM SEMANTIC_VIEW(sv_customers DIMENSIONS cust.d_cust_id WHERE cust.d_region = 'EAST')))",
        # DIMENSIONS ad-hoc subquery
        "SELECT * FROM SEMANTIC_VIEW(sv_orders DIMENSIONS ord.d_cust_id IN (SELECT cust_id FROM t_customers) METRICS ord.m_total)",
    ]

    def test_all_doc_subquery_examples_are_flagged(self):
        vqrs = [{"name": f"doc_{i}", "sql": sql} for i, sql in enumerate(self.DOC_VALID_EXAMPLES)]
        issues = check_vqr_subqueries(vqrs)
        flagged = {iss["vqr"] for iss in issues}
        for vqr in vqrs:
            assert vqr["name"] in flagged, f"{vqr['name']} not flagged:\n{vqr['sql']}"

    DOC_INVALID_FROM_FACTS_METRICS = [
        # Doc says these are INVALID (subquery in FACTS/METRICS) — but they still have 2 SELECTs,
        # so Check 8 would catch them regardless of the specific restriction
        "SELECT * FROM SEMANTIC_VIEW(sv_orders FACTS f_amount * (SELECT MAX(amount) FROM t_orders))",
        "SELECT * FROM SEMANTIC_VIEW(sv_orders METRICS m_total / (SELECT COUNT(*) FROM t_customers))",
    ]

    def test_facts_metrics_subquery_examples_also_flagged(self):
        vqrs = [{"name": f"invalid_{i}", "sql": sql} for i, sql in enumerate(self.DOC_INVALID_FROM_FACTS_METRICS)]
        issues = check_vqr_subqueries(vqrs)
        assert len(issues) == len(vqrs)

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location("sv_validator_m2m", ROOT / "scripts" / "sv_validator.py")
validator = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = validator
SPEC.loader.exec_module(validator)


def _ddl(tables, relationships, metrics="orders.total_amount AS SUM(amount) COMMENT = 'Total order amount'"):
    return f"""CREATE SEMANTIC VIEW db.sch.sv
TABLES (
{tables}
)
RELATIONSHIPS (
{relationships}
)
DIMENSIONS (
  orders.promo_code AS promo_code COMMENT = 'Promo code on the order'
)
METRICS (
  {metrics}
);"""


DIRECT_TABLES = """  orders AS db.sch.orders PRIMARY KEY (order_id),
  promotions AS db.sch.promotions"""
DIRECT_REL = "  orders_to_promotions AS orders(promo_code) REFERENCES promotions(promo_code)"

BRIDGE_TABLES = """  books AS db.sch.books PRIMARY KEY (book_id),
  authors AS db.sch.authors PRIMARY KEY (author_id),
  book_authors AS db.sch.book_authors PRIMARY KEY (book_id, author_id)"""
BRIDGE_REL = """  book_authors(author_id) REFERENCES authors(author_id),
  book_authors(book_id) REFERENCES books(book_id)"""


def _by_name(results):
    return {r.name: r for r in results}


def test_relationship_parser_captures_right_columns():
    rel = validator._parse_single_relationship(DIRECT_REL.strip())
    assert rel["right_table"] == "promotions"
    assert rel["right_cols"] == ["promo_code"]
    plain = validator._parse_single_relationship("orders(customer_id) REFERENCES customers")
    assert plain["right_table"] == "customers"
    assert plain["right_cols"] == []


def test_direct_m2m_fails_pk_check_by_default_with_hint():
    results = _by_name(validator.validate_ddl(_ddl(DIRECT_TABLES, DIRECT_REL)))
    pk = results["pk_on_referenced_tables"]
    assert not pk.passed and pk.severity == "error"
    assert "allow_many_to_many" in pk.message
    m2m = results["many_to_many_relationships"]
    assert not m2m.passed and m2m.severity == "warning"
    assert "orders_to_promotions" in m2m.message


def test_direct_m2m_passes_when_explicitly_allowed():
    results = _by_name(validator.validate_ddl(_ddl(DIRECT_TABLES, DIRECT_REL), allow_many_to_many=True))
    assert results["pk_on_referenced_tables"].passed
    assert results["many_to_many_relationships"].passed
    assert "orders_to_promotions" in results["many_to_many_relationships"].message


def test_using_metric_on_direct_m2m_endpoint_is_flagged_even_when_allowed():
    metrics = "orders.total_amount USING (orders_to_promotions) AS SUM(amount) COMMENT = 'Total order amount'"
    results = _by_name(validator.validate_ddl(_ddl(DIRECT_TABLES, DIRECT_REL, metrics), allow_many_to_many=True))
    m2m = results["many_to_many_relationships"]
    assert not m2m.passed
    assert "orders.total_amount" in m2m.message


def test_non_unique_column_on_keyed_table_is_direct_m2m():
    tables = """  orders AS db.sch.orders PRIMARY KEY (order_id),
  promotions AS db.sch.promotions PRIMARY KEY (promo_id)"""
    ctx = validator._build_context(_ddl(tables, DIRECT_REL))
    found = validator._direct_many_to_many(ctx)
    assert [r["name"] for r in found] == ["orders_to_promotions"]


def test_referencing_the_primary_key_is_not_m2m():
    tables = """  orders AS db.sch.orders PRIMARY KEY (order_id),
  customers AS db.sch.customers PRIMARY KEY (customer_id)"""
    rel = "  orders_to_customers AS orders(customer_id) REFERENCES customers(customer_id)"
    results = _by_name(validator.validate_ddl(_ddl(tables, rel)))
    assert results["pk_on_referenced_tables"].passed
    assert results["many_to_many_relationships"].passed
    assert "No many-to-many" in results["many_to_many_relationships"].message


def test_asof_relationship_is_not_treated_as_m2m():
    tables = """  orders AS db.sch.orders PRIMARY KEY (order_id),
  rates AS db.sch.rates"""
    rel = "  orders_to_rates AS orders(order_ts) REFERENCES rates(valid_from) ASOF"
    ctx = validator._build_context(_ddl(tables, rel))
    assert validator._direct_many_to_many(ctx) == []


def test_bridge_table_is_detected_and_using_metric_on_endpoint_flagged():
    ddl = _ddl(BRIDGE_TABLES, BRIDGE_REL, "books.total_pages AS SUM(pages) COMMENT = 'Total pages'")
    ctx = validator._build_context(ddl)
    assert [b for b, _ in validator._bridge_tables(ctx)] == ["BOOK_AUTHORS"]
    results = _by_name(validator.validate_ddl(ddl))
    assert results["pk_on_referenced_tables"].passed
    assert results["many_to_many_relationships"].passed
    assert "bridge: BOOK_AUTHORS" in results["many_to_many_relationships"].message

    using = "books.total_pages USING (book_authors) AS SUM(pages) COMMENT = 'Total pages'"
    flagged = _by_name(validator.validate_ddl(_ddl(BRIDGE_TABLES, BRIDGE_REL, using)))
    assert not flagged["many_to_many_relationships"].passed
    assert "books.total_pages" in flagged["many_to_many_relationships"].message


def test_ordinary_fact_with_two_dimensions_is_not_a_bridge():
    tables = """  orders AS db.sch.orders PRIMARY KEY (order_id),
  customers AS db.sch.customers PRIMARY KEY (customer_id),
  products AS db.sch.products PRIMARY KEY (product_id)"""
    rel = """  orders(customer_id) REFERENCES customers,
  orders(product_id) REFERENCES products"""
    assert validator._bridge_tables(validator._build_context(_ddl(tables, rel))) == []


def test_cli_flag_enables_direct_m2m(tmp_path, monkeypatch):
    path = tmp_path / "sv.sql"
    path.write_text(_ddl(DIRECT_TABLES, DIRECT_REL))
    monkeypatch.setattr(sys, "argv", ["sv_validator.py", str(path)])
    assert validator._cli_main() == 1
    monkeypatch.setattr(sys, "argv", ["sv_validator.py", "--allow-many-to-many", str(path)])
    out_ok = validator._cli_main()
    assert out_ok in (0, 1)
    results = _by_name(validator.validate_file(str(path), allow_many_to_many=True))
    assert results["pk_on_referenced_tables"].passed
    assert results["many_to_many_relationships"].passed


def _read(rel):
    return (ROOT / rel).read_text(encoding="utf-8")


def test_materialization_docs_reflect_ga_and_semi_additive():
    mat = _read("skills/sv-materialize/SKILL.md")
    assert "Preview feature (Open" not in mat
    assert "generally available" in mat
    assert "| Semi-additive metric (NON ADDITIVE BY clause) | 🚫 N/A | **Cannot materialize** |" not in mat
    assert "semi-additive metrics (NON ADDITIVE BY), metrics with USING clause" not in mat
    assert "SYSTEM$CHECK_HYPOTHETICAL_SEMANTIC_VIEW_MATERIALIZATION_REWRITE" in mat
    assert "SYSTEM$CHECK_SEMANTIC_VIEW_MATERIALIZATION_REWRITE" in mat
    assert "suggest-sv-materializations" in mat
    snippets = _read("references/sv-snippet-patterns.md")
    assert "Semi-additive metrics (NON ADDITIVE BY) cannot be materialized" not in snippets
    assert "semi-additive (NON ADDITIVE BY) metrics,\nmetrics with USING clause" not in snippets
    assert "can be materialized since GA" in snippets


def test_m2m_docs_no_longer_claim_tables_cannot_be_related():
    rel = _read("skills/sv-ddl/phases/04_relationships.md")
    assert "cannot be directly related in a semantic view" not in rel
    assert "--allow-many-to-many" in rel
    assert "LOD" in rel and "USING" in rel
    audit = _read("skills/sv-audit/phases/12_audit_recommend.md")
    assert "many-to-many joins cannot be\nrelationships" not in audit
    syntax = _read("skills/sv-ddl/reference/ddl_syntax.md")
    assert "many-to-many" in syntax and "2026-11-13" in syntax


def test_metric_parser_reads_modifiers_placed_before_as():
    using = validator._parse_single_column("fact.m USING (rel_a) AS SUM(x)")
    assert using["using"] == "rel_a" and using["expr"] == "SUM(x)"
    semi = validator._parse_single_column("snap.bal NON ADDITIVE BY (d DESC) AS SUM(b)")
    assert semi["non_additive"] and semi["expr"] == "SUM(b)"
    both = validator._parse_single_column("fact.m USING (rel_b) NON ADDITIVE BY (d) AS SUM(x)")
    assert both["using"] == "rel_b" and both["non_additive"]
    plain = validator._parse_single_column("fact.m AS SUM(x) COMMENT = 'c'")
    assert plain["using"] is None and not plain["non_additive"]


def test_multi_relationship_pair_passes_when_metrics_declare_using():
    tables = """  fact AS db.sch.fact PRIMARY KEY (id),
  dates AS db.sch.dates PRIMARY KEY (d)"""
    rels = """  fact_open AS fact(open_d) REFERENCES dates,
  fact_close AS fact(close_d) REFERENCES dates"""
    ok = _ddl(tables, rels, "fact.opened USING (fact_open) AS COUNT(id) COMMENT = 'Opened'")
    bad = _ddl(tables, rels, "fact.opened AS COUNT(id) COMMENT = 'Opened'")
    assert _by_name(validator.validate_ddl(ok))["using_clause_for_multi_rel"].passed
    assert not _by_name(validator.validate_ddl(bad))["using_clause_for_multi_rel"].passed

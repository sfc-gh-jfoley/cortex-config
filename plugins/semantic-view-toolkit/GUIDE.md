# Semantic View Toolkit Guide

This guide follows one team, the analytics group at a retailer, as they turn a sprawling `ANALYTICS_DB` into a semantic view that answers revenue questions reliably. It covers the four stages: create, tune, optimize, and monitor. Names, counts, and scores in the story are illustrative.

## Create

Priya's team has dozens of tables in `ANALYTICS_DB.PUBLIC` and a stakeholder who wants to ask, "What was revenue by region last quarter?" Before writing any DDL, she runs **sv-discovery**. It uses key relationships, naming patterns, and ACCESS_HISTORY co-occurrence to propose domain groupings: orders and customers in one, product catalog in another. It also estimates token size for each proposed SV, which matters because an oversized SV makes the agent prune it, adding latency and lowering answer quality.

She takes the sales grouping and runs **sv-ddl** against it. The skill generates a `CREATE SEMANTIC VIEW` with descriptions for tables, columns, and metrics, classifies columns as dimensions, facts, or metrics, and validates relationships between tables. Priya reviews the output and keeps only the columns the business uses.

The team has a legacy definition of "net revenue" that subtracts returns. The generated description reads "net sales amount," which is not how the business says it. Priya rewrites that description by hand. Generated descriptions are a starting point, and proprietary terms are the part they will not get right on their own.

For a snapshot table, where "revenue at quarter end" needs a semi-additive pattern, Priya uses **sv-snippet-suggester**. It matches the table model to a canonical pattern rather than leaving her to design it from scratch.

## Tune

An SV that compiles and looks right is still unverified. Priya needs verified queries: question and SQL pairs whose answers the team already trusts.

**vqr-generator** mines the last 90 days of query history against the new SV's tables and proposes candidate question and SQL pairs. It marks each candidate VALID, INVALID, or NEEDS_FIX, so Priya knows which ones are usable.

The candidate set is noisy. Some candidates duplicate each other, some use subqueries where a simple aggregate would do, and a few filter differently from the metric definition. **vqr-curator** reviews the set and gives each VQR a verdict: keep, fix the SQL, deduplicate, simplify, or remove. It also reports coverage gaps, such as regional revenue with no VQR at all. The curator makes no changes until Priya approves them.

The aim is roughly ten to twenty VQRs that each cover a distinct question shape. Priya stops adding them once the set covers the common shapes, because more VQRs mostly add redundancy.

As a team practice, Priya holds back a set of eval questions and does not turn them into VQRs. Otherwise the score measures memorization, not accuracy.

## Optimize

Before tuning anything, Priya runs **sv-coverage-checker** against the eval questions. It checks each question structurally: does the SV have the tables, columns, and join paths needed to answer it? Some questions come back NOT_ANSWERABLE because a relationship is missing. She fixes those first, because descriptions cannot repair a missing join.

With the structural gaps closed, she runs **sv-evaluation** to record a baseline `sql_correctness` score against the VQR set.

She then runs **sv-iterative-optimizer**. It changes one thing per iteration, such as a description, a filter, or a synonym, reruns the evaluation, and keeps the change only if the score improves. Each decision is logged. Priya reviews the proposals at each gate. When three consecutive changes are rejected, the local search has stalled.

Priya switches to **sv-gepa-optimizer**, which maintains a population of SV variants and selects winners through tournaments on mini-batches of questions. She reviews the winning configuration and accepts it deliberately. The toolkit never overwrites production on its own.

If the stakeholder later asks questions that span finance and sales, **sv-rearchitect** composes the existing domain SVs into a multi-SV agent or nested SV design. Deciding where to split the domains is still a design choice Priya makes.

## Monitor

The SV is live, and the work does not stop. Two skills keep it healthy.

**sv-audit** is read-only. It compares the SV to what people actually query: tables frequently joined around the SV but not included, columns nobody uses, and joins that appear in queries with no declared relationship. Priya runs it periodically and treats the findings as a backlog.

**sv-watch** runs on a schedule. It catches a schema change that would break the SV, such as a renamed column, and flags time-relative VQRs that have gone stale. "Revenue this quarter" was written against a quarter that has since ended. Its alerts are written to `WATCH_LOG`, and Priya routes them to the team's channel.

Performance is separate from accuracy. When the regional revenue dashboard starts timing out, **sv-materialize** designs a precomputed aggregation with a freshness target. Use it when slowness is real and measured.

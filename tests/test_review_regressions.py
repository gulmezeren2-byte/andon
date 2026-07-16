"""Regression tests from the pre-release review.

Before the first public push, the codebase went through an adversarial review.
Every test in this file pins a finding from that review so it stays fixed:

1. groupby dropping NaN group labels -> false PASS (the critical one)
2. NaN reaching the --json output through empty-filter aggregates
3. reconcile.sum silently swallowing an `agg:` parameter
4. percent_sum coercing text to NaN and passing anyway
5. excel.integrity leaving the honesty block empty
6. filenames containing '#' being misread as sheet references
7. an empty CSV surfacing as an "unexpected" engine error
"""

import json

from conftest import one
from typer.testing import CliRunner

from andon.cli import app
from andon.result import Status

runner = CliRunner()


def test_null_group_labels_are_not_dropped(tmp_path, workbook_factory, run_spec) -> None:
    # One revenue row has no region. The claim only covers EU. A verifier that
    # lets groupby drop the unlabeled row would PASS here — it must FAIL.
    (tmp_path / "sales.csv").write_text(
        "region,revenue\nEU,100\n,50\n", encoding="utf-8"
    )
    wb = workbook_factory("claim.xlsx", {"S": {"A1": "region", "B1": "revenue",
                                               "A2": "EU", "B2": 100.0}})
    report = run_spec(
        {
            "version": 1,
            "sources": {"sales": "sales.csv", "claim": f"{wb.name}#S!A1:B2"},
            "checks": [
                {
                    "reconcile.group_sum": {
                        "column": "revenue",
                        "by": "region",
                        "left": {"source": "sales"},
                        "right": {"source": "claim"},
                    }
                }
            ],
        }
    )
    r = one(report)
    assert r.status is Status.FAIL
    assert "<null>" in r.evidence["only_in_left"]
    assert r.evidence["null_group_labels"]["left"] == 1


def test_percent_sum_by_group_sees_null_labels(tmp_path, run_spec) -> None:
    (tmp_path / "shares.csv").write_text(
        "quarter,share\nQ1,60\nQ1,40\n,100\n", encoding="utf-8"
    )
    report = run_spec(
        {
            "version": 1,
            "sources": {"shares": "shares.csv"},
            "checks": [
                {"internal.percent_sum": {"source": "shares", "column": "share", "by": "quarter"}}
            ],
        }
    )
    r = one(report)
    assert r.status is Status.PASS  # the "<null>" group sums to 100 too — but it is seen
    assert r.evidence["groups"] == 2
    assert r.evidence["null_group_labels"] == 1


def test_empty_filter_aggregate_is_error_not_nan(orders_csv, run_spec) -> None:
    report = run_spec(
        {
            "version": 1,
            "sources": {"orders": orders_csv.name},
            "checks": [
                {
                    "reconcile.aggregate": {
                        "agg": "mean",
                        "column": "revenue",
                        "left": {"source": "orders", "where": "region == 'ATLANTIS'"},
                        "right": {"value": 100.0},
                    }
                }
            ],
        }
    )
    r = one(report)
    assert r.status is Status.ERROR
    assert "0 numeric rows" in r.summary


def test_json_output_never_contains_nan(tmp_path) -> None:
    (tmp_path / "orders.csv").write_text("region,revenue\nEU,1\n", encoding="utf-8")
    spec = tmp_path / "andon.yaml"
    spec.write_text(
        "version: 1\n"
        "sources: {orders: orders.csv}\n"
        "checks:\n"
        "  - reconcile.aggregate:\n"
        "      agg: mean\n"
        "      column: revenue\n"
        "      left: {source: orders, where: \"region == 'NOPE'\"}\n"
        "      right: {value: 1}\n",
        encoding="utf-8",
    )
    result = runner.invoke(app, ["run", str(spec), "--json"])
    assert result.exit_code == 3  # the check ERRORs; it must not FAIL with NaN
    payload = json.loads(result.output)  # valid JSON, full stop
    assert "NaN" not in result.output
    assert payload["verdict"] == "INCOMPLETE"


def test_reconcile_sum_rejects_agg_parameter(orders_csv, run_spec) -> None:
    # `reconcile.sum: {agg: mean}` must be an error, not a silently ignored knob.
    report = run_spec(
        {
            "version": 1,
            "sources": {"orders": orders_csv.name},
            "checks": [
                {
                    "reconcile.sum": {
                        "agg": "mean",
                        "column": "revenue",
                        "left": {"source": "orders"},
                        "right": {"value": 1.0},
                    }
                }
            ],
        }
    )
    r = one(report)
    assert r.status is Status.ERROR
    assert "agg" in r.summary


def test_percent_sum_does_not_coerce_text(tmp_path, run_spec) -> None:
    # [40, 35, "oops", 25] must not quietly sum to 100.
    (tmp_path / "shares.csv").write_text(
        "share\n40\n35\noops\n25\n", encoding="utf-8"
    )
    report = run_spec(
        {
            "version": 1,
            "sources": {"shares": "shares.csv"},
            "checks": [{"internal.percent_sum": {"source": "shares", "column": "share"}}],
        }
    )
    r = one(report)
    assert r.status is Status.ERROR
    assert "non-numeric" in r.summary


def test_integrity_scan_fills_the_honesty_block(workbook_factory, run_spec) -> None:
    wb = workbook_factory("book.xlsx", {"Data": {"A1": 1}, "Notes": {"A1": "x"}})
    report = run_spec(
        {
            "version": 1,
            "sources": {"wb": wb.name},
            "checks": [{"excel.integrity": {"source": "wb", "sheets": ["Data"]}}],
        }
    )
    assert one(report).status is Status.PASS
    assert [s.alias for s in report.sources] == ["wb"]
    assert "integrity scan: Data" in report.sources[0].detail
    assert report.not_checked == [f"{wb.name}#Notes"]


def test_hash_in_filename_is_a_file_not_a_sheet(tmp_path, run_spec) -> None:
    (tmp_path / "report#1.csv").write_text("id\n1\n2\n", encoding="utf-8")
    report = run_spec(
        {
            "version": 1,
            "sources": {"r": "report#1.csv"},
            "checks": [{"schema.unique": {"source": "r", "column": "id"}}],
        }
    )
    assert one(report).status is Status.PASS


def test_empty_csv_is_a_source_error_not_a_bug(tmp_path, run_spec) -> None:
    (tmp_path / "empty.csv").write_text("", encoding="utf-8")
    report = run_spec(
        {
            "version": 1,
            "sources": {"e": "empty.csv"},
            "checks": [{"schema.unique": {"source": "e", "column": "id"}}],
        }
    )
    r = one(report)
    assert r.status is Status.ERROR
    assert "as CSV" in r.summary
    assert "unexpected" not in r.evidence  # a bad input file is not an andon bug


def test_per_side_column_override_shows_in_evidence(tmp_path, run_spec) -> None:
    (tmp_path / "a.csv").write_text("gross\n10\n20\n", encoding="utf-8")
    (tmp_path / "b.csv").write_text("total\n30\n", encoding="utf-8")
    report = run_spec(
        {
            "version": 1,
            "sources": {"a": "a.csv", "b": "b.csv"},
            "checks": [
                {
                    "reconcile.sum": {
                        "left": {"source": "a", "column": "gross"},
                        "right": {"source": "b", "column": "total"},
                    }
                }
            ],
        }
    )
    r = one(report)
    assert r.status is Status.PASS
    assert r.evidence["column"] == "gross, total"


def test_conflicting_side_keys_rejected(orders_csv, run_spec) -> None:
    report = run_spec(
        {
            "version": 1,
            "sources": {"orders": orders_csv.name},
            "checks": [
                {
                    "reconcile.row_count": {
                        "left": {"source": "orders"},
                        "right": {"value": 5, "where": "status == 'shipped'"},
                    }
                }
            ],
        }
    )
    r = one(report)
    assert r.status is Status.ERROR
    assert "value" in r.summary

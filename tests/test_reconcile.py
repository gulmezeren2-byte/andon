from pathlib import Path

from conftest import one

from andon.result import Status


def spec_with(orders: Path, extra_sources: dict | None = None, *checks: dict) -> dict:
    return {
        "version": 1,
        "sources": {"orders": orders.name, **(extra_sources or {})},
        "checks": list(checks),
    }


def test_row_count_against_literal_passes(orders_csv, run_spec) -> None:
    report = run_spec(
        spec_with(
            orders_csv,
            None,
            {
                "reconcile.row_count": {
                    "left": {"source": "orders", "where": "status == 'shipped'"},
                    "right": {"value": 5},
                }
            },
        )
    )
    assert one(report).status is Status.PASS


def test_row_count_catches_dropped_filter(orders_csv, run_spec) -> None:
    # The claim (6) forgot that one order is cancelled.
    report = run_spec(
        spec_with(
            orders_csv,
            None,
            {
                "reconcile.row_count": {
                    "left": {"source": "orders", "where": "status == 'shipped'"},
                    "right": {"value": 6},
                }
            },
        )
    )
    r = one(report)
    assert r.status is Status.FAIL
    assert r.evidence["delta"] == -1


def test_sum_against_excel_cell(orders_csv, workbook_factory, run_spec) -> None:
    wb = workbook_factory("report.xlsx", {"Summary": {"B6": 650.0}})
    report = run_spec(
        spec_with(
            orders_csv,
            {"report": f"{wb.name}#Summary"},
            {
                "reconcile.sum": {
                    "column": "revenue",
                    "left": {"source": "orders", "where": "status == 'shipped'"},
                    "right": {"source": "report", "cell": "B6"},
                }
            },
        )
    )
    assert one(report).status is Status.PASS


def test_sum_catches_inflated_claim_beyond_tolerance(
    orders_csv, workbook_factory, run_spec
) -> None:
    wb = workbook_factory("report.xlsx", {"Summary": {"B6": 663.0}})  # +2% "adjustment"
    report = run_spec(
        spec_with(
            orders_csv,
            {"report": f"{wb.name}#Summary"},
            {
                "reconcile.sum": {
                    "column": "revenue",
                    "left": {"source": "orders", "where": "status == 'shipped'"},
                    "right": {"source": "report", "cell": "B6"},
                    "tolerance": "0.5%",
                }
            },
        )
    )
    r = one(report)
    assert r.status is Status.FAIL
    assert "claimed" in r.summary


def test_sum_within_relative_tolerance_passes(orders_csv, workbook_factory, run_spec) -> None:
    wb = workbook_factory("report.xlsx", {"Summary": {"B6": 650.5}})
    report = run_spec(
        spec_with(
            orders_csv,
            {"report": f"{wb.name}#Summary"},
            {
                "reconcile.sum": {
                    "column": "revenue",
                    "left": {"source": "orders", "where": "status == 'shipped'"},
                    "right": {"source": "report", "cell": "B6"},
                    "tolerance": "0.5%",
                }
            },
        )
    )
    assert one(report).status is Status.PASS


def test_aggregate_mean(orders_csv, run_spec) -> None:
    report = run_spec(
        spec_with(
            orders_csv,
            None,
            {
                "reconcile.aggregate": {
                    "agg": "mean",
                    "column": "revenue",
                    "left": {"source": "orders", "where": "status == 'shipped'"},
                    "right": {"value": 130.0},
                }
            },
        )
    )
    assert one(report).status is Status.PASS


def test_group_sum_finds_the_bad_region(orders_csv, workbook_factory, run_spec) -> None:
    wb = workbook_factory(
        "byregion.xlsx",
        {
            "S": {
                "A1": "region", "B1": "revenue",
                "A2": "EU", "B2": 300.0,
                "A3": "US", "B3": 250.0,   # true shipped US is 200.0
                "A4": "APAC", "B4": 150.0,
            }
        },
    )
    report = run_spec(
        spec_with(
            orders_csv,
            {"claim": f"{wb.name}#S!A1:B4"},
            {
                "reconcile.group_sum": {
                    "column": "revenue",
                    "by": "region",
                    "left": {"source": "orders", "where": "status == 'shipped'"},
                    "right": {"source": "claim"},
                }
            },
        )
    )
    r = one(report)
    assert r.status is Status.FAIL
    assert r.evidence["mismatched_count"] == 1
    assert r.evidence["mismatched"][0]["group"] == "US"


def test_keys_subset_catches_invented_ids(orders_csv, workbook_factory, run_spec) -> None:
    wb = workbook_factory(
        "detail.xlsx",
        {"S": {"A1": "order_id", "A2": 1001, "A3": 1002, "A4": 9999}},
    )
    report = run_spec(
        spec_with(
            orders_csv,
            {"claim": f"{wb.name}#S!A1:A4"},
            {
                "reconcile.keys": {
                    "column": "order_id",
                    "mode": "subset",
                    "left": {"source": "orders"},
                    "right": {"source": "claim"},
                }
            },
        )
    )
    r = one(report)
    assert r.status is Status.FAIL
    assert r.evidence["only_in_right_count"] == 1


def test_non_numeric_column_is_an_error_not_a_guess(orders_csv, run_spec) -> None:
    report = run_spec(
        spec_with(
            orders_csv,
            None,
            {
                "reconcile.sum": {
                    "column": "status",
                    "left": {"source": "orders"},
                    "right": {"value": 1.0},
                }
            },
        )
    )
    r = one(report)
    assert r.status is Status.ERROR
    assert "non-numeric" in r.summary

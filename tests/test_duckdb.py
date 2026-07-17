"""DuckDB source tests — 'the report vs. a warehouse query'.

Skipped cleanly when the optional dependency isn't installed, so the core
suite never depends on DuckDB being present.
"""

from __future__ import annotations

import pytest

pytest.importorskip("duckdb")

from conftest import one  # noqa: E402

from andon.result import Status  # noqa: E402
from andon.sources import SourceStore, parse_ref  # noqa: E402


def test_parse_duckdb_ref(tmp_path) -> None:
    ref = parse_ref("duckdb:SELECT 1 AS x", tmp_path)
    assert ref.query == "SELECT 1 AS x"
    assert ref.path == tmp_path


def test_empty_duckdb_query_rejected(tmp_path) -> None:
    with pytest.raises(Exception, match="SQL query"):
        parse_ref("duckdb:   ", tmp_path)


def test_duckdb_source_returns_a_frame(orders_csv) -> None:
    store = SourceStore(
        orders_csv.parent,
        {"agg": f"duckdb:SELECT region, SUM(revenue) AS rev "
                f"FROM read_csv_auto('{orders_csv.name}') GROUP BY region"},
    )
    df = store.frame("agg")
    assert set(df.columns) == {"region", "rev"}
    assert len(df) == 3  # EU, US, APAC


def test_report_reconciles_against_a_duckdb_query(orders_csv, run_spec) -> None:
    # Shipped revenue in the sample is 650.0. Verify a claimed total against a
    # DuckDB aggregation of the raw CSV — files inside the SQL resolve against
    # the spec directory.
    report = run_spec(
        {
            "version": 1,
            "sources": {
                "shipped": (
                    f"duckdb:SELECT SUM(revenue) AS rev "
                    f"FROM read_csv_auto('{orders_csv.name}') WHERE status = 'shipped'"
                ),
            },
            "checks": [
                {
                    "reconcile.sum": {
                        "column": "rev",
                        "left": {"source": "shipped"},
                        "right": {"value": 650.0},
                    }
                }
            ],
        }
    )
    assert one(report).status is Status.PASS


def test_duckdb_catches_a_mismatch(orders_csv, run_spec) -> None:
    report = run_spec(
        {
            "version": 1,
            "sources": {
                "shipped": (
                    f"duckdb:SELECT SUM(revenue) AS rev "
                    f"FROM read_csv_auto('{orders_csv.name}') WHERE status = 'shipped'"
                ),
            },
            "checks": [
                {
                    "reconcile.sum": {
                        "column": "rev",
                        "left": {"source": "shipped"},
                        "right": {"value": 700.0},  # wrong
                    }
                }
            ],
        }
    )
    assert one(report).status is Status.FAIL


def test_bad_duckdb_sql_is_a_source_error(orders_csv, run_spec) -> None:
    report = run_spec(
        {
            "version": 1,
            "sources": {"broken": "duckdb:SELECT * FROM nonexistent_table_xyz"},
            "checks": [{"schema.columns": {"source": "broken", "required": ["x"]}}],
        }
    )
    r = one(report)
    assert r.status is Status.ERROR
    assert "DuckDB query failed" in r.summary


def test_duckdb_honesty_block_hides_the_path(orders_csv, run_spec) -> None:
    report = run_spec(
        {
            "version": 1,
            "sources": {
                "q": f"duckdb:SELECT COUNT(*) AS n FROM read_csv_auto('{orders_csv.name}')"
            },
            "checks": [{"schema.columns": {"source": "q", "required": ["n"]}}],
        }
    )
    assert report.results[0].status is Status.PASS
    info = report.sources[0]
    assert info.path == "(DuckDB query)"
    assert info.kind == "duckdb"

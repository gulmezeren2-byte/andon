from conftest import one

from andon.result import Status


def orders_spec(orders_csv, check: dict) -> dict:
    return {"version": 1, "sources": {"orders": orders_csv.name}, "checks": [check]}


def test_columns_all_present(orders_csv, run_spec) -> None:
    report = run_spec(
        orders_spec(
            orders_csv,
            {"schema.columns": {"source": "orders", "required": ["order_id", "revenue"]}},
        )
    )
    assert one(report).status is Status.PASS


def test_columns_missing_named(orders_csv, run_spec) -> None:
    report = run_spec(
        orders_spec(
            orders_csv,
            {"schema.columns": {"source": "orders", "required": ["order_id", "margin"]}},
        )
    )
    r = one(report)
    assert r.status is Status.FAIL
    assert "margin" in r.summary


def test_forbid_extra(orders_csv, run_spec) -> None:
    report = run_spec(
        orders_spec(
            orders_csv,
            {
                "schema.columns": {
                    "source": "orders",
                    "required": ["order_id"],
                    "forbid_extra": True,
                }
            },
        )
    )
    assert one(report).status is Status.FAIL


def test_unique_passes(orders_csv, run_spec) -> None:
    report = run_spec(
        orders_spec(orders_csv, {"schema.unique": {"source": "orders", "column": "order_id"}})
    )
    assert one(report).status is Status.PASS


def test_unique_catches_duplicates(tmp_path, run_spec) -> None:
    (tmp_path / "d.csv").write_text("id,v\n1,a\n1,b\n2,c\n", encoding="utf-8")
    report = run_spec(
        {
            "version": 1,
            "sources": {"d": "d.csv"},
            "checks": [{"schema.unique": {"source": "d", "column": "id"}}],
        }
    )
    r = one(report)
    assert r.status is Status.FAIL
    assert r.evidence["duplicate_rows"] == 2


def test_not_null(tmp_path, run_spec) -> None:
    (tmp_path / "n.csv").write_text("id,v\n1,\n2,x\n", encoding="utf-8")
    report = run_spec(
        {
            "version": 1,
            "sources": {"n": "n.csv"},
            "checks": [{"schema.not_null": {"source": "n", "columns": ["id", "v"]}}],
        }
    )
    r = one(report)
    assert r.status is Status.FAIL
    assert r.evidence["null_counts"] == {"id": 0, "v": 1}


def test_allowed_values(orders_csv, run_spec) -> None:
    report = run_spec(
        orders_spec(
            orders_csv,
            {
                "schema.allowed_values": {
                    "source": "orders",
                    "column": "status",
                    "allowed": ["shipped"],
                }
            },
        )
    )
    r = one(report)
    assert r.status is Status.FAIL
    assert r.evidence["unexpected_values"] == ["cancelled"]


def test_date_continuity_gap(tmp_path, run_spec) -> None:
    (tmp_path / "days.csv").write_text(
        "day,v\n2026-01-01,1\n2026-01-02,1\n2026-01-04,1\n", encoding="utf-8"
    )
    report = run_spec(
        {
            "version": 1,
            "sources": {"days": "days.csv"},
            "checks": [
                {"schema.date_continuity": {"source": "days", "column": "day", "freq": "D"}}
            ],
        }
    )
    r = one(report)
    assert r.status is Status.FAIL
    assert r.evidence["missing"] == ["2026-01-03"]


def test_date_continuity_no_gap(orders_csv, run_spec) -> None:
    report = run_spec(
        orders_spec(
            orders_csv,
            {"schema.date_continuity": {"source": "orders", "column": "order_date", "freq": "D"}},
        )
    )
    assert one(report).status is Status.PASS

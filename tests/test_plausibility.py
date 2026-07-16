from conftest import one

from andon.result import Status


def test_bounds_flags_but_never_fails(orders_csv, run_spec) -> None:
    report = run_spec(
        {
            "version": 1,
            "sources": {"orders": orders_csv.name},
            "checks": [
                {
                    "plausibility.bounds": {
                        "source": "orders",
                        "column": "revenue",
                        "min": 0,
                        "max": 199.0,  # one order is 200.0
                    }
                }
            ],
        }
    )
    r = one(report)
    assert r.status is Status.REVIEW
    assert r.evidence["above_max"] == 1
    assert report.exit_code() == 2
    assert report.exit_code(strict=True) == 1


def test_bounds_pass(orders_csv, run_spec) -> None:
    report = run_spec(
        {
            "version": 1,
            "sources": {"orders": orders_csv.name},
            "checks": [
                {"plausibility.bounds": {"source": "orders", "column": "revenue", "min": 0}}
            ],
        }
    )
    assert one(report).status is Status.PASS


def test_new_categories_flagged(orders_csv, tmp_path, run_spec) -> None:
    (tmp_path / "new.csv").write_text("region\nEU\nLATAM\n", encoding="utf-8")
    report = run_spec(
        {
            "version": 1,
            "sources": {"orders": orders_csv.name, "new": "new.csv"},
            "checks": [
                {
                    "plausibility.new_categories": {
                        "column": "region",
                        "left": {"source": "orders"},
                        "right": {"source": "new"},
                    }
                }
            ],
        }
    )
    r = one(report)
    assert r.status is Status.REVIEW
    assert r.evidence["new_categories"] == ["LATAM"]


def test_mean_shift_flags_large_move(orders_csv, tmp_path, run_spec) -> None:
    (tmp_path / "next.csv").write_text("revenue\n5000\n5200\n", encoding="utf-8")
    report = run_spec(
        {
            "version": 1,
            "sources": {"orders": orders_csv.name, "next": "next.csv"},
            "checks": [
                {
                    "plausibility.mean_shift": {
                        "column": "revenue",
                        "left": {"source": "orders"},
                        "right": {"source": "next"},
                        "max_sigmas": 3,
                    }
                }
            ],
        }
    )
    assert one(report).status is Status.REVIEW

"""Engine behavior: isolation, honesty, and the heuristic guard."""

from andon.checks import Outcome, register
from andon.result import Status

# A deliberately misbehaving heuristic check: it tries to FAIL, which the
# registry contract forbids. Registered once at import time.
try:

    @register("test.rogue_heuristic", heuristic=True)
    def _rogue(store, params):  # type: ignore[no-untyped-def]
        return Outcome(Status.FAIL, "I think I can fail the build")

except RuntimeError:  # pragma: no cover - double import safety
    pass


def test_skip_is_recorded_with_reason(orders_csv, run_spec) -> None:
    report = run_spec(
        {
            "version": 1,
            "sources": {"orders": orders_csv.name},
            "checks": [
                {
                    "skip": "waiting for January data",
                    "schema.unique": {"source": "orders", "column": "order_id"},
                },
                {"schema.not_null": {"source": "orders", "column": "order_id"}},
            ],
        }
    )
    r = report.results[0]
    assert r.status is Status.SKIP
    assert r.summary == "waiting for January data"
    assert report.exit_code() == 0  # a skip next to real passes is not a verdict


def test_all_skipped_is_not_a_pass(orders_csv, run_spec) -> None:
    # Zero verifications must never exit 0 — silence is not a blessing.
    report = run_spec(
        {
            "version": 1,
            "sources": {"orders": orders_csv.name},
            "checks": [
                {"skip": True, "schema.unique": {"source": "orders", "column": "order_id"}},
            ],
        }
    )
    assert report.verdict == "EMPTY"
    assert report.exit_code() == 3
    assert report.exit_code(strict=True) == 1


def test_missing_file_is_error_not_crash(run_spec) -> None:
    report = run_spec(
        {
            "version": 1,
            "sources": {"ghost": "ghost.csv"},
            "checks": [
                {"schema.unique": {"source": "ghost", "column": "id"}},
            ],
        }
    )
    r = report.results[0]
    assert r.status is Status.ERROR
    assert "not found" in r.summary
    assert report.verdict == "INCOMPLETE"
    assert report.exit_code() == 3
    assert report.exit_code(strict=True) == 1


def test_one_broken_check_does_not_stop_the_rest(orders_csv, run_spec) -> None:
    report = run_spec(
        {
            "version": 1,
            "sources": {"orders": orders_csv.name, "ghost": "ghost.csv"},
            "checks": [
                {"schema.unique": {"source": "ghost", "column": "id"}},
                {"schema.unique": {"source": "orders", "column": "order_id"}},
            ],
        }
    )
    assert [r.status for r in report.results] == [Status.ERROR, Status.PASS]


def test_heuristic_cannot_fail_the_build(orders_csv, run_spec) -> None:
    report = run_spec(
        {
            "version": 1,
            "sources": {"orders": orders_csv.name},
            "checks": [{"test.rogue_heuristic": {}}],
        }
    )
    r = report.results[0]
    assert r.status is Status.REVIEW
    assert "downgraded" in r.evidence


def test_fail_beats_error_beats_review_in_exit_code(orders_csv, run_spec) -> None:
    report = run_spec(
        {
            "version": 1,
            "sources": {"orders": orders_csv.name, "ghost": "ghost.csv"},
            "checks": [
                {"schema.unique": {"source": "ghost", "column": "id"}},  # ERROR
                {
                    "reconcile.row_count": {  # FAIL
                        "left": {"source": "orders"},
                        "right": {"value": 999},
                    }
                },
            ],
        }
    )
    assert report.verdict == "FAIL"
    assert report.exit_code() == 1


def test_report_records_sources_and_unread_sheets(
    orders_csv, workbook_factory, run_spec
) -> None:
    wb = workbook_factory("r.xlsx", {"Used": {"A1": 6}, "Scratch": {"A1": "tmp"}})
    report = run_spec(
        {
            "version": 1,
            "sources": {"orders": orders_csv.name, "report": f"{wb.name}#Used"},
            "checks": [
                {
                    "reconcile.row_count": {
                        "left": {"source": "orders"},
                        "right": {"source": "report", "cell": "A1"},
                    }
                }
            ],
        }
    )
    assert report.results[0].status is Status.PASS
    aliases = {s.alias for s in report.sources}
    assert aliases == {"orders", "report"}
    assert report.not_checked == [f"{wb.name}#Scratch"]


def test_check_timings_are_recorded(orders_csv, run_spec) -> None:
    report = run_spec(
        {
            "version": 1,
            "sources": {"orders": orders_csv.name},
            "checks": [{"schema.unique": {"source": "orders", "column": "order_id"}}],
        }
    )
    assert report.results[0].duration_ms >= 0
    assert report.to_dict()["checks"][0]["duration_ms"] >= 0

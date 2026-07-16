from conftest import one

from andon.result import Status


def test_total_row_honest(workbook_factory, run_spec) -> None:
    wb = workbook_factory(
        "t.xlsx", {"S": {"B10": 100.0, "B11": 200.0, "B12": 50.0, "B13": 350.0}}
    )
    report = run_spec(
        {
            "version": 1,
            "sources": {"report": f"{wb.name}#S"},
            "checks": [
                {"internal.total_row": {"source": "report", "parts": "B10:B12", "total": "B13"}}
            ],
        }
    )
    assert one(report).status is Status.PASS


def test_total_row_catches_stale_total(workbook_factory, run_spec) -> None:
    # Someone edited a part and never touched the total.
    wb = workbook_factory(
        "t.xlsx", {"S": {"B10": 100.0, "B11": 200.0, "B12": 75.0, "B13": 350.0}}
    )
    report = run_spec(
        {
            "version": 1,
            "sources": {"report": f"{wb.name}#S"},
            "checks": [
                {"internal.total_row": {"source": "report", "parts": "B10:B12", "total": "B13"}}
            ],
        }
    )
    r = one(report)
    assert r.status is Status.FAIL
    assert r.evidence["delta"] == 25.0


def test_total_row_skips_blanks_and_says_so(workbook_factory, run_spec) -> None:
    wb = workbook_factory("t.xlsx", {"S": {"B10": 100.0, "B12": 200.0, "B13": 300.0}})
    report = run_spec(
        {
            "version": 1,
            "sources": {"report": f"{wb.name}#S"},
            "checks": [
                {"internal.total_row": {"source": "report", "parts": "B10:B12", "total": "B13"}}
            ],
        }
    )
    r = one(report)
    assert r.status is Status.PASS
    assert "1 blank" in r.evidence["parts"]


def test_percent_sum_range_off_by_a_point(workbook_factory, run_spec) -> None:
    wb = workbook_factory("p.xlsx", {"S": {"C2": 40.0, "C3": 35.0, "C4": 26.3}})
    report = run_spec(
        {
            "version": 1,
            "sources": {"report": f"{wb.name}#S"},
            "checks": [{"internal.percent_sum": {"source": "report", "range": "C2:C4"}}],
        }
    )
    r = one(report)
    assert r.status is Status.FAIL
    assert "101.3" in r.summary


def test_percent_sum_by_group(tmp_path, run_spec) -> None:
    (tmp_path / "shares.csv").write_text(
        "quarter,region,share\nQ1,EU,60\nQ1,US,40\nQ2,EU,55\nQ2,US,44\n", encoding="utf-8"
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
    assert r.status is Status.FAIL
    assert r.evidence["off_target"] == [{"group": "Q2", "sum": 99.0}]


def test_recompute_holds(tmp_path, run_spec) -> None:
    (tmp_path / "m.csv").write_text(
        "gross,vat,net\n120,20,100\n240,40,200\n", encoding="utf-8"
    )
    report = run_spec(
        {
            "version": 1,
            "sources": {"m": "m.csv"},
            "checks": [
                {"internal.recompute": {"source": "m", "expr": "gross - vat", "equals": "net"}}
            ],
        }
    )
    assert one(report).status is Status.PASS


def test_recompute_catches_broken_derivation(tmp_path, run_spec) -> None:
    (tmp_path / "m.csv").write_text(
        "gross,vat,net\n120,20,100\n240,40,190\n", encoding="utf-8"
    )
    report = run_spec(
        {
            "version": 1,
            "sources": {"m": "m.csv"},
            "checks": [
                {"internal.recompute": {"source": "m", "expr": "gross - vat", "equals": "net"}}
            ],
        }
    )
    r = one(report)
    assert r.status is Status.FAIL
    assert r.evidence["violations"] == 1
    assert r.evidence["sample"][0]["stated"] == 190


def test_recompute_one_sided_nan_is_a_violation(tmp_path, run_spec) -> None:
    (tmp_path / "m.csv").write_text(
        "gross,vat,net\n120,20,100\n240,,200\n", encoding="utf-8"
    )
    report = run_spec(
        {
            "version": 1,
            "sources": {"m": "m.csv"},
            "checks": [
                {"internal.recompute": {"source": "m", "expr": "gross - vat", "equals": "net"}}
            ],
        }
    )
    r = one(report)
    assert r.status is Status.FAIL
    assert r.evidence["violations"] == 1

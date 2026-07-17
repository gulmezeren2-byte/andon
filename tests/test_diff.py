"""andon diff: what changed between two workbook versions."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from andon.cli import app
from andon.diff import diff_workbooks
from andon.errors import SourceError

runner = CliRunner()


def test_no_changes(workbook_factory) -> None:
    b = workbook_factory("before.xlsx", {"S": {"A1": 100, "B2": "x"}})
    a = workbook_factory("after.xlsx", {"S": {"A1": 100, "B2": "x"}})
    r = diff_workbooks(b, a)
    assert r.changes == []
    assert r.exit_code() == 0
    assert r.cells_compared == 2


def test_numeric_change_has_delta_and_pct(workbook_factory) -> None:
    b = workbook_factory("before.xlsx", {"S": {"A1": 100.0}})
    a = workbook_factory("after.xlsx", {"S": {"A1": 110.0}})
    r = diff_workbooks(b, a)
    assert len(r.changes) == 1
    c = r.changes[0]
    assert c.kind == "numeric"
    assert c.delta == 10.0
    assert c.pct == 10.0
    assert r.exit_code() == 2  # a change, but not a new error


def test_new_error_is_the_headline(workbook_factory) -> None:
    b = workbook_factory("before.xlsx", {"S": {"A1": 5}})
    a = workbook_factory("after.xlsx", {"S": {"A1": "#REF!"}})
    r = diff_workbooks(b, a)
    assert r.has_new_errors
    assert r.changes[0].kind == "new_error"
    assert r.exit_code() == 1
    assert r.exit_code(strict=True) == 1


def test_tolerance_hides_small_moves(workbook_factory) -> None:
    b = workbook_factory("before.xlsx", {"S": {"A1": 100.0}})
    a = workbook_factory("after.xlsx", {"S": {"A1": 100.3}})
    assert diff_workbooks(b, a, tolerance="0.5%").changes == []
    assert len(diff_workbooks(b, a).changes) == 1  # shows without tolerance


def test_appeared_and_vanished(workbook_factory) -> None:
    b = workbook_factory("before.xlsx", {"S": {"A1": 1, "C3": 9}})
    a = workbook_factory("after.xlsx", {"S": {"A1": 1, "B2": 5}})
    r = diff_workbooks(b, a)
    kinds = {(c.coord, c.kind) for c in r.changes}
    assert ("B2", "appeared") in kinds
    assert ("C3", "vanished") in kinds


def test_formula_change_compared_by_formula(workbook_factory) -> None:
    b = workbook_factory("before.xlsx", {"S": {"A1": "=B1+C1"}})
    a = workbook_factory("after.xlsx", {"S": {"A1": "=B1+C2"}})
    r = diff_workbooks(b, a)
    assert len(r.changes) == 1
    assert r.changes[0].kind == "formula"
    assert r.changes[0].before == "=B1+C1"
    assert r.changes[0].after == "=B1+C2"


def test_identical_formula_is_not_a_change(workbook_factory) -> None:
    b = workbook_factory("before.xlsx", {"S": {"A1": "=B1*2"}})
    a = workbook_factory("after.xlsx", {"S": {"A1": "=B1*2"}})
    assert diff_workbooks(b, a).changes == []


def test_text_change(workbook_factory) -> None:
    b = workbook_factory("before.xlsx", {"S": {"A1": "draft"}})
    a = workbook_factory("after.xlsx", {"S": {"A1": "final"}})
    r = diff_workbooks(b, a)
    assert r.changes[0].kind == "text"


def test_sheet_added_and_removed(workbook_factory) -> None:
    b = workbook_factory("before.xlsx", {"S": {"A1": 1}, "Old": {"A1": 1}})
    a = workbook_factory("after.xlsx", {"S": {"A1": 1}, "New": {"A1": 1}})
    r = diff_workbooks(b, a)
    assert r.sheets_added == ["New"]
    assert r.sheets_removed == ["Old"]
    assert r.exit_code() == 2


def test_sheet_filter(workbook_factory) -> None:
    b = workbook_factory("before.xlsx", {"A": {"A1": 1}, "B": {"A1": 1}})
    a = workbook_factory("after.xlsx", {"A": {"A1": 2}, "B": {"A1": 2}})
    r = diff_workbooks(b, a, sheets=["A"])
    assert len(r.changes) == 1
    assert r.changes[0].sheet == "A"


def test_missing_file_is_source_error(workbook_factory, tmp_path) -> None:
    b = workbook_factory("before.xlsx", {"S": {"A1": 1}})
    with pytest.raises(SourceError, match="not found"):
        diff_workbooks(b, tmp_path / "nope.xlsx")


def test_cli_diff_flags_a_new_error(workbook_factory) -> None:
    b = workbook_factory("before.xlsx", {"S": {"A1": 100}})
    a = workbook_factory("after.xlsx", {"S": {"A1": "#REF!"}})
    result = runner.invoke(app, ["diff", str(b), str(a)])
    assert result.exit_code == 1
    assert "new_error" in result.output


def test_cli_diff_json(workbook_factory) -> None:
    import json

    b = workbook_factory("before.xlsx", {"S": {"A1": 100.0}})
    a = workbook_factory("after.xlsx", {"S": {"A1": 120.0}})
    result = runner.invoke(app, ["diff", str(b), str(a), "--json"])
    assert result.exit_code == 2
    payload = json.loads(result.output)
    assert payload["counts"]["numeric"] == 1
    assert payload["changes"][0]["delta"] == 20.0


def test_cli_diff_clean_exits_zero(workbook_factory) -> None:
    b = workbook_factory("before.xlsx", {"S": {"A1": 1}})
    a = workbook_factory("after.xlsx", {"S": {"A1": 1}})
    result = runner.invoke(app, ["diff", str(b), str(a)])
    assert result.exit_code == 0
    assert "No changes" in result.output

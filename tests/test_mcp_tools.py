"""MCP tool-logic tests. These exercise the plain dict-returning functions, not
the transport, so they run without the `mcp` extra installed."""

from __future__ import annotations

from andon.mcp_server import tool_diff, tool_inspect, tool_run


def test_tool_run_pass(tmp_path, orders_csv) -> None:  # type: ignore[no-untyped-def]
    spec = tmp_path / "andon.yaml"
    spec.write_text(
        "version: 1\n"
        "sources: {orders: orders.csv}\n"
        "checks:\n  - schema.unique: {source: orders, column: order_id}\n",
        encoding="utf-8",
    )
    result = tool_run(str(spec))
    assert result["verdict"] == "PASS"
    assert result["checks"][0]["status"] == "pass"


def test_tool_run_fail(tmp_path, orders_csv) -> None:  # type: ignore[no-untyped-def]
    spec = tmp_path / "andon.yaml"
    spec.write_text(
        "version: 1\n"
        "sources: {orders: orders.csv}\n"
        "checks:\n"
        "  - reconcile.row_count:\n"
        "      left: {source: orders}\n"
        "      right: {value: 999}\n",
        encoding="utf-8",
    )
    result = tool_run(str(spec))
    assert result["verdict"] == "FAIL"


def test_tool_run_bad_spec(tmp_path) -> None:  # type: ignore[no-untyped-def]
    spec = tmp_path / "bad.yaml"
    spec.write_text("version: 1\nsources: {}\nchecks:\n  - no.such_check: {}\n", encoding="utf-8")
    result = tool_run(str(spec))
    assert result["verdict"] == "SPEC_ERROR"
    assert "error" in result


def test_tool_inspect_flags_error_cell(workbook_factory) -> None:  # type: ignore[no-untyped-def]
    wb = workbook_factory("book.xlsx", {"S": {"A1": 1, "B2": "#REF!"}})
    result = tool_inspect(str(wb))
    assert result["verdict"] == "FAIL"


def test_tool_inspect_clean(workbook_factory) -> None:  # type: ignore[no-untyped-def]
    wb = workbook_factory("clean.xlsx", {"S": {"A1": 1, "A2": 2}})
    result = tool_inspect(str(wb))
    assert result["verdict"] == "PASS"


def test_tool_diff_numeric(workbook_factory) -> None:  # type: ignore[no-untyped-def]
    b = workbook_factory("before.xlsx", {"S": {"A1": 100.0}})
    a = workbook_factory("after.xlsx", {"S": {"A1": 110.0}})
    result = tool_diff(str(b), str(a))
    assert result["counts"]["numeric"] == 1
    assert result["changes"][0]["delta"] == 10.0


def test_tool_diff_new_error(workbook_factory) -> None:  # type: ignore[no-untyped-def]
    b = workbook_factory("before.xlsx", {"S": {"A1": 5}})
    a = workbook_factory("after.xlsx", {"S": {"A1": "#REF!"}})
    result = tool_diff(str(b), str(a))
    assert result["counts"]["new_error"] == 1


def test_tool_diff_missing_file(workbook_factory, tmp_path) -> None:  # type: ignore[no-untyped-def]
    b = workbook_factory("before.xlsx", {"S": {"A1": 1}})
    result = tool_diff(str(b), str(tmp_path / "nope.xlsx"))
    assert "error" in result

"""MCP tool-logic tests. These exercise the plain dict-returning functions, not
the transport, so they run without the `mcp` extra installed."""

from __future__ import annotations

import builtins

import pytest

from andon.mcp_server import server_class, tool_diff, tool_inspect, tool_run


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


# --------------------------------------------------------------------------- #
# The SDK renamed its high-level server between majors — `FastMCP` in 1.x,
# `MCPServer` in 2.x — and deleted the old module outright, which broke every
# published server built on it. Both spellings are accepted, and the failure now
# says which problem it actually is.
# --------------------------------------------------------------------------- #
def test_the_server_class_resolves_against_whichever_sdk_is_installed() -> None:
    pytest.importorskip("mcp")
    resolved = server_class()
    assert resolved.__name__ in {"MCPServer", "FastMCP"}
    assert hasattr(resolved, "tool")


def test_an_sdk_exposing_neither_api_is_not_called_a_missing_install(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pytest.importorskip("mcp")
    real_import = builtins.__import__

    def without_a_server_api(name, *args, **kwargs):  # type: ignore[no-untyped-def]
        if name in {"mcp.server", "mcp.server.fastmcp"}:
            raise ImportError(f"No module named {name!r}")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", without_a_server_api)
    with pytest.raises(SystemExit) as caught:
        server_class()
    message = str(caught.value)
    # telling someone to install the extra they already installed is a dead end
    assert "pip install" not in message
    assert "incompatibility" in message

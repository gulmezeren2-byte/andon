"""MCP server: expose andon's verify / inspect / diff to an agent runtime.

Same structure as the rest of andon's optional surfaces: every tool's work is
a plain function returning a dict and knowing nothing about MCP. The FastMCP
wrapper at the bottom is registered only when the `mcp` extra is installed, so
the logic is unit-tested without an agent runtime and `mcp` stays out of the
core dependency set.

This makes andon a thing an agent can *call*: draft an analysis, then have the
agent run the spec, inspect the workbook, or diff two versions — and get a
structured verdict back, not prose.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from andon.diff import diff_workbooks
from andon.engine import run as run_spec
from andon.errors import AndonError
from andon.spec import Spec


def tool_run(spec_path: str) -> dict[str, Any]:
    """Run an andon verification spec (YAML) and return the full report: verdict,
    per-check results with evidence, and the honesty block (what was read, what
    was skipped). The `verdict` field is the go/no-go signal."""
    try:
        return run_spec(spec_path).to_dict()
    except AndonError as exc:
        return {"error": str(exc), "verdict": "SPEC_ERROR"}


def tool_inspect(workbook_path: str, sheets: list[str] | None = None) -> dict[str, Any]:
    """Integrity-scan an .xlsx/.xlsm workbook without writing a spec: error cells
    (#REF! …), values typed over formulas, numbers stored as text, hidden rows,
    external links. Optionally limit to specific worksheets."""
    path = Path(workbook_path)
    params: dict[str, Any] = {"source": "workbook"}
    if sheets:
        params["sheets"] = sheets
    try:
        spec = Spec.from_dict(
            {
                "version": 1,
                "sources": {"workbook": path.name},
                "checks": [{"excel.integrity": params}],
            },
            base_dir=path.resolve().parent,
            path=f"<inspect {path.name}>",
        )
        return run_spec(spec).to_dict()
    except AndonError as exc:
        return {"error": str(exc), "verdict": "SPEC_ERROR"}


def tool_diff(
    before: str,
    after: str,
    tolerance: str | None = None,
    sheets: list[str] | None = None,
) -> dict[str, Any]:
    """Diff two workbook versions and classify what changed: a new error cell
    on its own, numeric moves with a delta and a percent, formula edits,
    appeared/vanished cells, added/removed sheets. `tolerance` (e.g. "0.5%")
    hides numeric noise."""
    try:
        return diff_workbooks(before, after, sheets=sheets, tolerance=tolerance).to_dict()
    except AndonError as exc:
        return {"error": str(exc)}


TOOLS = [tool_run, tool_inspect, tool_diff]


def build_server() -> Any:
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:  # pragma: no cover - exercised only without the extra
        raise SystemExit(
            "The MCP server needs the optional dependency: pip install 'andon-verify[mcp]'"
        ) from exc

    server = FastMCP("andon")
    for fn in TOOLS:
        server.tool()(fn)
    return server


def main() -> None:  # pragma: no cover - transport entry point
    build_server().run()


if __name__ == "__main__":  # pragma: no cover
    main()

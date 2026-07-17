"""Command line interface.

    andon run andon.yaml        run a verification spec
    andon inspect report.xlsx   integrity-scan a workbook without writing a spec
    andon diff old.xlsx new.xlsx  what changed between two workbook versions
    andon init                  write a commented starter spec

Exit codes are a contract (CI depends on them):
0 = every check passed · 1 = at least one FAIL · 2 = REVIEW flags only ·
3 = nothing verified (a check could not run, or everything was skipped) ·
4 = the spec itself is broken.
"""

from __future__ import annotations

import contextlib
import json
import sys
from pathlib import Path

import typer
from rich import box
from rich.console import Console
from rich.table import Table

import andon as _andon
from andon.diff import DiffReport, diff_workbooks
from andon.engine import run as run_spec
from andon.errors import SourceError, SpecError
from andon.render import render_json, render_markdown, render_terminal
from andon.spec import Spec

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
    help="Deterministic verification for AI-generated analysis.",
)

_console = Console()
_err = Console(stderr=True)

STARTER_SPEC = """\
# andon verification spec
# docs: https://github.com/gulmezeren2-byte/andon/blob/main/docs/checks.md
version: 1

# Sources are the files under test. Relative paths resolve against this file.
#   name: data/file.csv
#   name: report.xlsx#Sheet          (a worksheet)
#   name: report.xlsx#Sheet!A1:D50   (a range, first row = header)
sources:
  orders: data/orders.csv
  report: out/weekly_report.xlsx#Summary

checks:
  # Does the report agree with the data it claims to summarize?
  - name: no dropped orders
    reconcile.row_count:
      left:  { source: orders, where: "status != 'cancelled'" }
      right: { source: report, cell: B4 }

  - name: revenue adds up
    reconcile.sum:
      column: revenue
      left:  { source: orders, where: "status != 'cancelled'" }
      right: { source: report, cell: B6 }
      tolerance: 0.01

  # Does the report agree with itself?
  - name: totals row is honest
    internal.total_row:
      source: report
      parts: B10:B21
      total: B22
      tolerance: 0.01

  # Is the workbook mechanically sound? (#REF!, values typed over formulas,
  # numbers stored as text)
  - name: workbook integrity
    excel.integrity:
      source: report
"""


def _version_callback(value: bool) -> None:
    if value:
        _console.print(f"andon {_andon.__version__}")
        raise typer.Exit()


@app.callback()
def _root(
    version: bool = typer.Option(
        False, "--version", "-V", callback=_version_callback, is_eager=True,
        help="Print the version and exit.",
    ),
) -> None:
    """andon — stop the line when the numbers don't add up."""


@app.command()
def run(
    spec: Path = typer.Argument(..., help="Path to a verification spec (YAML)."),
    as_json: bool = typer.Option(False, "--json", help="Print the full report as JSON."),
    strict: bool = typer.Option(
        False, "--strict", help="Treat REVIEW flags and ERRORs as failures (exit 1)."
    ),
    evidence: bool = typer.Option(
        False, "--evidence", help="Show evidence for passing checks too."
    ),
    md: Path | None = typer.Option(
        None, "--md", help="Also write the report as Markdown to this path."
    ),
) -> None:
    """Run every check in SPEC and exit with the verdict."""
    try:
        report = run_spec(spec)
    except SpecError as exc:
        _err.print(f"[bold red]spec error:[/bold red] {exc}")
        raise typer.Exit(4) from exc

    if md is not None:
        md.write_text(render_markdown(report), encoding="utf-8")
    if as_json:
        # Plain print, no rich: this output is for parsers, not for eyes.
        typer.echo(render_json(report))
    else:
        render_terminal(report, _console, evidence=evidence)
    raise typer.Exit(report.exit_code(strict=strict))


@app.command()
def inspect(
    workbook: Path = typer.Argument(..., help="An .xlsx/.xlsm file to integrity-scan."),
    sheet: list[str] = typer.Option(
        None, "--sheet", "-s", help="Limit the scan to these worksheets (repeatable)."
    ),
    as_json: bool = typer.Option(False, "--json", help="Print the full report as JSON."),
    strict: bool = typer.Option(False, "--strict", help="Treat REVIEW flags as failures."),
) -> None:
    """Integrity-scan a workbook without writing a spec."""
    if not workbook.is_file():
        _err.print(f"[bold red]error:[/bold red] file not found: {workbook}")
        raise typer.Exit(4)
    params: dict = {"source": "workbook"}
    if sheet:
        params["sheets"] = list(sheet)
    spec = Spec.from_dict(
        {
            "version": 1,
            "sources": {"workbook": workbook.name},
            "checks": [{"name": f"integrity of {workbook.name}", "excel.integrity": params}],
        },
        base_dir=workbook.resolve().parent,
        path=f"<inspect {workbook.name}>",
    )
    report = run_spec(spec)
    if as_json:
        typer.echo(render_json(report))
    else:
        render_terminal(report, _console)
    raise typer.Exit(report.exit_code(strict=strict))


_DIFF_STYLE = {
    "new_error": "bold red",
    "numeric": "yellow",
    "formula": "cyan",
    "text": "white",
    "appeared": "green",
    "vanished": "dim",
}


def _render_diff(report: DiffReport, console: Console) -> None:
    console.print()
    if not report.changes and not report.sheets_added and not report.sheets_removed:
        console.print(
            f"[green]No changes[/] between {report.before} and {report.after} "
            f"({report.cells_compared} cells compared"
            + (f", tolerance {report.tolerance}" if report.tolerance else "")
            + ")."
        )
        console.print()
        return

    for s in report.sheets_added:
        console.print(f"[green]+ sheet added:[/] {s}")
    for s in report.sheets_removed:
        console.print(f"[red]- sheet removed:[/] {s}")

    if report.changes:
        table = Table(box=box.SIMPLE_HEAD)
        table.add_column("cell")
        table.add_column("change")
        table.add_column("before → after", overflow="fold")
        for c in report.changes:
            loc = f"{c.sheet}!{c.coord}"
            if c.kind == "numeric":
                move = f"{c.before} → {c.after}  ({c.delta:+g}"
                move += f", {c.pct:+g}%)" if c.pct is not None else ")"
            elif c.kind in ("appeared", "vanished"):
                move = f"{c.after}" if c.kind == "appeared" else f"{c.before}"
            else:
                move = f"{c.before} → {c.after}"
            table.add_row(loc, f"[{_DIFF_STYLE[c.kind]}]{c.kind}[/]", move)
        console.print(table)

    parts = [f"{report.count(k)} {k}" for k in _DIFF_STYLE if report.count(k)]
    summary = ", ".join(parts)
    if report.has_new_errors:
        console.print(f"[bold red]{summary}[/] — a new error cell is the one to look at first.")
    else:
        console.print(f"[dim]{summary}[/]")
    console.print()


@app.command()
def diff(
    before: Path = typer.Argument(..., help="The earlier workbook."),
    after: Path = typer.Argument(..., help="The later workbook."),
    sheet: list[str] = typer.Option(
        None, "--sheet", "-s", help="Limit the diff to these worksheets (repeatable)."
    ),
    tolerance: str = typer.Option(
        None, "--tolerance", "-t", help="Hide numeric changes within this (e.g. 0.01 or 0.5%)."
    ),
    as_json: bool = typer.Option(False, "--json", help="Emit the diff as JSON."),
    strict: bool = typer.Option(
        False, "--strict", help="Exit 1 on any change, not only on a new error."
    ),
) -> None:
    """Diff two workbook versions: what changed, and does it matter?

    Numeric moves come with a delta and a percent; a new #REF! (or other error)
    is called out on its own. Exit 0 = nothing meaningful changed, 1 = a new
    error appeared (or, with --strict, any change), 2 = changes but no new error.
    """
    try:
        report = diff_workbooks(before, after, sheets=sheet or None, tolerance=tolerance)
    except (SourceError, SpecError) as exc:
        _err.print(f"[bold red]error:[/bold red] {exc}")
        raise typer.Exit(4) from exc
    if as_json:
        typer.echo(json.dumps(report.to_dict(), indent=2, ensure_ascii=True, default=str))
    else:
        _render_diff(report, _console)
    raise typer.Exit(report.exit_code(strict=strict))


@app.command()
def init(
    path: Path = typer.Argument(Path("andon.yaml"), help="Where to write the starter spec."),
    force: bool = typer.Option(False, "--force", help="Overwrite an existing file."),
) -> None:
    """Write a commented starter spec to PATH."""
    if path.exists() and not force:
        _err.print(f"[bold red]error:[/bold red] {path} already exists (use --force).")
        raise typer.Exit(4)
    path.write_text(STARTER_SPEC, encoding="utf-8")
    _console.print(f"wrote {path} — edit the sources and checks, then: andon run {path}")


def main() -> None:
    # A verifier must never crash while printing its own verdict. On console
    # code pages that cannot encode a character (legacy Windows, exotic
    # locales), degrade the character instead of raising.
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            with contextlib.suppress(Exception):  # pragma: no cover - stream quirks
                reconfigure(errors="replace")
    app()


if __name__ == "__main__":
    main()

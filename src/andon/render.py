"""Rendering: terminal, JSON and Markdown views of a Report.

The renderer's contract is negative: it must not say anything that is not in
the report. No advice, no speculation, no "probably". The one editorial
element it is allowed is the closing line of the honesty block, which states
what a verification run *is* — because that sentence is the product.
"""

from __future__ import annotations

import json
from typing import Any

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from andon.result import Report, Status

_STATUS_STYLE = {
    Status.PASS: "green",
    Status.FAIL: "bold red",
    Status.REVIEW: "yellow",
    Status.SKIP: "dim",
    Status.ERROR: "bold magenta",
}

_STATUS_LABEL = {
    Status.PASS: "PASS",
    Status.FAIL: "FAIL",
    Status.REVIEW: "REVIEW",
    Status.SKIP: "SKIP",
    Status.ERROR: "ERROR",
}

# Runtime strings stay ASCII: legacy Windows consoles run on code pages that
# cannot encode fancier characters, and a verifier that crashes while printing
# its own verdict would be a bad joke.
HONESTY_FOOTER = (
    "andon verified the assertions above and nothing else. "
    "A PASS is not an opinion about the analysis; it is arithmetic about these claims."
)


def _banner(report: Report) -> tuple[str, str]:
    v = report.verdict
    if v == "FAIL":
        return f"STOP THE LINE: {report.count(Status.FAIL)} check(s) failed", "bold white on red"
    if v == "INCOMPLETE":
        return (
            f"INCOMPLETE: {report.count(Status.ERROR)} check(s) could not run "
            f"(not verified is not fine)",
            "bold white on dark_magenta",
        )
    if v == "REVIEW":
        return (
            f"REVIEW: {report.count(Status.REVIEW)} flag(s) raised for a human",
            "black on yellow",
        )
    if v == "EMPTY":
        skipped = report.count(Status.SKIP)
        return (
            f"NOTHING VERIFIED: 0 checks ran ({skipped} skipped)",
            "bold white on dark_magenta",
        )
    return f"PASS: all {report.count(Status.PASS)} check(s) passed", "bold white on green"


def _fmt_evidence_value(value: Any) -> str:
    if isinstance(value, list):
        if not value:
            return "[]"
        return "; ".join(str(v) for v in value)
    if isinstance(value, dict):
        return ", ".join(f"{k}={v}" for k, v in value.items())
    return str(value)


def render_terminal(report: Report, console: Console, *, evidence: bool = False) -> None:
    console.print()
    table = Table(box=box.SIMPLE_HEAD, pad_edge=False, expand=False)
    table.add_column("status", justify="left", no_wrap=True)
    table.add_column("check", overflow="fold")
    table.add_column("result", overflow="fold")
    for r in report.results:
        table.add_row(
            f"[{_STATUS_STYLE[r.status]}]{_STATUS_LABEL[r.status]}[/]",
            f"{r.check_id}  {r.name}",
            r.summary,
        )
    console.print(table)

    detailed = [
        r
        for r in report.results
        if evidence or r.status in (Status.FAIL, Status.ERROR, Status.REVIEW)
    ]
    shown = [r for r in detailed if r.evidence]
    if shown:
        console.print("[bold]Evidence[/bold]")
        for r in shown:
            console.print(
                f"  [{_STATUS_STYLE[r.status]}]{_STATUS_LABEL[r.status]}[/] "
                f"{r.check_id} {r.name} [dim]({r.kind})[/dim]"
            )
            for key, value in r.evidence.items():
                console.print(f"    [dim]{key}:[/dim] {_fmt_evidence_value(value)}")
        console.print()

    # Honesty block: what was read, what was not checked.
    lines: list[str] = []
    if report.sources:
        lines.append("[bold]Read:[/bold]")
        for s in report.sources:
            rows = f", {s.rows} rows" if s.rows is not None else ""
            tail = f" - {s.detail}" if s.detail else ""
            lines.append(f"  {s.alias}: {s.path} ({s.kind}{rows}){tail}")
    skipped = [r for r in report.results if r.status is Status.SKIP]
    if skipped:
        lines.append("[bold]Skipped:[/bold]")
        lines.extend(f"  {r.check_id} {r.name} — {r.summary}" for r in skipped)
    if report.not_checked:
        lines.append("[bold]Never read:[/bold]")
        lines.extend(f"  {item}" for item in report.not_checked)
    lines.append(f"[dim]{HONESTY_FOOTER}[/dim]")
    console.print(Panel("\n".join(lines), title="what this run did and did not do", box=box.SQUARE))

    text, style = _banner(report)
    console.print(Panel(text, style=style, box=box.HEAVY))
    console.print()


def _json_safe(value: Any) -> Any:
    """NaN/inf are not JSON. They should never reach here (empty aggregates are
    ERRORs upstream), but a machine-readable contract does not get to rely on
    'should': scrub them to null rather than emit a token jq will choke on."""
    if isinstance(value, float) and (value != value or value in (float("inf"), float("-inf"))):
        return None
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    return value


def render_json(report: Report) -> str:
    # ensure_ascii keeps the stream valid on any console code page; agents
    # parse this, humans get the terminal renderer.
    return json.dumps(_json_safe(report.to_dict()), indent=2, ensure_ascii=True, default=str)


def render_markdown(report: Report) -> str:
    lines = [
        f"## andon — {report.verdict}",
        "",
        f"Spec: `{report.spec_path}` · andon {report.andon_version} · {report.finished_at}",
        "",
        "| status | check | result |",
        "|---|---|---|",
    ]
    for r in report.results:
        lines.append(f"| {_STATUS_LABEL[r.status]} | `{r.check_id}` {r.name} | {r.summary} |")
    problems = [r for r in report.results if r.status in (Status.FAIL, Status.ERROR, Status.REVIEW)]
    if problems:
        lines += ["", "### Evidence", ""]
        for r in problems:
            lines.append(f"**{_STATUS_LABEL[r.status]} — {r.name}** (`{r.kind}`)")
            lines.append("")
            for key, value in r.evidence.items():
                lines.append(f"- {key}: {_fmt_evidence_value(value)}")
            lines.append("")
    if report.not_checked:
        lines += ["### Never read", ""]
        lines += [f"- {item}" for item in report.not_checked]
        lines.append("")
    lines += ["---", "", f"_{HONESTY_FOOTER}_", ""]
    return "\n".join(lines)

"""Regenerate docs/demo.svg from the quarterly-report example.

The screenshot in the README is not a mock-up: it is this script running the
real spec against the real (deliberately sabotaged) example workbook. If the
output format changes, re-run me so the README never lies about what the tool
prints.

    uv run python scripts/make_demo_svg.py
"""

from __future__ import annotations

from pathlib import Path

from rich.console import Console

from andon.engine import run
from andon.render import render_terminal

ROOT = Path(__file__).parent.parent


def main() -> None:
    report = run(ROOT / "examples" / "quarterly-report" / "andon.yaml")
    console = Console(record=True, width=96, force_terminal=True)
    render_terminal(report, console)
    out = ROOT / "docs" / "demo.svg"
    console.save_svg(out, title="andon run examples/quarterly-report/andon.yaml")
    print(f"wrote {out} (verdict: {report.verdict})")


if __name__ == "__main__":
    main()

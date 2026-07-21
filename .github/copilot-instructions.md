# Copilot instructions — andon

Deterministic verifier that re-checks the numbers in a finished report or workbook against their source data using arithmetic — reconciliation, internal consistency, schema contracts, Excel integrity — never a second LLM. Python 3.10+, managed with `uv` (hatchling backend); the PyPI distribution is `andon-verify` but the import package and CLI stay `andon`.

## Build, test, lint

```bash
uv sync --dev                              # CI adds: --extra duckdb --extra mcp  (so those tests run, not skip)
uv run pytest                              # real CSV/XLSX fixtures, no mocks
uv run ruff check src tests                # line-length 100; select E,F,I,UP,B,SIM,RET,C4
uv run mypy src                            # disallow_untyped_defs = true
uv run python scripts/make_demo_svg.py     # regenerate docs/demo.svg if demo output changed (same PR)
```

CLI: `andon run spec.yaml [--json --strict --md out.md]`, `andon inspect x.xlsx`, `andon diff a.xlsx b.xlsx`, `andon init`. MCP front end: `andon-mcp` (tools `run`, `inspect`, `diff`). CI (Linux + Windows, py3.10 & 3.14) also asserts the sabotaged `examples/quarterly-report` exits 1.

## Architecture

A run is "YAML spec in -> `Report` out". `spec.py` parses the spec (each check entry has exactly one dotted kind like `reconcile.sum`; only `name`/`id`/`skip` are also allowed; relative paths resolve against the spec file's dir). `sources.py` (`SourceStore`) loads CSV/Excel/parquet/DuckDB/JSON and resolves each check "side". `engine.py` runs every check in its own try/except (one bad check never aborts the run; exceptions become ERROR findings) and returns a `Report`. `result.py` holds `Status` (PASS/FAIL/REVIEW/SKIP/ERROR), `Report.verdict`, and `Report.exit_code()`. `render.py` emits terminal/JSON/Markdown; `cli.py` (typer + rich) and `mcp_server.py` are the two front ends; `diff.py` powers `andon diff`.

## Structure

- `src/andon/checks/` — one module per family (`reconcile`, `internal`, `schema`, `excel_integrity`, `plausibility`); `checks/__init__.py` is the registry plus shared param helpers.
- `tests/` — one file per module; fixtures `orders_csv`, `workbook_factory`, `run_spec` live in `conftest.py`.
- `docs/checks.md` (full parameter reference) · `examples/quarterly-report/` (demo) · `skills/verify-with-andon/` (agent skill) · `action.yml` / `Dockerfile` / `.pre-commit-hooks.yaml` (integrations).

## Conventions

- **Add a check** = one `(store, params) -> Outcome` function decorated `@register("family.name", heuristic=?)` in a `checks/` module, then imported at the bottom of `checks/__init__.py`. Nothing else in the engine changes.
- **Reject unknown/missing params** via `reject_unknown(params, allowed, kind)` + `require(...)` -> `SpecError`. A parameter that silently does nothing is forbidden ("a verifier lying about what it verified").
- **Only arithmetic may FAIL.** Heuristic checks register `heuristic=True` and may return REVIEW at most; the engine downgrades any FAIL they emit.
- **Never coerce text to numbers** — use `numeric_series()`, which raises `SourceError` on non-numeric cells (a corrupt cell surfaces as ERROR, never a silent NaN).
- **Errors name context**: "Column 'x' not found. Columns are: a, b, c" — never a bare message. `SpecError` fails fast before any check (exit 4); `SourceError`/unexpected exceptions become ERROR findings, not crashes.
- **Every result carries an `evidence` dict** (values, deltas, tolerances); the renderer invents nothing outside it.
- Determinism is enforced: no network, no randomness, no LLM inside the verifier. Exit codes 0/1/2/3/4 are a public contract CI depends on. `from __future__ import annotations` everywhere; Windows is a first-class target (Excel lives there).

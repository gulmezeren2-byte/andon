# Changelog

## 0.7.0 — 2026-08-03

Fixes a false PASS. A plausibility check that could not read a single value was
reporting that nothing fell outside the bounds — which was true only in the way that
vacuous statements are true.

- **A check that examined nothing no longer passes.** `plausibility.bounds` coerced its
  column to numbers, dropped what would not convert, and then found zero values out of
  bounds in the empty remainder. Given a Turkish Excel export — `1.234,56`, `;`-separated,
  the ordinary shape in this tool's home market — the whole column reads as text, and a
  bound of `min: 999999999` came back **PASS**. It now reports
  *"no numeric values in `tutar`; nothing was compared against the bounds"*.
  For a tool that prints *"a PASS is not an opinion about the analysis; it is arithmetic
  about these claims"* under every report, this was the one defect it could not afford.
- **Partial reads carry their denominator.** When only some of a column parses, the
  verdict says so — *"stays within bounds, but only read 2 of 4 value(s)"* — and
  `plausibility.mean_shift` does the same rather than reporting the mean of whatever
  happened to convert as though it were the mean of the data. Evidence now carries
  `values_checked` / `values_total` / `values_skipped` on both.
- **The skipped count was wrong, too.** It was computed as a coercion delta, so values
  pandas had already turned into `NaN` while *reading* — `n/a`, `-`, `#N/A`, all in its
  default `na_values` — were dropped silently and reported as zero skipped.
- **CSV sources take `decimal` and `thousands`.** `encoding` and `delimiter` existed for
  exactly this reason and stopped one step short: without saying how numbers are
  punctuated, a Turkish file could be read but never measured. Declaring
  `decimal: ","` and `thousands: "."` makes the column checkable; the two must differ,
  and a source that sets them to the same character is refused rather than guessed at.
- Clean numeric data still passes silently. The fix adds no noise to a run that had
  nothing wrong with it, which a regression test pins.


## 0.6.2 — 2026-07-30

- **Fixed: the MCP server would not start with version 2 of the MCP SDK.** The SDK
  renamed its high-level server class between majors — `mcp.server.fastmcp.FastMCP`
  in 1.x, `mcp.server.MCPServer` in 2.x — and removed the old module outright, so a
  fresh `pip install 'andon-verify[mcp]'` resolved SDK 2.0.0 and the server died at import.
  Both spellings are now accepted; they are drop-in for what is used of them, so
  nobody is pinned to one SDK generation.
- **And the error no longer sends you in a circle.** The old handler treated every
  import failure as a missing optional dependency and said to install the extra —
  which, once the SDK moved, was advice to repeat the step you had already done. A
  package that isn't installed and an SDK that moved are different problems, and are
  now reported as such.


## 0.6.1 — 2026-07-29

- **Fixed a crash when output is piped on Windows.** A piped stdout gets the legacy
  code page rather than UTF-8, and findings quote the workbook — sheet names, labels
  and cell values, routinely non-ASCII — which raised `UnicodeEncodeError` and took the
  command down. So `andon run spec.yaml | tee`, and any CI step capturing the log,
  failed on ordinary data. Output streams are now asked for UTF-8, and the guard never
  fails if a stream won't take it.

## 0.6.0 — 2026-07-17

- **JSON and JSONL sources.** A source can now be a `.json` file (an array of record
  objects) or a `.jsonl`/`.ndjson` file (one object per line), alongside CSV, Excel,
  parquet and DuckDB. Agents emit JSON; andon can now verify it directly against the data
  it came from, instead of making you convert to CSV first. Errors name the shape andon
  expected, so a malformed file fails clearly.

## 0.5.0 — 2026-07-17

- **CSV encoding and delimiter controls.** A CSV source can now be given as a mapping —
  `{path: data/satis.csv, encoding: cp1254, delimiter: ";"}` — instead of a bare path.
  The default encoding is now `utf-8-sig`, which reads plain utf-8 *and* strips the BOM
  Excel writes (so it no longer poisons the first column name). A wrong encoding fails
  with a message that names the likely culprit (Turkish exports are often cp1254),
  rather than silently mojibaking the data and then "verifying" it.

## 0.4.0 — 2026-07-17

- **MCP server**: `andon-mcp` exposes three tools to any MCP-speaking agent runtime —
  `run` (execute a spec), `inspect` (integrity-scan a workbook with no spec written), and
  `diff` (classify what changed between two workbook versions). The agent gets the same
  structured verdict a human gets. Optional extra: `pip install 'andon-verify[mcp]'`.

## 0.3.0 — 2026-07-17

- **`andon diff`**: compare two workbook versions and classify what changed — a new error
  cell (`#REF!` …) called out on its own, numeric moves with a delta and a percent, formula
  edits, appeared/vanished cells, added/removed sheets. `--tolerance` hides numeric noise;
  `--json` for pipelines. Exit codes: 0 = nothing meaningful changed, 1 = a new error (or
  `--strict`: any change), 2 = changes but no new error.

## 0.2.1 — 2026-07-17

- `andon --version` now reads the installed distribution version dynamically, so it can
  never drift from `pyproject.toml` again (0.2.0 reported 0.1.0).

## 0.2.0 — 2026-07-17

- **DuckDB sources**: a source can be a SQL query (`duckdb: SELECT ...`) instead of a
  file, so a report can be reconciled against the same data a BI tool reads. DuckDB reads
  CSV/parquet/JSON and `.duckdb` files inside the query. Optional extra:
  `pip install 'andon-verify[duckdb]'`.
- **GitHub Action**: `uses: gulmezeren2-byte/andon@v1` runs a spec in CI and writes the
  verdict to the job summary.
- **pre-commit hook**: `.pre-commit-hooks.yaml` ships an `andon` hook, so a broken report
  can stop a commit.

## 0.1.0 — 2026-07-16

First public release.

- Five check families: `reconcile` (row_count, sum, aggregate, group_sum, keys),
  `internal` (total_row, percent_sum, recompute), `schema` (columns, unique, not_null,
  allowed_values, date_continuity), `excel.integrity`, `plausibility` (bounds,
  new_categories, mean_shift).
- The heuristic guard: checks registered as heuristic cannot FAIL a run, enforced by
  the engine rather than by convention.
- Honesty block in every report: sources actually read, checks skipped, worksheets
  never touched.
- CLI (`run`, `inspect`, `init`) with contract exit codes (0/1/2/3/4), `--json`,
  `--strict`, `--md`.
- Worked example with planted defects (`examples/quarterly-report/`).
- CSV, Excel (sheet and range references) and parquet sources; cell reads use cached
  values and refuse to guess at uncalculated formulas.

# Changelog

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

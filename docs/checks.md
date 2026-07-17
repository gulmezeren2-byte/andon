# Check reference

Everything a spec can say, with the exact semantics. If this page and the code ever
disagree, the code is the bug or this page is — either way, open an issue.

## Spec anatomy

```yaml
version: 1                       # required; this build supports version 1

sources:                         # alias -> reference
  orders: data/orders.csv        # csv
  history: data/2025.parquet     # parquet (pip install andon-verify[parquet])
  report: out/q2.xlsx#Summary    # a worksheet
  regions: out/q2.xlsx#Summary!A8:C12   # a range; first row is the header

checks:
  - name: human-readable label   # optional; defaults to the check kind
    id: revenue-total            # optional; defaults to c01, c02, ...
    skip: waiting for June data  # optional; true or a reason string
    reconcile.sum:               # exactly one check kind per entry
      ...parameters...
```

Rules the parser enforces:

- Exactly one check kind per entry. `name`, `id`, `skip` are the only other keys.
- Unknown check kinds are hard errors with a "did you mean" hint; unknown parameters
  are hard errors that list what is allowed. A typo must never silently weaken a
  verification.
- Relative paths resolve against the spec file's directory, not your current directory.

## Sides

Comparisons take a `left` and a `right` side. A side is one of:

```yaml
{ source: orders }                            # a whole table
{ source: orders, where: "status == 'x'" }    # a filtered table (pandas query syntax)
{ source: report, cell: B6 }                  # one cell of a workbook (the cached value)
{ value: 1240 }                               # a literal claimed number
{ source: orders, column: net_revenue }       # per-side column override (aggregates)
```

Conventions used below: **left** is the data, **right** is the claim. Evidence always
carries both values, the delta and the tolerance actually used.

## Tolerances

```yaml
tolerance: 0.01     # absolute, in the unit of the compared value
tolerance: 0.5%     # relative to the claimed (right) value
```

Defaults: exact (`±0`) for counts and key comparisons; `±1e-6` for sums and other float
aggregates; `±0.1` for percent sums. A relative tolerance against a claimed value of
exactly 0 accepts only 0.

---

## reconcile — the report vs. its data

### reconcile.row_count

Row count of the left side equals the claimed count on the right.

```yaml
- name: no dropped orders
  reconcile.row_count:
    left:  { source: orders, where: "status != 'cancelled'" }
    right: { source: report, cell: B4 }   # or { value: 1240 }
    tolerance: 0                          # default: exact
```

### reconcile.sum / reconcile.aggregate

An aggregate of a numeric column equals the claim. `reconcile.sum` is shorthand for
`reconcile.aggregate` with `agg: sum`; other aggregates are `mean`, `min`, `max`,
`count`.

```yaml
- reconcile.aggregate:
    agg: mean
    column: revenue          # applies to any side that is a table
    left:  { source: orders, where: "status == 'shipped'" }
    right: { source: report, cell: B5 }
    tolerance: 1%
```

Non-numeric values in the column are an ERROR, not a coercion. Nulls are ignored and
their count is reported in the evidence.

### reconcile.group_sum

Per-group sums agree between two tables. Catches the single wrong region in an
otherwise correct breakdown, and groups that exist on only one side.

```yaml
- reconcile.group_sum:
    column: revenue
    by: region
    left:  { source: orders, where: "status == 'shipped'" }
    right: { source: regions }           # a table with `region` and `revenue` columns
    tolerance: 0.5
```

FAILs on: any group off beyond tolerance, groups missing from the claim, claimed groups
absent from the data. Evidence lists up to 10 of each.

### reconcile.keys

Key sets agree between two tables.

```yaml
- reconcile.keys:
    column: order_id
    mode: subset      # every claimed key must exist in the data
    left:  { source: orders }
    right: { source: detail_table }
```

`mode: equal` (default) requires identical key sets; `mode: subset` requires
right ⊆ left — use it when the report shows a selection of real rows and you want to
catch invented ones.

---

## internal — the report vs. itself

### internal.total_row

A total cell equals the sum of its parts. Blank cells in the range are skipped and
counted; text in the range is an ERROR.

```yaml
- internal.total_row:
    source: report
    parts: B15:B17
    total: B18
    tolerance: 0.01
```

### internal.percent_sum

Shares sum to a target (default 100). Three forms: a range of cells, a column, or a
column per group.

```yaml
- internal.percent_sum: { source: report, range: B9:B12 }
- internal.percent_sum: { source: shares, column: share_pct, by: quarter, tolerance: 0.1 }
```

### internal.recompute

A derived column really derives. Both expressions are pandas `eval` syntax over the
table's columns; rows where they disagree beyond tolerance are violations. NaN on both
sides is agreement; NaN on one side is a violation.

```yaml
- internal.recompute:
    source: invoice_lines
    expr: gross - vat
    equals: net
    tolerance: 0.01
```

---

## schema — the data vs. its assumptions

```yaml
- schema.columns:        { source: orders, required: [order_id, revenue], forbid_extra: false }
- schema.unique:         { source: orders, column: order_id }        # or columns: [a, b]
- schema.not_null:       { source: orders, columns: [order_id, region] }
- schema.allowed_values: { source: orders, column: status, allowed: [shipped, cancelled] }
- schema.date_continuity: { source: orders, column: order_date, freq: D }
```

`date_continuity` accepts pandas period frequencies (`D`, `W-MON`, `M`, `Q`, ...) and
fails on missing periods between the column's min and max. All schema checks accept an
optional `where` filter.

---

## excel.integrity — the workbook vs. entropy

```yaml
- excel.integrity:
    source: report
    sheets: [Summary, Detail]   # optional; default is every sheet
```

Deterministic (can FAIL): error values in cells (`#REF!`, `#DIV/0!`, `#VALUE!`,
`#N/A`, `#NAME?`, `#NULL!`, `#NUM!`) and formulas containing `#REF!`.

Heuristic (REVIEW at most):

- numeric constants inside a column that is ≥60% formulas (min 5) — someone typed over
  a formula;
- numbers stored as text, including `"1.234,56"`-style Turkish/European formatting that
  silently drops out of every `SUM`;
- hidden rows/columns inside the used range;
- references into other workbooks.

Informational only (never changes the verdict): merged ranges, volatile formulas
(`NOW`, `TODAY`, `RAND`, `INDIRECT`, `OFFSET`). They are in the evidence because they
are worth knowing, and not in the verdict because in real reports they are too common
to be a signal.

Sheets excluded via `sheets:` are listed under "Never read" in the honesty block.

---

## plausibility — flags for a human, never failures

Everything here is registered as heuristic: the engine will not let these checks FAIL
a run, even if they try. Treat a REVIEW as "someone should know why," not "wrong."

```yaml
- plausibility.bounds:         { source: orders, column: revenue, min: 0, where: "status == 'shipped'" }
- plausibility.new_categories: { column: region, left: { source: history }, right: { source: orders } }
- plausibility.mean_shift:     { column: revenue, left: { source: history }, right: { source: orders }, max_sigmas: 3 }
```

If you want a bound that *fails* the build, you don't want plausibility — reconcile
against source data, or run with `--strict` and treat REVIEW as blocking.

---

## The JSON report

`andon run spec.yaml --json` emits (abridged — a real report also carries
`started_at`/`finished_at` timestamps and a `detail` field per source):

```json
{
  "andon_version": "0.1.0",
  "spec": "andon.yaml",
  "verdict": "FAIL",
  "counts": {"pass": 4, "fail": 5, "review": 1, "skip": 0, "error": 0},
  "checks": [
    {
      "id": "c03",
      "kind": "reconcile.row_count",
      "name": "shipped order count matches the data",
      "status": "fail",
      "summary": "row counts disagree: 539 in data vs 551 claimed (-12)",
      "evidence": {"left_count": 539, "right_count": 551, "delta": -12, "tolerance": "±0"},
      "duration_ms": 12.4
    }
  ],
  "sources": [{"alias": "orders", "path": "data/orders.csv", "kind": "csv", "rows": 561}],
  "not_checked": ["report.xlsx#Scratch"]
}
```

Field names are part of the public contract from 0.1.0 on; additions may happen,
renames won't without a major version.

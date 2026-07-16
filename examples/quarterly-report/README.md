# The sabotaged quarterly report

A worked example: `data/orders.csv` is the truth, `report.xlsx` is an "AI-drafted"
quarterly report with planted defects, and `andon.yaml` is the spec that catches them.
The defects are the ones I actually meet in reporting work:

| where | defect | caught by |
|---|---|---|
| `Summary!B3` | order count from a stale snapshot (+12 cancelled orders) | `reconcile.row_count` |
| `Summary!B4` | net revenue typed over by hand, +1.8% | `reconcile.sum` |
| `Summary!B9:B12` | region shares that sum to 101.2 | `internal.percent_sum` |
| `Summary!B18` | a total row computed before the May data refresh | `internal.total_row` |
| `Detail!G2` | `=SUM(#REF!)` — the column it pointed at was deleted | `excel.integrity` |
| `Detail!D5`, `Detail!F2:F3` | a constant typed over a formula column; freight keyed in as text (`1.234,56`) | `excel.integrity` |
| the 201st order | a refund posted as negative revenue — plausible, so it flags REVIEW, not FAIL | `plausibility.bounds` |

Four checks pass on purpose: a verifier that only ever fails teaches people to ignore
it. The `Scratch` sheet is deliberately excluded from the integrity scan so the report
must admit it under "Never read".

## Run it

```
andon run andon.yaml            # expect: STOP THE LINE, exit code 1
andon run andon.yaml --json     # the same verdict, machine-readable
```

## Regenerate the files

Everything is deterministic (seeded RNG), so the numbers in the README screenshot are
reproducible:

```
python make_example.py
```

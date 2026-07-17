# andon

**Stop the line when the numbers don't add up.**

[![CI](https://github.com/gulmezeren2-byte/andon/actions/workflows/ci.yml/badge.svg)](https://github.com/gulmezeren2-byte/andon/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](pyproject.toml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

andon re-checks the numbers in finished analysis — the report your AI agent just drafted,
the workbook a colleague "quickly updated" — against the data they came from and against
themselves. It does this with arithmetic, not with another LLM: reconciliation,
internal consistency, schema contracts and Excel workbook integrity, written down as a
small YAML spec and enforced with exit codes.

![andon stopping the line on a sabotaged quarterly report](docs/demo.svg)

That screenshot is real output. The example it runs on is in
[`examples/quarterly-report/`](examples/quarterly-report/), staged by a script that
plants the defects I keep meeting in real reporting work: a count taken from a stale
snapshot, a revenue total typed over by hand, shares that sum to 101.2, a total row
nobody updated after a data refresh, a `#REF!`, and freight numbers stored as text.

## Why this exists

I'm an industrial engineer. I build and run operations reporting — delivery KPIs,
forecast accuracy, inventory analytics — and over the last two years an increasing share
of the first drafts around me has been written by AI agents. They are fast, tireless,
and confidently wrong in ways a tired human is not: the filter that silently dropped
cancelled orders, the percentage column that almost sums to 100, the total row that
survived three edits of its parts.

The common answer is to ask a second model to review the first one. I think that is the
wrong tool. Whether 539 rows really sum to 257,060.48 is not a matter of opinion, and no
amount of model capability makes an opinion the right instrument for it.

Manufacturing solved this problem decades ago. On a Toyota line, any worker who spots a
defect pulls a cord — the *andon* — and the line stops until the problem is understood.
The machine equivalent, *jidoka*, is a machine that stops itself when it detects an
abnormal condition. This tool is that cord for spreadsheets and reports: a small,
deterministic gate between "the analysis is written" and "the analysis is sent."

## The iron rules

andon's behavior is easier to trust because it is constrained. These rules are enforced
in code, not just promised here:

1. **Only arithmetic can fail the build.** Heuristic checks (distribution shifts,
   plausibility bounds) can raise a REVIEW flag; the engine will not let them FAIL, even
   if a buggy check tries.
2. **No silent blessings.** Every report ends with what was read, what was skipped, and
   which worksheets were never touched (the report calls this the honesty block). A
   PASS covers the listed assertions and nothing else.
3. **A check that can't run is a finding, not a pass.** Missing file, unreadable range,
   text in a numeric column — the run continues, the check is recorded as ERROR, and the
   exit code is non-zero. "Not verified" must never be readable as "fine."
4. **Read-only by construction.** There is no code path that writes to your data.

## Install

```
pip install andon-verify
```

The PyPI distribution is named `andon-verify` (the bare `andon` name was already
taken); the command and the import stay `andon` — `andon run ...`, `import andon`.
From source: `pip install git+https://github.com/gulmezeren2-byte/andon`.

## Quick start

Point andon at data and claims:

```yaml
# andon.yaml
version: 1

sources:
  orders: data/orders.csv
  report: out/weekly.xlsx#Summary

checks:
  - name: no dropped orders
    reconcile.row_count:
      left:  { source: orders, where: "status != 'cancelled'" }
      right: { source: report, cell: B4 }

  - name: revenue adds up
    reconcile.sum:
      column: revenue
      left:  { source: orders, where: "status != 'cancelled'" }
      right: { source: report, cell: B6 }
      tolerance: 0.5%

  - name: totals row is honest
    internal.total_row:
      source: report
      parts: B10:B21
      total: B22
      tolerance: 0.01

  - name: workbook is mechanically sound
    excel.integrity:
      source: report
```

```
andon run andon.yaml            # human-readable verdict
andon run andon.yaml --json     # full machine-readable report
andon inspect out/weekly.xlsx   # integrity-scan a workbook, no spec needed
andon init                      # write a commented starter spec
```

Or try the sabotaged example in this repo:

```
git clone https://github.com/gulmezeren2-byte/andon
cd andon/examples/quarterly-report
andon run andon.yaml
```

## What it checks

| Family | Checks | Question it answers | Can FAIL? |
|---|---|---|---|
| `reconcile` | `row_count`, `sum`, `aggregate`, `group_sum`, `keys` | Does the report agree with the data it came from? | yes |
| `internal` | `total_row`, `percent_sum`, `recompute` | Does the report agree with itself? | yes |
| `schema` | `columns`, `unique`, `not_null`, `allowed_values`, `date_continuity` | Is the data shaped the way everyone assumes? | yes |
| `excel` | `integrity` | Is the workbook mechanically sound? (`#REF!`, values typed over formulas, numbers stored as text — including the `1.234,56` flavor — hidden rows, external links) | on error cells |
| `plausibility` | `bounds`, `new_categories`, `mean_shift` | Should a human look at this before anyone trusts it? | no — REVIEW at most |

Full parameter reference with examples: [`docs/checks.md`](docs/checks.md).

## Exit codes and CI

Exit codes are a contract:

| code | meaning |
|---|---|
| 0 | every check passed |
| 1 | at least one FAIL (with `--strict`: also on REVIEW/ERROR/nothing-ran) |
| 2 | no failures, but REVIEW flags were raised |
| 3 | nothing was verified — a check could not run, or every check was skipped |
| 4 | the spec itself is broken |

```yaml
# in a GitHub Actions job, after your report is generated:
- run: pip install andon-verify
- run: andon run reports/andon.yaml --strict --md verdict.md
```

`--md` writes a Markdown verdict you can post as a PR comment.

## Using andon with AI agents

andon is built to be *driven by* agents, not to contain one:

- `--json` emits the full report with stable field names; the exit code alone is enough
  for a go/no-go decision.
- Error messages name the sources, columns and sheets involved, so an agent can repair
  its own spec instead of guessing ("Column 'Revenue' not found. Columns are: region,
  share_pct, revenue").
- [`skills/verify-with-andon/`](skills/verify-with-andon/) ships a skill for Claude
  Code and compatible harnesses that teaches an agent the discipline: after drafting any
  analysis, write the spec, run andon, and report the verdict — including the rule that
  loosening a tolerance to make a check pass must be declared, never silent.

My working rule: the agent that wrote the analysis also writes the spec, and neither is
finished until `andon run` exits 0 — or a human has signed off on every flag it raised.

## What andon is not

- **Not a data-quality platform.** [Great Expectations](https://github.com/great-expectations/great_expectations)
  and [pandera](https://github.com/unionai-oss/pandera) validate data *inside pipelines*,
  in code, usually against a warehouse. andon verifies *claims in finished artifacts* —
  the report against its source — and treats Excel as a first-class citizen, because
  that is where analysis actually lives in most companies.
- **Not an LLM evaluator.** It doesn't score model outputs; it re-derives numbers.
- **Not a replacement for reading the report.** It removes a class of mechanical error
  so human review can spend itself on judgment.

## Limitations, honestly

- **Formula cells need cached values.** andon reads the value Excel last calculated. A
  workbook produced by a library and never opened in Excel/LibreOffice carries no cached
  values for its formulas; andon refuses to guess and reports exactly that.
- **`where` filters are pandas `query()` expressions.** They are expressive, which means
  a spec can encode the same mistakes as any query. Specs are code — review them like code.
- **Heuristic checks have false positives by design.** That is why they cannot fail a
  build.
- **Scale is untested beyond mid-size files.** Everyday operational workbooks and CSVs
  (hundreds of thousands of rows) are fine; nobody has benchmarked it against 10 GB of
  parquet. If you do, tell me what broke.
- Parquet sources need `pip install 'andon-verify[parquet]'`.

## Roadmap

Near-term, in order:

- **SQL sources** (DuckDB) so a side can be a query, not only a file
- **`andon diff`** — two versions of the same workbook, explained cell by cell
- **MCP server** exposing `run`/`inspect` to agent harnesses natively
- CSV dialect and encoding controls

Not planned: dashboards, scheduled runners, LLM-powered anything inside the verifier.
The verifier stays deterministic; that is the point.

## How this project is built

I design the checks, decide the semantics and review every line; I use AI agents
(Claude Code) heavily for implementation speed, and the commit trailers say so. If that
bothers you, read `tests/` first: the suite builds real CSV and XLSX fixtures, no
mocks, and it is the contract. Tests don't care who typed them.

## License

[MIT](LICENSE) — Mehmet Eren Gülmez

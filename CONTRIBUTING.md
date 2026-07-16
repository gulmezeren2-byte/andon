# Contributing

Thanks for considering it. A few ground rules keep this project the kind of tool
people can bet a report on.

## Ground rules

- **Open an issue before building a new check family.** The check surface is the
  product; I keep it deliberately small and I say no to additions that overlap with an
  existing family or that belong in a pipeline tool instead.
- **Every check change ships with tests against real files.** The suite builds actual
  CSV/XLSX fixtures — no mocks. If your check has a failure mode, there must be a test
  that triggers it.
- **Determinism is non-negotiable.** No network calls, no randomness, no LLMs inside
  the verifier. Heuristic checks must be registered `heuristic=True` so the engine can
  keep them from failing a build.
- **Error messages carry context.** If a check can't run, the message must name the
  source, column or sheet involved and, where possible, list what *does* exist. "Column
  not found" is not an acceptable message; "Column 'x' not found. Columns are: a, b, c"
  is.
- **Run it on real data before you submit.** A check that only ever met synthetic
  fixtures usually has an opinion problem waiting in production.

## Mechanics

```
uv sync --dev
uv run pytest
uv run ruff check src tests
uv run mypy src
```

All three must be clean. CI runs them on Linux and Windows — Windows is not an
afterthought here; it is where the Excel files live.

Keep PRs scoped to one change. If the demo output changes, regenerate the README asset
with `uv run python scripts/make_demo_svg.py` in the same PR, so the screenshot never
lies about what the tool prints.

# Security

## Model

andon is a local, offline tool: it makes no network calls, executes no formulas, and
has no code path that writes to your data files. The attack surface that remains:

- **Spec `where`/`expr` fields are pandas `query`/`eval` expressions.** They run with
  the pandas engine against your DataFrames. Treat specs from untrusted sources the way
  you would treat SQL from untrusted sources: read them first.
- **Workbooks are parsed with openpyxl.** A hostile file could try to exploit the
  parser; keep your dependencies current.

## Reporting

Report vulnerabilities through GitHub's private security advisories on this repository
(Security → Report a vulnerability). I'll acknowledge within a few days.

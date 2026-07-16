---
name: verify-with-andon
description: After producing or editing any data analysis artifact (report, Excel file, summary table), write an andon verification spec and run it. Use whenever numbers are derived from data and are about to be presented as results.
---

# Verify analysis with andon

You have just produced (or edited) an analysis artifact: a report workbook, a summary
table, a set of claimed figures. Before presenting it, verify it with andon. The
verification is deterministic arithmetic — your own confidence in the numbers is not a
substitute for it.

## The discipline

1. **Write the spec while the derivation is fresh.** For every number you put in the
   artifact, you know which source rows and filters produced it. Encode exactly that as
   a check. If you cannot write the check, you do not actually know where the number
   came from — treat that as a defect in the analysis, not in the spec.

2. **Cover four layers, in this order:**
   - `schema.*` — the assumptions about the source data (unique keys, allowed values,
     date continuity);
   - `reconcile.*` — every headline figure against the source, with the same filters
     you used to derive it;
   - `internal.*` — totals vs parts, percentages vs 100, derived columns vs their
     formulas;
   - `excel.integrity` — if the artifact is a workbook.

3. **Run and read:**

   ```
   andon run andon.yaml --json
   ```

   Exit 0 = all pass. Exit 1 = at least one FAIL: the artifact is wrong or the spec is —
   find out which before touching anything else. Exit 2 = REVIEW flags: report them to
   the user verbatim; do not resolve them yourself. Exit 3 = nothing was verified (a
   check could not run, or every check was skipped): fix the spec or say plainly that
   the claim is unverified. Exit 4 = broken spec.

4. **Report the verdict with the artifact.** Include the counts (passed/failed/review)
   and the honesty block's "Never read" list. A clean verdict is part of the
   deliverable; a dirty one is the deliverable.

## Hard rules

- Never loosen a tolerance, add a `skip:`, or narrow a `where:` to make a check pass
  without stating in your response exactly what you changed and why. A silently
  weakened spec is worse than no spec.
- Never present a number the spec does not cover as if it were verified. Say which
  figures are covered and which are not.
- If a cell read fails with "no cached value" (library-written workbook), point the
  check at the underlying data range instead of the formula cell.
- Prefer failing loudly over passing quietly: when unsure between two ways to write a
  check, write the stricter one and let the human relax it.

## Spec syntax

Run `andon init` for a commented starter, or see the full reference:
https://github.com/gulmezeren2-byte/andon/blob/main/docs/checks.md

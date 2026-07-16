"""Internal-consistency checks: does the report agree with itself?

A report that disagrees with itself needs no source data to be proven wrong.
Totals that don't equal their parts, percentages that sum to 101.3, derived
columns that don't derive — these are the cheapest bugs to catch and the most
embarrassing ones to ship.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from andon.checks import (
    Outcome,
    group_labels,
    numeric_series,
    register,
    reject_unknown,
    require,
    sample,
)
from andon.errors import SourceError, SpecError
from andon.result import Status
from andon.sources import SourceStore
from andon.tolerance import FLOAT_EPS, Tolerance, parse_tolerance


@register("internal.total_row")
def total_row(store: SourceStore, params: dict[str, Any]) -> Outcome:
    kind = "internal.total_row"
    reject_unknown(params, ("source", "parts", "total", "tolerance"), kind)
    alias = require(params, "source", kind)
    parts_range = require(params, "parts", kind)
    total_cell = require(params, "total", kind)
    tol = parse_tolerance(params.get("tolerance"), FLOAT_EPS)

    values, blanks = store.values(alias, str(parts_range))
    if not values:
        raise SourceError(f"{kind}: range {parts_range} contains no numbers.")
    total = store.cell(alias, str(total_cell))
    if total is None or isinstance(total, bool) or not isinstance(total, (int, float)):
        raise SourceError(f"{kind}: {alias}!{total_cell} is {total!r}, not a number.")

    parts_sum = float(sum(values))
    claimed = float(total)
    evidence = {
        "parts": f"{parts_range} ({len(values)} numbers, {blanks} blank)",
        "total_cell": str(total_cell),
        "parts_sum": round(parts_sum, 6),
        "total": round(claimed, 6),
        "delta": round(parts_sum - claimed, 6),
        "tolerance": tol.describe(),
    }
    if tol.allows(parts_sum, claimed):
        return Outcome(Status.PASS, f"total row honest at {claimed:,.2f}", evidence)
    return Outcome(
        Status.FAIL,
        f"total {claimed:,.2f} != sum of parts {parts_sum:,.2f} "
        f"(delta {parts_sum - claimed:+,.2f})",
        evidence,
    )


@register("internal.percent_sum")
def percent_sum(store: SourceStore, params: dict[str, Any]) -> Outcome:
    kind = "internal.percent_sum"
    reject_unknown(
        params, ("source", "column", "range", "by", "target", "tolerance", "where"), kind
    )
    alias = require(params, "source", kind)
    try:
        target = float(params.get("target", 100.0))
    except (TypeError, ValueError) as exc:
        raise SpecError(f"{kind}: `target` must be a number.") from exc
    tol = parse_tolerance(params.get("tolerance"), Tolerance("abs", 0.1))

    column = params.get("column")
    cell_range = params.get("range")
    if bool(column) == bool(cell_range):
        raise SpecError(f"{kind}: provide exactly one of `column` or `range`.")
    if cell_range and (params.get("where") or params.get("by")):
        raise SpecError(f"{kind}: the `range` form does not take `where` or `by`.")

    if cell_range:
        values, blanks = store.values(alias, str(cell_range))
        total = float(sum(values))
        evidence = {
            "range": str(cell_range),
            "n_values": len(values),
            "blanks": blanks,
            "sum": round(total, 6),
            "target": target,
            "tolerance": tol.describe(),
        }
        if tol.allows(total, target):
            return Outcome(Status.PASS, f"shares sum to {total:,.2f}", evidence)
        return Outcome(
            Status.FAIL,
            f"shares sum to {total:,.2f}, expected {target:g} (off by {total - target:+.2f})",
            evidence,
        )

    df = store.frame(alias, params.get("where"))
    series = numeric_series(df, str(column), kind)
    by = params.get("by")
    if by:
        if by not in df.columns:
            raise SourceError(f"{kind}: group column {by!r} not found.")
        labels, null_labels = group_labels(df[by])
        sums = series.groupby(labels).sum()
        bad = [
            {"group": g, "sum": round(float(s), 4)}
            for g, s in sums.items()
            if not tol.allows(float(s), target)
        ]
        evidence = {
            "column": column,
            "by": by,
            "groups": int(len(sums)),
            "target": target,
            "tolerance": tol.describe(),
            "off_target": sample(bad),
            "off_target_count": len(bad),
            "null_group_labels": null_labels,
        }
        if not bad:
            return Outcome(
                Status.PASS, f"shares sum to {target:g} in all {len(sums)} groups", evidence
            )
        return Outcome(
            Status.FAIL, f"{len(bad)} group(s) do not sum to {target:g}", evidence
        )
    total = float(series.sum())
    evidence = {
        "column": column,
        "sum": round(total, 6),
        "target": target,
        "tolerance": tol.describe(),
    }
    if tol.allows(total, target):
        return Outcome(Status.PASS, f"shares sum to {total:,.2f}", evidence)
    return Outcome(
        Status.FAIL,
        f"shares sum to {total:,.2f}, expected {target:g} (off by {total - target:+.2f})",
        evidence,
    )


@register("internal.recompute")
def recompute(store: SourceStore, params: dict[str, Any]) -> Outcome:
    kind = "internal.recompute"
    reject_unknown(params, ("source", "expr", "equals", "tolerance", "where"), kind)
    alias = require(params, "source", kind)
    expr = str(require(params, "expr", kind))
    equals = str(require(params, "equals", kind))
    tol = parse_tolerance(params.get("tolerance"), FLOAT_EPS)

    df = store.frame(alias, params.get("where"))
    try:
        recomputed = pd.to_numeric(df.eval(expr), errors="coerce")
        stated = pd.to_numeric(df.eval(equals), errors="coerce")
    except Exception as exc:
        raise SourceError(
            f"{kind}: cannot evaluate {expr!r} == {equals!r} -> {exc}. "
            f"Columns are: {', '.join(map(str, df.columns))}"
        ) from exc

    delta = (recomputed - stated).abs()
    if tol.kind == "rel":
        limit = stated.abs() * tol.value
    else:
        limit = pd.Series(tol.value, index=stated.index)
    # NaN on both sides is agreement; NaN on exactly one side is a violation.
    # (pandas comparisons involving NaN are False, so the XOR term must be OR-ed in.)
    one_sided_nan = recomputed.isna() ^ stated.isna()
    violating = df.index[(delta > limit) | one_sided_nan]

    rows = []
    for idx in violating[:10]:
        re_val = recomputed[idx]
        st_val = stated[idx]
        rows.append(
            {
                "row": int(idx),
                "recomputed": None if pd.isna(re_val) else round(float(re_val), 6),
                "stated": None if pd.isna(st_val) else round(float(st_val), 6),
            }
        )
    evidence = {
        "expr": expr,
        "equals": equals,
        "rows_checked": int(len(df)),
        "violations": len(violating),
        "tolerance": tol.describe(),
        "sample": rows,
    }
    if len(violating) == 0:
        return Outcome(
            Status.PASS, f"`{equals} = {expr}` holds on all {len(df)} rows", evidence
        )
    return Outcome(
        Status.FAIL,
        f"`{equals} = {expr}` fails on {len(violating)} of {len(df)} rows",
        evidence,
    )

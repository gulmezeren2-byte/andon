"""Reconciliation checks: does the report agree with the data it came from?

These are the checks that catch the classic failure of AI-drafted analysis:
the pipeline silently dropped, duplicated or re-filtered rows somewhere
between the source and the number in the report. Every check here compares
two *sides* — each side is a filtered table, a cell in a workbook, or a
literal claimed value.
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
from andon.tolerance import EXACT, FLOAT_EPS, parse_tolerance

_AGGS = ("sum", "mean", "min", "max", "count")


def _describe_side(side: Any) -> str:
    if isinstance(side, dict):
        if "value" in side:
            return f"literal {side['value']}"
        bits = [str(side.get("source", "?"))]
        if side.get("cell"):
            bits.append(f"!{side['cell']}")
        if side.get("where"):
            bits.append(f" where {side['where']}")
        return "".join(bits)
    return f"literal {side}"


@register("reconcile.row_count")
def row_count(store: SourceStore, params: dict[str, Any]) -> Outcome:
    reject_unknown(params, ("left", "right", "tolerance"), "reconcile.row_count")
    left = require(params, "left", "reconcile.row_count")
    right = require(params, "right", "reconcile.row_count")
    tol = parse_tolerance(params.get("tolerance"), EXACT)

    counts: list[float] = []
    for label, side in (("left", left), ("right", right)):
        kind, resolved = store.resolve_side(side, context=f"reconcile.row_count.{label}")
        counts.append(float(len(resolved)) if kind == "frame" else float(resolved))

    actual, claimed = counts
    ok = tol.allows(actual, claimed)
    evidence = {
        "left": _describe_side(left),
        "right": _describe_side(right),
        "left_count": int(actual),
        "right_count": int(claimed),
        "delta": int(actual - claimed),
        "tolerance": tol.describe(),
    }
    if ok:
        return Outcome(Status.PASS, f"row counts agree at {int(actual)}", evidence)
    return Outcome(
        Status.FAIL,
        f"row counts disagree: {int(actual)} in data vs {int(claimed)} claimed "
        f"({int(actual - claimed):+d})",
        evidence,
    )


def _aggregate(
    store: SourceStore, params: dict[str, Any], kind: str, agg: str, *, agg_param: bool
) -> Outcome:
    allowed = ("left", "right", "column", "agg", "tolerance") if agg_param else (
        "left", "right", "column", "tolerance"
    )
    reject_unknown(params, allowed, kind)
    left = require(params, "left", kind)
    right = require(params, "right", kind)
    column = params.get("column")
    tol = parse_tolerance(params.get("tolerance"), FLOAT_EPS)

    values: list[float] = []
    nulls: list[int] = []
    used_cols: list[str] = []
    for label, side in (("left", left), ("right", right)):
        side_kind, resolved = store.resolve_side(side, context=f"{kind}.{label}")
        if side_kind == "scalar":
            values.append(float(resolved))
            nulls.append(0)
            continue
        col = (side.get("column") if isinstance(side, dict) else None) or column
        if not col:
            raise SpecError(f"{kind}: the {label} side is a table, so `column` is required.")
        used_cols.append(str(col))
        series = numeric_series(resolved, col, label)
        nulls.append(int(series.isna().sum()))
        if agg == "count":
            values.append(float(series.notna().sum()))
            continue
        if agg == "sum":
            values.append(float(series.sum()))  # sum over zero rows is a legitimate 0
            continue
        if series.dropna().empty:
            raise SourceError(
                f"{kind}: cannot compute `{agg}` over 0 numeric rows on the {label} "
                f"side (the filter may have removed everything). An empty aggregate "
                f"is a finding, not a number."
            )
        values.append(float(getattr(series, agg)()))

    actual, claimed = values
    ok = tol.allows(actual, claimed)
    evidence = {
        "aggregate": agg,
        "column": column or (", ".join(dict.fromkeys(used_cols)) or None),
        "left": _describe_side(left),
        "right": _describe_side(right),
        "left_value": round(actual, 6),
        "right_value": round(claimed, 6),
        "delta": round(actual - claimed, 6),
        "tolerance": tol.describe(),
        "nulls_ignored": {"left": nulls[0], "right": nulls[1]},
    }
    if ok:
        return Outcome(Status.PASS, f"{agg} agrees at {actual:,.2f}", evidence)
    return Outcome(
        Status.FAIL,
        f"{agg} disagrees: {actual:,.2f} in data vs {claimed:,.2f} claimed "
        f"(delta {actual - claimed:+,.2f}, tolerance {tol.describe()})",
        evidence,
    )


@register("reconcile.sum")
def sum_check(store: SourceStore, params: dict[str, Any]) -> Outcome:
    # `agg:` deliberately not accepted here — reconcile.sum sums. If you want
    # another aggregate, say so with reconcile.aggregate; a parameter that
    # silently did nothing would be this tool lying about what it verified.
    return _aggregate(store, params, "reconcile.sum", "sum", agg_param=False)


@register("reconcile.aggregate")
def aggregate_check(store: SourceStore, params: dict[str, Any]) -> Outcome:
    agg = str(params.get("agg", "sum"))
    if agg not in _AGGS:
        raise SpecError(f"reconcile.aggregate: `agg` must be one of {', '.join(_AGGS)}.")
    return _aggregate(store, params, "reconcile.aggregate", agg, agg_param=True)


@register("reconcile.group_sum")
def group_sum(store: SourceStore, params: dict[str, Any]) -> Outcome:
    kind = "reconcile.group_sum"
    reject_unknown(params, ("left", "right", "column", "by", "tolerance"), kind)
    left = require(params, "left", kind)
    right = require(params, "right", kind)
    column = require(params, "column", kind)
    by = require(params, "by", kind)
    tol = parse_tolerance(params.get("tolerance"), FLOAT_EPS)

    frames: list[pd.Series] = []
    null_labels = {"left": 0, "right": 0}
    for label, side in (("left", left), ("right", right)):
        side_kind, resolved = store.resolve_side(side, context=f"{kind}.{label}")
        if side_kind != "frame":
            raise SpecError(f"{kind}: both sides must be tables.")
        if by not in resolved.columns:
            raise SourceError(
                f"{kind}: group column {by!r} not on the {label} side. "
                f"Columns are: {', '.join(map(str, resolved.columns))}"
            )
        series = numeric_series(resolved, column, label)
        labels, nulls = group_labels(resolved[by])
        null_labels[label] = nulls
        frames.append(series.groupby(labels).sum())

    left_g, right_g = frames
    merged = pd.concat([left_g, right_g], axis=1, keys=["left", "right"])

    only_left = merged.index[merged["right"].isna()].tolist()
    only_right = merged.index[merged["left"].isna()].tolist()
    both = merged.dropna()
    mismatched = [
        {
            "group": idx,
            "left": round(float(row["left"]), 6),
            "right": round(float(row["right"]), 6),
            "delta": round(float(row["left"] - row["right"]), 6),
        }
        for idx, row in both.iterrows()
        if not tol.allows(float(row["left"]), float(row["right"]))
    ]

    evidence = {
        "column": column,
        "by": by,
        "groups_compared": int(len(both)),
        "tolerance": tol.describe(),
        "mismatched": sample(mismatched),
        "mismatched_count": len(mismatched),
        "only_in_left": sample(only_left),
        "only_in_left_count": len(only_left),
        "only_in_right": sample(only_right),
        "only_in_right_count": len(only_right),
        "null_group_labels": null_labels,
    }
    problems = len(mismatched) + len(only_left) + len(only_right)
    if problems == 0:
        return Outcome(
            Status.PASS, f"all {len(both)} groups reconcile on {column}", evidence
        )
    parts = []
    if mismatched:
        parts.append(f"{len(mismatched)} group(s) off beyond {tol.describe()}")
    if only_left:
        parts.append(f"{len(only_left)} group(s) missing from the claim")
    if only_right:
        parts.append(f"{len(only_right)} claimed group(s) not in the data")
    return Outcome(Status.FAIL, "; ".join(parts), evidence)


@register("reconcile.keys")
def keys(store: SourceStore, params: dict[str, Any]) -> Outcome:
    kind = "reconcile.keys"
    reject_unknown(params, ("left", "right", "column", "mode"), kind)
    left = require(params, "left", kind)
    right = require(params, "right", kind)
    column = require(params, "column", kind)
    mode = str(params.get("mode", "equal"))
    if mode not in ("equal", "subset"):
        raise SpecError(
            f"{kind}: `mode` must be 'equal' or 'subset' (subset: every right key exists in left)."
        )

    sets: list[set[str]] = []
    for label, side in (("left", left), ("right", right)):
        side_kind, resolved = store.resolve_side(side, context=f"{kind}.{label}")
        if side_kind != "frame":
            raise SpecError(f"{kind}: both sides must be tables.")
        if column not in resolved.columns:
            raise SourceError(
                f"{kind}: key column {column!r} not on the {label} side. "
                f"Columns are: {', '.join(map(str, resolved.columns))}"
            )
        sets.append(set(resolved[column].dropna().astype(str)))

    left_keys, right_keys = sets
    only_left = sorted(left_keys - right_keys)
    only_right = sorted(right_keys - left_keys)

    evidence = {
        "column": column,
        "mode": mode,
        "left_unique": len(left_keys),
        "right_unique": len(right_keys),
        "only_in_left_count": len(only_left),
        "only_in_left": sample(only_left),
        "only_in_right_count": len(only_right),
        "only_in_right": sample(only_right),
    }
    if mode == "subset":
        if not only_right:
            return Outcome(
                Status.PASS,
                f"every claimed key exists in the data ({len(right_keys)} checked)",
                evidence,
            )
        return Outcome(
            Status.FAIL,
            f"{len(only_right)} claimed key(s) do not exist in the data",
            evidence,
        )
    if not only_left and not only_right:
        return Outcome(Status.PASS, f"key sets identical ({len(left_keys)} keys)", evidence)
    return Outcome(
        Status.FAIL,
        f"key sets differ: {len(only_left)} only in data, {len(only_right)} only in claim",
        evidence,
    )

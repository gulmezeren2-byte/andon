"""Plausibility checks: heuristics that may raise a flag, never a failure.

Everything in this module is registered with ``heuristic=True``, which means
the engine will not let it FAIL a run no matter what it returns. That is the
point: "the mean moved three sigmas" is a reason for a human to look, not
proof that the number is wrong. Quarter ends exist. Campaigns exist.

If you find yourself wanting one of these to fail the build, what you
actually want is a deterministic bound written into the spec — use
`plausibility.bounds` with explicit limits and treat REVIEW seriously, or
reconcile against source data instead.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from andon.checks import Outcome, register, reject_unknown, require, sample
from andon.errors import SourceError, SpecError
from andon.result import Status
from andon.sources import SourceStore


def _series(store: SourceStore, side: Any, column: str, kind: str, label: str) -> pd.Series:
    side_kind, resolved = store.resolve_side(side, context=f"{kind}.{label}")
    if side_kind != "frame":
        raise SpecError(f"{kind}: the {label} side must be a table.")
    if column not in resolved.columns:
        raise SourceError(
            f"{kind}: column {column!r} not on the {label} side. "
            f"Columns are: {', '.join(map(str, resolved.columns))}"
        )
    return resolved[column]


@register("plausibility.bounds", heuristic=True)
def bounds(store: SourceStore, params: dict[str, Any]) -> Outcome:
    kind = "plausibility.bounds"
    reject_unknown(params, ("source", "column", "min", "max", "where"), kind)
    alias = require(params, "source", kind)
    column = require(params, "column", kind)
    lo = params.get("min")
    hi = params.get("max")
    if lo is None and hi is None:
        raise SpecError(f"{kind}: provide `min`, `max` or both.")

    df = store.frame(alias, params.get("where"))
    if column not in df.columns:
        raise SourceError(f"{kind}: column {column!r} not found.")
    raw = df[column]
    coerced = pd.to_numeric(raw, errors="coerce")
    non_numeric = int(coerced.isna().sum() - raw.isna().sum())
    series = coerced.dropna()

    below = series[series < lo] if lo is not None else series.iloc[0:0]
    above = series[series > hi] if hi is not None else series.iloc[0:0]
    n_bad = int(len(below) + len(above))

    evidence = {
        "column": column,
        "min": lo,
        "max": hi,
        "values_checked": int(len(series)),
        "non_numeric_ignored": non_numeric,
        "below_min": int(len(below)),
        "above_max": int(len(above)),
        "sample_out_of_bounds": sample(
            [round(float(v), 4) for v in pd.concat([below, above]).head(10)]
        ),
    }
    if lo is not None and hi is not None:
        bounds_text = f"outside [{lo}, {hi}]"
    elif lo is not None:
        bounds_text = f"below {lo}"
    else:
        bounds_text = f"above {hi}"

    if n_bad == 0:
        return Outcome(Status.PASS, f"{column} stays within bounds", evidence)
    return Outcome(
        Status.REVIEW,
        f"{n_bad} value(s) of {column} fall {bounds_text}; look before you trust",
        evidence,
    )


@register("plausibility.new_categories", heuristic=True)
def new_categories(store: SourceStore, params: dict[str, Any]) -> Outcome:
    kind = "plausibility.new_categories"
    reject_unknown(params, ("column", "left", "right"), kind)
    column = require(params, "column", kind)
    base = _series(store, require(params, "left", kind), column, kind, "left")
    candidate = _series(store, require(params, "right", kind), column, kind, "right")

    known = set(base.dropna().astype(str))
    seen = set(candidate.dropna().astype(str))
    novel = sorted(seen - known)

    evidence = {
        "column": column,
        "known_categories": len(known),
        "new_categories": novel[:20],
        "new_count": len(novel),
    }
    if not novel:
        return Outcome(Status.PASS, f"no unseen categories in {column}", evidence)
    return Outcome(
        Status.REVIEW,
        f"{len(novel)} category value(s) in {column} never seen in the baseline "
        f"(first: {novel[0]!r})",
        evidence,
    )


@register("plausibility.mean_shift", heuristic=True)
def mean_shift(store: SourceStore, params: dict[str, Any]) -> Outcome:
    kind = "plausibility.mean_shift"
    reject_unknown(params, ("column", "left", "right", "max_sigmas"), kind)
    column = require(params, "column", kind)
    try:
        max_sigmas = float(params.get("max_sigmas", 3.0))
    except (TypeError, ValueError) as exc:
        raise SpecError(f"{kind}: `max_sigmas` must be a number.") from exc
    if max_sigmas <= 0:
        raise SpecError(f"{kind}: `max_sigmas` must be positive.")

    base = pd.to_numeric(
        _series(store, require(params, "left", kind), column, kind, "left"), errors="coerce"
    ).dropna()
    candidate = pd.to_numeric(
        _series(store, require(params, "right", kind), column, kind, "right"), errors="coerce"
    ).dropna()
    if base.empty or candidate.empty:
        raise SourceError(f"{kind}: one of the sides has no numeric data in {column!r}.")

    base_mean = float(base.mean())
    base_std = float(base.std(ddof=0))
    cand_mean = float(candidate.mean())
    shift = abs(cand_mean - base_mean)
    sigmas = shift / base_std if base_std > 0 else float("inf") if shift > 0 else 0.0

    evidence = {
        "column": column,
        "baseline_mean": round(base_mean, 6),
        "baseline_std": round(base_std, 6),
        "candidate_mean": round(cand_mean, 6),
        "shift_sigmas": round(sigmas, 3) if sigmas != float("inf") else "inf",
        "max_sigmas": max_sigmas,
    }
    if sigmas <= max_sigmas:
        return Outcome(
            Status.PASS,
            f"mean of {column} within {max_sigmas} sigma of baseline",
            evidence,
        )
    return Outcome(
        Status.REVIEW,
        f"mean of {column} moved {evidence['shift_sigmas']} sigma against baseline; "
        f"plausible, but somebody should know why",
        evidence,
    )

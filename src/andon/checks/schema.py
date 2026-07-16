"""Schema and contract checks: is the data shaped the way everyone assumes?

These are deliberately unexciting. They exist because every reconciliation
mistake I have ever chased in a real operation eventually traced back to an
assumption nobody had written down: an order id that was "obviously" unique,
a status column that "only" had four values, a week that "couldn't" be
missing. Write the assumption down; let the machine hold it.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from andon.checks import Outcome, register, reject_unknown, require, sample
from andon.errors import SourceError, SpecError
from andon.result import Status
from andon.sources import SourceStore


def _columns_param(params: dict[str, Any], kind: str) -> list[str]:
    if params.get("column") is not None and params.get("columns") is not None:
        raise SpecError(f"{kind}: give `column` or `columns`, not both.")
    raw = params.get("columns") or params.get("column")
    if raw is None:
        raise SpecError(f"{kind}: missing `column` (or `columns`).")
    if isinstance(raw, str):
        return [raw]
    if isinstance(raw, list) and all(isinstance(c, str) for c in raw):
        return raw
    raise SpecError(f"{kind}: `columns` must be a string or a list of strings.")


def _need_columns(df: pd.DataFrame, cols: list[str], kind: str) -> None:
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise SourceError(
            f"{kind}: column(s) not found: {', '.join(missing)}. "
            f"Columns are: {', '.join(map(str, df.columns))}"
        )


@register("schema.columns")
def columns(store: SourceStore, params: dict[str, Any]) -> Outcome:
    kind = "schema.columns"
    reject_unknown(params, ("source", "required", "forbid_extra", "where"), kind)
    alias = require(params, "source", kind)
    required = require(params, "required", kind)
    if not isinstance(required, list) or not all(isinstance(c, str) for c in required):
        raise SpecError(f"{kind}: `required` must be a list of column names.")
    forbid_extra = bool(params.get("forbid_extra", False))

    df = store.frame(alias, params.get("where"))
    have = [str(c) for c in df.columns]
    missing = [c for c in required if c not in have]
    extra = [c for c in have if c not in required]

    evidence = {
        "required": required,
        "present": have,
        "missing": missing,
        "extra": extra if forbid_extra else sample(extra),
    }
    if missing:
        return Outcome(Status.FAIL, f"missing column(s): {', '.join(missing)}", evidence)
    if forbid_extra and extra:
        return Outcome(Status.FAIL, f"unexpected column(s): {', '.join(extra)}", evidence)
    return Outcome(Status.PASS, f"all {len(required)} required columns present", evidence)


@register("schema.unique")
def unique(store: SourceStore, params: dict[str, Any]) -> Outcome:
    kind = "schema.unique"
    reject_unknown(params, ("source", "column", "columns", "where"), kind)
    alias = require(params, "source", kind)
    cols = _columns_param(params, kind)

    df = store.frame(alias, params.get("where"))
    _need_columns(df, cols, kind)
    dup_mask = df.duplicated(subset=cols, keep=False)
    if dup_mask.any():
        dupes = df.loc[dup_mask, cols].astype(str).agg(" / ".join, axis=1)
        duplicate_keys = sample(sorted(dupes.unique().tolist()))
    else:
        duplicate_keys = []

    evidence = {
        "key": cols,
        "rows": int(len(df)),
        "duplicate_rows": int(dup_mask.sum()),
        "duplicate_keys": duplicate_keys,
    }
    if not dup_mask.any():
        return Outcome(
            Status.PASS, f"{' + '.join(cols)} unique across {len(df)} rows", evidence
        )
    return Outcome(
        Status.FAIL,
        f"{int(dup_mask.sum())} row(s) share a supposedly unique key {' + '.join(cols)}",
        evidence,
    )


@register("schema.not_null")
def not_null(store: SourceStore, params: dict[str, Any]) -> Outcome:
    kind = "schema.not_null"
    reject_unknown(params, ("source", "column", "columns", "where"), kind)
    alias = require(params, "source", kind)
    cols = _columns_param(params, kind)

    df = store.frame(alias, params.get("where"))
    _need_columns(df, cols, kind)
    null_counts = {c: int(df[c].isna().sum()) for c in cols}
    bad = {c: n for c, n in null_counts.items() if n}

    evidence = {"rows": int(len(df)), "null_counts": null_counts}
    if not bad:
        return Outcome(Status.PASS, f"no nulls in {', '.join(cols)}", evidence)
    worst = ", ".join(f"{c} ({n})" for c, n in bad.items())
    return Outcome(Status.FAIL, f"null values found: {worst}", evidence)


@register("schema.allowed_values")
def allowed_values(store: SourceStore, params: dict[str, Any]) -> Outcome:
    kind = "schema.allowed_values"
    reject_unknown(params, ("source", "column", "allowed", "where"), kind)
    alias = require(params, "source", kind)
    column = require(params, "column", kind)
    allowed = require(params, "allowed", kind)
    if not isinstance(allowed, list) or not allowed:
        raise SpecError(f"{kind}: `allowed` must be a non-empty list.")

    df = store.frame(alias, params.get("where"))
    _need_columns(df, [column], kind)
    values = df[column].dropna().astype(str)
    allowed_set = {str(a) for a in allowed}
    outside = values[~values.isin(allowed_set)]

    evidence = {
        "column": column,
        "allowed": sorted(allowed_set),
        "rows": int(len(df)),
        "violations": int(len(outside)),
        "unexpected_values": sample(sorted(outside.unique().tolist())),
    }
    if outside.empty:
        return Outcome(Status.PASS, f"{column} stays within its allowed set", evidence)
    return Outcome(
        Status.FAIL,
        f"{len(outside)} row(s) carry values outside the allowed set for {column}",
        evidence,
    )


@register("schema.date_continuity")
def date_continuity(store: SourceStore, params: dict[str, Any]) -> Outcome:
    kind = "schema.date_continuity"
    reject_unknown(params, ("source", "column", "freq", "where"), kind)
    alias = require(params, "source", kind)
    column = require(params, "column", kind)
    freq = str(params.get("freq", "D"))

    df = store.frame(alias, params.get("where"))
    _need_columns(df, [column], kind)
    parsed = pd.to_datetime(df[column], errors="coerce")
    unparseable = int(parsed.isna().sum() - df[column].isna().sum())
    if unparseable:
        raise SourceError(
            f"{kind}: {unparseable} value(s) in {column!r} are not parseable dates."
        )
    parsed = parsed.dropna()
    if parsed.empty:
        raise SourceError(f"{kind}: {column!r} has no dates to check.")

    try:
        expected = pd.period_range(parsed.min(), parsed.max(), freq=freq)
    except ValueError as exc:
        raise SpecError(f"{kind}: bad `freq` {freq!r}: {exc}") from exc
    present = set(parsed.dt.to_period(freq))
    missing = [str(p) for p in expected if p not in present]

    evidence = {
        "column": column,
        "freq": freq,
        "from": str(parsed.min().date()),
        "to": str(parsed.max().date()),
        "periods_expected": int(len(expected)),
        "periods_missing": len(missing),
        "missing": sample(missing),
    }
    if not missing:
        return Outcome(
            Status.PASS,
            f"{column} covers all {len(expected)} {freq} periods without gaps",
            evidence,
        )
    return Outcome(
        Status.FAIL,
        f"{len(missing)} {freq} period(s) missing from {column} "
        f"(first: {missing[0]})",
        evidence,
    )

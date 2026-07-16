"""Check registry.

A check is a function `(store, params) -> Outcome` registered under a dotted
kind name (`reconcile.sum`). Adding a new check family means adding one module
to this package and importing it at the bottom of this file — nothing else in
the engine changes.

Two conventions every check must follow:

1. Unknown parameters are a SpecError. A misspelled `tolerence:` that
   silently falls back to the default would be a verification tool lying
   about what it verified.
2. The `heuristic` flag is honest. Checks registered with `heuristic=True`
   may return REVIEW at worst — the engine enforces that they never FAIL.
   That enforcement is what makes "only arithmetic can fail the build" a
   property of the system instead of a promise in the README.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from andon.errors import SourceError, SpecError
from andon.result import Status


@dataclass
class Outcome:
    status: Status
    summary: str
    evidence: dict[str, Any] = field(default_factory=dict)


CheckFn = Callable[..., Outcome]  # (store: SourceStore, params: dict) -> Outcome


@dataclass(frozen=True)
class _Entry:
    fn: CheckFn
    heuristic: bool


_REGISTRY: dict[str, _Entry] = {}


def register(kind: str, *, heuristic: bool = False) -> Callable[[CheckFn], CheckFn]:
    def wrap(fn: CheckFn) -> CheckFn:
        if kind in _REGISTRY:
            raise RuntimeError(f"Check kind registered twice: {kind}")
        _REGISTRY[kind] = _Entry(fn=fn, heuristic=heuristic)
        return fn

    return wrap


def get_check(kind: str) -> _Entry:
    return _REGISTRY[kind]


def registered_kinds() -> frozenset[str]:
    return frozenset(_REGISTRY)


# -- shared parameter helpers -------------------------------------------------


def require(params: dict[str, Any], key: str, kind: str) -> Any:
    if key not in params or params[key] is None:
        raise SpecError(f"{kind}: missing required parameter `{key}`.")
    return params[key]


def reject_unknown(params: dict[str, Any], allowed: Iterable[str], kind: str) -> None:
    extra = sorted(set(params) - set(allowed))
    if extra:
        raise SpecError(
            f"{kind}: unknown parameter(s) {', '.join(extra)}. "
            f"Allowed: {', '.join(sorted(allowed))}."
        )


def sample(items: Iterable[Any], limit: int = 10) -> list[Any]:
    """First N items for evidence lists. Evidence is proof, not a dump."""
    out: list[Any] = []
    for x in items:
        out.append(x)
        if len(out) >= limit:
            break
    return out


def numeric_series(df: pd.DataFrame, column: str, context: str) -> pd.Series:
    """A column as numbers, or an error. andon never coerces text to numbers:
    a corrupted cell must surface as ERROR, not vanish into a NaN that sum()
    happily skips."""
    if column not in df.columns:
        raise SourceError(
            f"{context}: column {column!r} not found. "
            f"Columns are: {', '.join(map(str, df.columns))}"
        )
    series = df[column]
    coerced = pd.to_numeric(series, errors="coerce")
    bad = int(coerced.isna().sum() - series.isna().sum())
    if bad:
        raise SourceError(
            f"{context}: column {column!r} has {bad} non-numeric value(s). "
            f"andon does not coerce text to numbers; clean the column or check it "
            f"with schema.allowed_values first."
        )
    return coerced


def group_labels(series: pd.Series) -> tuple[pd.Series, int]:
    """Group-key labels as strings, with nulls made explicit.

    pandas' groupby drops NaN keys by default, and `.astype(str)` does not
    reliably turn NaN into a string across pandas versions. A verifier that
    silently drops unlabeled rows would commit exactly the sin it exists to
    catch — so null labels become a visible "<null>" group and their count is
    returned for the evidence."""
    nulls = int(series.isna().sum())
    labels = series.map(lambda v: "<null>" if pd.isna(v) else str(v))
    return labels, nulls


# Import check families so registration runs. Order is alphabetical; nothing
# depends on it.
from andon.checks import (  # noqa: E402
    excel_integrity,  # noqa: F401
    internal,  # noqa: F401
    plausibility,  # noqa: F401
    reconcile,  # noqa: F401
    schema,  # noqa: F401
)

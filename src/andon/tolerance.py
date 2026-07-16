"""Tolerance parsing and comparison.

A tolerance in a spec is either absolute (`tolerance: 0.01`, in the unit of
the compared value) or relative (`tolerance: "0.5%"`, relative to the claimed
value). Every comparison in andon goes through this module, so the semantics
are in exactly one place:

* absolute:  |actual - claimed| <= value
* relative:  |actual - claimed| <= |claimed| * value

Relative tolerance against a claimed value of exactly zero would accept
nothing but zero, which is what you want: "within 0.5% of 0" is 0.
"""

from __future__ import annotations

from dataclasses import dataclass

from andon.errors import SpecError


@dataclass(frozen=True)
class Tolerance:
    kind: str  # "abs" | "rel"
    value: float

    def allows(self, actual: float, claimed: float) -> bool:
        delta = abs(actual - claimed)
        if self.kind == "abs":
            return delta <= self.value
        return delta <= abs(claimed) * self.value

    def describe(self) -> str:
        if self.kind == "abs":
            # Render integers without a trailing .0 so "0" reads as exact.
            v = int(self.value) if float(self.value).is_integer() else self.value
            return f"±{v}"
        return f"±{self.value * 100:g}%"


def parse_tolerance(raw: object, default: Tolerance) -> Tolerance:
    """Parse the `tolerance` field of a check. Missing → the check's default."""
    if raw is None:
        return default
    if isinstance(raw, bool):
        raise SpecError("`tolerance` must be a number or a percentage string.")
    if isinstance(raw, (int, float)):
        if raw < 0:
            raise SpecError("`tolerance` cannot be negative.")
        return Tolerance("abs", float(raw))
    if isinstance(raw, str):
        text = raw.strip()
        if text.endswith("%"):
            try:
                pct = float(text[:-1].strip())
            except ValueError as exc:
                raise SpecError(f"Cannot parse percentage tolerance: {raw!r}") from exc
            if pct < 0:
                raise SpecError("`tolerance` cannot be negative.")
            return Tolerance("rel", pct / 100.0)
        try:
            return Tolerance("abs", float(text))
        except ValueError as exc:
            raise SpecError(f"Cannot parse tolerance: {raw!r}") from exc
    raise SpecError(f"Cannot parse tolerance: {raw!r}")


EXACT = Tolerance("abs", 0.0)
FLOAT_EPS = Tolerance("abs", 1e-6)

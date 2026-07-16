import pytest

from andon.errors import SpecError
from andon.tolerance import EXACT, Tolerance, parse_tolerance


def test_default_used_when_missing() -> None:
    assert parse_tolerance(None, EXACT) is EXACT


def test_absolute_number() -> None:
    tol = parse_tolerance(0.5, EXACT)
    assert tol.kind == "abs"
    assert tol.allows(100.4, 100.0)
    assert not tol.allows(100.6, 100.0)


def test_percentage_string() -> None:
    tol = parse_tolerance("0.5%", EXACT)
    assert tol.kind == "rel"
    assert tol.allows(100.4, 100.0)
    assert not tol.allows(100.6, 100.0)


def test_relative_against_zero_accepts_only_zero() -> None:
    tol = Tolerance("rel", 0.05)
    assert tol.allows(0.0, 0.0)
    assert not tol.allows(0.0001, 0.0)


def test_numeric_string_is_absolute() -> None:
    tol = parse_tolerance("2", EXACT)
    assert tol.kind == "abs"
    assert tol.value == 2.0


@pytest.mark.parametrize("bad", [-1, "-2%", "abc", True, [1]])
def test_bad_tolerances_rejected(bad: object) -> None:
    with pytest.raises(SpecError):
        parse_tolerance(bad, EXACT)


def test_describe_reads_naturally() -> None:
    assert Tolerance("abs", 0.0).describe() == "±0"
    assert Tolerance("abs", 0.01).describe() == "±0.01"
    assert Tolerance("rel", 0.005).describe() == "±0.5%"

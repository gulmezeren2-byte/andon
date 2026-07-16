from pathlib import Path

import pytest

from andon.errors import SpecError
from andon.spec import Spec, load_spec

BASE = Path(".")


def make(checks: list, sources: dict | None = None) -> Spec:
    return Spec.from_dict(
        {"version": 1, "sources": sources or {"x": "x.csv"}, "checks": checks}, base_dir=BASE
    )


def test_minimal_spec_parses() -> None:
    spec = make([{"schema.unique": {"source": "x", "column": "id"}}])
    assert spec.checks[0].kind == "schema.unique"
    assert spec.checks[0].check_id == "c01"
    assert spec.checks[0].name == "schema.unique"


def test_version_is_mandatory() -> None:
    with pytest.raises(SpecError, match="version"):
        Spec.from_dict({"sources": {}, "checks": [{}]}, base_dir=BASE)


def test_unknown_kind_gets_a_hint() -> None:
    with pytest.raises(SpecError, match="reconcile.row_count"):
        make([{"reconcile.rowcount": {}}])


def test_two_kinds_in_one_entry_rejected() -> None:
    with pytest.raises(SpecError, match="exactly one"):
        make([{"schema.unique": {}, "schema.not_null": {}}])


def test_entry_with_only_reserved_keys_rejected() -> None:
    with pytest.raises(SpecError, match="exactly one"):
        make([{"name": "does nothing"}])


def test_duplicate_ids_rejected() -> None:
    with pytest.raises(SpecError, match="Duplicate check id"):
        make(
            [
                {"id": "same", "schema.unique": {"source": "x", "column": "id"}},
                {"id": "same", "schema.not_null": {"source": "x", "column": "id"}},
            ]
        )


def test_skip_accepts_reason_string() -> None:
    spec = make([{"skip": "waiting for data", "schema.unique": {"source": "x", "column": "id"}}])
    assert spec.checks[0].skip == "waiting for data"


def test_checks_must_be_nonempty() -> None:
    with pytest.raises(SpecError, match="non-empty"):
        Spec.from_dict({"version": 1, "sources": {}, "checks": []}, base_dir=BASE)


def test_load_spec_missing_file() -> None:
    with pytest.raises(SpecError, match="not found"):
        load_spec("does/not/exist.yaml")


def test_load_spec_resolves_base_dir(tmp_path: Path) -> None:
    spec_file = tmp_path / "sub" / "andon.yaml"
    spec_file.parent.mkdir()
    spec_file.write_text(
        "version: 1\nsources: {x: data.csv}\n"
        "checks:\n  - schema.unique: {source: x, column: id}\n",
        encoding="utf-8",
    )
    spec = load_spec(spec_file)
    assert spec.base_dir == spec_file.parent.resolve()

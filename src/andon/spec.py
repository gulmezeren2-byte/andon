"""Spec model: the verification contract.

A spec is a YAML file. It names data sources and lists checks against them:

    version: 1

    sources:
      orders: data/orders.csv
      report: out/weekly.xlsx#Summary
      sales:                       # a mapping carries CSV read options
        path: data/sales.csv
        encoding: cp1254           # default utf-8-sig (reads utf-8 + BOM)
        delimiter: ";"             # default ","

    checks:
      - name: no dropped orders
        reconcile.row_count:
          left:  { source: orders, where: "status != 'cancelled'" }
          right: { source: report, cell: B4 }

Design decisions worth knowing:

* Each check entry carries exactly one check kind (``reconcile.row_count``
  above). ``name``, ``id`` and ``skip`` are the only other keys allowed, so a
  typo in a kind name is a hard SpecError, never a silently ignored check.
* Relative paths resolve against the *spec file's directory*, not the current
  working directory. A spec should mean the same thing no matter where you
  run it from.
* Specs are code. Review them like code: a ``where`` filter can hide as many
  sins as a SQL query can.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from andon.checks import registered_kinds
from andon.errors import SpecError

SUPPORTED_VERSIONS = (1,)
RESERVED_KEYS = {"name", "id", "skip"}


@dataclass
class CheckSpec:
    check_id: str
    kind: str
    params: dict[str, Any]
    name: str
    skip: bool | str = False


@dataclass
class Spec:
    version: int
    base_dir: Path
    sources: dict[str, Any] = field(default_factory=dict)
    checks: list[CheckSpec] = field(default_factory=list)
    path: str = "<memory>"

    @classmethod
    def from_dict(cls, data: dict[str, Any], base_dir: Path, path: str = "<memory>") -> Spec:
        if not isinstance(data, dict):
            raise SpecError("Spec root must be a mapping.")

        version = data.get("version")
        if version not in SUPPORTED_VERSIONS:
            raise SpecError(
                f"Unsupported or missing spec version: {version!r}. "
                f"This build of andon supports: {', '.join(map(str, SUPPORTED_VERSIONS))}."
            )

        raw_sources = data.get("sources", {})
        if not isinstance(raw_sources, dict) or not all(
            isinstance(k, str) and isinstance(v, (str, dict)) for k, v in raw_sources.items()
        ):
            raise SpecError(
                "`sources` must map alias names to a path string, or to a mapping "
                "with a `path:` plus CSV options (encoding, delimiter)."
            )

        raw_checks = data.get("checks")
        if not isinstance(raw_checks, list) or not raw_checks:
            raise SpecError("`checks` must be a non-empty list.")

        known = registered_kinds()
        checks: list[CheckSpec] = []
        for i, entry in enumerate(raw_checks, start=1):
            checks.append(_parse_check(entry, i, known))

        seen: set[str] = set()
        for c in checks:
            if c.check_id in seen:
                raise SpecError(f"Duplicate check id: {c.check_id!r}.")
            seen.add(c.check_id)

        return cls(
            version=version,
            base_dir=base_dir,
            sources=dict(raw_sources),
            checks=checks,
            path=path,
        )


def _parse_check(entry: Any, index: int, known: frozenset[str]) -> CheckSpec:
    where = f"checks[{index}]"
    if not isinstance(entry, dict):
        raise SpecError(f"{where}: each check must be a mapping.")

    kind_keys = [k for k in entry if k not in RESERVED_KEYS]
    if len(kind_keys) != 1:
        raise SpecError(
            f"{where}: expected exactly one check kind per entry, "
            f"got {kind_keys or 'none'}. Reserved keys are: {sorted(RESERVED_KEYS)}."
        )

    kind = kind_keys[0]
    if kind not in known:
        hint = _closest(kind, known)
        raise SpecError(
            f"{where}: unknown check kind {kind!r}."
            + (f" Did you mean {hint!r}?" if hint else "")
            + f" Known kinds: {', '.join(sorted(known))}."
        )

    params = entry[kind]
    if params is None:
        params = {}
    if not isinstance(params, dict):
        raise SpecError(f"{where}: parameters for {kind!r} must be a mapping.")

    name = entry.get("name") or kind
    check_id = str(entry.get("id") or f"c{index:02d}")
    skip = entry.get("skip", False)
    if not isinstance(skip, (bool, str)):
        raise SpecError(f"{where}: `skip` must be true/false or a reason string.")

    return CheckSpec(check_id=check_id, kind=kind, params=params, name=str(name), skip=skip)


def _closest(kind: str, known: frozenset[str]) -> str | None:
    """Cheap typo hint: same family, or same tail."""
    family = kind.split(".", 1)[0]
    same_family = sorted(k for k in known if k.startswith(family + "."))
    if same_family:
        return same_family[0]
    tail = kind.rsplit(".", 1)[-1]
    same_tail = sorted(k for k in known if k.endswith("." + tail))
    return same_tail[0] if same_tail else None


def load_spec(path: str | Path) -> Spec:
    p = Path(path)
    if not p.is_file():
        raise SpecError(f"Spec file not found: {p}")
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise SpecError(f"Spec is not valid YAML: {exc}") from exc
    return Spec.from_dict(data, base_dir=p.parent.resolve(), path=str(p))

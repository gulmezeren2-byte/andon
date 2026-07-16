"""Result model: what a verification run produces.

The design rule that matters here: a result must carry its own evidence.
"FAIL" without the two numbers that disagree is an accusation, not a finding.
Every CheckResult therefore has an `evidence` dict with the actual values,
deltas and tolerances involved, and the renderer never invents anything that
is not in that dict.
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Status(str, Enum):
    """Outcome of a single check.

    PASS    the assertion held, within its declared tolerance.
    FAIL    the assertion did not hold. Only deterministic checks may FAIL.
    REVIEW  a heuristic raised a flag. A human should look; the build may not
            treat this as failure unless run with --strict.
    SKIP    the check was disabled in the spec.
    ERROR   the check could not run (missing file, bad range). Not a pass.
    """

    PASS = "pass"
    FAIL = "fail"
    REVIEW = "review"
    SKIP = "skip"
    ERROR = "error"


@dataclass
class CheckResult:
    check_id: str
    kind: str
    name: str
    status: Status
    summary: str
    evidence: dict[str, Any] = field(default_factory=dict)
    duration_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.check_id,
            "kind": self.kind,
            "name": self.name,
            "status": self.status.value,
            "summary": self.summary,
            "evidence": self.evidence,
            "duration_ms": round(self.duration_ms, 2),
        }


@dataclass
class SourceInfo:
    """What andon actually read, recorded for the honesty block."""

    alias: str
    path: str
    kind: str  # csv | excel | parquet
    detail: str = ""  # sheet/range if any
    rows: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "alias": self.alias,
            "path": self.path,
            "kind": self.kind,
            "detail": self.detail,
            "rows": self.rows,
        }


@dataclass
class Report:
    spec_path: str
    results: list[CheckResult] = field(default_factory=list)
    sources: list[SourceInfo] = field(default_factory=list)
    not_checked: list[str] = field(default_factory=list)
    started_at: str = ""
    finished_at: str = ""
    andon_version: str = ""

    # -- aggregation ------------------------------------------------------

    def count(self, status: Status) -> int:
        return sum(1 for r in self.results if r.status is status)

    @property
    def verdict(self) -> str:
        """One word for the whole run. FAIL beats ERROR beats REVIEW beats PASS.

        A run where nothing actually executed (no checks, or every check
        skipped) is EMPTY, not PASS: zero verifications is not a clean bill of
        health, however green it might feel."""
        if self.count(Status.FAIL):
            return "FAIL"
        if self.count(Status.ERROR):
            return "INCOMPLETE"
        if self.count(Status.REVIEW):
            return "REVIEW"
        if self.count(Status.PASS) == 0:
            return "EMPTY"
        return "PASS"

    def exit_code(self, strict: bool = False) -> int:
        """Exit codes are part of the public contract (documented in README):

        0  every check passed
        1  at least one FAIL (or, with strict=True, any REVIEW/ERROR)
        2  no failures, but at least one REVIEW flag
        3  no failures, but nothing was verified either — a check could not
           run, or every check was skipped
        """
        if self.count(Status.FAIL):
            return 1
        if self.count(Status.ERROR):
            return 1 if strict else 3
        if self.count(Status.REVIEW):
            return 1 if strict else 2
        if self.count(Status.PASS) == 0:  # nothing ran: silence is not a blessing
            return 1 if strict else 3
        return 0

    # -- serialization -----------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "andon_version": self.andon_version,
            "spec": self.spec_path,
            "verdict": self.verdict,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "counts": {s.value: self.count(s) for s in Status},
            "checks": [r.to_dict() for r in self.results],
            "sources": [s.to_dict() for s in self.sources],
            "not_checked": self.not_checked,
        }


def utcnow() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

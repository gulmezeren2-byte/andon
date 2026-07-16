"""The engine: run every check, survive every check, hide nothing.

Failure isolation is the design decision here. A verifier that crashes on
check 3 of 12 verifies nothing — so each check runs in its own try/except,
and anything that goes wrong becomes an ERROR *finding* with the exception
text as evidence. ERROR is not PASS: it exits non-zero (code 3) because "I
could not verify this" must never be readable as "this is fine".
"""

from __future__ import annotations

import time
from pathlib import Path

import andon
from andon.checks import get_check
from andon.errors import AndonError
from andon.result import CheckResult, Report, Status, utcnow
from andon.sources import SourceStore
from andon.spec import Spec, load_spec


def run(spec: Spec | str | Path) -> Report:
    if not isinstance(spec, Spec):
        spec = load_spec(spec)

    store = SourceStore(spec.base_dir, spec.sources)
    report = Report(
        spec_path=spec.path,
        started_at=utcnow(),
        andon_version=andon.__version__,
    )

    for check in spec.checks:
        if check.skip:
            reason = check.skip if isinstance(check.skip, str) else "skipped in spec"
            report.results.append(
                CheckResult(
                    check_id=check.check_id,
                    kind=check.kind,
                    name=check.name,
                    status=Status.SKIP,
                    summary=reason,
                )
            )
            continue

        entry = get_check(check.kind)
        started = time.perf_counter()
        try:
            outcome = entry.fn(store, check.params)
        except AndonError as exc:
            outcome = None
            result = CheckResult(
                check_id=check.check_id,
                kind=check.kind,
                name=check.name,
                status=Status.ERROR,
                summary=str(exc),
                evidence={"error": type(exc).__name__},
            )
        except Exception as exc:  # a bug in andon or a truly hostile file —
            outcome = None  # either way the run must finish and say so.
            result = CheckResult(
                check_id=check.check_id,
                kind=check.kind,
                name=check.name,
                status=Status.ERROR,
                summary=f"unexpected {type(exc).__name__}: {exc}",
                evidence={"error": type(exc).__name__, "unexpected": True},
            )
        if outcome is not None:
            if entry.heuristic and outcome.status is Status.FAIL:
                # The registry contract says heuristics cannot fail a run.
                # Enforce it even against a buggy check, and say so out loud.
                outcome.status = Status.REVIEW
                outcome.evidence["downgraded"] = (
                    "this check is heuristic; FAIL was downgraded to REVIEW"
                )
            result = CheckResult(
                check_id=check.check_id,
                kind=check.kind,
                name=check.name,
                status=outcome.status,
                summary=outcome.summary,
                evidence=outcome.evidence,
            )
        result.duration_ms = (time.perf_counter() - started) * 1000
        report.results.append(result)

    report.sources = store.infos()
    report.not_checked = store.unreferenced_sheets()
    report.finished_at = utcnow()
    return report

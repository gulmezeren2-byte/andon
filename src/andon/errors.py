"""Errors raised by andon.

Two rules govern error handling in this codebase:

1. A broken *spec* is the user's problem and should fail fast, loudly and
   before any check runs (`SpecError`).
2. A broken *check at runtime* (missing file, unreadable range) is a finding,
   not a crash: the engine catches it and records the check with status ERROR.
   Only `SourceError` and unexpected exceptions are handled that way — a bug
   in andon itself should still surface as a bug.
"""


class AndonError(Exception):
    """Base class for all andon errors."""


class SpecError(AndonError):
    """The verification spec is invalid (bad YAML, unknown check, bad reference)."""


class SourceError(AndonError):
    """A data source could not be read the way the spec describes it."""

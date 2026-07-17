"""andon — deterministic verification for AI-generated analysis.

The public API is intentionally small:

    import andon

    report = andon.run("andon.yaml")
    if report.exit_code() != 0:
        ...

Everything else (check implementations, source loaders) is internal and may
change between minor versions.
"""

from importlib.metadata import PackageNotFoundError, version

from andon.engine import run
from andon.result import CheckResult, Report, Status
from andon.spec import Spec, load_spec

try:
    # Single source of truth: the installed distribution's version, so
    # `andon --version` can never drift from pyproject.toml.
    __version__ = version("andon-verify")
except PackageNotFoundError:  # pragma: no cover - running from a source tree
    __version__ = "0.0.0+unknown"

__all__ = [
    "run",
    "load_spec",
    "Spec",
    "Report",
    "CheckResult",
    "Status",
    "__version__",
]

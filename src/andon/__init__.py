"""andon — deterministic verification for AI-generated analysis.

The public API is intentionally small:

    import andon

    report = andon.run("andon.yaml")
    if report.exit_code() != 0:
        ...

Everything else (check implementations, source loaders) is internal and may
change between minor versions.
"""

from andon.engine import run
from andon.result import CheckResult, Report, Status
from andon.spec import Spec, load_spec

__version__ = "0.1.0"

__all__ = [
    "run",
    "load_spec",
    "Spec",
    "Report",
    "CheckResult",
    "Status",
    "__version__",
]

"""JULI: a local-first crew of AI agents that builds software."""

import sys

__version__ = "0.2.0"

# pip refuses a new install on an older Python, but an environment made before
# 3.10 was dropped still starts: say what to do instead of failing on an import.
if sys.version_info < (3, 11):  # noqa: UP036 - the check is for interpreters below the supported floor
    raise SystemExit(
        f"JULI needs Python 3.11 or later, and this environment runs Python {sys.version_info[0]}.{sys.version_info[1]}. "
        'Install a newer Python, then recreate the virtual environment (.venv) with it and install JULI again: see "Get started" in the README.'
    )

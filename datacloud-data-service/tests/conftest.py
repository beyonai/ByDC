"""Pytest configuration. Ensures sqlparse is available for tests."""
from __future__ import annotations

import sys
from pathlib import Path

# Add tmp_sqlparse to path if sqlparse is not installed (e.g. when running without [sql] extra)
try:
    import sqlparse  # noqa: F401
except ImportError:
    _tmp_sqlparse = Path(__file__).resolve().parent.parent / "tmp_sqlparse"
    if _tmp_sqlparse.exists():
        sys.path.insert(0, str(_tmp_sqlparse))

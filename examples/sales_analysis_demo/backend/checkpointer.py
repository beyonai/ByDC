"""langgraph dev checkpointer entry point for sales-analysis-agent.

The OpenGauss-compatible implementation lives in the core engine:
    src/datacloud_analysis/session/pg_opengauss.py

langgraph.json references this file as:
    "checkpointer": {"backend": "custom", "path": "./checkpointer.py:get_checkpointer"}

Note: the source path contains a hyphen (datacloud-analysis) which Python cannot import
normally, so we use importlib — the same approach used by agent.py in this package.
"""

import importlib.util
import os
import sys

_pg_py_path = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        "../../../datacloud-analysis/src/datacloud_analysis/session/pg_opengauss.py",
    )
)
_spec = importlib.util.spec_from_file_location("_datacloud_pg_opengauss", _pg_py_path)
_mod = importlib.util.module_from_spec(_spec)
sys.modules["_datacloud_pg_opengauss"] = _mod
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]

get_checkpointer = _mod.get_checkpointer

__all__ = ["get_checkpointer"]

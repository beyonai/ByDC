"""Tools package — atomic capabilities exposed to the Agent (design §3.1 TOOLBOX).

Tool              Module          Design symbol
-------           ------          -------------
search_knowledge  knowledge       T_KNOW_SEARCH

File I/O tool ``read_file`` is registered directly in
``orchestration/execution/node.py`` and reads through the
``ResultFileStorage`` injected via ``InvocationContext``.

.. note::
    ``sbx_read_file``, ``sbx_write_file``, ``sbx_run_code`` from
    ``tools.sandbox`` are deprecated and no longer exported here.
"""

from .knowledge import search_knowledge

__all__ = [
    "search_knowledge",
]

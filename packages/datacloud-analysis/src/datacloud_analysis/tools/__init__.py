"""Tools package — atomic capabilities exposed to the Agent (design §3.1 TOOLBOX).

Tool              Module          Design symbol
-------           ------          -------------
search_knowledge  knowledge       T_KNOW_SEARCH

Memory tools (recall_memory, search_memory, read_memory) live in
``memory.tools`` to keep the memory package self-contained.

File I/O tools (read_file, write_file) are registered directly in
``orchestration/execution/node.py`` and delegate to the Gateway
``FileManager`` when ``gateway_context`` is available.

.. note::
    ``sbx_read_file``, ``sbx_write_file``, ``sbx_run_code`` from
    ``tools.sandbox`` are deprecated and no longer exported here.
"""

from .knowledge import search_knowledge

__all__ = [
    "search_knowledge",
]

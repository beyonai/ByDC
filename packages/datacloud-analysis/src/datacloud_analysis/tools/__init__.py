"""Tools package — atomic capabilities exposed to the Agent (design §3.1 TOOLBOX).

Tool              Module          Design symbol
-------           ------          -------------
search_knowledge  knowledge       T_KNOW_SEARCH
render_report     report          T_REPORT

Memory tools (recall_memory, search_memory, read_memory) live in
``memory.tools`` to keep the memory package self-contained.

File I/O tools (read_file, write_file) and code execution tools
(write_code, execute_code) are registered directly in
``orchestration/execution/node.py`` and delegate to the Gateway
``FileManager`` when ``gateway_context`` is available.

.. note::
    ``sbx_read_file``, ``sbx_write_file``, ``sbx_run_code`` from
    ``tools.sandbox`` are deprecated and no longer exported here.
"""

from .knowledge import search_knowledge
from .report import render_report

__all__ = [
    "search_knowledge",
    "render_report",
]

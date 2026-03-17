"""Tools package — atomic capabilities exposed to the Agent (design §3.1 TOOLBOX).

Tool          Module          Design symbol
-------       ------          -------------
search_knowledge  knowledge   T_KNOW_SEARCH
data_query        data        T_DATA_QUERY
sbx_run_code      sandbox     T_SBX_RUN
sbx_read_file     sandbox     T_SBX_READ
sbx_write_file    sandbox     T_SBX_WRITE
build_skill       skill       T_SKILL_BUILD
render_report     report      T_REPORT

Memory tools (recall_memory, search_memory, read_memory) live in
``memory.tools`` to keep the memory package self-contained.
"""

from .data import data_query
from .knowledge import search_knowledge
from .report import render_report
from .sandbox import sbx_read_file, sbx_run_code, sbx_write_file
from .skill import build_skill

__all__ = [
    "search_knowledge",
    "data_query",
    "sbx_run_code",
    "sbx_read_file",
    "sbx_write_file",
    "build_skill",
    "render_report",
]

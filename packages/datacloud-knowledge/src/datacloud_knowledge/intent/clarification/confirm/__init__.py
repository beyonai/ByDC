"""LLM 确认 — 基于召回结果，一次调用确认主结构 + complex_conditions 术语。

公共 API:
    - llm_confirm_structured  — legacy: 确认 StructuredQuery/Compute
    - llm_confirm_main         — 分治: 确认主结构术语
    - llm_confirm_cc           — 分治: 确认单条 complex_condition
    - format_recall_context    — 格式化召回上下文
    - format_main_confirm_context  — 格式化主结构确认上下文
    - format_cc_confirm_context    — 格式化 cc 确认上下文

内部模块:
    - _retry   — 重试逻辑、参数清洗
    - _context — 上下文格式化
    - _main    — llm_confirm_main / llm_confirm_structured
    - _cc      — llm_confirm_cc
"""

import time  # noqa: F401 — test backward compat (monkeypatch.setattr(confirm.time, ...))

from ._cc import llm_confirm_cc
from ._context import (
    format_cc_confirm_context,
    format_main_confirm_context,
    format_recall_context,
)

# Re-export internal symbols for backward compat (tests/eval scripts)
from ._main import (
    _save_test_case,  # noqa: F401
    llm_confirm_main,
    llm_confirm_structured,
)
from ._retry import (
    _invoke_confirm_with_retry,  # noqa: F401
    _is_retryable_confirm_error,  # noqa: F401
    _sanitize_confirm_args,  # noqa: F401
)

__all__ = [
    "format_cc_confirm_context",
    "format_main_confirm_context",
    "format_recall_context",
    "llm_confirm_cc",
    "llm_confirm_main",
    "llm_confirm_structured",
]

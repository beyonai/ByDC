"""LLM 主结构确认 — 一次调用确认主结构 + complex_conditions 术语。

包含 legacy llm_confirm_structured 和新分治 llm_confirm_main。
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

from datacloud_knowledge.i18n import get_confirm_prompt
from datacloud_knowledge.intent.clarification.models import (
    ConfirmedStructuredCompute,
    ConfirmedStructuredQuery,
    MainConfirmResult,
)

from ._context import _build_user_prompt
from ._retry import _invoke_confirm_with_retry, _sanitize_confirm_args

logger = logging.getLogger(__name__)


# ── 数据采集（DATACLOUD_COLLECT_CONFIRM_CASES=1 时启用）───────────────

_TEST_CASE_FILE = (
    Path(__file__).resolve().parents[5]
    / "scripts"
    / "manual"
    / "llm_confirm_test_cases.json"
)


def _save_test_case(
    case_input: dict[str, Any],
    result: ConfirmedStructuredQuery | ConfirmedStructuredCompute | None,
) -> None:
    """追加一条测试用例到 JSON 文件。采集失败不影响主流程。"""
    try:
        cases: list[dict[str, Any]] = []
        if _TEST_CASE_FILE.exists():
            cases = json.loads(_TEST_CASE_FILE.read_text("utf-8"))

        cases.append(
            {
                **case_input,
                "result": result.model_dump() if result is not None else None,
            }
        )

        _TEST_CASE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _TEST_CASE_FILE.write_text(
            json.dumps(cases, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        logger.info(
            "[confirm] 测试用例已保存: %s (共 %d 条)", _TEST_CASE_FILE.name, len(cases)
        )
    except Exception:
        logger.debug("[confirm] 测试用例保存失败，忽略", exc_info=True)


# ── Helper ───────────────────────────────────────────────────────────


def _check_needs_clarification(
    result: ConfirmedStructuredQuery | ConfirmedStructuredCompute,
) -> bool:
    """判断是否需要用户澄清。"""
    if result.clarify_items:
        return True
    for cc in result.confirmed_conditions:
        for tm in cc.term_mappings:
            if tm.confirmed is None and tm.candidates:
                return True
    return False


# ── Legacy 确认入口 ──────────────────────────────────────────────────


def llm_confirm_structured(
    *,
    query: str,
    structured_input: dict[str, Any],
    recall_context: str,
    mode: Literal["query", "compute"],
    language: str = "zh_CN",
    on_event: Callable[[Any], None] | None = None,
) -> ConfirmedStructuredQuery | ConfirmedStructuredCompute | None:
    """调用 LLM 确认结构化查询中的术语。

    Args:
        query: 用户原始查询。
        structured_input: StructuredQuery 或 StructuredCompute 的 dict。
        recall_context: 格式化的召回上下文。
        mode: "query" 或 "compute"。
        on_event: 可选回调。

    Returns:
        确认后的结构，LLM 失败时返回 None。
    """
    if not recall_context.strip():
        logger.info("[confirm] 召回结果为空，跳过 LLM 确认")
        return None

    _collecting = os.environ.get("DATACLOUD_COLLECT_CONFIRM_CASES") == "1"
    _collect_input: dict[str, Any] | None = None
    if _collecting:
        _collect_input = {
            "query": query,
            "structured_input": structured_input,
            "recall_context": recall_context,
            "mode": mode,
        }

    model_cls: type[ConfirmedStructuredQuery] | type[ConfirmedStructuredCompute] = (
        ConfirmedStructuredQuery if mode == "query" else ConfirmedStructuredCompute
    )

    user_prompt = _build_user_prompt(
        query, structured_input, recall_context, mode, language=language
    )
    logger.debug("[confirm] recall_context:\n%s", recall_context)

    try:
        from datacloud_knowledge.intent.llm_utils import (
            build_llm,
            extract_json_from_text,
            stream_invoke_with_thinking,
        )

        llm = build_llm()
        llm_with_tool = llm.bind_tools([model_cls])
        response = _invoke_confirm_with_retry(
            lambda: stream_invoke_with_thinking(
                llm_with_tool,
                [
                    {
                        "role": "system",
                        "content": get_confirm_prompt(language, "main_legacy"),
                    },
                    {"role": "user", "content": user_prompt},
                ],
                on_event=on_event,
            )
        )
        if response and response.tool_calls:
            args = response.tool_calls[0]["args"]
            _sanitize_confirm_args(args)
            logger.debug(
                "[confirm] LLM 确认完成: %s",
                json.dumps(args, ensure_ascii=False),
            )
            result = model_cls.model_validate(args)
            result.needs_clarification = _check_needs_clarification(result)
            if _collect_input is not None:
                _save_test_case(_collect_input, result)
            return result

        # 兜底：从 content 文本中提取 JSON
        raw_content = (
            response.content if hasattr(response, "content") else str(response)
        )
        content = (
            "\n".join(str(part) for part in raw_content)
            if isinstance(raw_content, list)
            else str(raw_content)
        )
        logger.warning("[confirm] LLM 未返回 tool call，尝试从文本提取 JSON")
        fallback = extract_json_from_text(content)
        if fallback is not None:
            result = model_cls.model_validate(fallback)
            result.needs_clarification = _check_needs_clarification(result)
            if _collect_input is not None:
                _save_test_case(_collect_input, result)
            return result
        logger.warning("[confirm] 兜底提取失败: %s", content[:200])
    except Exception:
        logger.exception("[confirm] LLM 确认失败")
    if _collect_input is not None:
        _save_test_case(_collect_input, None)
    return None


# ── 分治主确认 ───────────────────────────────────────────────────────


def llm_confirm_main(
    *,
    context: str,
    language: str = "zh_CN",
    on_event: Callable[[Any], None] | None = None,
) -> MainConfirmResult | None:
    """调用 LLM 确认主结构术语（编号模式）。

    Args:
        context: format_main_confirm_context 生成的上下文。
        language: 语言标识（"zh_CN" / "en_US"）。
        on_event: 可选回调。

    Returns:
        MainConfirmResult，LLM 失败时返回 None。
    """
    if not context.strip():
        logger.info("[confirm_main] context empty, skip")
        return None

    try:
        from datacloud_knowledge.intent.llm_utils import (
            build_llm,
            extract_json_from_text,
            stream_invoke_with_thinking,
        )

        llm = build_llm()
        llm_with_tool = llm.bind_tools([MainConfirmResult])
        response = _invoke_confirm_with_retry(
            lambda: stream_invoke_with_thinking(
                llm_with_tool,
                [
                    {"role": "system", "content": get_confirm_prompt(language, "main")},
                    {"role": "user", "content": context},
                ],
                on_event=on_event,
            )
        )
        if response and response.tool_calls:
            args = response.tool_calls[0]["args"]
            _sanitize_confirm_args(args)
            logger.debug(
                "[confirm_main] LLM 确认完成: %s",
                json.dumps(args, ensure_ascii=False)[:500],
            )
            result = MainConfirmResult.model_validate(args)
            result.needs_clarification = any(
                tc.confirmed is None and tc.candidates for tc in result.confirmations
            )
            return result

        raw_content = (
            response.content if hasattr(response, "content") else str(response)
        )
        content = (
            "\n".join(str(part) for part in raw_content)
            if isinstance(raw_content, list)
            else str(raw_content)
        )
        logger.warning("[confirm_main] LLM 未返回 tool call，尝试从文本提取")
        fallback = extract_json_from_text(content)
        if fallback is not None:
            result = MainConfirmResult.model_validate(fallback)
            result.needs_clarification = any(
                tc.confirmed is None and tc.candidates for tc in result.confirmations
            )
            return result
        logger.warning("[confirm_main] 兜底提取失败: %s", content[:200])
    except Exception:
        logger.exception("[confirm_main] LLM 确认失败")
    return None

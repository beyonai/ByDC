"""LLM complex_condition 确认 — 分治确认每条 complex_condition 的术语。"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

from datacloud_knowledge.i18n import get_confirm_prompt
from datacloud_knowledge.intent.clarification.models import CCConfirmResult

from ._retry import _invoke_confirm_with_retry, _sanitize_confirm_args

logger = logging.getLogger(__name__)


def llm_confirm_cc(
    *,
    context: str,
    language: str = "zh_CN",
    on_event: Callable[[Any], None] | None = None,
) -> CCConfirmResult | None:
    """调用 LLM 确认单条 complex_condition 术语（编号模式）。

    Args:
        context: format_cc_confirm_context 生成的上下文。
        language: 语言标识（"zh_CN" / "en_US"）。
        on_event: 可选回调。

    Returns:
        CCConfirmResult，LLM 失败时返回 None。
    """
    if not context.strip():
        logger.info("[confirm_cc] context empty, skip")
        return None

    try:
        from datacloud_knowledge.intent.llm_utils import (
            build_llm,
            extract_json_from_text,
            stream_invoke_with_thinking,
        )

        llm = build_llm()
        llm_with_tool = llm.bind_tools([CCConfirmResult])
        response = _invoke_confirm_with_retry(
            lambda: stream_invoke_with_thinking(
                llm_with_tool,
                [
                    {"role": "system", "content": get_confirm_prompt(language, "cc")},
                    {"role": "user", "content": context},
                ],
                on_event=on_event,
            )
        )
        if response and response.tool_calls:
            args = response.tool_calls[0]["args"]
            _sanitize_confirm_args(args)
            logger.debug(
                "[confirm_cc] LLM 确认完成: %s",
                json.dumps(args, ensure_ascii=False)[:500],
            )
            result = CCConfirmResult.model_validate(args)
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
        logger.warning("[confirm_cc] LLM 未返回 tool call，尝试从文本提取")
        fallback = extract_json_from_text(content)
        if fallback is not None:
            result = CCConfirmResult.model_validate(fallback)
            result.needs_clarification = any(
                tc.confirmed is None and tc.candidates for tc in result.confirmations
            )
            return result
        logger.warning("[confirm_cc] 兜底提取失败: %s", content[:200])
    except Exception:
        logger.exception("[confirm_cc] LLM 确认失败")
    return None

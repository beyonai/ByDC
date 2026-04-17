"""TC-PC-01 ~ TC-PC-07: Prompt Caching 兼容性测试。

覆盖目标（直接测试 _build_system_message 辅助函数）：
- TC-PC-01: provider=anthropic → content 为结构化列表，stable 块含 cache_control
- TC-PC-02: provider=anthropic，dynamic_prompt 为空 → 列表只有一个元素
- TC-PC-03: provider=anthropic，stable+dynamic 均有 → 列表有两个元素，第二块无 cache_control
- TC-PC-04: provider=openai → content 为纯字符串，无 cache_control
- TC-PC-05: provider 未配置（默认 openai）→ 同 TC-PC-04
- TC-PC-06: stable_system_prompt=None → 退回纯字符串（不论 provider）
- TC-PC-07: anthropic 路径，stable+dynamic 拼接等于原 system_prompt（内容完整性）
- TC-PC-08: openai 路径，SystemMessage 可被 ChatOpenAI 正常序列化，无未知字段
"""

from __future__ import annotations

import os
from unittest.mock import patch

from langchain_core.messages import SystemMessage

from datacloud_analysis.orchestration.execution.react_loop import _build_system_message

_STABLE = "你是一个数据分析助手。\n\n## 执行规则\n规则内容..."
_DYNAMIC = "\n\n## 当前会话信息\n- 当前时间：2026年04月17日 10:00"
_FULL = _STABLE + _DYNAMIC


# ===========================================================================
# TC-PC-01: provider=anthropic → 结构化列表 + stable 块含 cache_control
# ===========================================================================
def test_tc_pc01_anthropic_system_message_has_cache_control() -> None:
    with patch.dict(os.environ, {"DATACLOUD_LLM_MODEL_PROVIDER": "anthropic"}):
        msg = _build_system_message(_FULL, stable_system_prompt=_STABLE, dynamic_prompt=_DYNAMIC)

    assert isinstance(msg, SystemMessage)
    assert isinstance(msg.content, list), f"anthropic 路径 content 应为列表，实际为 {type(msg.content)}"
    first_block = msg.content[0]
    assert isinstance(first_block, dict)
    assert first_block.get("type") == "text"
    assert first_block.get("text") == _STABLE
    assert "cache_control" in first_block, "stable block 必须包含 cache_control"
    assert first_block["cache_control"] == {"type": "ephemeral"}


# ===========================================================================
# TC-PC-02: provider=anthropic，dynamic_prompt 为空 → 列表只有一个 block
# ===========================================================================
def test_tc_pc02_anthropic_no_dynamic_single_block() -> None:
    with patch.dict(os.environ, {"DATACLOUD_LLM_MODEL_PROVIDER": "anthropic"}):
        msg = _build_system_message(_STABLE, stable_system_prompt=_STABLE, dynamic_prompt="")

    assert isinstance(msg.content, list)
    assert len(msg.content) == 1, "无 dynamic_prompt 时应只有一个 block"
    assert msg.content[0]["cache_control"] == {"type": "ephemeral"}


# ===========================================================================
# TC-PC-03: provider=anthropic，stable+dynamic 均有 → 两个 block，第二块无 cache_control
# ===========================================================================
def test_tc_pc03_anthropic_two_blocks_dynamic_has_no_cache_control() -> None:
    with patch.dict(os.environ, {"DATACLOUD_LLM_MODEL_PROVIDER": "anthropic"}):
        msg = _build_system_message(_FULL, stable_system_prompt=_STABLE, dynamic_prompt=_DYNAMIC)

    assert isinstance(msg.content, list)
    assert len(msg.content) == 2, "stable+dynamic 应生成两个 block"
    second_block = msg.content[1]
    assert second_block.get("text") == _DYNAMIC
    assert "cache_control" not in second_block, "dynamic block 不应含 cache_control"


# ===========================================================================
# TC-PC-04: provider=openai → content 为纯字符串，无 cache_control
# ===========================================================================
def test_tc_pc04_openai_system_message_is_plain_string() -> None:
    with patch.dict(os.environ, {"DATACLOUD_LLM_MODEL_PROVIDER": "openai"}):
        msg = _build_system_message(_FULL, stable_system_prompt=_STABLE, dynamic_prompt=_DYNAMIC)

    assert isinstance(msg, SystemMessage)
    assert isinstance(msg.content, str), (
        f"openai 路径 content 应为纯字符串，实际为 {type(msg.content)}"
    )
    assert "cache_control" not in msg.content, "openai 路径不得含 cache_control 字样"
    assert msg.content == _FULL


# ===========================================================================
# TC-PC-05: provider 未配置（默认 openai）→ 同 TC-PC-04
# ===========================================================================
def test_tc_pc05_default_provider_is_openai_compatible() -> None:
    env_without_provider = {k: v for k, v in os.environ.items() if k != "DATACLOUD_LLM_MODEL_PROVIDER"}
    with patch.dict(os.environ, env_without_provider, clear=True):
        msg = _build_system_message(_FULL, stable_system_prompt=_STABLE, dynamic_prompt=_DYNAMIC)

    assert isinstance(msg.content, str), "未配置 provider 时应退回纯字符串"
    assert "cache_control" not in msg.content


# ===========================================================================
# TC-PC-06: stable_system_prompt=None → 退回纯字符串（不论 provider=anthropic）
# ===========================================================================
def test_tc_pc06_no_stable_prompt_falls_back_to_string() -> None:
    with patch.dict(os.environ, {"DATACLOUD_LLM_MODEL_PROVIDER": "anthropic"}):
        msg = _build_system_message(_FULL, stable_system_prompt=None, dynamic_prompt=_DYNAMIC)

    assert isinstance(msg.content, str), "stable_system_prompt=None 时应为纯字符串"
    assert msg.content == _FULL


# ===========================================================================
# TC-PC-07: anthropic 路径，所有 block.text 拼接等于原 system_prompt（内容完整性）
# ===========================================================================
def test_tc_pc07_anthropic_content_completeness() -> None:
    with patch.dict(os.environ, {"DATACLOUD_LLM_MODEL_PROVIDER": "anthropic"}):
        msg = _build_system_message(_FULL, stable_system_prompt=_STABLE, dynamic_prompt=_DYNAMIC)

    assert isinstance(msg.content, list)
    full_text = "".join(b.get("text", "") for b in msg.content if isinstance(b, dict))
    assert full_text == _FULL, (
        f"anthropic 路径内容拼接应与原 system_prompt 相同\n"
        f"期望: {_FULL!r}\n实际: {full_text!r}"
    )


# ===========================================================================
# TC-PC-08: openai 路径，SystemMessage 可被 ChatOpenAI 序列化，无未知字段
# ===========================================================================
def test_tc_pc08_openai_no_unknown_fields_for_api() -> None:
    """模拟 ChatOpenAI 消息序列化，确认不会因 cache_control 导致 400 错误。"""
    with patch.dict(os.environ, {"DATACLOUD_LLM_MODEL_PROVIDER": "openai"}):
        msg = _build_system_message(_FULL, stable_system_prompt=_STABLE, dynamic_prompt=_DYNAMIC)

    from langchain_openai.chat_models.base import _convert_message_to_dict

    openai_dict = _convert_message_to_dict(msg)

    assert openai_dict["role"] == "system"
    assert isinstance(openai_dict["content"], str)
    assert "cache_control" not in openai_dict
    assert "cache_control" not in openai_dict.get("content", "")

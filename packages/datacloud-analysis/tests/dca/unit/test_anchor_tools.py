"""附06-V3 需求一/二/三 — 测试文件（先红后绿）

测试目标：
  - tool_pool.py 新增 TOOL_POOL_THRESHOLD 常量和 is_anchor_mode() 函数
  - anchor_tools.py 新建，make_anchor_tools 返回 activate_anchor / mark_dead_end 两个工具
  - activate_anchor 正确激活对象工具到 active_tools，记录 reasoning_graph anchor 节点
  - mark_dead_end 正确写入 reasoning_graph.dead_ends
  - worker.py 改动：不再依赖 _ext_codes（extResourceList）
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

# ── 3.2.1 阈值常量与 is_anchor_mode ────────────────────────────────────────────

def test_tool_pool_threshold_constant_exists() -> None:
    from datacloud_analysis.tools.tool_pool import TOOL_POOL_THRESHOLD

    assert isinstance(TOOL_POOL_THRESHOLD, int)
    assert TOOL_POOL_THRESHOLD > 0, "阈值应大于0"


def test_is_anchor_mode_function_exists() -> None:
    from datacloud_analysis.tools.tool_pool import is_anchor_mode

    # 函数应存在且可调用
    result = is_anchor_mode()
    assert isinstance(result, bool)


def test_is_anchor_mode_below_threshold(monkeypatch: Any) -> None:
    """TOOL_POOL 工具数 <= 阈值时，返回 False（全量挂载模式）。"""
    from datacloud_analysis.tools import tool_pool

    monkeypatch.setattr(tool_pool, "TOOL_POOL_THRESHOLD", 100)
    # TOOL_POOL 工具数默认远小于100
    assert tool_pool.is_anchor_mode() is False


def test_is_anchor_mode_above_threshold(monkeypatch: Any) -> None:
    """TOOL_POOL 工具数 > 阈值时，返回 True（锚点模式）。"""
    from datacloud_analysis.tools import tool_pool

    monkeypatch.setattr(tool_pool, "TOOL_POOL_THRESHOLD", 0)  # 阈值设为0，任意工具数都超过
    # 先注册一个工具
    fake = MagicMock()
    fake.name = "_test_anchor_mode_tool"
    tool_pool.register_tool("_test_anchor_mode_tool", fake, object_code="ops_test")
    try:
        assert tool_pool.is_anchor_mode() is True
    finally:
        tool_pool.TOOL_POOL.pop("_test_anchor_mode_tool", None)
        tool_pool.TOOL_TO_OBJECT.pop("_test_anchor_mode_tool", None)


# ── 3.2.2 anchor_tools 模块 ────────────────────────────────────────────────────

def test_anchor_tools_module_importable() -> None:
    from datacloud_analysis.tools import anchor_tools  # noqa: F401


def test_make_anchor_tools_returns_two_tools() -> None:
    from datacloud_analysis.tools.anchor_tools import make_anchor_tools

    tools = make_anchor_tools(get_state_fn=lambda: {})
    tool_names = {t.name for t in tools}
    assert "activate_anchor" in tool_names, "应包含 activate_anchor 工具"
    assert "mark_dead_end" in tool_names, "应包含 mark_dead_end 工具"


def test_activate_anchor_adds_tools_to_active_tools() -> None:
    """activate_anchor 应将对象工具加入 active_tools。"""
    from datacloud_analysis.tools import tool_pool
    from datacloud_analysis.tools.anchor_tools import make_anchor_tools

    # 准备：注册一个假工具到 TOOL_POOL
    fake = MagicMock()
    fake.name = "get_spans_test"
    tool_pool.register_tool("get_spans_test", fake, object_code="ops_langfuse_trace_test")

    state_store: dict[str, Any] = {"active_tools": [], "reasoning_graph": None}
    tools = make_anchor_tools(get_state_fn=lambda: state_store)
    activate = next(t for t in tools if t.name == "activate_anchor")

    try:
        result = activate.invoke({"object_code": "ops_langfuse_trace_test"})

        assert isinstance(result, str)
        assert "get_spans_test" in state_store.get("active_tools", []), (
            "activate_anchor 应将对象工具加入 active_tools"
        )
    finally:
        tool_pool.TOOL_POOL.pop("get_spans_test", None)
        tool_pool.TOOL_TO_OBJECT.pop("get_spans_test", None)


def test_activate_anchor_records_to_reasoning_graph() -> None:
    """activate_anchor 应在 reasoning_graph 中记录锚点切换节点。"""
    from datacloud_analysis.tools import tool_pool
    from datacloud_analysis.tools.anchor_tools import make_anchor_tools

    fake = MagicMock()
    fake.name = "find_error_spans_test"
    tool_pool.register_tool("find_error_spans_test", fake, object_code="ops_trace_test")

    state_store: dict[str, Any] = {"active_tools": [], "reasoning_graph": None}
    tools = make_anchor_tools(get_state_fn=lambda: state_store)
    activate = next(t for t in tools if t.name == "activate_anchor")

    try:
        activate.invoke({"object_code": "ops_trace_test"})
        rg = state_store.get("reasoning_graph")
        assert rg is not None, "activate_anchor 应写入 reasoning_graph"
        nodes = rg.get("nodes") or {}
        assert len(nodes) >= 1, "应有至少1个节点"
        # 找 anchor_switch 类型的节点
        anchor_nodes = [n for n in nodes.values() if n.get("type") == "anchor_switch"]
        assert len(anchor_nodes) >= 1, "应有 anchor_switch 类型节点"
        anchor = anchor_nodes[0]
        assert anchor["object_code"] == "ops_trace_test"
        assert "find_error_spans_test" in anchor["activated_tools"]
    finally:
        tool_pool.TOOL_POOL.pop("find_error_spans_test", None)
        tool_pool.TOOL_TO_OBJECT.pop("find_error_spans_test", None)


def test_activate_anchor_unknown_object_returns_error() -> None:
    """activate_anchor 传入不存在的 object_code 应返回错误提示。"""
    from datacloud_analysis.tools.anchor_tools import make_anchor_tools

    state_store: dict[str, Any] = {"active_tools": [], "reasoning_graph": None}
    tools = make_anchor_tools(get_state_fn=lambda: state_store)
    activate = next(t for t in tools if t.name == "activate_anchor")

    result = activate.invoke({"object_code": "nonexistent_object_xyz"})
    assert "未找到" in result or "not found" in result.lower(), (
        "未知对象应返回错误提示"
    )


def test_mark_dead_end_writes_to_reasoning_graph() -> None:
    """mark_dead_end 应将排除路径写入 reasoning_graph.dead_ends。"""
    from datacloud_analysis.tools.anchor_tools import make_anchor_tools

    state_store: dict[str, Any] = {
        "active_tools": [],
        "reasoning_graph": {"nodes": {}, "current_node_id": "", "findings": [], "dead_ends": []},
    }
    tools = make_anchor_tools(get_state_fn=lambda: state_store)
    mark = next(t for t in tools if t.name == "mark_dead_end")

    result = mark.invoke({
        "object_code": "ops_langfuse_trace",
        "reason": "get_spans 返回空，无诊断信号",
    })

    assert isinstance(result, str)
    rg = state_store.get("reasoning_graph") or {}
    dead_ends = rg.get("dead_ends") or []
    assert len(dead_ends) == 1, "应写入1条 dead_end 记录"
    assert dead_ends[0]["object_code"] == "ops_langfuse_trace"
    assert "get_spans" in dead_ends[0]["reason"]


def test_mark_dead_end_accumulates_multiple_entries() -> None:
    """多次调用 mark_dead_end 应累积，不覆盖。"""
    from datacloud_analysis.tools.anchor_tools import make_anchor_tools

    state_store: dict[str, Any] = {
        "reasoning_graph": {"nodes": {}, "current_node_id": "", "findings": [], "dead_ends": []},
    }
    tools = make_anchor_tools(get_state_fn=lambda: state_store)
    mark = next(t for t in tools if t.name == "mark_dead_end")

    mark.invoke({"object_code": "ops_obj_a", "reason": "无数据"})
    mark.invoke({"object_code": "ops_obj_b", "reason": "错误路径"})

    dead_ends = state_store["reasoning_graph"]["dead_ends"]
    assert len(dead_ends) == 2
    codes = {d["object_code"] for d in dead_ends}
    assert "ops_obj_a" in codes
    assert "ops_obj_b" in codes


# ── worker.py 需求一：不再依赖 extResourceList ─────────────────────────────────

def test_worker_no_longer_reads_ext_codes() -> None:
    """worker.py 的 start_heartbeat 不应再读取 _ext_codes（extResourceList 已废弃）。"""
    from pathlib import Path

    worker_path = Path(
        r"D:\data\code\baiying\byclaw-all\byclaw-data\src\byclaw_data\worker.py"
    )
    if not worker_path.exists():
        pytest.skip("worker.py not found in expected path")

    source = worker_path.read_text(encoding="utf-8")
    # 找 start_heartbeat 方法里的逻辑
    # _ext_codes 是旧的 extResourceList 读取字段，改动后不应出现在 TOOL_POOL 初始化相关逻辑中
    # 定位 TOOL_POOL 初始化区块（包含 _init_ext_tool_pool 的那段代码）
    tool_pool_block_start = source.find("_init_ext_tool_pool")
    assert tool_pool_block_start > 0, "应包含 _init_ext_tool_pool 调用"

    # 找该调用前后约200字符的上下文，不应含 _ext_codes
    context = source[max(0, tool_pool_block_start - 300):tool_pool_block_start + 300]
    assert "_ext_codes" not in context, (
        "TOOL_POOL 初始化区块不应再读取 _ext_codes（extResourceList 已废弃）\n"
        f"上下文：{context[:200]}"
    )

"""锚点推理工具（附06-V3 需求二）。

工具池工具数超过阈值时，LLM 无法全量挂载所有工具。
这两个工具提供"选锚点 → 展开 → 换锚点"的渐进式推理能力：

- activate_anchor：LLM 选定最相关本体对象后调用，将该对象工具加入 active_tools
- mark_dead_end：LLM 判断某条路径走不通时调用，记录排除原因，准备换锚点

两个工具通过工厂函数 make_anchor_tools(get_state_fn) 创建，
与 make_reasoning_graph_tools 共享同一 state 访问方式（闭包注入）。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from langchain_core.tools import tool


def make_anchor_tools(
    get_state_fn: Callable[[], dict[str, Any]],
) -> list[Any]:
    """创建锚点推理工具列表。

    Args:
        get_state_fn: 返回当前 AgentState dict 的函数（闭包，per-request）。

    Returns:
        [activate_anchor, mark_dead_end] 两个 LangChain tool 对象。
    """

    @tool("activate_anchor")
    def activate_anchor(object_code: str) -> str:
        """激活指定本体对象或视图为锚点，将其工具加入当前可调用列表。

        当工具池中对象数超过阈值、无法全量挂载时使用。
        从"可选本体对象"列表中选择最相关的1个对象/视图调用此工具开始推理。
        推理中可多次调用以切换锚点。

        - Object 锚点：Object 自身工具加入 active_tools，after_hook 沿 OWL 关系图渐进解锁
        - View 锚点：View 的 query_view_xxx 工具加入 active_tools，内部多对象执行对 LLM 透明

        Args:
            object_code: 本体对象或视图编码，如 "ops_langfuse_trace" 或 "view_crm_analysis"
        """
        try:
            from datacloud_analysis.tools.tool_pool import (  # noqa: PLC0415
                TOOL_POOL,
                TOOL_TO_OBJECT,
            )
        except ImportError:
            return "TOOL_POOL 未初始化，无法激活锚点"

        state = get_state_fn() or {}
        existing = set(state.get("active_tools") or [])

        # 找出属于该对象/视图的所有工具名（Object 和 View 在 TOOL_POOL 里平级）
        tools_of_obj = [
            name
            for name, code in TOOL_TO_OBJECT.items()
            if code == object_code and name in TOOL_POOL
        ]
        if not tools_of_obj:
            return (
                f"未找到对象/视图 {object_code!r} 的工具，"
                "请检查 object_code 是否正确，或该对象未加载到 TOOL_POOL"
            )

        new_tools = [t for t in tools_of_obj if t not in existing]
        state["active_tools"] = list(existing) + new_tools

        # 记录锚点切换事件到 reasoning_graph
        rg = dict(
            state.get("reasoning_graph")
            or {"nodes": {}, "current_node_id": "", "findings": [], "dead_ends": []}
        )
        nodes = dict(rg.get("nodes") or {})
        node_id = f"anchor_{len(nodes)}"
        nodes[node_id] = {
            "id": node_id,
            "type": "anchor_switch",
            "object_code": object_code,
            "activated_tools": new_tools,
            "status": "active",
        }
        rg["nodes"] = nodes
        rg["current_node_id"] = node_id
        if "dead_ends" not in rg:
            rg["dead_ends"] = []
        state["reasoning_graph"] = rg

        if new_tools:
            return f"已激活 {object_code}，解锁 {len(new_tools)} 个工具：{', '.join(new_tools)}"
        return f"{object_code} 的工具已全部激活（无新增）"

    @tool("mark_dead_end")
    def mark_dead_end(object_code: str, reason: str) -> str:
        """标记当前锚点路径为死路，记录排除原因，准备换锚点继续推理。

        当沿某个锚点对象展开后发现无法定位根因、工具调用结果与问题无关时调用。
        已走的步骤不会丢失，作为"排除项"保存，避免后续重复尝试。

        Args:
            object_code: 要标记为死路的本体对象编码
            reason: 排除原因，如"get_spans 返回空，无诊断信号"
        """
        state = get_state_fn() or {}
        rg = dict(
            state.get("reasoning_graph")
            or {"nodes": {}, "current_node_id": "", "findings": [], "dead_ends": []}
        )
        dead_ends = list(rg.get("dead_ends") or [])
        dead_ends.append({"object_code": object_code, "reason": reason})
        rg["dead_ends"] = dead_ends
        state["reasoning_graph"] = rg
        return (
            f"已标记 {object_code!r} 为死路：{reason}。"
            "请从'可选本体对象'列表中选择新的锚点继续推理。"
        )

    return [activate_anchor, mark_dead_end]

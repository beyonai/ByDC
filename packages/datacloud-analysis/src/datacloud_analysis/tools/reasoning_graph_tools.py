"""推理图谱工具：get_reasoning_map / add_finding。

使用标准 @tool 函数（不用 OWL Script），因为需要读写 AgentState，
Script 执行环境不支持 state 访问。

通过工厂函数 make_reasoning_graph_tools(get_state_fn) 创建，
在 create_agent() 或 OntologyAgent.ask() 里调用，传入 state getter 闭包。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from langchain_core.tools import tool


def make_reasoning_graph_tools(
    get_state_fn: Callable[[], dict[str, Any]],
) -> list[Any]:
    """创建推理图谱工具列表。

    Args:
        get_state_fn: 返回当前 AgentState dict 的函数（闭包，per-request）。

    Returns:
        [get_reasoning_map, add_finding] 两个 LangChain tool 对象。
    """

    @tool("get_reasoning_map")
    def get_reasoning_map() -> str:
        """查看当前诊断进度，包括已执行步骤、新解锁工具和已确认结论。
        在诊断过程中随时调用，了解目前走到哪一步、有哪些工具可用。
        """
        state = get_state_fn() or {}
        graph: dict[str, Any] = state.get("reasoning_graph") or {}
        nodes: dict[str, Any] = graph.get("nodes") or {}
        findings: list[str] = graph.get("findings") or []
        active_tools: list[str] = state.get("active_tools") or []

        lines: list[str] = ["**诊断进度：**"]

        for node in nodes.values():
            tag = f"，tag={node.get('diagnostic_tag', '')}" if node.get("diagnostic_tag") else ""
            unlocked = node.get("unlocked_tools") or []
            ul_str = f"，解锁 {', '.join(unlocked)}" if unlocked else ""
            lines.append(
                f"  [{node.get('id', '?')}] {node.get('action', '?')} "
                f"→ {node.get('result_summary', '')}{tag}{ul_str}"
            )

        always_on = {
            "get_spans",
            "find_error_spans",
            "get_agent_diag",
            "search_by_tags",
            "match_by_symptom",
            "get_reasoning_map",
            "add_finding",
            "finish_react",
        }
        extra = [t for t in active_tools if t not in always_on]
        if extra:
            lines.append(f"\n**当前可用的解锁工具（共{len(extra)}个）：**")
            for t in extra:
                lines.append(f"  - `{t}`")

        lines.append("\n**已确认结论：**")
        if findings:
            for f in findings:
                lines.append(f"  - {f}")
        else:
            lines.append("  （空）")

        return "\n".join(lines)

    @tool("add_finding")
    def add_finding(conclusion: str) -> str:
        """记录一条已确认的诊断结论。
        当通过工具验证确认了故障根因后调用，写入诊断报告。

        Args:
            conclusion: 结论描述，如 "BY_003: DATACLOUD_ONTOLOGY_PATH 配错，工具挂载为0"
        """
        if not conclusion.strip():
            return "错误：conclusion 不能为空"

        state = get_state_fn()
        if state is None:
            return f"已记录结论：{conclusion}"

        rg: dict[str, Any] = dict(
            state.get("reasoning_graph") or {"nodes": {}, "current_node_id": "", "findings": []}
        )
        findings: list[str] = list(rg.get("findings") or [])
        findings.append(conclusion)
        rg["findings"] = findings
        state["reasoning_graph"] = rg

        return f"已记录结论：{conclusion}"

    return [get_reasoning_map, add_finding]

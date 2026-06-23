"""ParamLinkGraph — 基于 OWL 参数绑定的工具串联推理索引。

从 OntologyLoader.get_action_params() 读取每个工具的入参/出参及其 object_property 绑定，
建立工具间的数据流串联关系索引，供 after_hook 解锁和 LLM 串联提示使用。

设计原则：
  - 不查数据库，从 OntologyLoader 内存数据构建，零额外 IO
  - object_property 展开规则：
      * "{{entity}}.field"  → "entity.field"（跨对象引用）
      * "field"             → "{belong_entity}.field"（同对象字段，自动补前缀）
  - 出参的 expanded_prop 与任意工具入参的 expanded_prop 相同 → 建立串联
  - 不建立自链接（同一工具的出参→入参不计）
  - build() 中每个工具异常静默跳过，整体结果通过 INFO 日志可见
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# 匹配 {{entity_code}}.field 格式
_CROSS_ENTITY_RE = re.compile(r"^\{\{([^}]+)\}\}\.(.+)$")


def _expand_object_property(prop: str, belong_entity: str) -> str:
    """将 object_property 展开为 "entity.field" 形式。

    规则：
      - "{{ops_dig_employee}}.agent_id" → "ops_dig_employee.agent_id"
      - "span_id"                        → "{belong_entity}.span_id"
      - "_internal"                      → "{belong_entity}._internal"（内部字段也展开，调用方自行过滤）

    Args:
        prop: object_property 原始值。
        belong_entity: 该参数所属工具的 belong_entity（对象 code）。

    Returns:
        展开后的 "entity.field" 字符串。
    """
    m = _CROSS_ENTITY_RE.match(prop)
    if m:
        return f"{m.group(1)}.{m.group(2)}"
    # 无跨对象前缀，用 belong_entity 补全
    return f"{belong_entity}.{prop}"


@dataclass
class ParamLink:
    """一条工具间参数串联关系。"""

    from_tool: str  # 出参所在工具
    to_tool: str  # 入参所在工具
    via_prop: str  # 展开后的 "entity.field" 路径
    from_field: str  # 出参 field_code
    to_field: str  # 入参 param_code


class ParamLinkGraph:
    """基于 OWL 参数绑定的工具串联推理索引。

    用法::

        plg = ParamLinkGraph()
        plg.build(TOOL_POOL, loader)

        # after_hook：获取当前工具执行完后可以解锁的下游工具
        next_tools = plg.get_next_tools("get_spans")

        # llm_call_node：生成串联提示注入 messages_window
        hint = plg.get_chain_hint(state["active_tools"])
    """

    def __init__(self) -> None:
        self._links: list[ParamLink] = []
        # 出发工具 → 串联关系列表（加速查询）
        self._from_index: dict[str, list[ParamLink]] = {}

    # ── 构建 ──────────────────────────────────────────────────────────────────

    def build(self, tool_pool: dict[str, Any], owl_loader: Any) -> None:
        """扫描 tool_pool 中所有工具的参数绑定，建立串联关系索引。

        Args:
            tool_pool: 进程级工具注册表 {tool_name: StructuredTool}。
            owl_loader: 已 load 好的 OntologyLoader，需提供 get_action_params(action_code)。
        """
        self._links = []
        self._from_index = {}

        tool_names = list(tool_pool.keys())

        # 第一遍：收集每个工具的出参/入参及展开后的 object_property
        # out_props[prop] = [(tool_name, field_code), ...]
        out_props: dict[str, list[tuple[str, str]]] = {}
        # in_props[prop]  = [(tool_name, param_code), ...]
        in_props: dict[str, list[tuple[str, str]]] = {}

        scanned = 0
        with_binding = 0

        for tool_name in tool_names:
            try:
                params = owl_loader.get_action_params(tool_name)
            except Exception:  # noqa: BLE001
                continue

            scanned += 1
            belong_entity: str = params.get("belong_entity") or ""

            # 收集出参
            response_params: list[dict] = params.get("response_params") or []
            for rp in response_params:
                prop_raw: str = rp.get("object_property") or ""
                field_code: str = rp.get("field_code") or ""
                if not prop_raw or not field_code:
                    continue
                expanded = _expand_object_property(prop_raw, belong_entity)
                out_props.setdefault(expanded, []).append((tool_name, field_code))
                with_binding += 1

            # 收集入参
            request_params: list[dict] = params.get("request_params") or []
            for req in request_params:
                prop_raw = req.get("object_property") or ""
                param_code: str = req.get("param_code") or ""
                if not prop_raw or not param_code:
                    continue
                expanded = _expand_object_property(prop_raw, belong_entity)
                in_props.setdefault(expanded, []).append((tool_name, param_code))

        # 第二遍：对每个出参 prop，找所有匹配的入参 → 建立 ParamLink（排除自链接）
        for prop, from_list in out_props.items():
            to_list = in_props.get(prop) or []
            for from_tool, from_field in from_list:
                for to_tool, to_field in to_list:
                    if from_tool == to_tool:
                        continue  # 不建立自链接
                    link = ParamLink(
                        from_tool=from_tool,
                        to_tool=to_tool,
                        via_prop=prop,
                        from_field=from_field,
                        to_field=to_field,
                    )
                    self._links.append(link)
                    self._from_index.setdefault(from_tool, []).append(link)

        logger.info(
            "ParamLinkGraph: scanned=%d tools_with_binding=%d links=%d",
            scanned,
            with_binding,
            len(self._links),
        )

    # ── 查询 ──────────────────────────────────────────────────────────────────

    def get_next_tools(self, tool_name: str) -> list[str]:
        """返回 tool_name 执行完后可串联的下游工具名列表（去重）。"""
        links = self._from_index.get(tool_name) or []
        seen: set[str] = set()
        result: list[str] = []
        for lnk in links:
            if lnk.to_tool not in seen:
                seen.add(lnk.to_tool)
                result.append(lnk.to_tool)
        return result

    def get_full_anchor_hint(self, anchor_object_code: str) -> str:
        """返回指定锚点对象下所有工具的完整参数数据流提示。

        从所有串联关系中筛选 via_prop 以 anchor_object_code 开头的链接，
        生成锚点激活时注入对话历史的完整路径图。

        Args:
            anchor_object_code: 锚点对象编码，如 "ops_langfuse_trace"。

        Returns:
            多行提示文本；无匹配时返回 ""。
        """
        if not self._links:
            return ""
        # 找出所有 from_tool 属于该锚点下的链接（via_prop 以锚点编码开头）
        relevant = [
            lnk for lnk in self._links
            if lnk.via_prop.startswith(f"{anchor_object_code}.")
            or lnk.from_tool in self._from_index
        ]
        # 取该锚点下所有工具作为出发点的 hint
        anchor_tools = [
            tool for tool, links in self._from_index.items()
            if any(lnk.via_prop.startswith(f"{anchor_object_code}.") for lnk in links)
        ]
        if not anchor_tools:
            # fallback：取所有工具（无法按锚点过滤时返回全量）
            return ""
        return self.get_chain_hint(anchor_tools)

    def get_chain_hint(self, active_tools: list[str]) -> str:
        """生成当前已激活工具集的参数数据流串联提示（注入 LLM messages_window）。"""
        if not active_tools:
            return ""
        lines: list[str] = []
        for tool_name in active_tools:
            links = self._from_index.get(tool_name) or []
            for lnk in links:
                lines.append(
                    f"- {lnk.from_tool}.{lnk.from_field} "
                    f"→ {lnk.to_tool}.{lnk.to_field} "
                    f"(via {lnk.via_prop})"
                )
        if not lines:
            return ""
        header = "[参数串联提示] 以下工具间存在参数数据流，可按顺序调用："
        return header + "\n" + "\n".join(lines)

    def summary(self) -> str:
        """返回索引摘要字符串，包含工具数和串联关系数。"""
        tool_count = len(self._from_index)
        link_count = len(self._links)
        return f"ParamLinkGraph: {tool_count} source tools, {link_count} links"


# ── 纯函数：供 hook_aware_tool_node 和 llm_call_node 调用（无 platform 依赖）────


# 触发全量注入的工具名集合
# 注：goto_ontology 是 activate_anchor 的新名（主工具），两者都要触发；
# search_ontology 命中后也会把对象工具写入 active_tools，同样触发。
_ANCHOR_TRIGGER_TOOLS: frozenset[str] = frozenset(
    {"goto_ontology", "activate_anchor", "search_ontology"}
)

# 从锚点工具的人类可读返回文本中提取 object_code，
# 形如「已激活 ops_langfuse_trace，解锁 …」「已跳转到 ops_xxx，…」。
_ANCHOR_TEXT_RE = re.compile(r"已(?:激活|跳转到)\s*([A-Za-z_][\w]*)")


def _extract_anchor_object(tool_result: Any) -> str:
    """从锚点工具返回结果中提取 object_code，兼容 dict 与 str 两种形态。

    - dict：直接读 object_code 键（结构化场景）。
    - str ：从返回文本正则提取（activate_anchor / goto_ontology 实际返回字符串）。
    """
    if isinstance(tool_result, dict):
        return str(tool_result.get("object_code") or "").strip()
    if isinstance(tool_result, str):
        m = _ANCHOR_TEXT_RE.search(tool_result)
        if m:
            return m.group(1).strip()
    return ""


def _build_anchor_chain_hint_update(
    tool_name: str,
    tool_result: "dict[str, Any] | str",
    current_anchor: str | None,
    plg: "ParamLinkGraph | None",
) -> "dict[str, Any] | None":
    """计算锚点激活后需要写入 state 的 chain hint 更新。

    在 goto_ontology / activate_anchor / search_ontology 工具返回时触发，
    且新锚点与当前不同。

    Args:
        tool_name: 刚执行完的工具名。
        tool_result: 工具返回结果。可能是已解析的 dict，也可能是工具实际
            返回的人类可读字符串（如「已激活 ops_langfuse_trace，…」）。
        current_anchor: state["chain_hint_anchor"] 当前值。
        plg: ParamLinkGraph 单例，None 时安全跳过。

    Returns:
        需要合并进 extra_state 的 dict（含 messages 和 chain_hint_anchor），
        或 None（不需要更新）。
    """
    if tool_name not in _ANCHOR_TRIGGER_TOOLS:
        return None
    if plg is None:
        return None

    new_anchor: str = _extract_anchor_object(tool_result)
    if not new_anchor or new_anchor == current_anchor:
        return None

    hint = plg.get_full_anchor_hint(new_anchor)
    if not hint:
        # 即使 hint 为空也更新锚点，避免重复尝试
        return {"chain_hint_anchor": new_anchor}

    from langchain_core.messages import HumanMessage  # noqa: PLC0415

    return {
        "chain_hint_anchor": new_anchor,
        "messages": [HumanMessage(content=f"[工具链路图 - 锚点:{new_anchor}]\n{hint}")],
    }


def _build_delta_chain_hint(
    plg: "ParamLinkGraph | None",
    prev_active: list[str],
    curr_active: list[str],
) -> str:
    """计算本轮新解锁工具的 delta chain hint。

    只对 curr_active - prev_active 的新增工具生成提示，避免重复全量注入。

    Args:
        plg: ParamLinkGraph 单例，None 时返回 ""。
        prev_active: 上一轮的 active_tools。
        curr_active: 本轮的 active_tools。

    Returns:
        delta 提示文本，无新增或无串联时返回 ""。
    """
    if plg is None:
        return ""
    prev_set = set(prev_active or [])
    curr_set = set(curr_active or [])
    delta = [t for t in curr_active if t not in prev_set]
    if not delta:
        return ""
    return plg.get_chain_hint(delta)

    def get_chain_hint(self, active_tools: list[str]) -> str:
        """生成当前已激活工具集的参数数据流串联提示（注入 LLM messages_window）。

        只显示 active_tools 中工具作为出发点的串联关系。
        若无任何串联，返回空字符串。

        Args:
            active_tools: 当前 AgentState.active_tools（工具名列表）。

        Returns:
            多行提示文本；无串联时返回 ""。
        """
        if not active_tools:
            return ""

        lines: list[str] = []
        for tool_name in active_tools:
            links = self._from_index.get(tool_name) or []
            for lnk in links:
                lines.append(
                    f"- {lnk.from_tool}.{lnk.from_field} "
                    f"→ {lnk.to_tool}.{lnk.to_field} "
                    f"(via {lnk.via_prop})"
                )

        if not lines:
            return ""

        header = "[参数串联提示] 以下工具间存在参数数据流，可按顺序调用："
        return header + "\n" + "\n".join(lines)

    def summary(self) -> str:
        """返回索引摘要字符串，包含工具数和串联关系数。"""
        tool_count = len(self._from_index)
        link_count = len(self._links)
        return f"ParamLinkGraph: {tool_count} source tools, {link_count} links"

"""锚点推理工具（附06-V3 需求二 + 附06-V7 三工具升级）。

工具列表：
- goto_ontology（原 activate_anchor 重命名）：沿 OWL 关系定向跳转
- mark_dead_end：标记死路，记录排除原因
- search_ontology：语义/关键字检索锚点入口
- get_reasoning_map：查阅推理轨迹，支持换方向或汇总结论

通过工厂函数 make_anchor_tools(get_state_fn) 创建，闭包注入 state。
activate_anchor 作为 goto_ontology 的别名保留，保持向后兼容。
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

# 懒加载：测试环境可能不安装，patch 必须在模块级有此名称
try:
    from datacloud_platform import get_platform
except ImportError:  # pragma: no cover
    get_platform = None  # type: ignore[assignment]

try:
    from datacloud_data_sdk.ontology.tool_loader import OntologyToolLoader
except ImportError:  # pragma: no cover
    OntologyToolLoader = None  # type: ignore[assignment]


def _build_scope_filter(allowed_scope: list) -> dict:
    """把 ScopeEntry 列表转成 platform.search_ontology() 可接受的过滤参数。"""
    base_ids, scene_ids, object_codes, view_codes = [], [], [], []
    for e in allowed_scope:
        if e.scope_type == "ONTOLOGY_BASE":
            base_ids.append(e.code)
        elif e.scope_type == "SCENE":
            scene_ids.append(e.code)
        elif e.scope_type == "OBJECT":
            object_codes.append(e.code)
        elif e.scope_type == "VIEW":
            view_codes.append(e.code)
    return {
        "base_ids": base_ids,
        "scene_ids": scene_ids,
        "object_codes": object_codes,
        "view_codes": view_codes,
    }


def _activate_object_with_context(
    state: dict[str, Any],
    object_code: str,
    tool_context: Any,
) -> tuple[list[str], str]:
    """权限校验 + 按需构建工具；tool_context 是 RequestToolContext 实例。"""
    platform = get_platform()
    term_info = platform.get_term_scope_info(object_code)
    library_id = term_info.get("library_id")
    scene_id = term_info.get("scene_id")

    if not tool_context.is_object_allowed(object_code, scene_id, library_id):
        return [], f"对象 {object_code!r} 不在当前授权范围，拒绝激活"

    existing = set(state.get("active_tools") or [])

    # 缓存路径
    if object_code in tool_context.object_to_tools:
        already = tool_context.object_to_tools[object_code]
        new_tools = [t for t in already if t not in existing]
        state["active_tools"] = list(existing) + new_tools
        return new_tools, ""

    # 按需构建
    detail = platform.get_scene_details(library_id, scene_id, object_code=[object_code])
    tool_context.loader.load_from_content(detail)

    tool_loader = OntologyToolLoader(
        mounted_objects=[object_code], loader=tool_context.loader
    )
    new_obj_tools: dict[str, Any] = tool_loader.load()

    tool_context.tools_map.update(new_obj_tools)
    tool_context.object_to_tools[object_code] = list(new_obj_tools.keys())

    new_tools = [t for t in new_obj_tools if t not in existing]
    state["active_tools"] = list(existing) + new_tools
    return new_tools, ""


def _do_search_ontology(
    query: str,
    scope: str = "all",
    type_filter: str = "all",
    top_k: int = 3,
) -> list[dict[str, Any]]:
    """内部搜索实现，供测试 mock 和工具调用。

    优先使用 SearchEngine（datacloud-server），不可用时回退到 TOOL_POOL 名称匹配。
    """
    try:
        import os  # noqa: PLC0415

        from datacloud_server.adapters.local_adapter import LocalOntologyAdapter  # noqa: PLC0415
        from datacloud_server.registry.registry import (  # noqa: PLC0415
            OntologyBaseEntry,
            OntologyBaseRegistry,
        )
        from datacloud_server.services.adapter_router import AdapterRouter  # noqa: PLC0415
        from datacloud_server.services.search_engine import (  # noqa: PLC0415
            RRFStrategy,
            SearchEngine,
        )
        from datacloud_server.storage.json_writer import JSONWriter  # noqa: PLC0415

        data_dir = os.environ.get("DATACLOUD_ONTOLOGY_PATH", "")
        if not data_dir:
            raise ValueError("DATACLOUD_ONTOLOGY_PATH 未配置")

        base_id = "default"
        registry = OntologyBaseRegistry()
        registry.register(
            OntologyBaseEntry(
                base_id=base_id,
                display_name="本体库",
                description="",
                owner_type="enterprise",
                source_type="LOCAL",
                ontology_path=data_dir,
            )
        )
        adapter = LocalOntologyAdapter(data_dir, JSONWriter())
        router = AdapterRouter(registry=registry, adapters={"LOCAL": adapter})  # type: ignore[arg-type]
        engine = SearchEngine(
            router=router,
            scopes=[(base_id, "object"), (base_id, "skill")],
            strategy=RRFStrategy(),
        )
        hits = engine.search(
            keyword=query,
            search_scope="metadata",
            result_per_type=top_k,
        )
        # 按 type_filter 过滤
        if type_filter != "all":
            hits = [h for h in hits if h.get("resultType") == type_filter]
        return hits[:top_k]
    except Exception as exc:  # noqa: BLE001
        logger.debug("search_ontology SearchEngine 不可用，回退到 TOOL_POOL: %s", exc)

    # 回退：在 TOOL_POOL 中做名称匹配
    try:
        from datacloud_analysis.tools.tool_pool import TOOL_TO_OBJECT  # noqa: PLC0415

        query_lower = query.lower()
        seen_objects: set[str] = set()
        results: list[dict[str, Any]] = []
        for tool_name, obj_code in TOOL_TO_OBJECT.items():
            if obj_code in seen_objects:
                continue
            if query_lower in obj_code.lower() or query_lower in tool_name.lower():
                seen_objects.add(obj_code)
                results.append(
                    {
                        "objectCode": obj_code,
                        "objectName": obj_code,
                        "resultType": "object",
                        "score": 0.5,
                    }
                )
                if len(results) >= top_k:
                    break
        return results
    except Exception:  # noqa: BLE001
        return []


def make_anchor_tools(
    get_state_fn: Callable[[], dict[str, Any]],
    get_tool_context_fn: Callable[[], Any] | None = None,
) -> list[Any]:
    """创建锚点推理工具列表。

    Args:
        get_state_fn: 返回当前 AgentState dict 的函数（闭包，per-request）。
        get_tool_context_fn: 返回 RequestToolContext 的函数；None 时退回旧路径。

    Returns:
        [goto_ontology, activate_anchor, mark_dead_end,
         search_ontology, get_reasoning_map] 工具列表。
    """

    def _get_or_init_rg(state: dict[str, Any]) -> dict[str, Any]:
        """获取或初始化 reasoning_graph。"""
        return dict(
            state.get("reasoning_graph")
            or {"nodes": {}, "current_node_id": "", "findings": [], "dead_ends": []}
        )

    def _activate_object(state: dict[str, Any], object_code: str) -> tuple[list[str], str]:
        """将 object_code 对应的工具加入 active_tools，返回 (new_tools, message)。"""
        tool_context = get_tool_context_fn() if get_tool_context_fn else None
        if tool_context is not None:
            return _activate_object_with_context(state, object_code, tool_context)
        # 旧路径（无 tool_context）
        try:
            from datacloud_analysis.tools.tool_pool import (  # noqa: PLC0415
                TOOL_POOL,
                TOOL_TO_OBJECT,
            )
        except ImportError:
            return [], "TOOL_POOL 未初始化，无法激活锚点"

        existing = set(state.get("active_tools") or [])
        tools_of_obj = [
            name
            for name, code in TOOL_TO_OBJECT.items()
            if code == object_code and name in TOOL_POOL
        ]
        if not tools_of_obj:
            return [], (
                f"未找到对象/视图 {object_code!r} 的工具，"
                "请检查 object_code 是否正确，或该对象未加载到 TOOL_POOL"
            )
        new_tools = [t for t in tools_of_obj if t not in existing]
        state["active_tools"] = list(existing) + new_tools
        return new_tools, ""

    # ── goto_ontology ──────────────────────────────────────────────────────────

    @tool("goto_ontology")
    def goto_ontology(object_code: str, reason: str) -> str:
        """直接跳转到指定本体对象并展开其 OWL 一跳关联。

        适用于已通过关系图推断出下一跳目标，跳过搜索直接锚定。
        reason 写入推理轨迹，供后续 get_reasoning_map 回顾。

        Args:
            object_code: 目标本体对象或视图编码，如 "ops_langfuse_trace"
            reason: 跳转原因，如"工具结果含 customer_id，需分析客户详情"
        """
        state = get_state_fn() or {}
        new_tools, err = _activate_object(state, object_code)
        if err and not new_tools:
            return err

        rg = _get_or_init_rg(state)
        nodes = dict(rg.get("nodes") or {})
        node_id = f"goto_{len(nodes)}"
        nodes[node_id] = {
            "id": node_id,
            "type": "goto_ontology",
            "object_code": object_code,
            "reason": reason,
            "activated_tools": new_tools,
            "tools_called": [],
            "result_summary": "",
            "is_dead_end": False,
            "status": "active",
        }
        rg["nodes"] = nodes
        rg["current_node_id"] = node_id
        state["reasoning_graph"] = rg

        if new_tools:
            return f"已跳转到 {object_code}，解锁 {len(new_tools)} 个工具：{', '.join(new_tools)}"
        return f"{object_code} 的工具已全部激活（无新增）"

    # ── activate_anchor（向后兼容别名）────────────────────────────────────────

    @tool("activate_anchor")
    def activate_anchor(object_code: str) -> str:
        """激活指定本体对象或视图为锚点（向后兼容，推荐使用 goto_ontology）。

        Args:
            object_code: 本体对象或视图编码
        """
        state = get_state_fn() or {}
        new_tools, err = _activate_object(state, object_code)
        if err and not new_tools:
            return err

        rg = _get_or_init_rg(state)
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

    # ── mark_dead_end ──────────────────────────────────────────────────────────

    @tool("mark_dead_end")
    def mark_dead_end(object_code: str, reason: str) -> str:
        """标记当前锚点路径为死路，记录排除原因，准备换锚点继续推理。

        Args:
            object_code: 要标记为死路的本体对象编码
            reason: 排除原因，如"get_spans 返回空，无诊断信号"
        """
        state = get_state_fn() or {}
        rg = _get_or_init_rg(state)
        dead_ends = list(rg.get("dead_ends") or [])
        dead_ends.append({"object_code": object_code, "reason": reason})
        rg["dead_ends"] = dead_ends
        state["reasoning_graph"] = rg
        return (
            f"已标记 {object_code!r} 为死路：{reason}。"
            "请调用 get_reasoning_map() 回顾推理轨迹后选择新方向继续推理。"
        )

    # ── search_ontology ────────────────────────────────────────────────────────

    @tool("search_ontology")
    def search_ontology(
        query: str,
        scope: str = "all",
        type: str = "all",  # noqa: A002
        top_k: int = 3,
    ) -> str:
        """在本体知识库中搜索推理起点。

        不确定从哪个对象入手时调用。冷启动时框架已自动调用一次，结果工具已解锁。
        推理中发现当前工具不够用时再次调用。

        搜索结果自动写入 active_tools，下一轮 bind_tools 后 LLM 即可调用。

        Args:
            query: 搜索关键词，如"链路追踪超时"
            scope: 搜索范围，"enterprise" | "personal" | "task" | "all"
            type: 结果类型，"object" | "view" | "skill" | "all"
            top_k: 返回候选数量，默认 3
        """
        state = get_state_fn() or {}
        hits = _do_search_ontology(query, scope, type, top_k)

        if not hits:
            return f"未找到与 '{query}' 相关的本体对象，请尝试调整关键词或 scope 参数。"

        # 将命中对象的工具写入 active_tools
        activated: list[str] = []
        try:
            from datacloud_analysis.tools.tool_pool import (  # noqa: PLC0415
                TOOL_POOL,
                TOOL_TO_OBJECT,
            )

            existing = set(state.get("active_tools") or [])
            for hit in hits:
                obj_code = hit.get("objectCode") or hit.get("object_code", "")
                if not obj_code:
                    continue
                new = [
                    n
                    for n, c in TOOL_TO_OBJECT.items()
                    if c == obj_code and n in TOOL_POOL and n not in existing
                ]
                existing.update(new)
                activated.extend(new)
            state["active_tools"] = list(existing)
        except ImportError:
            pass

        # 构建返回文本
        lines = [f"找到 {len(hits)} 个候选对象："]
        for hit in hits:
            obj_code = hit.get("objectCode") or hit.get("object_code", "")
            obj_name = hit.get("objectName") or hit.get("object_name", obj_code)
            score = hit.get("score", 0)
            lines.append(f"  - {obj_code}（{obj_name}）score={score:.2f}")
        if activated:
            lines.append(f"\n已解锁 {len(activated)} 个工具：{', '.join(activated[:5])}")
        # after_hook 通过 hits_json 注释块解析结构化命中（包含 skill 类型），不依赖人类可读文本
        import json as _json  # noqa: PLC0415

        lines.append(f"\n<!-- hits_json:{_json.dumps(hits, ensure_ascii=False)} -->")
        return "\n".join(lines)

    # ── get_reasoning_map ──────────────────────────────────────────────────────

    @tool("get_reasoning_map")
    def get_reasoning_map() -> str:
        """查阅本次推理的完整探索轨迹。

        两种用途：
        1. 换方向：dead_end 后从历史节点选新方向继续推理
        2. 汇总结论：推理接近完成时，回顾已收集数据和 findings，整合输出最终报告

        数据来源：state["reasoning_graph"]（由 HookAwareToolNode 维护）
        """
        state = get_state_fn() or {}
        rg = state.get("reasoning_graph") or {}

        nodes = rg.get("nodes") or {}
        dead_ends = rg.get("dead_ends") or []
        findings = rg.get("findings") or []
        task_objects = rg.get("task_objects") or []

        # 构建锚点列表
        anchors = []
        for node in nodes.values():
            anchors.append(
                {
                    "object_code": node.get("object_code", ""),
                    "tools_called": node.get("tools_called", []),
                    "findings_summary": node.get("findings_summary", ""),
                    "is_dead_end": node.get("is_dead_end", False),
                }
            )

        result = {
            "anchors": anchors,
            "dead_ends": dead_ends,
            "findings": findings,
            "task_objects": task_objects,
        }

        lines = ["## 推理轨迹"]
        if anchors:
            lines.append(f"\n**已探索对象（{len(anchors)} 个）：**")
            for a in anchors:
                status = "❌ 死路" if a["is_dead_end"] else "✅ 有效"
                lines.append(f"  - {a['object_code']} [{status}]")
                if a["findings_summary"]:
                    lines.append(f"    结论：{a['findings_summary']}")
        else:
            lines.append("\n暂无探索记录。")

        if dead_ends:
            lines.append(f"\n**已排除路径（{len(dead_ends)} 条）：**")
            for d in dead_ends:
                lines.append(f"  - {d['object_code']}：{d.get('reason', '')}")

        if findings:
            lines.append(f"\n**已确认结论（{len(findings)} 条）：**")
            for f_item in findings:
                lines.append(f"  - {f_item}")

        if task_objects:
            lines.append(f"\n**已物化任务对象（{len(task_objects)} 个）：**")
            for t_obj in task_objects:
                lines.append(
                    f"  - {t_obj.get('code', '')}（{t_obj.get('row_count', 0)}行）："
                    f"{t_obj.get('summary', '')}"
                )

        lines.append(f"\n---\n原始数据：{json.dumps(result, ensure_ascii=False)}")
        return "\n".join(lines)

    # ── record_finding ─────────────────────────────────────────────────────────

    @tool("record_finding")
    def record_finding(summary: str) -> str:
        """记录推理阶段性结论，写入推理轨迹。

        推理出阶段性发现时立即调用，将关键发现写入 reasoning_graph.findings。
        不要等到最后才汇总——每步有结论就记录。
        纯文字结论用此工具，不要物化数据。

        Args:
            summary: 结论摘要，如"发现 8432 条超时 trace，主要集中在 payment-service"
        """
        state = get_state_fn() or {}
        rg = _get_or_init_rg(state)
        findings = list(rg.get("findings") or [])
        findings.append(summary)
        rg["findings"] = findings
        state["reasoning_graph"] = rg
        return f"已记录结论（第 {len(findings)} 条）：{summary}"

    return [
        goto_ontology,
        activate_anchor,
        mark_dead_end,
        search_ontology,
        get_reasoning_map,
        record_finding,
    ]

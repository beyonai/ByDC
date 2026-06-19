"""进程级工具注册表（Tool Pool）。

存储全量 StructuredTool 对象，不进 LangGraph checkpoint（StructuredTool 含 coroutine 不可序列化）。
AgentState.active_tools 只存工具名（list[str]），llm_call_node 每轮按名字从此表取出工具对象
合并进 tools_map 后传给 llm.bind_tools()。

关键设计：
  - 进程级全局 dict，生命周期与进程相同
  - 所有 ops_* 对象的工具在 start_heartbeat() 时一次性全量注册
  - TOOL_TO_OBJECT 反查表：工具名 → 所属对象 code，供 after_hook 查询 OntologyRelationGraph
  - _RELATION_GRAPH：OntologyRelationGraph 单例，after_hook 调用 get_next_objects()
  - TOOL_POOL_THRESHOLD：工具数超过阈值时启用锚点驱动模式
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# 工具名 → StructuredTool（进程级内存，不可 checkpoint）
TOOL_POOL: dict[str, Any] = {}

# 工具名 → object_code 反查表（after_hook 需要）
TOOL_TO_OBJECT: dict[str, str] = {}

# OntologyRelationGraph 进程级单例
_RELATION_GRAPH: Any = None  # OntologyRelationGraph | None

# AOCI 格式本体索引（进程级缓存，构建一次复用）
_ONTOLOGY_INDEX: str = ""


def get_ontology_index() -> str:
    """返回 AOCI 格式本体索引字符串，未初始化时返回空字符串。"""
    return _ONTOLOGY_INDEX

# 工具池阈值：工具数超过此值时启用锚点驱动模式（LLM 自选锚点 + 渐进式解锁）
# 低于或等于阈值时全量挂载（原有行为不变）
TOOL_POOL_THRESHOLD: int = int(os.getenv("TOOL_POOL_THRESHOLD", "30"))


def is_anchor_mode() -> bool:
    """当前是否处于锚点驱动模式。

    工具池中工具数量超过 TOOL_POOL_THRESHOLD 时返回 True，
    此时 LLM 需要先选择锚点对象（activate_anchor），再渐进式展开。
    低于阈值时全量挂载，直接可用，返回 False。
    """
    return len(TOOL_POOL) > TOOL_POOL_THRESHOLD


# 进程级 OntologyLoader 单例（供 anchor_tools.py 判断 View/Object 用）
_SHARED_LOADER: Any = None  # OntologyLoader | None


def _get_shared_loader() -> Any:
    """返回进程级 OntologyLoader 单例，未初始化时返回 None。"""
    return _SHARED_LOADER


def register_tool(name: str, tool: Any, *, object_code: str = "") -> None:
    """注册工具到 TOOL_POOL，同时更新 TOOL_TO_OBJECT 反查表。

    Args:
        name: 工具名（与 StructuredTool.name 一致）。
        tool: StructuredTool 实例。
        object_code: 工具所属的本体对象 code（如 "ops_langfuse_trace"）。
    """
    TOOL_POOL[name] = tool
    if object_code:
        TOOL_TO_OBJECT[name] = object_code


def get_tools(names: list[str]) -> dict[str, Any]:
    """批量按名字从 TOOL_POOL 取工具对象。

    不存在的名字静默跳过，不报错。

    Returns:
        {tool_name: StructuredTool} 字典，只包含 TOOL_POOL 中存在的工具。
    """
    return {n: TOOL_POOL[n] for n in names if n in TOOL_POOL}


def _get_object_code_by_tool(tool_name: str) -> str | None:
    """从 TOOL_TO_OBJECT 反查工具所属的本体对象 code。

    Returns:
        object_code 字符串；工具未注册时返回 None。
    """
    return TOOL_TO_OBJECT.get(tool_name)


def get_relation_graph() -> Any:
    """返回 OntologyRelationGraph 进程级单例，未初始化时返回 None。"""
    return _RELATION_GRAPH


def _init_ext_tool_pool(
    resource_path: str | Path,
    loader: Any = None,
    ext_codes: list[str] | None = None,
    name_prefix: str | None = None,
) -> None:
    """扫描 OWL 目录下的对象，全量加载到 TOOL_POOL（初始全部 LOCKED）。

    两种调用模式：
    - ext_codes 指定（byclaw-data worker 模式）：只加载列表中的对象，由 extResourceList 控制
    - ext_codes=None（直接调用模式）：扫描 object/ 目录，name_prefix 过滤前缀（None=全量）

    Args:
        resource_path: 本体资源根目录（含 object/ 子目录）。
        loader: 已 load 好的 OntologyLoader 实例，与 TOOL_POOL 工具生成共用同一实例。
        ext_codes: 指定加载的对象 code 列表。None 表示扫描目录。
        name_prefix: ext_codes=None 时的目录扫描前缀过滤（None=全量，"ops_"=只加载ops_*）。
    """
    global _RELATION_GRAPH, _SHARED_LOADER  # noqa: PLW0603
    _SHARED_LOADER = loader

    resource_path = Path(resource_path)
    object_dir = resource_path / "object"
    if not object_dir.exists():
        logger.warning("TOOL_POOL init: object dir not found: %s", object_dir)
        return

    # 确定要加载的对象列表
    if ext_codes is not None:
        ops_codes = list(ext_codes)
        logger.info(
            "TOOL_POOL init: ext_codes mode, loading %d objects: %s",
            len(ops_codes),
            ops_codes,
        )
    else:
        ops_codes = sorted([
            d.name for d in object_dir.iterdir()
            if d.is_dir() and (name_prefix is None or d.name.startswith(name_prefix))
        ])
        logger.info(
            "TOOL_POOL init: scan mode (prefix=%r), found %d objects: %s",
            name_prefix,
            len(ops_codes),
            ops_codes,
        )

    if not ops_codes:
        logger.warning("TOOL_POOL init: no objects to load")
        return

    # 如果没有传入 loader，用独立 OntologyLoader 加载（避免影响 Agent 的 loader）
    if loader is None:
        try:
            from datacloud_data_sdk.ontology.loader import OntologyLoader  # noqa: PLC0415
            from datacloud_data_service.tools.virtual_action_injector import (  # noqa: PLC0415
                inject_virtual_actions,
            )

            loader = OntologyLoader()
            loader.load_from_owl_resource_directory(resource_path, object_codes=ops_codes)
            inject_virtual_actions(loader)
        except Exception:  # noqa: BLE001
            logger.warning("TOOL_POOL init: failed to create OntologyLoader", exc_info=True)
            return

    # 逐对象注册到 TOOL_POOL
    from datacloud_analysis.tools.ontology_tool_loader import OntologyToolLoader  # noqa: PLC0415

    registered_total = 0
    for obj_code in ops_codes:
        try:
            single_loader = OntologyToolLoader(
                mounted_objects=[obj_code],
                loader=loader,
                resource_path=str(resource_path),
            )
            obj_tools: dict[str, Any] = single_loader.load()
        except Exception:  # noqa: BLE001
            logger.warning(
                "TOOL_POOL init: OntologyToolLoader failed for %s", obj_code, exc_info=True
            )
            continue
        for tool_name, tool_obj in obj_tools.items():
            register_tool(tool_name, tool_obj, object_code=obj_code)
        registered_total += len(obj_tools)
        if obj_tools:
            logger.debug("TOOL_POOL init: %s → %s", obj_code, sorted(obj_tools.keys()))

    logger.info(
        "TOOL_POOL init: registered %d tools from %d objects",
        registered_total,
        len(ops_codes),
    )

    # 构建 OntologyRelationGraph 单例（从 loader 内存读取，零额外 IO）
    if loader is not None:
        try:
            from datacloud_analysis.tools.ontology_relation_graph import (  # noqa: PLC0415
                OntologyRelationGraph,
            )

            _RELATION_GRAPH = OntologyRelationGraph(loader)
            logger.info(
                "OntologyRelationGraph: built %d relations from OntologyLoader",
                len(_RELATION_GRAPH._relations),
            )
        except Exception:  # noqa: BLE001
            logger.warning("OntologyRelationGraph: init failed", exc_info=True)


def _infer_object_code(tool_name: str, ops_codes: list[str]) -> str:
    """从工具名推断所属 object_code。

    策略：找 ops_codes 中最长的能匹配工具名后缀的 code。
    例：tool_name="get_spans"，无法直接匹配；
        tool_name="query_ops_agent_trace" → 匹配 "ops_agent_trace"。
    """
    for code in sorted(ops_codes, key=len, reverse=True):
        if tool_name.endswith(code) or code in tool_name:
            return code
    return ""

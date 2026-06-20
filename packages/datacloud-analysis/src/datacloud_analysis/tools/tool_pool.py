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

    只统计 object/view 工具数（排除 activate_skill_* skill wrapper），
    避免 skill wrapper 注册后意外触发 anchor_mode。
    工具数超过 TOOL_POOL_THRESHOLD 时返回 True。
    """
    object_tool_count = sum(1 for name in TOOL_POOL if not name.startswith("activate_skill_"))
    return object_tool_count > TOOL_POOL_THRESHOLD


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
        ops_codes = sorted(
            [
                d.name
                for d in object_dir.iterdir()
                if d.is_dir() and (name_prefix is None or d.name.startswith(name_prefix))
            ]
        )
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


# ── Skill wrapper 注册 ────────────────────────────────────────────────────────


def _make_skill_wrapper(skill: dict[str, Any]) -> Any:
    """为单个 skill 生成 activate_skill_<name> StructuredTool。

    wrapper 函数体负责：
      1. 读 SKILL.md frontmatter（_parse_skill_frontmatter_cached）
      2. 执行 Level3 data_check preconditions
      3. 通过后加载 SKILL.md body，执行占位符替换，返回步骤指令
    """
    from langchain_core.tools import tool as _tool  # noqa: PLC0415

    from datacloud_analysis.tools.activate_skill import (  # noqa: PLC0415
        _load_skill_body,
    )

    skill_location: str = skill["location"]
    skill_name: str = skill["name"]
    delegation: str = skill.get("delegation", "auto")  # type: ignore[assignment]
    step_count: int = int(skill.get("step_count", 0))  # type: ignore[arg-type]

    # delegation 提示写入工具描述，LLM 据此决策是否用 sub_agent
    if delegation == "required":
        delegation_hint = "（步骤多，必须通过 sub_agent 分身执行）"
    elif delegation == "never":
        delegation_hint = "（轻量 skill，在主 Agent 直接执行）"
    else:
        delegation_hint = (
            f"（共 {step_count} 步，步骤多时建议通过 sub_agent 分身执行）" if step_count > 5 else ""
        )
    description = f"{skill['description']}{delegation_hint}"

    wrapper_tool_name = f"activate_skill_{skill_name.replace('-', '_')}"

    @_tool(wrapper_tool_name, description=description)
    async def wrapper() -> str:
        fm = _parse_skill_frontmatter_cached(skill_location)
        ok = await _check_preconditions_data_check(fm, cache=_get_request_cache())
        if not ok:
            return f"[skill '{skill_name}' 前置条件不满足，建议转 ReAct 自由探索]"
        tools_dict = dict(TOOL_POOL.items())
        body, warnings, err = _load_skill_body(skill_location, tools_dict)
        if err:
            return err
        result = f"# Skill: {skill_name}\n\n{body}"
        if warnings:
            result += "\n\n" + "\n".join(warnings)
        return result

    return wrapper


def register_skill_wrappers(catalog: list[dict[str, Any]]) -> None:
    """扫描 skill catalog，为每个 skill 注册 activate_skill_<name> wrapper 到 TOOL_POOL。

    跳过 required_tools 不满足的 skill。
    skill wrapper 不加入 OntologyRelationGraph，OWL after_hook 不会解锁它。
    """
    for skill in catalog:
        required: list[str] = skill.get("required_tools") or []  # type: ignore[assignment]
        missing = [t for t in required if t not in TOOL_POOL]
        if missing:
            logger.warning(
                "skill %r 跳过注册：required_tools %s 未全部加载",
                skill.get("name"),
                missing,
            )
            continue
        name: str = skill["name"]  # type: ignore[assignment]
        wrapper_name = f"activate_skill_{name.replace('-', '_')}"
        TOOL_POOL[wrapper_name] = _make_skill_wrapper(skill)
        TOOL_TO_OBJECT[wrapper_name] = f"skill_{name}"
        logger.debug("register_skill_wrappers: registered %s", wrapper_name)

    logger.info(
        "register_skill_wrappers: registered %d skill wrappers",
        sum(1 for k in TOOL_POOL if k.startswith("activate_skill_")),
    )


def _parse_skill_frontmatter_cached(abs_path: str) -> dict[str, Any]:
    """读取并缓存 SKILL.md frontmatter（进程级，TTL=300s）。"""
    import time  # noqa: PLC0415
    from pathlib import Path  # noqa: PLC0415

    from datacloud_analysis.skills.catalog import parse_skill_frontmatter  # noqa: PLC0415

    now = time.monotonic()
    cached = _SKILL_FM_CACHE.get(abs_path)
    if cached is not None:
        ts, fm = cached
        if now - ts < _SKILL_FM_CACHE_TTL:
            return fm

    skill_dir = Path(abs_path).parent
    result = parse_skill_frontmatter(skill_dir) or {}
    _SKILL_FM_CACHE[abs_path] = (now, result)
    return result


def _get_request_cache() -> dict[str, Any]:
    """返回当前请求级的 data_check 缓存 dict（生命周期 = 单次请求）。"""
    try:
        from datacloud_data_sdk.context import get_current_context  # noqa: PLC0415

        ctx = get_current_context()
        extras: dict[str, Any] = getattr(ctx, "extras", None) or {}
        if "_skill_data_check_cache" not in extras:
            extras["_skill_data_check_cache"] = {}
        return extras["_skill_data_check_cache"]  # type: ignore[return-value]
    except Exception:  # noqa: BLE001
        return {}


async def _check_preconditions_data_check(
    fm: dict[str, Any],
    cache: dict[str, Any],
) -> bool:
    """执行 preconditions 中的 data_check 规则，全部通过返回 True。

    cache key = f"{action}:{json(params_resolved)}"
    """
    import json  # noqa: PLC0415
    import re  # noqa: PLC0415

    preconditions: list[dict[str, Any]] = fm.get("preconditions") or []
    data_checks = [r for r in preconditions if r.get("type") == "data_check"]
    if not data_checks:
        return True

    try:
        from datacloud_data_sdk.context import get_current_context  # noqa: PLC0415

        ctx = get_current_context()
        extras: dict[str, Any] = getattr(ctx, "extras", None) or {}
        state_dict: dict[str, Any] = extras.get("_current_state") or {}
    except Exception:  # noqa: BLE001
        state_dict = {}

    def _resolve_params(params: dict[str, Any]) -> dict[str, Any]:
        def _sub(v: str) -> str:
            def replacer(m: re.Match[str]) -> str:
                key = m.group(1)
                return str(state_dict.get(key) or extras.get(key) or "")

            return re.sub(r"\{\{ctx\.(\w+)\}\}", replacer, v)

        return {k: _sub(v) if isinstance(v, str) else v for k, v in params.items()}

    for rule in data_checks:
        action: str = rule.get("action", "")
        params = _resolve_params(dict(rule.get("params") or {}))
        cache_key = f"{action}:{json.dumps(params, sort_keys=True, ensure_ascii=False)}"

        if cache_key in cache:
            result = cache[cache_key]
        else:
            # 找到对应工具并调用
            tool_name = action.split(".")[-1] if "." in action else action
            tool_obj = TOOL_POOL.get(tool_name)
            if tool_obj is None:
                logger.warning("data_check: tool %r not in TOOL_POOL, skipping", tool_name)
                continue
            try:
                result = await tool_obj.ainvoke(params)
            except Exception as exc:  # noqa: BLE001
                logger.warning("data_check: tool %r failed: %s", tool_name, exc)
                cache[cache_key] = None
                return False
            cache[cache_key] = result

        assert_expr: str = rule.get("assert", "")
        if assert_expr:
            try:
                passed = bool(eval(assert_expr, {"result": result}))  # noqa: S307
            except Exception:  # noqa: BLE001
                passed = False
            if not passed:
                return False

    return True


# 进程级 skill frontmatter 缓存
_SKILL_FM_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_SKILL_FM_CACHE_TTL: float = 300.0

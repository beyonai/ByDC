"""Built-in tool hook: Step1 复杂度判断 + Step2 双通道歧义判断（v3）。

流程：
  1. 非 query_*/compute_* 工具 → 直接跳过
  2. 剥除元字段（query, complex_conditions, 旧版三字段）
  3. Step 1：complex_conditions 非空 → is_complex=True
  4. Step 2：_get_field_catalog 参数术语映射检查
     a. 全部 1:1 命中 → CLEAR
        is_complex=False → 返回 None（OQL 直查）
        is_complex=True  → redirect → data_query_*
     b. 存在未命中项 → NEED_CONFIRM
        → analyze_query_clarification_query/compute（TODO 待实现，现返回固定 stub）
        → interrupt 追问
        → 恢复后 _apply_resume_to_tool_params 写回 filters
        is_complex=False → patch（OQL 直查）
        is_complex=True  → redirect → data_query_*
"""

from __future__ import annotations

import json
import logging
from typing import Any

from datacloud_analysis.tool_hook_plugins.types import HookContext, HookDecision

try:
    from langgraph.types import interrupt  # type: ignore[import]
except ImportError:  # pragma: no cover
    interrupt = None  # type: ignore[assignment]

PLUGIN_ID = "builtin.query_clarification"
PRIORITY = 100
ENABLED = True

logger = logging.getLogger(__name__)

_QUERY_PREFIXES: frozenset[str] = frozenset({"query_", "compute_"})
_DATA_TOOL_PREFIXES: frozenset[str] = frozenset({"query_", "data_query_", "compute_"})


def _is_query_or_compute_tool(tool_name: str) -> bool:
    """仅匹配 query_* / compute_*（不含 data_query_*）。"""
    return any(tool_name.startswith(p) for p in _QUERY_PREFIXES)


def _is_data_tool(tool_name: str) -> bool:
    """判断是否为数据类工具（query_/data_query_/compute_ 前缀）。"""
    return any(tool_name.startswith(p) for p in _DATA_TOOL_PREFIXES)


def _scope_code_from_tool(tool_name: str) -> str:
    """从 query_ads_foo → ads_foo，compute_ads_foo → ads_foo。"""
    for prefix in ("query_", "compute_"):
        if tool_name.startswith(prefix):
            return tool_name[len(prefix) :]
    return tool_name


def _get_field_catalog(
    tool_name: str,
    ctx: HookContext,
) -> dict[str, str]:
    """从 OntologyLoader 读取当前工具的字段目录 {term → field_code}。

    返回字典包含：
    - field_code → field_code（field_code 本身）
    - field_name（中文名）→ field_code
    loader=None 时返回空 dict。
    """
    loader: Any = (ctx.get("metadata") or {}).get("loader")
    if loader is None:
        return {}

    scope_code = _scope_code_from_tool(tool_name)
    catalog: dict[str, str] = {}

    try:
        # 先尝试作为对象加载
        ontology_class = loader.get_ontology_class(scope_code)
        for f in ontology_class.fields:
            code = getattr(f, "field_code", None) or getattr(f, "property_code", None)
            name = getattr(f, "field_name", None) or getattr(f, "property_name", None)
            if code:
                catalog[code] = code
                if name and name != code:
                    catalog[name] = code
    except Exception:  # noqa: BLE001
        # 尝试作为视图加载
        try:
            view = loader.get_view(scope_code)
            for obj in getattr(view, "objects", []):
                for f in getattr(obj, "fields", []):
                    code = getattr(f, "field_code", None) or getattr(f, "property_code", None)
                    name = getattr(f, "field_name", None) or getattr(f, "property_name", None)
                    if code:
                        catalog[code] = code
                        if name and name != code:
                            catalog[name] = code
        except Exception:  # noqa: BLE001
            pass

    return catalog


def _collect_terms_from_params(tool_params: dict[str, Any]) -> list[str]:
    """从 tool_params 收集需要映射的术语列表（filters.field、select 项等）。

    优先读取 field_name_cn（LLM 填写的中文名），fallback 到 field（向后兼容）。
    """

    def _get_field_term(item: dict[str, Any]) -> str | None:
        v = item.get("field_name_cn") or item.get("field")
        return str(v) if v else None

    terms: list[str] = []
    for f in tool_params.get("filters", []):
        if isinstance(f, dict):
            t = _get_field_term(f)
            if t:
                terms.append(t)
    for s in tool_params.get("select", []):
        if s:
            terms.append(str(s))
    for d in tool_params.get("dimensions", []):
        if isinstance(d, dict):
            t = _get_field_term(d)
            if t:
                terms.append(t)
    for m in tool_params.get("metrics", []):
        if isinstance(m, dict):
            t = _get_field_term(m)
            if t:
                terms.append(t)
    for o in tool_params.get("order_by", []):
        if isinstance(o, dict):
            t = _get_field_term(o)
            if t:
                terms.append(t)
    for h in tool_params.get("having", []):
        if isinstance(h, dict):
            t = _get_field_term(h)
            if t:
                terms.append(t)
    return terms


def _resolve_terms(
    terms: list[str],
    catalog: dict[str, str],
) -> tuple[dict[str, str], list[str]]:
    """将术语列表映射到 field_code。

    Returns:
        resolved: {term → field_code} 1:1 命中的映射
        unresolved: 未命中 catalog 的术语列表
    """
    resolved: dict[str, str] = {}
    unresolved: list[str] = []
    for term in terms:
        if term in catalog:
            resolved[term] = catalog[term]
        else:
            unresolved.append(term)
    return resolved, unresolved


def _apply_resolved_to_params(
    tool_params: dict[str, Any],
    resolved: dict[str, str],
) -> dict[str, Any]:
    """将 resolved 映射写回 tool_params（中文名 → field_code）。

    优先处理 field_name_cn：解析后写入 field 键，并移除 field_name_cn。
    fallback 到旧 field 键（向后兼容）。
    """
    patched = dict(tool_params)

    def _map(term: str) -> str:
        return resolved.get(term, term)

    def _translate_field(item: dict[str, Any]) -> dict[str, Any]:
        """将 field_name_cn 解析为 field_code，写入 field 键，移除 field_name_cn。"""
        if not isinstance(item, dict):
            return item
        cn_val = item.get("field_name_cn")
        if cn_val:
            resolved_code = _map(str(cn_val))
            new_item = {k: v for k, v in item.items() if k != "field_name_cn"}
            new_item["field"] = resolved_code
            return new_item
        old_field = item.get("field")
        if old_field:
            return {**item, "field": _map(str(old_field))}
        return item

    patched["filters"] = [
        _translate_field(f) if isinstance(f, dict) else f for f in patched.get("filters", [])
    ]
    patched["select"] = [_map(s) for s in patched.get("select", [])]
    patched["dimensions"] = [
        _translate_field(d) if isinstance(d, dict) else d for d in patched.get("dimensions", [])
    ]
    patched["metrics"] = [
        _translate_field(m) if isinstance(m, dict) else m for m in patched.get("metrics", [])
    ]
    patched["order_by"] = [
        _translate_field(o) if isinstance(o, dict) else o for o in patched.get("order_by", [])
    ]
    patched["having"] = [
        _translate_field(h) if isinstance(h, dict) else h for h in patched.get("having", [])
    ]
    return patched


def _build_redirect_decision(
    tool_name: str,
    query: str,
    tool_params: dict[str, Any],
) -> HookDecision:
    """构建 redirect HookDecision，路由到 data_query_* 工具。"""
    scope_code = _scope_code_from_tool(tool_name)
    target_tool = f"data_query_{scope_code}"

    # 将已解析的参数序列化为 contextKnowledge 供 PlanAgent 使用
    context_knowledge = json.dumps(
        {
            "query": query,
            "resolved_params": {
                k: v for k, v in tool_params.items() if k not in ("query", "complex_conditions")
            },
        },
        ensure_ascii=False,
    )

    return {
        "action": "redirect",
        "tool": target_tool,
        "params": {
            "query": query,
            "contextKnowledge": context_knowledge,
        },
    }


# ── TODO 占位：澄清分析函数（罗同学实现）─────────────────────────────────────


def analyze_query_clarification_query(
    query: str,
    ontology_code: str,
    structured_query: dict[str, Any],
) -> dict[str, Any]:
    """TODO(罗同学): 分析 query_* 调用的歧义，返回 paradigmList 供 interrupt 使用。

    当前 stub：固定返回 needsXX=True + 空 paradigmList，触发 interrupt 追问。
    实现后需根据 ontology_code 的字段 Schema 做真实召回。
    """
    # STUB：固定返回，使流程可以跑通
    return {
        "needsClarification": True,
        "form": json.dumps({"paradigmList": []}),
    }


def analyze_query_clarification_compute(
    query: str,
    ontology_code: str,
    structured_compute: dict[str, Any],
) -> dict[str, Any]:
    """TODO(罗同学): 分析 compute_* 调用的歧义，返回 paradigmList 供 interrupt 使用。

    当前 stub：固定返回 needsXX=True + 空 paradigmList，触发 interrupt 追问。
    """
    return {
        "needsClarification": True,
        "form": json.dumps({"paradigmList": []}),
    }


def format_clarification_query(
    original_params: dict[str, Any],
    form: dict[str, Any],
) -> dict[str, Any]:
    """TODO(罗同学): 将用户 paradigm 选择合并回 query_* 参数 dict。

    当前 stub：原样返回 original_params，不做任何修改。
    """
    return dict(original_params)


def format_clarification_compute(
    original_params: dict[str, Any],
    form: dict[str, Any],
) -> dict[str, Any]:
    """TODO(罗同学): 将用户 paradigm 选择合并回 compute_* 参数 dict。

    当前 stub：原样返回 original_params，不做任何修改。
    """
    return dict(original_params)


# ── 核心 resume 写回 ──────────────────────────────────────────────────────────


def _apply_resume_to_tool_params(
    ctx: HookContext,
    tool_name: str,
    resume_value: Any,
    user_query: str,
) -> None:
    """将用户 paradigm 选择写回 tool_params，防止恢复时再次触发歧义。

    resume_value 结构：{"paradigmList": [{"keyword": "...", "choiceKeyword": "...", ...}]}
    """
    selected: list[dict[str, Any]] = []
    if isinstance(resume_value, dict):
        selected = resume_value.get("paradigmList", [])

    tool_params: dict[str, Any] = dict(ctx.get("tool_params") or {})

    # 构建 keyword → choiceKeyword 映射（用户的选择结果）
    choice_map: dict[str, str] = {}
    for item in selected:
        kw = item.get("keyword") or ""
        choice = item.get("choiceKeyword") or ""
        if kw and choice:
            choice_map[kw] = choice

    if not choice_map:
        return

    def _remap(term: str) -> str:
        return choice_map.get(term, term)

    def _resume_translate_field(item: dict[str, Any]) -> dict[str, Any]:
        """将用户选择的 choiceKeyword 写回 field，支持 field_name_cn → field 翻译。"""
        if not isinstance(item, dict):
            return item
        cn_val = item.get("field_name_cn")
        if cn_val and str(cn_val) in choice_map:
            new_item = {k: v for k, v in item.items() if k != "field_name_cn"}
            new_item["field"] = choice_map[str(cn_val)]
            return new_item
        old_field = item.get("field")
        if old_field:
            return {**item, "field": _remap(str(old_field))}
        return item

    # 写回 filters.field
    tool_params["filters"] = [
        _resume_translate_field(f) if isinstance(f, dict) else f
        for f in tool_params.get("filters", [])
    ]
    # 写回 select
    tool_params["select"] = [_remap(s) for s in tool_params.get("select", [])]
    # 写回 dimensions
    tool_params["dimensions"] = [
        _resume_translate_field(d) if isinstance(d, dict) else d
        for d in tool_params.get("dimensions", [])
    ]
    # 写回 metrics
    tool_params["metrics"] = [
        _resume_translate_field(m) if isinstance(m, dict) else m
        for m in tool_params.get("metrics", [])
    ]
    # 写回 order_by
    tool_params["order_by"] = [
        _resume_translate_field(o) if isinstance(o, dict) else o
        for o in tool_params.get("order_by", [])
    ]
    # 写回 having
    tool_params["having"] = [
        _resume_translate_field(h) if isinstance(h, dict) else h
        for h in tool_params.get("having", [])
    ]
    ctx["tool_params"] = tool_params


# ── 主 hook 入口 ──────────────────────────────────────────────────────────────


async def before_call_back(ctx: HookContext) -> HookDecision | None:
    """Step1 复杂度判断 + Step2 双通道歧义判断。

    Args:
        ctx: HookContext，含 tool_name / tool_params / metadata(loader) 等。

    Returns:
        None               — 简单查询 CLEAR，放行给 QueryExecutor（OQL）
        redirect decision  — 复杂查询 CLEAR，路由到 data_query_*
        patch decision     — 歧义消除后恢复，更新 tool_params
        redirect decision  — COMPLEX + 歧义消除后，路由到 data_query_*
    """
    tool_name: str = ctx.get("tool_name", "")

    # 非 query_*/compute_* 工具直接跳过
    if not _is_query_or_compute_tool(tool_name):
        return None

    # ── 剥除元字段（before_callback 消费，不透传给底层执行体）────────────────
    tool_params: dict[str, Any] = dict(ctx.get("tool_params") or {})
    query: str = str(tool_params.pop("query", "") or "")
    complex_conditions: list[str] = list(tool_params.pop("complex_conditions", None) or [])

    # 兼容旧版元字段（过渡期）
    tool_params.pop("intent_reason", None)
    tool_params.pop("extraction_confidence", None)
    tool_params.pop("ambiguous_params", None)

    ctx["tool_params"] = tool_params

    logger.info(
        "[query_clarification] tool=%s | is_complex=%s | query=%s",
        tool_name,
        bool(complex_conditions),
        query[:80],
    )

    # ── Step 1：复杂度判断 ────────────────────────────────────────────────────
    is_complex: bool = bool(complex_conditions)

    # ── Step 2：双通道歧义判断 ────────────────────────────────────────────────
    catalog = _get_field_catalog(tool_name, ctx)
    terms = _collect_terms_from_params(tool_params)

    # resolved 始终初始化为空 dict；catalog 有值时才做术语解析
    resolved: dict[str, str] = {}

    if catalog and terms:
        resolved, unresolved = _resolve_terms(terms, catalog)

        if unresolved:
            # 存在未命中术语 → NEED_CONFIRM
            logger.info("[query_clarification] NEED_CONFIRM: unresolved=%s", unresolved)
            # 调用澄清分析（当前 stub，TODO 待实现）
            scope_code = _scope_code_from_tool(tool_name)
            if tool_name.startswith("compute_"):
                clarify_result = analyze_query_clarification_compute(query, scope_code, tool_params)
            else:
                clarify_result = analyze_query_clarification_query(query, scope_code, tool_params)

            try:
                paradigm_list = json.loads(clarify_result.get("form", "{}") or "{}").get(
                    "paradigmList", []
                )
            except Exception:  # noqa: BLE001
                paradigm_list = []

            resume_value = interrupt(
                {
                    "prompt": "查询条件存在歧义，请确认查询维度",
                    "reason_code": "PARADIGM_CLARIFICATION",
                    "ask_user_payload": {"paradigmList": paradigm_list},
                }
            )
            # 恢复后写回 tool_params（_apply_resume_to_tool_params 内部已处理 field_name_cn → field）
            _apply_resume_to_tool_params(ctx, tool_name, resume_value, query)
            tool_params = dict(ctx["tool_params"])

            # 兜底翻译：resume 后仍可能残留未命中的 field_name_cn（用户未选或选择为空）
            # 对这些残留项做原样透传（field_name_cn → field），确保 SQL builder 不报语法错误
            tool_params = _apply_resolved_to_params(tool_params, resolved)
            ctx["tool_params"] = tool_params

            # 恢复后路由
            if is_complex:
                return _build_redirect_decision(tool_name, query, tool_params)
            return {"action": "patch", "patch": {"tool_params": tool_params}}
    else:
        if not catalog and terms:
            # loader 未注入时打警告：field_name_cn 无法映射到 field_code，将原样透传
            logger.warning(
                "[query_clarification] loader not available, "
                "field_name_cn will be passed as-is to field (cannot resolve to field_code)"
            )
        else:
            logger.debug("[query_clarification] no terms to resolve, skip term resolution")

    # ── 字段名结构翻译（无条件执行）────────────────────────────────────────────
    # 无论 catalog 是否为空，都必须将 field_name_cn 翻译为 field 键，
    # 确保 SQL builder 能读到 field（resolved={} 时原样透传中文名值）。
    # 若 catalog 有映射，则写入 field_code；否则写入原始中文名（至少避免 SQL 语法错误）。
    patched_params = _apply_resolved_to_params(tool_params, resolved)
    ctx["tool_params"] = patched_params
    tool_params = patched_params

    # ── 路由决策 ─────────────────────────────────────────────────────────────
    if is_complex:
        return _build_redirect_decision(tool_name, query, tool_params)

    # SIMPLE + CLEAR → 放行
    return None

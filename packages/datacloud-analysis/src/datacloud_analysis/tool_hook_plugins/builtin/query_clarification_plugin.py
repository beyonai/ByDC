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
        → analyze_query_clarification → interrupt 追问
        → 恢复后 format_clarification 写回参数
        is_complex=False → patch（OQL 直查）
        is_complex=True  → redirect → data_query_*
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

try:
    from datacloud_knowledge.intent.clarification import (
        analyze_query_clarification_compute as _sdk_analyze_compute,
    )
    from datacloud_knowledge.intent.clarification import (
        analyze_query_clarification_query as _sdk_analyze_query,
    )
    from datacloud_knowledge.intent.clarification import (
        format_clarification_compute as _sdk_format_compute,
    )
    from datacloud_knowledge.intent.clarification import (
        format_clarification_query as _sdk_format_query,
    )

    _HAS_SDK_CLARIFICATION = True
except ImportError:  # pragma: no cover
    _HAS_SDK_CLARIFICATION = False
    _sdk_analyze_compute = None  # type: ignore[assignment]
    _sdk_analyze_query = None  # type: ignore[assignment]
    _sdk_format_compute = None  # type: ignore[assignment]
    _sdk_format_query = None  # type: ignore[assignment]

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

# LLM 可能以 JSON 字符串形式传递的列表字段
_JSON_LIST_FIELDS: frozenset[str] = frozenset(
    {"select", "order_by", "filters", "dimensions", "metrics", "having"}
)

# 字段编码识别：纯 ASCII identifier（snake_case / camelCase）
_FIELD_CODE_RE: re.Pattern[str] = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _is_field_code(term: str) -> bool:
    """Return True if term looks like a field code (ASCII identifier, no Chinese).

    字段编码（如 total_revenue）不需要 catalog 查询，直接透传；
    中文名（如 '管理网格总营收（万元）'）需要 catalog 查询后映射。
    """
    return bool(_FIELD_CODE_RE.match(term))


def _normalize_json_fields(params: dict[str, Any]) -> dict[str, Any]:
    """将 LLM 以 JSON 字符串形式传递的列表字段解码为 list。

    LLM tool call 有时将 select / order_by 等字段序列化为 JSON 字符串
    （如 ``'["管理网格名称", "企业数量"]'``），而非原生 list。
    逐字符迭代字符串会导致术语提取逐字拆分，产生 119 个单字"术语"。
    """
    normalized = dict(params)
    for key in _JSON_LIST_FIELDS:
        val = normalized.get(key)
        if isinstance(val, str):
            val = val.strip()
            if val.startswith("["):
                try:
                    parsed = json.loads(val)
                    if isinstance(parsed, list):
                        normalized[key] = parsed
                        logger.debug("[query_clarification] decoded JSON string field %s", key)
                except (json.JSONDecodeError, ValueError):
                    pass
    return normalized


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
            for f in getattr(view, "fields", []):
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
        if not v:
            return None
        s = str(v)
        # 字段编码不需要 catalog 查询，跳过；只收集需要映射的中文名
        return None if _is_field_code(s) else s

    terms: list[str] = []
    for f in tool_params.get("filters") or []:
        if isinstance(f, dict):
            t = _get_field_term(f)
            if t:
                terms.append(t)
    for s in tool_params.get("select") or []:
        # select 是字符串列表：字段编码直通，只收集中文名
        if s and not _is_field_code(str(s)):
            terms.append(str(s))
    for d in tool_params.get("dimensions") or []:
        if isinstance(d, dict):
            t = _get_field_term(d)
            if t:
                terms.append(t)
    for m in tool_params.get("metrics") or []:
        if isinstance(m, dict):
            t = _get_field_term(m)
            if t:
                terms.append(t)
    for o in tool_params.get("order_by") or []:
        if isinstance(o, dict):
            t = _get_field_term(o)
            if t:
                terms.append(t)
    for h in tool_params.get("having") or []:
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


# LLM 可能使用的非标准排序方向键（都应规范化为 Schema 定义的 direction）
_SORT_KEY_ALIASES: frozenset[str] = frozenset({"sort", "op", "order"})


def _normalize_sort_key(item: dict[str, Any]) -> dict[str, Any]:
    """将 LLM 可能使用的非标准排序键规范化为 Schema 定义的 direction 键。

    LLM 有时发送 {"sort": "asc"} / {"op": "asc"} / {"order": "asc"}
    而非 Schema 定义的 {"direction": "asc"}，底层 SQL builder 不识别这些键，
    导致排序方向丢失（使用默认 DESC）。

    规则：
    - 存在别名键且 direction 不存在 → 取第一个别名键的值写入 direction，移除所有别名键
    - direction 已存在 → 保留 direction，仅移除冗余的别名键
    - 不含任何别名键 → 原样返回
    """
    if not isinstance(item, dict):
        return item
    alias_keys = _SORT_KEY_ALIASES & item.keys()
    if not alias_keys:
        return item
    new_item = {k: v for k, v in item.items() if k not in _SORT_KEY_ALIASES}
    if "direction" not in new_item:
        # 取任一别名键的值（通常只有一个）
        new_item["direction"] = next(item[k] for k in _SORT_KEY_ALIASES if k in item)
    return new_item


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
        """将 field_name_cn 或 field（中文名/编码）解析为 field_code，写入 field 键。

        - field_name_cn / field = 中文名 → catalog 映射 → field_code
        - field_name_cn / field = 字段编码 → 直接透传（跳过 catalog）
        """
        if not isinstance(item, dict):
            return item
        # 优先读 field_name_cn，fallback 到 field
        raw = item.get("field_name_cn") or item.get("field")
        if raw:
            s = str(raw)
            # 字段编码直接透传；中文名走 catalog 映射
            resolved_code = s if _is_field_code(s) else _map(s)
            new_item = {k: v for k, v in item.items() if k not in ("field_name_cn", "field")}
            new_item["field"] = resolved_code
            return new_item
        return item

    patched["filters"] = [
        _translate_field(f) if isinstance(f, dict) else f for f in patched.get("filters") or []
    ]
    # select 是字符串列表：字段编码直通，中文名走 _map 映射
    patched["select"] = [
        s if _is_field_code(str(s)) else _map(str(s)) for s in patched.get("select") or []
    ]
    patched["dimensions"] = [
        _translate_field(d) if isinstance(d, dict) else d for d in patched.get("dimensions") or []
    ]
    patched["metrics"] = [
        _translate_field(m) if isinstance(m, dict) else m for m in patched.get("metrics") or []
    ]
    patched["order_by"] = [
        _normalize_sort_key(_translate_field(o) if isinstance(o, dict) else o)
        for o in patched.get("order_by") or []
    ]
    patched["having"] = [
        _translate_field(h) if isinstance(h, dict) else h for h in patched.get("having") or []
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


# ── 澄清 SDK 调用 ──────────────────────────────────────────────────────────────


def _analyze_clarification(
    query: str,
    ontology_code: str,
    structured_input: dict[str, Any],
    *,
    is_compute: bool,
) -> tuple[list[dict[str, Any]], str]:
    """调用 SDK 澄清分析，返回 (paradigmList, knowledge)。"""
    if is_compute:
        result = _sdk_analyze_compute(query, ontology_code, structured_input)
    else:
        result = _sdk_analyze_query(query, ontology_code, structured_input)

    logger.info(
        "[query_clarification] SDK result: needs=%s form_len=%d knowledge_len=%d",
        result.needs_clarification,
        len(result.form or ""),
        len(result.knowledge or ""),
    )
    paradigm_list = json.loads(result.form or "{}").get("paradigmList", [])
    logger.info("[query_clarification] paradigmList count=%d", len(paradigm_list))
    return paradigm_list, result.knowledge


def _format_clarification(
    query: str,
    structured_input: dict[str, Any],
    form_str: str,
    knowledge: str,
    *,
    is_compute: bool,
) -> dict[str, Any]:
    """调用 SDK 格式化，返回写回后的参数 dict。SDK 不可用时原样返回。"""
    if not _HAS_SDK_CLARIFICATION:
        return dict(structured_input)
    if is_compute:
        return _sdk_format_compute(query, structured_input, form_str, knowledge)  # type: ignore[misc]
    return _sdk_format_query(query, structured_input, form_str, knowledge)  # type: ignore[misc]


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
    tool_params: dict[str, Any] = _normalize_json_fields(dict(ctx.get("tool_params") or {}))
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
            if interrupt is None:
                logger.warning(
                    "[query_clarification] interrupt unavailable, skip clarification interrupt"
                )
                tool_params = _apply_resolved_to_params(tool_params, resolved)
                ctx["tool_params"] = tool_params
                if is_complex:
                    return _build_redirect_decision(tool_name, query, tool_params)
                return None

            scope_code = _scope_code_from_tool(tool_name)
            structured_input = {**tool_params, "complex_conditions": complex_conditions}
            is_compute = tool_name.startswith("compute_")

            paradigm_list, clarify_knowledge = _analyze_clarification(
                query,
                scope_code,
                structured_input,
                is_compute=is_compute,
            )

            if not paradigm_list:
                # 澄清分析失败或无需澄清，跳过 interrupt，按原流程继续
                logger.info("[query_clarification] paradigmList 为空，跳过澄清 interrupt")
                tool_params = _apply_resolved_to_params(tool_params, resolved)
                ctx["tool_params"] = tool_params
                if is_complex:
                    return _build_redirect_decision(tool_name, query, tool_params)
                return {"action": "patch", "patch": {"tool_params": tool_params}}

            resume_value = interrupt(
                {
                    "prompt": "查询条件存在歧义，请确认查询维度",
                    "reason_code": "PARADIGM_CLARIFICATION",
                    "ask_user_payload": {
                        "paradigmList": paradigm_list,
                        "query": query,
                        # 前端需原样放入 metadata 传回，供 resume 后 format 使用
                        "clarify_knowledge": clarify_knowledge,
                    },
                }
            )

            # resume 后调 SDK format 写回参数
            knowledge = ""
            paradigm_list_from_resume: list[dict[str, Any]] = []
            if isinstance(resume_value, dict):
                meta = resume_value.get("metadata") or {}
                knowledge = str(meta.get("clarify_knowledge") or "")
                para_result = resume_value.get("paradigmResult") or []
                if para_result and isinstance(para_result[0], dict):
                    paradigm_list_from_resume = list(para_result[0].get("paradigmList") or [])
                if not paradigm_list_from_resume:
                    paradigm_list_from_resume = list(meta.get("paradigmList") or [])

            form_str = json.dumps({"paradigmList": paradigm_list_from_resume}, ensure_ascii=False)
            tool_params = _format_clarification(
                query,
                structured_input,
                form_str,
                knowledge,
                is_compute=is_compute,
            )

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

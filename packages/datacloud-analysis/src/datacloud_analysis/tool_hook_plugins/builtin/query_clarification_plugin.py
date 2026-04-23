"""Built-in tool hook: Step1 复杂度判断 + Step2 双通道歧义判断（v3）。

流程：
  1. 非 query_*/compute_* 工具 → 直接跳过
  2. 剥除元字段（query, complex_conditions, 旧版三字段）
  3. Step 1：complex_conditions 非空 → is_complex=True
  4. Step 2：resolve_field_aliases 轻量消歧：
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

import hashlib
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

try:
    from datacloud_knowledge.knowledge_search import resolve_field_aliases

    _HAS_RESOLVE_ALIASES = True
except ImportError:  # pragma: no cover
    resolve_field_aliases = None  # type: ignore[assignment]
    _HAS_RESOLVE_ALIASES = False

from datacloud_analysis.tool_hook_plugins.types import (
    ClarificationNeededError,
    HookContext,
    HookDecision,
)

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

# query_* schema 中不存在的 compute-only 字段；LLM 误填时静默丢弃，确保日志与 schema 一致
_QUERY_STRIP_FIELDS: frozenset[str] = frozenset({"dimensions", "metrics", "having"})


def _make_cache_key(tool_name: str, query: str) -> str:
    """生成澄清缓存键，绑定到 tool_name + query 两元组。"""
    digest = hashlib.md5(query.encode()).hexdigest()[:12]  # noqa: S324
    return f"{tool_name}:{digest}"


# LLM 可能以 JSON 字符串形式传递的列表字段
_JSON_LIST_FIELDS: frozenset[str] = frozenset(
    {"select", "order_by", "filters", "dimensions", "metrics", "having"}
)

# 字段编码识别：纯 ASCII identifier（snake_case / camelCase）
_FIELD_CODE_RE: re.Pattern[str] = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_HAS_CHINESE_RE: re.Pattern[str] = re.compile(r"[\u4e00-\u9fff]")
_NUMERIC_RE: re.Pattern[str] = re.compile(r"^[\d.]+$")
_NUMERIC_CN_RE: re.Pattern[str] = re.compile(r"^[\d.]+[万亿元%‰]+$")
_DATE_RE: re.Pattern[str] = re.compile(
    r"^\d{4}[-/年]\d{1,2}[-/月]?(\d{1,2}日?)?$|^\d{6,8}$|^\d{4}年?$"
)


def _is_field_code(term: str) -> bool:
    """Return True if term looks like a field code (ASCII identifier, no Chinese).

    字段编码（如 total_revenue）不需要 catalog 查询，直接透传；
    中文名（如 '管理网格总营收（万元）'）需要 catalog 查询后映射。
    """
    return bool(_FIELD_CODE_RE.match(term))


def _is_term_value_candidate(value: Any) -> bool:
    """Return True if a filter value looks like a human-readable term.

    值歧义澄清只收集自然语言/中文值，跳过：
    - 空值
    - 纯数字 / 日期 / 百分比等量化值
    - 纯 ASCII 标识符（常见编码值）
    """
    text = str(value).strip()
    if not text:
        return False
    if _NUMERIC_RE.match(text) or _NUMERIC_CN_RE.match(text) or _DATE_RE.match(text):
        return False
    if _is_field_code(text):
        return False
    return bool(_HAS_CHINESE_RE.search(text))


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


def _collect_terms_from_params(
    tool_params: dict[str, Any],
) -> tuple[list[str], list[str]]:
    """从 tool_params 收集需要映射的术语，按类型分组返回。

    Returns:
        (field_terms, value_terms):
          - field_terms: 字段名/别名（filters.field、select、dimensions 等）
          - value_terms: 过滤值（filters.value 中的中文值，op=like 除外）
    """

    def _get_field_term(item: dict[str, Any]) -> str | None:
        v = item.get("field_name_cn") or item.get("field")
        if not v:
            return None
        s = str(v)
        return None if _is_field_code(s) else s

    field_terms: list[str] = []
    value_terms: list[str] = []

    for f in tool_params.get("filters") or []:
        if isinstance(f, dict):
            t = _get_field_term(f)
            if t:
                field_terms.append(t)
            # op=like 是模糊搜索，不需要精确消歧
            if str(f.get("op") or "").lower() != "like":
                raw_value = f.get("value")
                values = raw_value if isinstance(raw_value, list) else [raw_value]
                for value in values:
                    if _is_term_value_candidate(value):
                        value_terms.append(str(value).strip())
    for s in tool_params.get("select") or []:
        if s and not _is_field_code(str(s)):
            field_terms.append(str(s))
    for d in tool_params.get("dimensions") or []:
        if isinstance(d, dict):
            t = _get_field_term(d)
            if t:
                field_terms.append(t)
    for m in tool_params.get("metrics") or []:
        if isinstance(m, dict):
            t = _get_field_term(m)
            if t:
                field_terms.append(t)
    for o in tool_params.get("order_by") or []:
        if isinstance(o, dict):
            t = _get_field_term(o)
            if t:
                field_terms.append(t)
    for h in tool_params.get("having") or []:
        if isinstance(h, dict):
            t = _get_field_term(h)
            if t:
                field_terms.append(t)
    return field_terms, value_terms


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


def _resolve_via_aliases(
    field_terms: list[str],
    value_terms: list[str],
    scope_code: str,
) -> tuple[dict[str, str], list[str]]:
    """轻量级别名消歧（字段 + 值，单次 DB 往返）。

    返回 (resolved, unresolved)。
    resolved 仅含字段名映射（{中文名 → field_code}），值命中直接从 unresolved 移除。
    ambiguous 候选视为 unresolved，交给慢路径处理。
    """
    all_terms = field_terms + value_terms
    if not _HAS_RESOLVE_ALIASES or not all_terms or not scope_code:
        logger.warning("[query_clarification] resolve_field_aliases skip")
        return {}, all_terms
    try:
        result = resolve_field_aliases(
            terms=field_terms,
            scope_code=scope_code,
            resolve_values=bool(value_terms),
            value_terms=value_terms,
        )
        unresolved = list(result.unresolved) + list(result.ambiguous.keys())
        logger.info(
            "[query_clarification] resolve_field_aliases: resolved=%d ambiguous=%d unresolved=%d",
            len(result.resolved),
            len(result.ambiguous),
            len(result.unresolved),
        )
        return result.resolved, unresolved
    except Exception:  # noqa: BLE001
        logger.warning(
            "[query_clarification] resolve_field_aliases failed",
            exc_info=True,
        )
        return {}, all_terms


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
    if "dimensions" in tool_params:
        patched["dimensions"] = [
            _translate_field(d) if isinstance(d, dict) else d
            for d in patched.get("dimensions") or []
        ]
    if "metrics" in tool_params:
        patched["metrics"] = [
            _translate_field(m) if isinstance(m, dict) else m for m in patched.get("metrics") or []
        ]
    patched["order_by"] = [
        _normalize_sort_key(_translate_field(o) if isinstance(o, dict) else o)
        for o in patched.get("order_by") or []
    ]
    if "having" in tool_params:
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
) -> tuple[list[dict[str, Any]], str, bool]:
    """调用 SDK 澄清分析，返回 (paradigmList, knowledge, needs_clarification)。"""
    sdk_fn_name = (
        "analyze_query_clarification_compute" if is_compute else "analyze_query_clarification_query"
    )
    logger.info(
        "[KG-CHAIN] call: datacloud_knowledge.intent.clarification.%s("
        "query=%r, ontology_code=%r, structured_input=%s)",
        sdk_fn_name,
        query[:100],
        ontology_code,
        json.dumps(structured_input, ensure_ascii=False, default=str)[:300],
    )
    if is_compute:
        result = _sdk_analyze_compute(query, ontology_code, structured_input)
    else:
        result = _sdk_analyze_query(query, ontology_code, structured_input)

    logger.info(
        "[KG-CHAIN] result: needs=%s form_len=%d knowledge_len=%d raw_form=%s",
        result.needs_clarification,
        len(result.form or ""),
        len(result.knowledge or ""),
        result.form,
    )
    paradigm_list = json.loads(result.form or "{}").get("paradigmList", [])
    for _p in paradigm_list:
        _results = list(_p.get("paradigmResult") or [])
        if _results:
            logger.info(
                "[KG-CHAIN] paradigm id=%s name=%s results=%s",
                _p.get("paradigmId"),
                _p.get("paradigmName"),
                [
                    {
                        "keyword": _r.get("keyword"),
                        "choiceKeyword": _r.get("choiceKeyword"),
                        "recall": _r.get("recall"),
                        "kid": _r.get("kid"),
                        "ktype": _r.get("ktype"),
                    }
                    for _r in _results
                ],
            )
    return paradigm_list, result.knowledge, result.needs_clarification


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


# ── Resume 路径共享逻辑 ───────────────────────────────────────────────────────


def _execute_resume(
    ctx: HookContext,
    tool_name: str,
    query: str,
    cached: dict[str, Any],
    graph_state: dict[str, Any] | None,
    resume_value: Any,
) -> HookDecision | None:
    """parse resume_value → format_clarification → 清除缓存 → 返回 HookDecision。

    由首次执行路径（interrupt 返回后）和 CACHE HIT 路径（_handle_resume）共同调用，
    是 resume 逻辑的唯一实现来源。
    """
    knowledge = ""
    paradigm_list_from_resume: list[dict[str, Any]] = []
    if isinstance(resume_value, dict):
        outer = resume_value.get("paradigmList") or []
        if outer and isinstance(outer[0], dict):
            paradigm_list_from_resume = list(outer[0].get("paradigmList") or [])
        meta = resume_value.get("metadata") or {}
        knowledge = str(meta.get("clarify_knowledge") or "")
    if not knowledge:
        knowledge = str(cached.get("clarify_knowledge") or "")

    logger.info(
        "[query_clarification] RESUME parsed: paradigm_list_count=%d knowledge_len=%d",
        len(paradigm_list_from_resume),
        len(knowledge),
    )

    structured_input: dict[str, Any] = dict(cached.get("structured_input") or {})
    is_compute: bool = bool(cached.get("is_compute"))
    resolved: dict[str, str] = dict(cached.get("resolved") or {})
    is_complex: bool = bool(cached.get("is_complex"))

    form_str = json.dumps({"paradigmList": paradigm_list_from_resume}, ensure_ascii=False)
    tool_params = _format_clarification(
        query,
        structured_input,
        form_str,
        knowledge,
        is_compute=is_compute,
    )
    logger.info(
        "[query_clarification] format_clarification args:"
        " query=%s | is_compute=%s | knowledge=%s"
        " | structured_input=%s | form_str=%s",
        query[:200],
        is_compute,
        knowledge[:200],
        json.dumps(structured_input, ensure_ascii=False, default=str)[:500],
        form_str[:500],
    )
    logger.info(
        "[query_clarification] format_clarification result: tool_params=%s",
        json.dumps(tool_params, ensure_ascii=False, default=str)[:500],
    )

    if graph_state is not None:
        graph_state.pop("_clarification_cache", None)
    logger.info("[query_clarification] _clarification_cache cleared from state")

    # SDK 回填的可能是官方中文字段名（choiceKeyword），需做二次翻译
    scope_code = _scope_code_from_tool(tool_name)
    _fresh_field_terms, _ = _collect_terms_from_params(tool_params)
    _fresh_resolved, _fresh_unresolved = _resolve_via_aliases(_fresh_field_terms, [], scope_code)
    logger.info(
        "[query_clarification] _execute_resume fresh_resolved=%s",
        _fresh_resolved,
    )
    if _fresh_resolved:
        resolved = {**resolved, **_fresh_resolved}

    tool_params = _apply_resolved_to_params(tool_params, resolved)
    tool_params["query"] = query  # _format_clarification 回填结果不含 query，需补回
    tool_params["query"] = query  # _format_clarification 回填结果不含 query，需补回
    ctx["tool_params"] = tool_params

    if is_complex:
        return _build_redirect_decision(tool_name, query, tool_params)
    return {"action": "patch", "patch": {"tool_params": tool_params}}


async def _handle_resume(
    ctx: HookContext,
    tool_name: str,
    graph_state: dict[str, Any],
    cached: dict[str, Any],
) -> HookDecision | None:
    """CACHE HIT 路径：调用 interrupt() 取回 resume_value，再委托 _execute_resume。

    LangGraph resume 时 interrupt() 直接返回用户提交的值，不再暂停。
    """
    query: str = str((ctx.get("tool_params") or {}).get("query", "") or "")
    paradigm_list: list[dict[str, Any]] = list(cached.get("paradigm_list") or [])
    clarify_knowledge: str = str(cached.get("clarify_knowledge") or "")

    logger.info("[query_clarification] RESUME resume_value type=%s value=%s", "pending", "...")
    resume_value = interrupt(
        {
            "prompt": "查询条件存在歧义，请确认查询维度",
            "reason_code": "PARADIGM_CLARIFICATION",
            "ask_user_payload": {"paradigmList": paradigm_list, "query": query},
            "_clarify_knowledge": clarify_knowledge,
        }
    )
    logger.info(
        "[query_clarification] RESUME resume_value type=%s value=%s",
        type(resume_value).__name__,
        json.dumps(resume_value, ensure_ascii=False, default=str)[:800]
        if resume_value is not None
        else "None",
    )
    return _execute_resume(ctx, tool_name, query, cached, graph_state, resume_value)


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

    # ── V0.3 早返回：clarification_formatted_params 已由 user_clarify_node 注入 ──
    # tool_dispatcher resume 时，state 已含格式化后参数，直接应用并返回，跳过全部分析
    _graph_state: dict[str, Any] | None = (ctx.get("metadata") or {}).get("state")
    if _graph_state is not None:
        _clarify_result = _graph_state.get("clarification_formatted_params")
        if _clarify_result and _clarify_result.get("tool_name") == tool_name:
            logger.info(
                "[query_clarification] V0.3 early-return: clarification_formatted_params hit"
            )
            _raw_query_fp = str((ctx.get("tool_params") or {}).get("query", "") or "")
            _fmt_params = dict(_clarify_result.get("params") or {})
            _is_complex_fp: bool = bool(_clarify_result.get("is_complex"))
            # ── 打印知识图谱侧数据（paradigm_list 每条 paradigmResult）──
            _paradigm_list_fp = list(_clarify_result.get("paradigm_list") or [])
            if not _paradigm_list_fp:
                _analyze_res = dict((_graph_state or {}).get("clarification_analyze_result") or {})
                _paradigm_list_fp = list(_analyze_res.get("paradigm_list") or [])
            for _p in _paradigm_list_fp:
                _p_results = list(_p.get("paradigmResult") or [])
                if _p_results:
                    logger.info(
                        "[query_clarification] KNOWLEDGE-GRAPH paradigm: id=%s name=%s results=%s",
                        _p.get("paradigmId"),
                        _p.get("paradigmName"),
                        [
                            {
                                "keyword": _r.get("keyword"),
                                "choiceKeyword": _r.get("choiceKeyword"),
                                "recall": _r.get("recall"),
                                "kid": _r.get("kid"),
                                "ktype": _r.get("ktype"),
                            }
                            for _r in _p_results
                        ],
                    )
            # choiceKeyword 应与本体 catalog 字段名严格对齐；
            # 若未命中说明知识图谱数据或表单生成有误，需修数据，不做兜底。
            _scope_code_fp = _scope_code_from_tool(tool_name)
            _field_terms_fp, _ = _collect_terms_from_params(_fmt_params)
            _resolved_fp, _unresolved_fp = _resolve_via_aliases(_field_terms_fp, [], _scope_code_fp)
            if _unresolved_fp:
                logger.warning(
                    "[query_clarification] V0.3 DATA-MISMATCH: unresolved terms %s"
                    " not found in ontology catalog — check KG choiceKeyword vs OWL field_name/aliases",
                    _unresolved_fp,
                )
            if _resolved_fp:
                _fmt_params = _apply_resolved_to_params(_fmt_params, _resolved_fp)
            _fmt_params["query"] = _raw_query_fp  # 澄清格式化结果不含 query，需补回
            ctx["tool_params"] = _fmt_params
            if _is_complex_fp:
                return _build_redirect_decision(tool_name, _raw_query_fp, _fmt_params)
            return {"action": "patch", "patch": {"tool_params": _fmt_params}}

    # ── CACHE HIT 早返回：跳过全部分析逻辑，直接进入 resume 路径 ─────────────
    # 注意：用 is not None 而非 bool 判断，state={} 是合法的可写空 dict
    if _graph_state is not None:
        _raw_query = str((ctx.get("tool_params") or {}).get("query", "") or "")
        _ck = _make_cache_key(tool_name, _raw_query)
        _cached = _graph_state.get("_clarification_cache")
        if _cached and _cached.get("cache_key") == _ck:
            logger.info("[query_clarification] CACHE HIT — full skip to resume path")
            return await _handle_resume(ctx, tool_name, _graph_state, _cached)

    # ── 剥除元字段（before_callback 消费）────────────────────────────────────
    # query 保留在 tool_params 中（工具本身需要），仅 complex_conditions 是纯路由元字段。
    # ── 剥除元字段（before_callback 消费）────────────────────────────────────
    # query 保留在 tool_params 中（工具本身需要），仅 complex_conditions 是纯路由元字段。
    tool_params: dict[str, Any] = _normalize_json_fields(dict(ctx.get("tool_params") or {}))
    query: str = str(tool_params.get("query", "") or "")
    query: str = str(tool_params.get("query", "") or "")
    complex_conditions: list[str] = list(tool_params.pop("complex_conditions", None) or [])

    # query_* schema 不含 compute-only 字段；LLM 若误填，静默丢弃
    if tool_name.startswith("query_"):
        for _sf in _QUERY_STRIP_FIELDS:
            tool_params.pop(_sf, None)

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
    scope_code = _scope_code_from_tool(tool_name)
    field_terms, value_terms = _collect_terms_from_params(tool_params)
    terms = field_terms + value_terms

    # resolved 始终初始化为空 dict
    resolved: dict[str, str] = {}

    # 轻量级别名消歧（字段 + 值，单次 DB 往返）
    resolved, unresolved = (
        _resolve_via_aliases(field_terms, value_terms, scope_code) if terms else ({}, [])
    )

    if terms and unresolved:
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

        # query 是 NL 描述，不属于结构化参数，不传给 SDK
        _sdk_params = {k: v for k, v in tool_params.items() if k != "query"}
        structured_input = {**_sdk_params, "complex_conditions": complex_conditions}
        # query 是 NL 描述，不属于结构化参数，不传给 SDK
        _sdk_params = {k: v for k, v in tool_params.items() if k != "query"}
        structured_input = {**_sdk_params, "complex_conditions": complex_conditions}
        is_compute = tool_name.startswith("compute_")

        # CACHE MISS：首次执行，调用 SDK；interrupt 前写入完整缓存供 resume 命中
        _ck = _make_cache_key(tool_name, query)
        logger.info("[query_clarification] CACHE MISS — calling _analyze_clarification()")
        paradigm_list, clarify_knowledge, needs_clarification = _analyze_clarification(
            query,
            scope_code,
            structured_input,
            is_compute=is_compute,
        )
        if _graph_state is not None:
            _graph_state["_clarification_cache"] = {
                "cache_key": _ck,
                "paradigm_list": paradigm_list,
                "clarify_knowledge": clarify_knowledge,
                "structured_input": structured_input,
                "is_compute": is_compute,
                "resolved": resolved,
                "is_complex": is_complex,
            }

        if not paradigm_list:
            # 澄清分析失败，跳过 interrupt，按原流程继续
            logger.info("[query_clarification] paradigmList 为空，跳过澄清 interrupt")
            tool_params = _apply_resolved_to_params(tool_params, resolved)
            ctx["tool_params"] = tool_params
            if is_complex:
                return _build_redirect_decision(tool_name, query, tool_params)
            return {"action": "patch", "patch": {"tool_params": tool_params}}

        if not needs_clarification:
            # LLM 确认所有术语无歧义 → 直接应用替换，不弹表单
            logger.info("[query_clarification] needs_clarification=False, 直接应用 LLM 确认结果")
            form_str = json.dumps({"paradigmList": paradigm_list}, ensure_ascii=False)
            patched = _format_clarification(
                query,
                structured_input,
                form_str,
                clarify_knowledge or "",
                is_compute=is_compute,
            )
            tool_params = _apply_resolved_to_params(patched, resolved)
            tool_params["query"] = query  # _format_clarification 回填结果不含 query，需补回
            tool_params["query"] = query  # _format_clarification 回填结果不含 query，需补回
            ctx["tool_params"] = tool_params
            if is_complex:
                return _build_redirect_decision(tool_name, query, tool_params)
            return {"action": "patch", "patch": {"tool_params": tool_params}}

        # ── V0.3：改为抛出 ClarificationNeededError，由 tool_dispatcher 捕获 ──
        logger.info("[query_clarification] NEED_CONFIRM: raising ClarificationNeededError")
        raise ClarificationNeededError(
            {
                "tool_name": tool_name,
                "query": query,
                "paradigm_list": paradigm_list,
                "clarify_knowledge": clarify_knowledge,
                "structured_input": structured_input,
                "ontology_code": scope_code,
                "is_compute": is_compute,
                "is_complex": is_complex,
            }
        )

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

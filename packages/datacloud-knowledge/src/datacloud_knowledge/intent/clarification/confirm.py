"""LLM 确认 — 基于召回结果，一次调用确认主结构 + complex_conditions 术语。

输入：ExtractedTerm 列表 + 召回候选
输出：ConfirmedStructuredQuery / ConfirmedStructuredCompute
"""

from __future__ import annotations

import json
import logging
import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

from .models import (
    CCConfirmResult,
    CCTermMeta,
    ConfirmedStructuredCompute,
    ConfirmedStructuredQuery,
    ExtractedTerm,
    MainConfirmResult,
    PreResolveResult,
    TermMeta,
)

logger = logging.getLogger(__name__)

_CONFIRM_MAX_RETRIES = 2
_CONFIRM_RETRYABLE_HTTP_STATUS: frozenset[int] = frozenset({429, 500, 502, 503, 504})
_CONFIRM_NON_RETRYABLE_HTTP_STATUS: frozenset[int] = frozenset({400, 401, 403})


# ── System Prompt ────────────────────────────────────────────────────


CONFIRM_SYSTEM_PROMPT = """\
你是数据查询确认助手。根据知识库召回结果，将结构化查询中的中文术语映射到真实 schema 字段。
分析完成后，你必须调用工具提交确认结果，不要用文本回复。

## 输入
- 用户原始查询
- 结构化查询参数（StructuredQuery 或 StructuredCompute）
- 每个中文术语的知识库召回候选
- 维度值线索

## 主结构确认规则
- 所有字段名和维度值只能来自召回候选或维度值线索，严禁编造
- 确定的术语直接替换为真实字段名
- 无法确定的放入 clarify_items，标注 source 和 path
- 候选列表中排在前面的通常更相关，但要结合语义判断
- 如果召回候选第一名与原始术语语义高度匹配，直接确认，不需要澄清

## 维度建模一致性规则
- select / metrics 中的字段应来自相同粒度的数据实体
- 如果候选中有多个不同粒度的字段（如学生级 vs 班级级），优先选择与 \
dimensions / group_by 粒度一致的字段
- 例：dimensions 按"班级"分组，则 metrics 优先选班级级别的字段（如"班级平均分"）\
而非学生级别的字段（如"学生成绩"）
- 例：查询"各班级的语文平均分和数学平均分"，dimensions 是班级，\
metrics 应选班级级别的成绩字段而非学生级别的

## 粒度与查询对象匹配规则
- 候选精选时必须考虑查询对象的粒度：优先选择与查询对象同粒度的字段
- 如果用户查询的对象是"班级"，优先选择班级级汇总字段，而非学生级明细字段
- 如果用户查询的对象是"学生"，优先选择学生级字段，而非班级级汇总字段
- 例：查询"各班级语文平均分排名后3的班级"，候选有 ['语文期末成绩', '班级语文平均分', '数据来源']，\
应优先选 '班级语文平均分'（与"班级"粒度一致），而非 '语文期末成绩'（学生粒度）
- 例：查询"成绩排名前10的学生"，候选有 ['班级语文平均分', '学生语文期末成绩', '数据来源']，\
应优先选 '学生语文期末成绩'（学生粒度），而非 '班级语文平均分'（班级粒度）

## 数值与量化条件规则
- 纯数值（如 50、30%、100万、202602）直接保留原值，不需要召回确认
- 数值型 whereValue 的 confirmed 直接填原值，不标记为需澄清

## alias 引用规则
- order_by / having 中如果引用了 metrics[].as 别名，保持别名不变，不做翻译
- 如果 order_by.field 不是 metrics alias 引用，而是有对应的召回候选，则正常替换

## 保持原始结构规则
- limit / offset 保持原始输入的值，不做修改
- 不要增删原始结构中的字段数量，只做术语→真实字段名的替换
- filters 中已有的条件结构（field/op/value）保持不变，只替换 field 名为召回候选中的真实字段名
- filters.field 如果是英文编码（如 stat_date），且召回候选中有对应的中文字段名，替换为中文字段名

## complex_conditions 确认规则
- 对每条 NL 中的中文术语做确认
- 输出 original_term / start / end / confirmed / candidates
- 只有一个高置信候选 → confirmed 填值
- 多候选无法区分 → confirmed = null，candidates 按语义相关度降序排列
- candidates 必须精选：只保留与原始术语语义相关的候选（最多 5 个），\
过滤掉明显不相关的
- candidates 不能为空：即使没有精确匹配，也必须从召回候选中选出最接近的 2~3 个供用户选择。\
系统中的字段命名可能与用户术语不同（如用户说"道法"，系统字段叫"道德与法律"），\
这种情况下应将语义最近的候选保留，让用户判断
- candidates 仅从召回候选中选取，严禁编造
- 示例：术语"成绩"的召回候选为 ['数据来源', '语文期末成绩', '数学期末成绩', '统计日期', '班级平均分']，\
精选后 candidates = ['语文期末成绩', '数学期末成绩', '班级平均分']，\
过滤掉 '数据来源' 和 '统计日期'（与"成绩"语义无关）

## 关键规则
- needs_clarification = true ⟺ clarify_items 非空 或任何 complex_condition 术语的 confirmed 为 null
- clarify_items 中的 source 必须标明来源: "select" / "where" / "group_by" / "order_by"
- clarify_items 中的 candidates 必须按语义相关度降序排列，最多 5 个，过滤明显不相关项
- clarify_items 中的 candidates 必须全部来自召回候选，严禁编造
- 分析完成后必须调用工具提交结果，不要用文本回复

## 示例

用户查询: "查询语文成绩前10名的学生"
结构化输入（StructuredQuery）:
{
  "select": ["学生姓名", "语文成绩"],
  "order_by": [{"field": "语文成绩", "direction": "desc"}],
  "limit": 10
}
知识库召回结果:
== 查询值 ==
  学生姓名 (select): ['学生姓名', '学生学号', '班级名称']
  语文成绩 (select): ['语文期末成绩', '语文平时成绩', '数学期末成绩']
== 排序目标 ==
  语文成绩 (orderBy): ['语文期末成绩', '语文平时成绩', '数学期末成绩']

正确的工具调用参数:
{
  "select": ["学生姓名", "语文期末成绩"],
  "order_by": [{"field": "语文期末成绩", "direction": "desc"}],
  "limit": 10,
  "clarify_items": [],
  "needs_clarification": false
}
说明：学生姓名精确命中；语文成绩→语文期末成绩（排名第一且语义匹配）；limit=10 保持不变。

粒度匹配示例:
用户查询: "查询平均分排名后3的班级"
结构化输入: {"select": ["班级名称", "平均分"], "order_by": [{"field": "平均分", "direction": "asc"}], "limit": 3}
知识库召回结果:
== 查询值 ==
  班级名称 (select): ['班级名称', '班级编号', '学生姓名']
  平均分 (select): ['学生语文成绩', '班级语文平均分', '班级数学平均分', '学生数学成绩', '数据来源']
== 排序目标 ==
  平均分 (orderBy): ['学生语文成绩', '班级语文平均分', '班级数学平均分', '学生数学成绩', '数据来源']

正确的工具调用参数:
{
  "select": ["班级名称"],
  "order_by": [{"field": null, "direction": "asc"}],
  "limit": 3,
  "clarify_items": [
    {"keyword": "平均分", "candidates": ["班级语文平均分", "班级数学平均分"], "reason": "查询对象是班级，优先选班级粒度的字段；有多个班级级平均分需用户选择", "source": "select", "path": "/select/1"}
  ],
  "needs_clarification": true
}
说明：查询对象是"班级"，候选中"班级语文平均分"和"班级数学平均分"是班级粒度，\
"学生语文成绩"和"学生数学成绩"是学生粒度 → 过滤掉学生粒度的候选和无关的"数据来源"。

错误示例（不要这样做）:
- candidates 中出现 "语文综合成绩" ← 不在召回结果中，属于编造
- limit 被改为 null ← 不应修改原始值
- 用文本回复而不调用工具 ← 必须调用工具提交
"""


# ── 召回上下文格式化 ─────────────────────────────────────────────────


def format_recall_context(
    terms: list[ExtractedTerm],
    recall_map: dict[str, list[dict[str, Any]]],
    *,
    complex_conditions: list[str] | None = None,
    dimension_value_hints: dict[str, list[Any]] | None = None,
) -> str:
    """将术语 + 召回候选格式化为 LLM 可读的上下文。

    Args:
        terms: 提取的术语列表。
        recall_map: key 为 "ktype:raw_text"，value 为候选 dict 列表。
        dimension_value_hints: 维度值线索。

    Returns:
        格式化的召回上下文文本。
    """
    lines: list[str] = []
    current_section = ""

    # 按 source 分区
    main_terms = [t for t in terms if t.source == "main"]
    cc_terms = [t for t in terms if t.source == "complex_condition"]

    # 主结构术语
    ktype_section_map = {
        "select": "查询值",
        "groupBy": "分组条件",
        "whereKey": "过滤条件（字段）",
        "whereValue": "过滤条件（值）",
        "orderBy": "排序目标",
    }
    for term in main_terms:
        if not term.search_enabled:
            continue
        section = ktype_section_map.get(term.ktype, term.ktype)
        if section != current_section:
            if lines:
                lines.append("")
            lines.append(f"== {section} ==")
            current_section = section

        key = f"{term.ktype}:{term.raw_text}"
        candidates = recall_map.get(key, [])
        if not candidates:
            lines.append(f"  {term.raw_text} ({term.ktype}): 无召回结果")
        else:
            names = [str(c.get("term_name", "")) for c in candidates[:5]]
            lines.append(f"  {term.raw_text} ({term.ktype}): {names}")

    # complex_conditions 术语
    if cc_terms:
        lines.append("")
        lines.append("== complex_conditions 术语 ==")
        # 按 condition_index 分组
        by_idx: dict[int, list[ExtractedTerm]] = {}
        for t in cc_terms:
            by_idx.setdefault(t.condition_index, []).append(t)
        for idx in sorted(by_idx):
            group = by_idx[idx]
            # 输出原始句子
            original = ""
            if complex_conditions and idx < len(complex_conditions):
                original = complex_conditions[idx]
            lines.append(f'  [{idx}] "{original}":')

            # 合并别名扩展词的候选到父术语
            merged = _merge_alias_candidates(group, recall_map)
            for raw_text, ktype, names in merged:
                if not names:
                    lines.append(f"    {raw_text} ({ktype}): 无召回结果")
                else:
                    lines.append(f"    {raw_text} ({ktype}): {names}")

    # 维度值线索
    if dimension_value_hints:
        hint_lines: list[str] = []
        for keyword, hints in dimension_value_hints.items():
            for h in hints:
                span = getattr(h, "matched_span", "")
                value = getattr(h, "matched_value", "")
                dim = getattr(h, "dimension_prop", "")
                hint_lines.append(f'  {keyword}: "{span}" → {value} (维度={dim})')
        if hint_lines:
            lines.append("")
            lines.append("== 维度值线索（从短语中识别，辅助理解） ==")
            lines.extend(hint_lines)

    return "\n".join(lines)


# ── LLM 输出清洗 ──────────────────────────────────────────────────────

# LLM 可能在列表字段中传 null（如 select: [null]），或以 JSON 字符串传递列表
_LIST_FIELDS_TO_SANITIZE = (
    "select",
    "filters",
    "order_by",
    "dimensions",
    "metrics",
    "having",
    "clarify_items",
    "confirmed_conditions",
)


def _sanitize_confirm_args(args: dict[str, Any]) -> None:
    """清洗 LLM tool call 参数：JSON 字符串解码 + 过滤列表中的 None 值。"""
    for field in _LIST_FIELDS_TO_SANITIZE:
        val = args.get(field)
        # LLM 有时以 JSON 字符串传递列表/对象
        if isinstance(val, str):
            try:
                parsed = json.loads(val)
                if isinstance(parsed, list):
                    val = parsed
                    args[field] = val
            except (json.JSONDecodeError, ValueError):
                pass
        if isinstance(val, list):
            args[field] = [item for item in val if item is not None]


# ── LLM 调用 ─────────────────────────────────────────────────────────


def llm_confirm_structured(
    *,
    query: str,
    structured_input: dict[str, Any],
    recall_context: str,
    mode: Literal["query", "compute"],
    on_event: Callable[[Any], None] | None = None,
) -> ConfirmedStructuredQuery | ConfirmedStructuredCompute | None:
    """调用 LLM 确认结构化查询中的术语。

    Args:
        query: 用户原始查询。
        structured_input: StructuredQuery 或 StructuredCompute 的 dict。
        recall_context: 格式化的召回上下文。
        mode: "query" 或 "compute"。
        on_event: 可选回调。

    Returns:
        确认后的结构，LLM 失败时返回 None。
    """
    if not recall_context.strip():
        logger.info("[confirm] 召回结果为空，跳过 LLM 确认")
        return None

    _collecting = os.environ.get("DATACLOUD_COLLECT_CONFIRM_CASES") == "1"
    _collect_input: dict[str, Any] | None = None
    if _collecting:
        _collect_input = {
            "query": query,
            "structured_input": structured_input,
            "recall_context": recall_context,
            "mode": mode,
        }

    model_cls: type[ConfirmedStructuredQuery] | type[ConfirmedStructuredCompute] = (
        ConfirmedStructuredQuery if mode == "query" else ConfirmedStructuredCompute
    )

    user_prompt = _build_user_prompt(query, structured_input, recall_context, mode)
    logger.debug("[confirm] recall_context:\n%s", recall_context)

    try:
        from datacloud_knowledge.intent.llm_utils import (
            build_llm,
            extract_json_from_text,
            stream_invoke_with_thinking,
        )

        llm = build_llm()
        llm_with_tool = llm.bind_tools([model_cls])
        response = _invoke_confirm_with_retry(
            lambda: stream_invoke_with_thinking(
                llm_with_tool,
                [
                    {"role": "system", "content": CONFIRM_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                on_event=on_event,
            )
        )
        if response and response.tool_calls:
            args = response.tool_calls[0]["args"]
            # LLM 可能在列表字段中传 null（如 select: [null]），清洗后再校验
            _sanitize_confirm_args(args)
            logger.debug(
                "[confirm] LLM 确认完成: %s",
                json.dumps(args, ensure_ascii=False),
            )
            result = model_cls.model_validate(args)
            result.needs_clarification = _check_needs_clarification(result)
            if _collect_input is not None:
                _save_test_case(_collect_input, result)
            return result

        # 兜底：从 content 文本中提取 JSON
        raw_content = response.content if hasattr(response, "content") else str(response)
        content = (
            "\n".join(str(part) for part in raw_content)
            if isinstance(raw_content, list)
            else str(raw_content)
        )
        logger.warning("[confirm] LLM 未返回 tool call，尝试从文本提取 JSON")
        fallback = extract_json_from_text(content)
        if fallback is not None:
            result = model_cls.model_validate(fallback)
            result.needs_clarification = _check_needs_clarification(result)
            if _collect_input is not None:
                _save_test_case(_collect_input, result)
            return result
        logger.warning("[confirm] 兜底提取失败: %s", content[:200])
    except Exception:
        logger.exception("[confirm] LLM 确认失败")
    if _collect_input is not None:
        _save_test_case(_collect_input, None)
    return None


def _is_retryable_confirm_error(exc: Exception) -> bool:
    """Return whether a clarification confirm failure is likely transient."""
    status = getattr(exc, "status_code", None) or getattr(exc, "status", None)
    if status is not None:
        if int(status) in _CONFIRM_NON_RETRYABLE_HTTP_STATUS:
            return False
        return int(status) in _CONFIRM_RETRYABLE_HTTP_STATUS
    if isinstance(exc, (TimeoutError, ConnectionError)):
        return True
    return isinstance(exc, ValueError) and "No generations found in stream" in str(exc)


def _invoke_confirm_with_retry(invoke: Callable[[], Any]) -> Any:
    """Invoke confirmation LLM call with minimal retry for transient failures."""
    last_exc: Exception | None = None

    for attempt in range(_CONFIRM_MAX_RETRIES + 1):
        try:
            return invoke()
        except Exception as exc:
            last_exc = exc
            if not _is_retryable_confirm_error(exc) or attempt >= _CONFIRM_MAX_RETRIES:
                raise

            wait_seconds = float(2**attempt)
            logger.warning(
                "[confirm] LLM 确认调用失败，第 %d/%d 次重试，等待 %.1f 秒: %s",
                attempt + 1,
                _CONFIRM_MAX_RETRIES,
                wait_seconds,
                exc,
            )
            time.sleep(wait_seconds)

    if last_exc is None:
        raise RuntimeError("confirm retry loop exited without result")
    raise last_exc


# ── 数据采集（DATACLOUD_COLLECT_CONFIRM_CASES=1 时启用）───────────────

_TEST_CASE_FILE = (
    Path(__file__).resolve().parents[4] / "scripts" / "manual" / "llm_confirm_test_cases.json"
)


def _save_test_case(
    case_input: dict[str, Any],
    result: ConfirmedStructuredQuery | ConfirmedStructuredCompute | None,
) -> None:
    """追加一条测试用例到 JSON 文件。采集失败不影响主流程。"""
    try:
        cases: list[dict[str, Any]] = []
        if _TEST_CASE_FILE.exists():
            cases = json.loads(_TEST_CASE_FILE.read_text("utf-8"))

        cases.append(
            {
                **case_input,
                "result": result.model_dump() if result is not None else None,
            }
        )

        _TEST_CASE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _TEST_CASE_FILE.write_text(
            json.dumps(cases, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        logger.info("[confirm] 测试用例已保存: %s (共 %d 条)", _TEST_CASE_FILE.name, len(cases))
    except Exception:
        logger.debug("[confirm] 测试用例保存失败，忽略", exc_info=True)


def _merge_alias_candidates(
    group: list[ExtractedTerm],
    recall_map: dict[str, list[dict[str, Any]]],
) -> list[tuple[str, str, list[str]]]:
    """将别名扩展词的召回候选合并到父术语，去重后统一展示。

    别名（parent_raw_text 非 None）的候选合并到对应父术语行，
    别名自身不再单独展示。每个术语的候选在召回阶段已经 top_k 截断，
    合并后只做去重，不再二次截断，避免丢失别名带来的有价值候选。

    Args:
        group: 同一 condition_index 下的术语列表。
        recall_map: 召回结果映射。

    Returns:
        [(raw_text, ktype, candidate_names), ...] 仅包含原始词（非别名）。
    """
    # 收集每个原始词的候选（含别名贡献）
    # key = (ktype, raw_text)
    parent_order: list[tuple[str, str]] = []
    parent_seen: set[tuple[str, str]] = set()
    merged_names: dict[tuple[str, str], list[str]] = {}

    for term in group:
        if not term.search_enabled:
            continue
        key = f"{term.ktype}:{term.raw_text}"
        candidates = recall_map.get(key, [])
        names = [str(c.get("term_name", "")) for c in candidates]

        if term.parent_raw_text is not None:
            # 别名 → 合并到父术语
            parent_key = (term.ktype, term.parent_raw_text)
            if parent_key not in parent_seen:
                parent_seen.add(parent_key)
                parent_order.append(parent_key)
                merged_names[parent_key] = []
            merged_names[parent_key].extend(names)
        else:
            # 原始词
            self_key = (term.ktype, term.raw_text)
            if self_key not in parent_seen:
                parent_seen.add(self_key)
                parent_order.append(self_key)
                merged_names[self_key] = []
            merged_names[self_key].extend(names)

    # 去重 + 截取 top 5
    result: list[tuple[str, str, list[str]]] = []
    for ktype, raw_text in parent_order:
        all_names = merged_names[(ktype, raw_text)]
        seen: set[str] = set()
        deduped: list[str] = []
        for name in all_names:
            if name and name not in seen:
                seen.add(name)
                deduped.append(name)
        result.append((raw_text, ktype, deduped))
    return result


def _build_user_prompt(
    query: str,
    structured_input: dict[str, Any],
    recall_context: str,
    mode: str,
) -> str:
    mode_label = "StructuredQuery" if mode == "query" else "StructuredCompute"
    return f"""\
## 用户原始查询
{query}

## 结构化输入（{mode_label}）
{json.dumps(structured_input, ensure_ascii=False, indent=2)}

## 知识库召回结果
{recall_context}

## 请确认并提交
根据召回结果，将中文术语映射到真实 schema 字段，然后调用工具提交确认结果。"""


def _check_needs_clarification(
    result: ConfirmedStructuredQuery | ConfirmedStructuredCompute,
) -> bool:
    """判断是否需要用户澄清。"""
    if result.clarify_items:
        return True
    for cc in result.confirmed_conditions:
        for tm in cc.term_mappings:
            if tm.confirmed is None and tm.candidates:
                return True
    return False


# ── 分治确认 System Prompts ──────────────────────────────────────────


MAIN_CONFIRM_SYSTEM_PROMPT = """\
你是数据查询确认助手。根据知识库召回结果，对待确认术语选择最匹配的候选。
分析完成后，你必须调用工具提交确认结果，不要用文本回复。

## 规则
- 对每个 #编号术语，从候选中选择语义最匹配的填入 confirmed
- 无法确定 → confirmed = null，candidates 填精选候选（最多5个），附 reason
- 重要：如果候选中没有与原始术语语义相关的字段，必须返回 confirmed = null，严禁强行选择不相关的候选
- 标注"取值范围"的术语，confirmed 只能从取值范围中选取
- 已确认字段仅供理解上下文，不需要处理
- 候选列表中排在前面的通常更相关，但要结合语义判断
- 如果候选第一名与原始术语语义高度匹配，直接确认
- 纯数值（如 50、30%、100万、202602）直接保留原值
- needs_clarification = true ⟺ 任何术语 confirmed 为 null 且 candidates 非空
- 分析完成后必须调用工具提交结果，不要用文本回复

## 维度建模一致性规则
- select / metrics 中的字段应来自相同粒度的数据实体
- 如果候选中有多个不同粒度的字段，优先选择与 dimensions / group_by 粒度一致的字段

## 粒度与查询对象匹配规则
- 候选精选时必须考虑查询对象的粒度：优先选择与查询对象同粒度的字段
"""

CC_CONFIRM_SYSTEM_PROMPT = """\
你是数据查询确认助手。对条件句中的中文术语做映射。
分析完成后，你必须调用工具提交确认结果，不要用文本回复。

## 规则
- 对每个 #编号术语，从候选中选择语义最匹配的填入 confirmed
- 无法确定 → confirmed = null，candidates 填精选候选（最多5个），附 reason
- candidates 必须精选：只保留语义相关的候选，过滤明显不相关项
- candidates 不能为空：即使没有精确匹配，也必须从候选中选出最接近的 2~3 个
- candidates 仅从召回候选中选取，严禁编造
- 纯数值（30%、100）不需要映射，不会出现在待确认列表中
- needs_clarification = true ⟺ 任何术语 confirmed 为 null 且 candidates 非空
- 分析完成后必须调用工具提交结果，不要用文本回复
"""


# ── 分治确认上下文格式化 ─────────────────────────────────────────────


def _term_key(t: ExtractedTerm) -> str:
    """生成术语的复合键：path:raw_text。"""
    return f"{t.path}:{t.raw_text}"


def format_main_confirm_context(
    structured_input: dict[str, Any],
    main_terms: list[ExtractedTerm],
    recall_map: dict[str, list[dict[str, Any]]],
    pre_resolve: PreResolveResult,
    *,
    mode: str = "query",
) -> tuple[str, dict[int, TermMeta]]:
    """格式化主结构 LLM 确认上下文（编号术语模式）。

    Args:
        structured_input: 已做 pre_resolve 替换后的结构化输入。
        main_terms: 主结构提取的术语列表。
        recall_map: 召回结果映射。
        pre_resolve: pre_resolve 阶段输出。
        mode: "query" 或 "compute"。

    Returns:
        (formatted_context, term_registry) 元组。
    """
    mode_label = "StructuredQuery" if mode == "query" else "StructuredCompute"
    lines: list[str] = []

    # 结构化输入（上下文参考）
    lines.append(f"## 结构化输入（{mode_label}，上下文参考）")
    lines.append(json.dumps(structured_input, ensure_ascii=False, indent=2))
    lines.append("")

    # 已确认字段（按 path 键入，显示时用 raw_text）
    if pre_resolve.confirmed:
        lines.append("## 已确认字段（仅供上下文，不需要处理）")
        # 收集已确认术语的 raw_text → term_name 映射（用于显示）
        shown: set[str] = set()
        for t in main_terms:
            if t.source != "main" or _term_key(t) not in pre_resolve.confirmed:
                continue
            rf = pre_resolve.confirmed[_term_key(t)]
            display_key = f"{rf.term_name}←{t.raw_text}"
            if display_key in shown:
                continue
            shown.add(display_key)
            source_tag = pre_resolve.provenance.get(_term_key(t), "")
            lines.append(f"  {rf.term_name} ← {t.raw_text}（{source_tag}）")
        lines.append("")

    # 编号待确认术语
    term_registry: dict[int, TermMeta] = {}
    term_id = 0

    # 按 ktype 分组展示
    ktype_section_map = {
        "select": "查询值",
        "groupBy": "分组条件",
        "whereKey": "过滤条件（字段）",
        "whereValue": "过滤条件（值）",
        "orderBy": "排序目标",
        "dimension": "维度",
        "metric": "指标",
    }

    unresolved_terms = [
        t
        for t in main_terms
        if t.source == "main"
        and t.search_enabled
        and _term_key(t) not in pre_resolve.confirmed
        and t.parent_raw_text is None  # 跳过别名扩展词
    ]

    if unresolved_terms:
        lines.append("## 待确认术语")
        current_section = ""
        for term in unresolved_terms:
            section = ktype_section_map.get(term.ktype, term.ktype)
            if section != current_section:
                current_section = section

            term_id += 1
            meta = TermMeta(path=term.path, ktype=term.ktype, raw_text=term.raw_text)
            term_registry[term_id] = meta

            key = f"{term.ktype}:{term.raw_text}"
            candidates = recall_map.get(key, [])
            names = [str(c.get("term_name", "")) for c in candidates[:5]]

            # whereValue 枚举约束（按 path 查找）
            enum_values = pre_resolve.value_enum_map.get(_term_key(term))
            if enum_values is not None and term.ktype == "whereValue":
                # 找到该 value 对应的 whereKey 名称
                where_key_name = _find_where_key_for_value(term, main_terms, pre_resolve)
                lines.append(f"  #{term_id} {term.raw_text} ({section}，字段={where_key_name})")
                lines.append(f"      取值范围: {enum_values}")
            else:
                lines.append(f"  #{term_id} {term.raw_text} ({section})")
                lines.append(f"      候选: {names}")
            lines.append("")

    if not unresolved_terms:
        lines.append("## 无待确认术语（所有字段已确认）")

    lines.append("## 请对每个编号术语确认并提交")

    return "\n".join(lines), term_registry


def _find_term_position(
    sentence: str,
    term: str,
    used_positions: set[int],
) -> tuple[int, int]:
    """在句子中查找术语位置，避免与已占用位置冲突。"""
    term_len = len(term)
    occurrences: list[int] = []
    search_start = 0
    while True:
        idx = sentence.find(term, search_start)
        if idx == -1:
            break
        occurrences.append(idx)
        search_start = idx + 1

    if not occurrences:
        return -1, -1
    if len(occurrences) == 1:
        return occurrences[0], occurrences[0] + term_len
    # 多次出现 → 选未占用的第一个
    for occ in occurrences:
        if occ not in used_positions:
            return occ, occ + term_len
    return occurrences[0], occurrences[0] + term_len


def _find_where_key_for_value(
    value_term: ExtractedTerm,
    all_terms: list[ExtractedTerm],
    pre_resolve: PreResolveResult,
) -> str:
    """查找 whereValue 对应的 whereKey 中文名。"""
    # 从 path 推断：filters.N.value.M → filters.N 是 filter 前缀
    filter_prefix = _extract_filter_prefix(value_term.path)
    if not filter_prefix:
        return "未知"
    for t in all_terms:
        if t.ktype == "whereKey" and _extract_filter_prefix(t.path) == filter_prefix:
            rf = pre_resolve.confirmed.get(_term_key(t))
            if rf:
                return rf.term_name
            return t.raw_text
    return "未知"


def _extract_filter_prefix(path: str) -> str:
    """从 path 提取 filter 前缀：'filters.1.field' → 'filters.1'。"""
    parts = path.split(".")
    if len(parts) >= 2 and parts[0] == "filters":
        return f"{parts[0]}.{parts[1]}"
    # metrics.N.filters.M.field → metrics.N.filters.M
    for i, p in enumerate(parts):
        if p == "filters" and i + 1 < len(parts):
            try:
                int(parts[i + 1])
                return ".".join(parts[: i + 2])
            except ValueError:
                pass
    return ""


def format_cc_confirm_context(
    cc_terms: list[ExtractedTerm],
    recall_map: dict[str, list[dict[str, Any]]],
    sentence: str,
    condition_index: int,
) -> tuple[str, dict[int, CCTermMeta]]:
    """格式化单条 complex_condition 的 LLM 确认上下文。

    Args:
        cc_terms: 该条 cc 的术语列表。
        recall_map: 召回结果映射。
        sentence: 原始条件句。
        condition_index: cc 索引。

    Returns:
        (formatted_context, cc_term_registry) 元组。
    """
    lines: list[str] = []
    cc_term_registry: dict[int, CCTermMeta] = {}

    lines.append("## 条件句")
    lines.append(f'"{sentence}"')
    lines.append("")

    # 合并别名候选到父术语
    merged = _merge_alias_candidates(cc_terms, recall_map)

    # 建立 raw_text → ExtractedTerm 映射（取第一个非别名的）
    raw_to_term: dict[str, ExtractedTerm] = {}
    for t in cc_terms:
        if t.parent_raw_text is None and t.raw_text not in raw_to_term:
            raw_to_term[t.raw_text] = t

    # 计算每个术语在句子中的位置（不依赖 LLM）
    used_positions: set[int] = set()

    term_id = 0
    if merged:
        lines.append("## 待确认术语")
        for raw_text, ktype, names in merged:
            term_id += 1

            # 从句子中查找位置
            start, end = _find_term_position(sentence, raw_text, used_positions)
            if start >= 0:
                used_positions.add(start)
            else:
                logger.warning(
                    "[confirm_cc] 术语 '%s' 未在句子中找到，位置设为 0/0",
                    raw_text,
                )

            meta = CCTermMeta(
                raw_text=raw_text,
                ktype=ktype,
                start=start if start >= 0 else 0,
                end=end if start >= 0 else 0,
                condition_index=condition_index,
            )
            cc_term_registry[term_id] = meta

            ktype_label = {
                "select": "指标/字段",
                "groupBy": "分组",
                "whereKey": "过滤字段",
                "whereValue": "过滤值",
                "orderBy": "排序",
            }.get(ktype, ktype)

            lines.append(f"  #{term_id} {raw_text} ({ktype_label})")
            if names:
                lines.append(f"      候选: {names}")
            else:
                lines.append("      候选: 无召回结果")
            lines.append("")

    lines.append("## 请对每个编号术语确认并提交")

    return "\n".join(lines), cc_term_registry


# ── 分治 LLM 调用 ────────────────────────────────────────────────────


def llm_confirm_main(
    *,
    context: str,
    on_event: Callable[[Any], None] | None = None,
) -> MainConfirmResult | None:
    """调用 LLM 确认主结构术语（编号模式）。

    Args:
        context: format_main_confirm_context 生成的上下文。
        on_event: 可选回调。

    Returns:
        MainConfirmResult，LLM 失败时返回 None。
    """
    if not context.strip():
        logger.info("[confirm_main] 上下文为空，跳过")
        return None

    try:
        from datacloud_knowledge.intent.llm_utils import (
            build_llm,
            extract_json_from_text,
            stream_invoke_with_thinking,
        )

        llm = build_llm()
        llm_with_tool = llm.bind_tools([MainConfirmResult])
        response = _invoke_confirm_with_retry(
            lambda: stream_invoke_with_thinking(
                llm_with_tool,
                [
                    {"role": "system", "content": MAIN_CONFIRM_SYSTEM_PROMPT},
                    {"role": "user", "content": context},
                ],
                on_event=on_event,
            )
        )
        if response and response.tool_calls:
            args = response.tool_calls[0]["args"]
            _sanitize_confirm_args(args)
            logger.debug(
                "[confirm_main] LLM 确认完成: %s",
                json.dumps(args, ensure_ascii=False)[:500],
            )
            result = MainConfirmResult.model_validate(args)
            # 代码侧校正 needs_clarification
            result.needs_clarification = any(
                tc.confirmed is None and tc.candidates for tc in result.confirmations
            )
            return result

        raw_content = response.content if hasattr(response, "content") else str(response)
        content = (
            "\n".join(str(part) for part in raw_content)
            if isinstance(raw_content, list)
            else str(raw_content)
        )
        logger.warning("[confirm_main] LLM 未返回 tool call，尝试从文本提取")
        fallback = extract_json_from_text(content)
        if fallback is not None:
            result = MainConfirmResult.model_validate(fallback)
            result.needs_clarification = any(
                tc.confirmed is None and tc.candidates for tc in result.confirmations
            )
            return result
        logger.warning("[confirm_main] 兜底提取失败: %s", content[:200])
    except Exception:
        logger.exception("[confirm_main] LLM 确认失败")
    return None


def llm_confirm_cc(
    *,
    context: str,
    on_event: Callable[[Any], None] | None = None,
) -> CCConfirmResult | None:
    """调用 LLM 确认单条 complex_condition 术语（编号模式）。

    Args:
        context: format_cc_confirm_context 生成的上下文。
        on_event: 可选回调。

    Returns:
        CCConfirmResult，LLM 失败时返回 None。
    """
    if not context.strip():
        logger.info("[confirm_cc] 上下文为空，跳过")
        return None

    try:
        from datacloud_knowledge.intent.llm_utils import (
            build_llm,
            extract_json_from_text,
            stream_invoke_with_thinking,
        )

        llm = build_llm()
        llm_with_tool = llm.bind_tools([CCConfirmResult])
        response = _invoke_confirm_with_retry(
            lambda: stream_invoke_with_thinking(
                llm_with_tool,
                [
                    {"role": "system", "content": CC_CONFIRM_SYSTEM_PROMPT},
                    {"role": "user", "content": context},
                ],
                on_event=on_event,
            )
        )
        if response and response.tool_calls:
            args = response.tool_calls[0]["args"]
            _sanitize_confirm_args(args)
            logger.debug(
                "[confirm_cc] LLM 确认完成: %s",
                json.dumps(args, ensure_ascii=False)[:500],
            )
            result = CCConfirmResult.model_validate(args)
            result.needs_clarification = any(
                tc.confirmed is None and tc.candidates for tc in result.confirmations
            )
            return result

        raw_content = response.content if hasattr(response, "content") else str(response)
        content = (
            "\n".join(str(part) for part in raw_content)
            if isinstance(raw_content, list)
            else str(raw_content)
        )
        logger.warning("[confirm_cc] LLM 未返回 tool call，尝试从文本提取")
        fallback = extract_json_from_text(content)
        if fallback is not None:
            result = CCConfirmResult.model_validate(fallback)
            result.needs_clarification = any(
                tc.confirmed is None and tc.candidates for tc in result.confirmations
            )
            return result
        logger.warning("[confirm_cc] 兜底提取失败: %s", content[:200])
    except Exception:
        logger.exception("[confirm_cc] LLM 确认失败")
    return None

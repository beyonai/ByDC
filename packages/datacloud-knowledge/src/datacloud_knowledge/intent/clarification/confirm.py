"""LLM 确认 — 基于召回结果，一次调用确认主结构 + complex_conditions 术语。

输入：ExtractedTerm 列表 + 召回候选
输出：ConfirmedStructuredQuery / ConfirmedStructuredCompute
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

from .models import (
    ConfirmedStructuredCompute,
    ConfirmedStructuredQuery,
    ExtractedTerm,
)

logger = logging.getLogger(__name__)


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
- 多候选无法区分 → confirmed = null，candidates 按相关度排序（仅从召回候选中选取）

## 关键规则
- needs_clarification = true ⟺ clarify_items 非空 或任何 complex_condition 术语的 confirmed 为 null
- clarify_items 中的 source 必须标明来源: "select" / "where" / "group_by" / "order_by"
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

    # ── 临时数据采集（收集测试集，上线前删除）──
    _collect_case_input = {
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
        response = stream_invoke_with_thinking(
            llm_with_tool,
            [
                {"role": "system", "content": CONFIRM_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            on_event=on_event,
        )
        if response and response.tool_calls:
            args = response.tool_calls[0]["args"]
            logger.debug(
                "[confirm] LLM 确认完成: %s",
                json.dumps(args, ensure_ascii=False),
            )
            result = model_cls.model_validate(args)
            result.needs_clarification = _check_needs_clarification(result)
            _save_test_case(_collect_case_input, result)
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
            _save_test_case(_collect_case_input, result)
            return result
        logger.warning("[confirm] 兜底提取失败: %s", content[:200])
    except Exception:
        logger.exception("[confirm] LLM 确认失败")
    _save_test_case(_collect_case_input, None)
    return None


# ── 临时数据采集（收集测试集，上线前删除）─────────────────────────────

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

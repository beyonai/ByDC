"""术语提取 — 从 StructuredQuery / StructuredCompute 中提取可召回的中文术语。

主结构 walker：遍历 select / filters / dimensions / metrics / order_by / having，
按 ktype 映射规则提取 ExtractedTerm。

complex_conditions：逐条调用 expand_query 展开为 NatQuery，再从中提取术语。
"""

from __future__ import annotations

import logging
import re
from typing import Any

from .models import ExtractedTerm

logger = logging.getLogger(__name__)

# 中文字符检测
_HAS_CHINESE_RE = re.compile(r"[\u4e00-\u9fff]")

# expr 分割：按 +-*/() 拆分
_EXPR_SPLIT_RE = re.compile(r"[+\-*/()]+")

# 纯数字 / 日期 / 中文数值（如 "50万"、"30%"、"100万元"）
_NUMERIC_RE = re.compile(r"^[\d.]+$")
_NUMERIC_CN_RE = re.compile(r"^[\d.]+[万亿元%‰]+$")
_DATE_RE = re.compile(
    r"^\d{4}[-/年]\d{1,2}[-/月]?(\d{1,2}日?)?$"
    r"|^\d{6,8}$"
    r"|^\d{4}年?$"
)

# 英文标识符（如 stat_date、total_revenue）— 需要走向量召回而非文本召回
_ENGLISH_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _is_skippable(value: str) -> bool:
    """判断值是否应跳过召回。

    跳过：空值、纯数字、日期、中文数值（50万/30%）、无中文的非标识符文本。
    不跳过：含中文的术语、英文标识符（stat_date 等，走向量召回）。
    """
    v = value.strip()
    if not v:
        return True
    if _NUMERIC_RE.match(v):
        return True
    if _NUMERIC_CN_RE.match(v):
        # "50万"、"100万元"、"30%" 等中文数值不需要知识库召回
        return True
    if _DATE_RE.match(v):
        return True
    # 英文标识符（如 stat_date）不跳过，后续走向量召回
    if _ENGLISH_IDENT_RE.match(v):
        return False
    return not bool(_HAS_CHINESE_RE.search(v))


def _is_vector_only(value: str) -> bool:
    """判断值是否应只走向量召回。

    英文标识符（如 stat_date、total_revenue）无法通过 BM25/子串匹配
    命中中文术语名，但向量语义检索可以匹配到对应的中文字段名。
    """
    return bool(_ENGLISH_IDENT_RE.match(value.strip()))


def _extract_expr_tokens(expr: str) -> list[str]:
    """从 metrics[].expr 中按 +-*/() 分割，提取含中文的 token。"""
    tokens: list[str] = []
    for segment in _EXPR_SPLIT_RE.split(expr):
        stripped = segment.strip()
        if len(stripped) >= 2 and _HAS_CHINESE_RE.search(stripped):
            tokens.append(stripped)
    return tokens


def extract_terms_query(
    structured_query: dict[str, Any],
) -> list[ExtractedTerm]:
    """从 StructuredQuery 中提取术语。

    Args:
        structured_query: StructuredQuery 的 dict 表示。

    Returns:
        ExtractedTerm 列表，按出现顺序排列。
    """
    terms: list[ExtractedTerm] = []

    # select[]
    for i, val in enumerate(structured_query.get("select") or []):
        text = str(val).strip()
        terms.append(
            ExtractedTerm(
                raw_text=text,
                ktype="select",
                path=f"select.{i}",
                source="main",
                condition_index=-1,
                search_enabled=not _is_skippable(text),
            )
        )

    # filters[]
    _extract_filters(
        structured_query.get("filters") or [],
        prefix="filters",
        terms=terms,
        source="main",
        condition_index=-1,
    )

    # order_by[]
    metrics_aliases = _collect_metrics_aliases(structured_query.get("metrics") or [])
    for i, item in enumerate(structured_query.get("order_by") or []):
        field = str(item.get("field", "")).strip() if isinstance(item, dict) else str(item).strip()
        # 跳过引用 metrics[].as 别名的 order_by
        skip = _is_skippable(field) or field in metrics_aliases
        terms.append(
            ExtractedTerm(
                raw_text=field,
                ktype="orderBy",
                path=f"order_by.{i}.field",
                source="main",
                condition_index=-1,
                search_enabled=not skip,
            )
        )

    return terms


def extract_terms_compute(
    structured_compute: dict[str, Any],
) -> list[ExtractedTerm]:
    """从 StructuredCompute 中提取术语。

    Args:
        structured_compute: StructuredCompute 的 dict 表示。

    Returns:
        ExtractedTerm 列表，按出现顺序排列。
    """
    terms: list[ExtractedTerm] = []
    metrics_aliases = _collect_metrics_aliases(structured_compute.get("metrics") or [])

    # dimensions[]
    for i, dim in enumerate(structured_compute.get("dimensions") or []):
        field = str(dim.get("field", "")).strip() if isinstance(dim, dict) else str(dim).strip()
        terms.append(
            ExtractedTerm(
                raw_text=field,
                ktype="groupBy",
                path=f"dimensions.{i}",
                source="main",
                condition_index=-1,
                search_enabled=not _is_skippable(field),
            )
        )

    # metrics[]
    for i, metric in enumerate(structured_compute.get("metrics") or []):
        if not isinstance(metric, dict):
            continue
        # metrics[].field
        field = str(metric.get("field", "")).strip()
        if field:
            terms.append(
                ExtractedTerm(
                    raw_text=field,
                    ktype="select",
                    path=f"metrics.{i}.field",
                    source="main",
                    condition_index=-1,
                    search_enabled=not _is_skippable(field),
                )
            )
        # metrics[].expr 中的中文 token
        expr = str(metric.get("expr", "")).strip()
        if expr:
            for token in _extract_expr_tokens(expr):
                terms.append(
                    ExtractedTerm(
                        raw_text=token,
                        ktype="select",
                        path=f"metrics.{i}.expr",
                        source="main",
                        condition_index=-1,
                        search_enabled=not _is_skippable(token),
                    )
                )
        # metrics[].filters[]
        _extract_filters(
            metric.get("filters", []),
            prefix=f"metrics.{i}.filters",
            terms=terms,
            source="main",
            condition_index=-1,
        )

    # filters[]
    _extract_filters(
        structured_compute.get("filters") or [],
        prefix="filters",
        terms=terms,
        source="main",
        condition_index=-1,
    )

    # having[] — field 引用 metrics[].as 别名，跳过
    for i, h in enumerate(structured_compute.get("having") or []):
        if not isinstance(h, dict):
            continue
        field = str(h.get("field", "")).strip()
        terms.append(
            ExtractedTerm(
                raw_text=field,
                ktype="select",
                path=f"having.{i}.field",
                source="main",
                condition_index=-1,
                search_enabled=False,  # 引用 metrics[].as，跳过
            )
        )

    # order_by[]
    for i, item in enumerate(structured_compute.get("order_by") or []):
        field = str(item.get("field", "")).strip() if isinstance(item, dict) else str(item).strip()
        skip = _is_skippable(field) or field in metrics_aliases
        terms.append(
            ExtractedTerm(
                raw_text=field,
                ktype="orderBy",
                path=f"order_by.{i}.field",
                source="main",
                condition_index=-1,
                search_enabled=not skip,
            )
        )

    return terms


def extract_terms_complex_conditions(
    complex_conditions: list[str],
) -> list[ExtractedTerm]:
    """对 complex_conditions 逐条 expand_query，提取术语。

    每条 NL 调用 expand_query 展开为 NatQuery，再从中提取术语。
    expand_query 失败时，将整条 NL 作为单个 select 术语。

    Args:
        complex_conditions: 自然语言条件列表。

    Returns:
        ExtractedTerm 列表。
    """
    from datacloud_knowledge.intent.natquery import expand_query

    terms: list[ExtractedTerm] = []
    for idx, sentence in enumerate(complex_conditions):
        stripped_sentence = sentence.strip()
        if not stripped_sentence:
            continue

        natquery = expand_query(stripped_sentence)
        if natquery is None:
            logger.warning(
                "[extract] complex_condition[%d] expand 失败，整条作为术语: %s",
                idx,
                stripped_sentence,
            )
            terms.append(
                ExtractedTerm(
                    raw_text=stripped_sentence,
                    ktype="select",
                    path=f"complex_conditions.{idx}",
                    source="complex_condition",
                    condition_index=idx,
                    search_enabled=not _is_skippable(stripped_sentence),
                )
            )
            continue

        terms.extend(_terms_from_natquery(natquery, condition_index=idx))

    return terms


def _terms_from_natquery(
    nq: Any,
    condition_index: int,
) -> list[ExtractedTerm]:
    """从 NatQuery 中提取术语（用于 complex_conditions expand 后）。"""
    terms: list[ExtractedTerm] = []
    prefix = f"complex_conditions.{condition_index}"

    # select
    for i, s in enumerate(nq.select):
        expr = str(s.expr).strip()
        for token in _extract_expr_tokens(expr) if _EXPR_SPLIT_RE.search(expr) else [expr]:
            if token and not _is_skippable(token):
                terms.append(
                    ExtractedTerm(
                        raw_text=token,
                        ktype="select",
                        path=f"{prefix}.select.{i}",
                        source="complex_condition",
                        condition_index=condition_index,
                    )
                )
        # alias
        for alias in s.alias:
            stripped_alias = alias.strip()
            if stripped_alias and not _is_skippable(stripped_alias):
                terms.append(
                    ExtractedTerm(
                        raw_text=stripped_alias,
                        ktype="select",
                        path=f"{prefix}.select.{i}.alias",
                        source="complex_condition",
                        condition_index=condition_index,
                    )
                )

    # where
    for i, w in enumerate(nq.where):
        field = str(w.field).strip()
        if field and not _is_skippable(field):
            terms.append(
                ExtractedTerm(
                    raw_text=field,
                    ktype="whereKey",
                    path=f"{prefix}.where.{i}.field",
                    source="complex_condition",
                    condition_index=condition_index,
                )
            )
        # field_alias
        for alias in w.field_alias:
            stripped_alias = alias.strip()
            if stripped_alias and not _is_skippable(stripped_alias):
                terms.append(
                    ExtractedTerm(
                        raw_text=stripped_alias,
                        ktype="whereKey",
                        path=f"{prefix}.where.{i}.field_alias",
                        source="complex_condition",
                        condition_index=condition_index,
                    )
                )
        # value
        values = w.value if isinstance(w.value, list) else [w.value]
        for v in values:
            v_str = str(v).strip()
            if v_str and not _is_skippable(v_str):
                terms.append(
                    ExtractedTerm(
                        raw_text=v_str,
                        ktype="whereValue",
                        path=f"{prefix}.where.{i}.value",
                        source="complex_condition",
                        condition_index=condition_index,
                    )
                )

    # group_by
    for i, g in enumerate(nq.group_by):
        field = str(g.field).strip()
        if field and not _is_skippable(field):
            terms.append(
                ExtractedTerm(
                    raw_text=field,
                    ktype="groupBy",
                    path=f"{prefix}.group_by.{i}",
                    source="complex_condition",
                    condition_index=condition_index,
                )
            )
        for alias in g.field_alias:
            stripped_alias = alias.strip()
            if stripped_alias and not _is_skippable(stripped_alias):
                terms.append(
                    ExtractedTerm(
                        raw_text=stripped_alias,
                        ktype="groupBy",
                        path=f"{prefix}.group_by.{i}.alias",
                        source="complex_condition",
                        condition_index=condition_index,
                    )
                )

    # order_by
    for i, o in enumerate(nq.order_by):
        cleaned = re.sub(r"\s+(?:ASC|DESC)\s*$", "", str(o), flags=re.IGNORECASE).strip()
        if cleaned and not _is_skippable(cleaned):
            terms.append(
                ExtractedTerm(
                    raw_text=cleaned,
                    ktype="orderBy",
                    path=f"{prefix}.order_by.{i}",
                    source="complex_condition",
                    condition_index=condition_index,
                )
            )

    return terms


# ── 内部辅助 ─────────────────────────────────────────────────────────


def _extract_filters(
    filters: list[Any],
    *,
    prefix: str,
    terms: list[ExtractedTerm],
    source: str,
    condition_index: int,
) -> None:
    """从 filters 列表中提取 whereKey + whereValue 术语。"""
    for i, f in enumerate(filters):
        if not isinstance(f, dict):
            continue
        # field
        field = str(f.get("field", "")).strip()
        if field:
            terms.append(
                ExtractedTerm(
                    raw_text=field,
                    ktype="whereKey",
                    path=f"{prefix}.{i}.field",
                    source=source,  # type: ignore[arg-type]
                    condition_index=condition_index,
                    search_enabled=not _is_skippable(field),
                    vector_only=_is_vector_only(field),
                )
            )
        # value
        raw_value = f.get("value", "")
        values = raw_value if isinstance(raw_value, list) else [raw_value]
        for v in values:
            v_str = str(v).strip()
            terms.append(
                ExtractedTerm(
                    raw_text=v_str,
                    ktype="whereValue",
                    path=f"{prefix}.{i}.value",
                    source=source,  # type: ignore[arg-type]
                    condition_index=condition_index,
                    search_enabled=not _is_skippable(v_str),
                    vector_only=_is_vector_only(v_str),
                )
            )


def _collect_metrics_aliases(metrics: list[Any]) -> set[str]:
    """收集 metrics[].as 别名集合，用于跳过 order_by/having 中的别名引用。"""
    aliases: set[str] = set()
    for m in metrics:
        if isinstance(m, dict):
            alias = str(m.get("as", "")).strip()
            if alias:
                aliases.add(alias)
    return aliases

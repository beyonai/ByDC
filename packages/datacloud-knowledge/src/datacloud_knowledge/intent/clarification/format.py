"""format_clarification — 应用用户选择，生成最终确定的结构。

输入：原始结构 + 前端回传的 paradigmList（含 choiceKeyword / choiceField / choiceValue）
输出：确定的 StructuredQuery / StructuredCompute dict
"""

from __future__ import annotations

import json
import logging
from typing import Any

from .models import KnowledgeMeta

logger = logging.getLogger(__name__)


def format_clarification_query(
    query: str,
    structured_query: dict[str, Any],
    form: str,
    knowledge: str,
) -> dict[str, Any]:
    """应用用户选择，输出确定的 StructuredQuery。

    Args:
        query: 用户原始查询。
        structured_query: 原始 StructuredQuery dict。
        form: 前端回传的 JSON（含 paradigmList）。
        knowledge: 内部元数据 JSON（KnowledgeMeta）。

    Returns:
        确定的 StructuredQuery dict。
    """
    return _apply_selections(query, structured_query, form, knowledge)


def format_clarification_compute(
    query: str,
    structured_compute: dict[str, Any],
    form: str,
    knowledge: str,
) -> dict[str, Any]:
    """应用用户选择，输出确定的 StructuredCompute。

    Args:
        query: 用户原始查询。
        structured_compute: 原始 StructuredCompute dict。
        form: 前端回传的 JSON（含 paradigmList）。
        knowledge: 内部元数据 JSON（KnowledgeMeta）。

    Returns:
        确定的 StructuredCompute dict。
    """
    return _apply_selections(query, structured_compute, form, knowledge)


def _apply_selections(
    query: str,
    structured: dict[str, Any],
    form: str,
    knowledge: str,
) -> dict[str, Any]:
    """通用选择应用逻辑。"""
    result = _deep_copy_dict(structured)

    # 解析前端回传
    try:
        form_data = json.loads(form) if form else {}
    except (json.JSONDecodeError, ValueError):
        logger.warning("[format] 无法解析 form JSON: %s", form[:200])
        form_data = {}

    # 解析内部元数据
    try:
        meta = KnowledgeMeta.model_validate_json(knowledge) if knowledge else None
    except Exception:
        logger.warning("[format] 无法解析 knowledge JSON: %s", knowledge[:200])
        meta = None

    paradigm_list = form_data.get("paradigmList", [])
    if not paradigm_list:
        logger.info("[format] paradigmList 为空，返回原始结构")
        result["query"] = query
        return result

    path_mapping = meta.path_mapping if meta else {}

    # 遍历 paradigmList，提取用户选择
    for paradigm in paradigm_list:
        paradigm_id = str(paradigm.get("paradigmId", ""))
        for item in paradigm.get("paradigmResult", []):
            _apply_paradigm_item(result, paradigm_id, item, path_mapping)

    # complex_conditions：用户选的组合句子写回
    _apply_complex_condition_selections(result, paradigm_list)

    result["query"] = query
    return result


def _apply_paradigm_item(
    result: dict[str, Any],
    paradigm_id: str,
    item: dict[str, Any],
    path_mapping: dict[str, str],
) -> None:
    """应用单个 paradigm item 的用户选择。"""
    # IFieldItem: choiceKeyword
    choice = item.get("choiceKeyword")
    if choice and paradigm_id in ("1", "2", "4"):
        kid = str(item.get("kid", ""))
        path = path_mapping.get(kid, "")
        if path:
            _set_by_path(result, path, choice)
        return

    # IConditionItem: choiceField / choiceValue
    choice_field = item.get("choiceField")
    choice_value = item.get("choiceValue")
    if choice_field or choice_value:
        # 过滤条件 — 按 path 替换
        field_path = item.get("_fieldPath", "")
        if choice_field and field_path:
            _set_by_path(result, field_path, choice_field)
        # value 替换暂不做 path 精确替换，因为 value 可能是复杂类型


def _apply_complex_condition_selections(
    result: dict[str, Any],
    paradigm_list: list[dict[str, Any]],
) -> None:
    """从 paradigmId=3 中提取 complex_condition 的用户选择。"""
    complex_conditions = result.get("complex_conditions", [])
    if not complex_conditions:
        return

    for paradigm in paradigm_list:
        if str(paradigm.get("paradigmId", "")) != "3":
            continue
        for item in paradigm.get("paradigmResult", []):
            ktype = item.get("ktype", "")
            if ktype != "complexCondition":
                continue
            # 用户选择的组合句子
            choice = item.get("choiceKeyword", "")
            if not choice:
                continue
            # 找到对应的 complex_condition 索引
            keyword = item.get("keyword", "")
            for idx, cc in enumerate(complex_conditions):
                if cc == keyword:
                    complex_conditions[idx] = choice
                    break

    result["complex_conditions"] = complex_conditions


def _set_by_path(obj: dict[str, Any], path: str, value: Any) -> None:
    """按 JSON pointer 路径设置值。

    路径格式：如 "select.0" / "filters.1.field" / "metrics.2.expr"
    """
    parts = path.split(".")
    current: Any = obj
    for _i, part in enumerate(parts[:-1]):
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list):
            try:
                current = current[int(part)]
            except (ValueError, IndexError):
                logger.debug("[format] 路径 %s 无法定位: %s", path, part)
                return
        else:
            return

    if current is None:
        return

    last = parts[-1]
    if isinstance(current, dict):
        current[last] = value
    elif isinstance(current, list):
        try:
            current[int(last)] = value
        except (ValueError, IndexError):
            logger.debug("[format] 路径 %s 无法设置: %s", path, last)


def _deep_copy_dict(d: dict[str, Any]) -> dict[str, Any]:
    """简单深拷贝 dict（通过 JSON 序列化）。"""
    return json.loads(json.dumps(d, ensure_ascii=False))

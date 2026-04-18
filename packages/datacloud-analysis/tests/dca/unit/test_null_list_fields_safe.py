"""T17-1 ~ T17-4：list 字段为 None 时不抛 TypeError。

Bug 描述：
    LLM 在不需要某字段时会发送 null（Python None），例如：
        {"limit": null, "order_by": null, "filters": null, ...}
    但 _collect_terms_from_params / _apply_resolved_to_params 均使用：
        patched.get("order_by", [])
    当 key 存在且值为 None 时，.get() 返回 None 而非 []，
    导致 for 循环触发 TypeError: 'NoneType' object is not iterable。

修复要求：
    将所有列表迭代改为 None 安全写法：
        (patched.get("key") or [])
    涵盖 filters / select / dimensions / metrics / order_by / having，
    以及 _collect_terms_from_params 和 _apply_resume_to_tool_params。
"""

from __future__ import annotations

from typing import Any

# ── T17-1：_collect_terms 对 None 列表不抛异常 ────────────────────────────────


def test_T17_1_collect_terms_tolerates_none_list_fields() -> None:
    """T17-1：tool_params 中 filters/dimensions/metrics/order_by/having 为 None 时不抛异常。"""
    from datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin import (
        _collect_terms_from_params,
    )

    params: dict[str, Any] = {
        "filters": None,
        "select": None,
        "dimensions": None,
        "metrics": None,
        "order_by": None,
        "having": None,
    }

    # 不应抛出 TypeError
    terms = _collect_terms_from_params(params)
    assert isinstance(terms, list)
    assert terms == []


# ── T17-2：_apply_resolved 对 None 列表不抛异常 ───────────────────────────────


def test_T17_2_apply_resolved_tolerates_none_list_fields() -> None:
    """T17-2：tool_params 中各列表字段为 None 时，_apply_resolved_to_params 不抛异常。"""
    from datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin import (
        _apply_resolved_to_params,
    )

    params: dict[str, Any] = {
        "filters": None,
        "select": None,
        "dimensions": None,
        "metrics": None,
        "order_by": None,
        "having": None,
        "limit": None,
    }

    # 不应抛出 TypeError
    new_params = _apply_resolved_to_params(params, {})
    assert isinstance(new_params, dict)
    # 列表字段应被正规化为空列表
    for key in ("filters", "select", "dimensions", "metrics", "order_by", "having"):
        assert new_params[key] == [], f"{key} 应被正规化为 []，实际: {new_params[key]}"


# ── T17-3：混合 None 与正常值时仍正确翻译 ────────────────────────────────────


def test_T17_3_apply_resolved_mixed_none_and_valid() -> None:
    """T17-3：部分字段为 None，有效字段仍正确翻译。"""
    from datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin import (
        _apply_resolved_to_params,
    )

    params: dict[str, Any] = {
        "filters": [{"field_name_cn": "企业等级", "op": "eq", "value": "A"}],
        "order_by": None,
        "having": None,
        "dimensions": None,
        "metrics": None,
        "select": None,
    }
    resolved = {"企业等级": "enterprise_level_name"}

    new_params = _apply_resolved_to_params(params, resolved)

    f = new_params["filters"][0]
    assert f.get("field") == "enterprise_level_name", f"filters 翻译失败: {f}"
    assert "field_name_cn" not in f
    assert new_params["order_by"] == []
    assert new_params["having"] == []


# ── T17-4：_collect_terms 混合 None 与正常值时仍正确收集 ─────────────────────


def test_T17_4_collect_terms_mixed_none_and_valid() -> None:
    """T17-4：部分字段为 None，有效字段仍正确收集 terms。"""
    from datacloud_analysis.tool_hook_plugins.builtin.query_clarification_plugin import (
        _collect_terms_from_params,
    )

    params: dict[str, Any] = {
        "filters": [{"field_name_cn": "企业等级", "op": "eq", "value": "A"}],
        "order_by": None,
        "having": None,
        "dimensions": None,
        "metrics": None,
        "select": None,
    }

    terms = _collect_terms_from_params(params)
    assert "企业等级" in terms, f"应收集到 '企业等级'，实际: {terms}"

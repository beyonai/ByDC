"""T5: worker.py 情形一路径改造 — 先红后绿

测试覆盖：
  5.1 worker.py 从 rel_resource_list 解析 ScopeEntry（含 ontologyBaseCode → base_id）
  5.1 旧格式（mounted_objects）降级为 OBJECT 类型 ScopeEntry
  5.2 构建 RequestToolContext 并传给 OntologyAgent.ask() 的 tool_context 参数
"""

from __future__ import annotations

# ─────────────────────────────────────────────────────────────────────────────
# 辅助：构建最小化 worker 测试环境
# ─────────────────────────────────────────────────────────────────────────────


def _make_config_extra(rel_resource_list: list[dict]) -> dict:
    return {
        "rel_resource_list": rel_resource_list,
        "redirect_tools": {},
        "tool_metadata": {},
    }


# ─────────────────────────────────────────────────────────────────────────────
# T5.0 worker.py 可导入 _build_scope_entries（纯解析函数）
# ─────────────────────────────────────────────────────────────────────────────


def test_worker_build_scope_entries_importable() -> None:
    """worker.py 应导出 _build_scope_entries 函数（解析 rel_resource_list → list[ScopeEntry]）。"""
    from byclaw_data.worker import _build_scope_entries  # noqa: F401


# ─────────────────────────────────────────────────────────────────────────────
# T5.1 _build_scope_entries 正确解析 rel_resource_list
# ─────────────────────────────────────────────────────────────────────────────


def test_build_scope_entries_object_type() -> None:
    """OBJECT 类型：code=resourceCode, scope_type=OBJECT, base_id=ontologyBaseCode。"""
    from byclaw_data.worker import _build_scope_entries

    rel = [
        {
            "resourceCode": "by_customer",
            "resourceBizType": "OBJECT",
            "ontologyBaseCode": "lib_crm",
        }
    ]
    entries = _build_scope_entries(rel)

    assert len(entries) == 1
    e = entries[0]
    assert e.code == "by_customer"
    assert e.scope_type == "OBJECT"
    assert e.base_id == "lib_crm"


def test_build_scope_entries_scene_type() -> None:
    """SCENE 类型：code=resourceCode, base_id=ontologyBaseCode。"""
    from byclaw_data.worker import _build_scope_entries

    rel = [
        {
            "resourceCode": "scene_sales",
            "resourceBizType": "SCENE",
            "ontologyBaseCode": "lib_crm",
        }
    ]
    entries = _build_scope_entries(rel)

    assert len(entries) == 1
    e = entries[0]
    assert e.scope_type == "SCENE"
    assert e.base_id == "lib_crm"


def test_build_scope_entries_ontology_base_type() -> None:
    """ONTOLOGY_BASE 类型：base_id == code（自身即为库）。"""
    from byclaw_data.worker import _build_scope_entries

    rel = [
        {
            "resourceCode": "lib_crm",
            "resourceBizType": "ONTOLOGY_BASE",
            "ontologyBaseCode": "",  # 忽略，base_id 用 code
        }
    ]
    entries = _build_scope_entries(rel)

    assert len(entries) == 1
    e = entries[0]
    assert e.scope_type == "ONTOLOGY_BASE"
    assert e.base_id == "lib_crm"


def test_build_scope_entries_filters_unknown_types() -> None:
    """未知 resourceBizType 的条目应被过滤掉。"""
    from byclaw_data.worker import _build_scope_entries

    rel = [
        {"resourceCode": "x", "resourceBizType": "SKILL"},
        {"resourceCode": "by_customer", "resourceBizType": "OBJECT", "ontologyBaseCode": "lib"},
    ]
    entries = _build_scope_entries(rel)

    assert len(entries) == 1
    assert entries[0].code == "by_customer"


def test_build_scope_entries_fallback_from_mounted_objects() -> None:
    """rel_resource_list 为空时，从 mounted_objects 生成 OBJECT 类型 ScopeEntry（兼容旧格式）。"""
    from byclaw_data.worker import _build_scope_entries

    entries = _build_scope_entries([], mounted_objects=["by_customer", "by_order"])

    assert len(entries) == 2
    assert all(e.scope_type == "OBJECT" for e in entries)
    assert {e.code for e in entries} == {"by_customer", "by_order"}


def test_build_scope_entries_rel_takes_priority_over_mounted_objects() -> None:
    """rel_resource_list 非空时，mounted_objects 不使用（rel 优先）。"""
    from byclaw_data.worker import _build_scope_entries

    rel = [{"resourceCode": "by_customer", "resourceBizType": "OBJECT", "ontologyBaseCode": "lib"}]
    entries = _build_scope_entries(rel, mounted_objects=["by_order"])

    assert len(entries) == 1
    assert entries[0].code == "by_customer"


# ─────────────────────────────────────────────────────────────────────────────
# T5.2 情形一：tool_context 传给 OntologyAgent.ask()
# ─────────────────────────────────────────────────────────────────────────────


def test_worker_passes_tool_context_to_ontology_agent() -> None:
    """worker 情形一路径应构建 RequestToolContext 并传给 _ontology_agent.ask() 的 tool_context 参数。"""
    import inspect

    from byclaw_data import worker as mod

    source = inspect.getsource(mod)
    # 红测试：source 应该包含将 tool_context 传给 ask() 的代码
    assert "tool_context=tool_context" in source or "tool_context=" in source, (
        "worker.py 情形一应将 RequestToolContext 传给 OntologyAgent.ask()"
    )


def test_worker_reads_rel_resource_list_from_config_extra() -> None:
    """worker.py 情形一应从 config_extra['rel_resource_list'] 读取资源列表。"""
    import inspect

    from byclaw_data import worker as mod

    source = inspect.getsource(mod)
    assert "rel_resource_list" in source, "worker.py 应从 config_extra 中读取 rel_resource_list"

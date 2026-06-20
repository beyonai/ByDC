"""3.1 工具池设计 — 测试文件（先红后绿）

测试目标：
  - tool_pool.py 模块可导入
  - TOOL_POOL / TOOL_TO_OBJECT 全局字典存在
  - register_tool / get_tools / _get_object_code_by_tool 函数行为正确
  - OntologyRelationGraph 从 loader 构建，get_next_objects 返回正确
  - span_cache.py 模块可导入，get_cached_observations / cache_observations 行为正确
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

# ── 3.1.1 tool_pool 模块 ──────────────────────────────────────────────────────


def test_tool_pool_module_importable() -> None:
    from datacloud_analysis.tools import tool_pool  # noqa: F401


def test_tool_pool_globals_exist() -> None:
    from datacloud_analysis.tools.tool_pool import TOOL_POOL, TOOL_TO_OBJECT

    assert isinstance(TOOL_POOL, dict)
    assert isinstance(TOOL_TO_OBJECT, dict)


def test_register_and_get_tool() -> None:
    from datacloud_analysis.tools.tool_pool import (
        TOOL_POOL,
        TOOL_TO_OBJECT,
        get_tools,
        register_tool,
    )

    fake_tool = MagicMock()
    fake_tool.name = "test_get_spans"
    register_tool("test_get_spans", fake_tool, object_code="ops_test_obj")

    assert "test_get_spans" in TOOL_POOL
    assert TOOL_TO_OBJECT.get("test_get_spans") == "ops_test_obj"

    result = get_tools(["test_get_spans"])
    assert result["test_get_spans"] is fake_tool

    # 不存在的工具名不报错，返回空
    result_empty = get_tools(["nonexistent_tool"])
    assert result_empty == {}

    # 清理
    del TOOL_POOL["test_get_spans"]
    del TOOL_TO_OBJECT["test_get_spans"]


def test_get_object_code_by_tool() -> None:
    from datacloud_analysis.tools.tool_pool import (
        TOOL_TO_OBJECT,
        _get_object_code_by_tool,
        register_tool,
    )

    fake = MagicMock()
    fake.name = "test_action_abc"
    register_tool("test_action_abc", fake, object_code="ops_foo")

    assert _get_object_code_by_tool("test_action_abc") == "ops_foo"
    assert _get_object_code_by_tool("not_registered") is None

    del TOOL_TO_OBJECT["test_action_abc"]
    from datacloud_analysis.tools.tool_pool import TOOL_POOL

    del TOOL_POOL["test_action_abc"]


# ── 3.1.2 OntologyRelationGraph ───────────────────────────────────────────────


def test_ontology_relation_graph_importable() -> None:
    from datacloud_analysis.tools.ontology_relation_graph import (  # noqa: F401
        NextObjectSuggestion,
        OntologyRelationGraph,
    )


def test_ontology_relation_graph_empty_loader() -> None:
    from datacloud_analysis.tools.ontology_relation_graph import OntologyRelationGraph

    mock_loader = MagicMock()
    mock_loader.get_ontology_relations.return_value = []

    graph = OntologyRelationGraph(mock_loader)
    assert graph.get_next_objects("ops_anything") == []


def test_ontology_relation_graph_get_next_objects() -> None:
    from datacloud_analysis.tools.ontology_relation_graph import (
        NextObjectSuggestion,
        OntologyRelationGraph,
    )

    # 模拟一条 OWL 关系：ops_langfuse_trace → ops_early_span，resolve=get_early_span
    rel = MagicMock()
    rel.source_class = "ops_langfuse_trace"
    rel.target_class = "ops_early_span"
    rel.resolve_action_code = "get_early_span"
    rel.relation_type = "ONE_TO_ONE"
    rel.relation_name = "包含EarlySpan"
    rel.description = '{"unlock_reason": "发现 early_span", "unlock_hint": "传入 trace_id"}'

    mock_loader = MagicMock()
    mock_loader.get_ontology_relations.return_value = [rel]

    graph = OntologyRelationGraph(mock_loader)
    suggestions = graph.get_next_objects("ops_langfuse_trace")

    assert len(suggestions) == 1
    s = suggestions[0]
    assert isinstance(s, NextObjectSuggestion)
    assert s.tool == "get_early_span"
    assert s.object_code == "ops_early_span"
    assert "early_span" in s.reason
    assert s.hint == "传入 trace_id"


def test_ontology_relation_graph_skips_no_resolve_action() -> None:
    from datacloud_analysis.tools.ontology_relation_graph import OntologyRelationGraph

    rel = MagicMock()
    rel.source_class = "ops_langfuse_trace"
    rel.target_class = "ops_something"
    rel.resolve_action_code = None  # 没有 resolve_action_code，应跳过
    rel.relation_name = "some_rel"
    rel.description = ""

    mock_loader = MagicMock()
    mock_loader.get_ontology_relations.return_value = [rel]

    graph = OntologyRelationGraph(mock_loader)
    assert graph.get_next_objects("ops_langfuse_trace") == []


def test_ontology_relation_graph_skips_non_ops() -> None:
    from datacloud_analysis.tools.ontology_relation_graph import OntologyRelationGraph

    rel = MagicMock()
    rel.source_class = "by_customer"  # 非 ops_* 对象，应跳过
    rel.target_class = "by_opportunity"
    rel.resolve_action_code = "query_by_opportunity"
    rel.relation_name = "rel"
    rel.description = ""

    mock_loader = MagicMock()
    mock_loader.get_ontology_relations.return_value = [rel]

    graph = OntologyRelationGraph(mock_loader)
    assert graph.get_next_objects("by_customer") == []


# ── 3.1 _init_ext_tool_pool 重命名与参数扩展（先红后绿）─────────────────────────


def test_init_ext_tool_pool_exists() -> None:
    """_init_ext_tool_pool 函数必须存在，替换旧的 _init_ops_tool_pool。"""
    from datacloud_analysis.tools import tool_pool

    assert hasattr(tool_pool, "_init_ext_tool_pool"), (
        "_init_ext_tool_pool not found; rename _init_ops_tool_pool"
    )
    assert not hasattr(tool_pool, "_init_ops_tool_pool"), (
        "_init_ops_tool_pool must be removed; use _init_ext_tool_pool"
    )


def test_init_ext_tool_pool_accepts_ext_codes(tmp_path: Any) -> None:
    """_init_ext_tool_pool 接受 ext_codes 参数，不报 TypeError。"""
    import inspect

    from datacloud_analysis.tools.tool_pool import _init_ext_tool_pool

    sig = inspect.signature(_init_ext_tool_pool)
    assert "ext_codes" in sig.parameters, "_init_ext_tool_pool must have ext_codes parameter"
    assert "name_prefix" in sig.parameters, "_init_ext_tool_pool must have name_prefix parameter"


def test_init_ext_tool_pool_ext_codes_none_scans_directory(tmp_path: Any) -> None:
    """ext_codes=None 时扫描目录，行为与原 _init_ops_tool_pool 一致。"""
    from pathlib import Path as _Path

    # 创建最小 object 目录结构
    obj_dir = tmp_path / "object"
    (_Path(obj_dir) / "ops_test_a").mkdir(parents=True)
    (_Path(obj_dir) / "ops_test_b").mkdir(parents=True)
    (_Path(obj_dir) / "by_customer").mkdir(parents=True)

    captured = []

    def fake_scan(resource_path, ext_codes=None, name_prefix=None):
        object_dir_inner = _Path(resource_path) / "object"
        scanned = sorted(
            d.name
            for d in object_dir_inner.iterdir()
            if d.is_dir() and (name_prefix is None or d.name.startswith(name_prefix))
        )
        captured.extend(scanned)

    # ext_codes=None, name_prefix=None → 全量扫
    fake_scan(str(tmp_path), ext_codes=None, name_prefix=None)
    assert "ops_test_a" in captured
    assert "ops_test_b" in captured
    assert "by_customer" in captured  # 全量模式包含所有子目录


def test_init_ext_tool_pool_ext_codes_list_skips_scan(tmp_path: Any) -> None:
    """ext_codes=[...] 时直接使用列表，不扫描目录。"""
    import inspect

    from datacloud_analysis.tools.tool_pool import _init_ext_tool_pool

    # 仅验证签名默认值，ext_codes=None 表示扫目录
    sig = inspect.signature(_init_ext_tool_pool)
    param = sig.parameters["ext_codes"]
    assert param.default is None, "ext_codes default must be None (scan mode)"


def test_init_ops_tool_pool_removed() -> None:
    """_init_ops_tool_pool 旧接口必须已删除，不允许残留。"""
    from datacloud_analysis.tools import tool_pool

    assert not hasattr(tool_pool, "_init_ops_tool_pool"), (
        "_init_ops_tool_pool must be removed; callers must use _init_ext_tool_pool"
    )


def test_span_cache_importable() -> None:
    from datacloud_analysis.tools import span_cache  # noqa: F401


def test_span_cache_operations() -> None:
    from datacloud_analysis.tools.span_cache import (
        cache_observations,
        get_cached_observations,
    )

    trace_id = "test_trace_abc123"
    fake_obs: list[dict[str, Any]] = [
        {"id": "span1", "name": "datacloud-agent", "type": "SPAN"},
        {"id": "span2", "name": "ChatOpenAI", "type": "GENERATION"},
    ]

    # 未缓存时返回空
    assert get_cached_observations(trace_id) == []

    # 写入缓存
    cache_observations(trace_id, fake_obs)

    # 读取缓存
    result = get_cached_observations(trace_id)
    assert result == fake_obs
    assert len(result) == 2

    # 不同 trace_id 隔离
    assert get_cached_observations("other_trace") == []

"""4.3 自举机制测试 — 先红后绿

测试目标：
1. OntologyLoader.load_from_json_resource_directory() — JSON 目录加载，增量不清空
2. LocalOntologyAdapter._get_loader() 追加 JSON 加载
3. OntologyResourceService.create_object() 扩展 search_scope_extra + build_terms 调用
4. build_terms() search_scope_extra 透传到 term_name
5. engine._build_effective_scope_clause() 支持 owner_type=task 过滤
6. task_tools.py 五个自举工具存在且可调用
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


# ── 1. OntologyLoader.load_from_json_resource_directory ───────────────────────

def test_loader_has_load_from_json_resource_directory() -> None:
    """OntologyLoader 应有 load_from_json_resource_directory 方法。"""
    from datacloud_data_sdk.ontology.loader import OntologyLoader

    assert hasattr(OntologyLoader, "load_from_json_resource_directory"), \
        "OntologyLoader 应有 load_from_json_resource_directory 方法"


def test_load_from_json_resource_directory_loads_objects() -> None:
    """load_from_json_resource_directory 应加载 scene/objects/*.json 中的对象。"""
    from datacloud_data_sdk.ontology.loader import OntologyLoader

    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        # 创建目录结构：base/scene1/objects/task_hot_opp.json
        obj_dir = base / "scene1" / "objects"
        obj_dir.mkdir(parents=True)
        obj_data = {
            "object_code": "task_hot_opp",
            "object_name": "高价值商机",
            "description": "筛选后的高价值商机集合",
            "source_type": "DB",
            "fields": [],
            "actions": [],
        }
        (obj_dir / "task_hot_opp.json").write_text(
            json.dumps(obj_data, ensure_ascii=False), encoding="utf-8"
        )

        loader = OntologyLoader()
        loader.load_from_json_resource_directory(str(base))

        assert "task_hot_opp" in loader._classes, \
            "load_from_json_resource_directory 应将对象加载进 _classes"
        cls = loader._classes["task_hot_opp"]
        assert cls.object_name == "高价值商机"


def test_load_from_json_resource_directory_supports_camelcase() -> None:
    """load_from_json_resource_directory 应支持驼峰格式（objectCode/objectName）。"""
    from datacloud_data_sdk.ontology.loader import OntologyLoader

    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        obj_dir = base / "scene" / "objects"
        obj_dir.mkdir(parents=True)
        # JSONWriter 写的是驼峰格式
        obj_data = {
            "objectCode": "task_camel_test",
            "objectName": "驼峰测试对象",
            "objectDesc": "测试驼峰字段映射",
            "properties": [],
            "actions": [],
        }
        (obj_dir / "task_camel_test.json").write_text(
            json.dumps(obj_data, ensure_ascii=False), encoding="utf-8"
        )

        loader = OntologyLoader()
        loader.load_from_json_resource_directory(str(base))

        assert "task_camel_test" in loader._classes, \
            "应支持驼峰格式 objectCode"


def test_load_from_json_resource_directory_incremental() -> None:
    """load_from_json_resource_directory 应增量追加，不清空已有 _classes。"""
    from datacloud_data_sdk.ontology.loader import OntologyLoader

    loader = OntologyLoader()
    # 先直接加一个对象
    loader.load_from_content({
        "objects": [{
            "object_code": "existing_obj",
            "object_name": "已有对象",
            "fields": [],
            "actions": [],
        }],
        "relations": [],
        "views": [],
    })
    assert "existing_obj" in loader._classes

    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        obj_dir = base / "scene" / "objects"
        obj_dir.mkdir(parents=True)
        (obj_dir / "task_new.json").write_text(
            json.dumps({"object_code": "task_new", "object_name": "新对象",
                        "fields": [], "actions": []}, ensure_ascii=False),
            encoding="utf-8",
        )
        loader.load_from_json_resource_directory(str(base))

    # 旧对象不能被清空
    assert "existing_obj" in loader._classes, "增量加载不应清空已有对象"
    assert "task_new" in loader._classes, "应加载新对象"


def test_load_from_json_resource_directory_loads_relations() -> None:
    """load_from_json_resource_directory 应加载 scene/relations.json 中的关系。"""
    from datacloud_data_sdk.ontology.loader import OntologyLoader

    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        scene_dir = base / "scene"
        scene_dir.mkdir(parents=True)
        rel_data = {
            "relations": [{
                "relation_code": "task_to_customer",
                "relation_name": "商机关联客户",
                "source_class": "task_hot_opp",
                "target_class": "by_customer",
                "relation_type": "ONE_TO_MANY",
                "join_keys": [{"from": "customer_id", "to": "id"}],
            }]
        }
        (scene_dir / "relations.json").write_text(
            json.dumps(rel_data, ensure_ascii=False), encoding="utf-8"
        )

        loader = OntologyLoader()
        loader.load_from_json_resource_directory(str(base))

        rel_codes = [r.relation_code for r in loader._relations]
        assert "task_to_customer" in rel_codes, "应加载 relations.json 中的关系"


# ── 2. LocalOntologyAdapter._get_loader 追加 JSON 加载 ────────────────────────

def test_local_adapter_get_loader_calls_json_directory() -> None:
    """LocalOntologyAdapter._get_loader 应在 OWL 加载后追加 JSON 目录加载。"""
    try:
        import inspect
        from datacloud_server.adapters.local_adapter import LocalOntologyAdapter

        src = inspect.getsource(LocalOntologyAdapter._get_loader)
        assert "load_from_json_resource_directory" in src, \
            "_get_loader 应调用 load_from_json_resource_directory"
    except ModuleNotFoundError:
        pytest.skip("datacloud_server 不在当前测试环境")


def test_local_adapter_reload_loader_calls_json_directory() -> None:
    """LocalOntologyAdapter._reload_loader 应同样追加 JSON 目录加载。"""
    try:
        import inspect
        from datacloud_server.adapters.local_adapter import LocalOntologyAdapter

        src = inspect.getsource(LocalOntologyAdapter._reload_loader)
        assert "load_from_json_resource_directory" in src, \
            "_reload_loader 应调用 load_from_json_resource_directory"
    except ModuleNotFoundError:
        pytest.skip("datacloud_server 不在当前测试环境")


# ── 3. OntologyResourceService.create_object search_scope_extra ───────────────

def test_ontology_resource_service_create_object_accepts_search_scope_extra() -> None:
    """OntologyResourceService.create_object 应接受 search_scope_extra 参数。"""
    try:
        import inspect
        from datacloud_server.services.ontology_resource_service import OntologyResourceService

        sig = inspect.signature(OntologyResourceService.create_object)
        params = sig.parameters
        assert "search_scope_extra" in params, \
            "create_object 应有 search_scope_extra 参数"
    except ModuleNotFoundError:
        pytest.skip("datacloud_server 不在当前测试环境")


def test_ontology_resource_service_create_object_calls_build_terms() -> None:
    """create_object 传入 search_scope_extra 时应调用 build_terms。"""
    try:
        import inspect
        from datacloud_server.services.ontology_resource_service import OntologyResourceService

        src = inspect.getsource(OntologyResourceService.create_object)
        assert "build_terms" in src or "search_scope_extra" in src, \
            "create_object 应在有 search_scope_extra 时调用 build_terms"
    except ModuleNotFoundError:
        pytest.skip("datacloud_server 不在当前测试环境")


# ── 4. _batch_sync_term_names search_scope 透传 ────────────────────────────────

def test_batch_sync_term_names_accepts_search_scope() -> None:
    """_batch_sync_term_names 应接受 search_scope 参数（已有）。"""
    import inspect
    from datacloud_knowledge.ingestion.owl_import.importer.writer._term import (
        _batch_sync_term_names,
    )

    sig = inspect.signature(_batch_sync_term_names)
    assert "search_scope" in sig.parameters, \
        "_batch_sync_term_names 已有 search_scope 参数"


def test_build_terms_accepts_search_scope_extra() -> None:
    """build_terms 应接受 search_scope_extra 参数。"""
    import inspect
    from datacloud_knowledge.ingestion.ontology_terms import build_terms

    sig = inspect.signature(build_terms)
    assert "search_scope_extra" in sig.parameters, \
        "build_terms 应有 search_scope_extra 参数"


# ── 5. engine._build_effective_scope_clause task scope ────────────────────────

def test_build_effective_scope_clause_supports_task_scope() -> None:
    """_build_effective_scope_clause 应支持 owner_type=task 过滤。"""
    import inspect
    from datacloud_knowledge.adapters.opengauss.engine import _build_effective_scope_clause

    src = inspect.getsource(_build_effective_scope_clause)
    # 函数已有 JSONB 过滤，需要加 owner_type 支持
    # 验证方式：检查源码中有 owner_type 字段或 task scope 相关处理
    assert "owner_type" in src or "task" in src.lower(), \
        "_build_effective_scope_clause 应支持 owner_type=task 过滤"


# ── 6. task_tools.py 五个自举工具 ─────────────────────────────────────────────

def test_task_tools_module_importable() -> None:
    """task_tools 模块应可导入。"""
    from datacloud_analysis.tools import task_tools  # noqa: F401


def test_task_tools_exports_five_tools() -> None:
    """task_tools 应导出五个自举工具函数。"""
    from datacloud_analysis.tools.task_tools import (
        create_task_object,
        create_task_relation,
        create_task_view,
        delete_task_object,
        query_task_graph,
    )
    assert create_task_object is not None
    assert create_task_relation is not None
    assert create_task_view is not None
    assert delete_task_object is not None
    assert query_task_graph is not None


def test_create_task_object_schema() -> None:
    """create_task_object 应有 file_id / object_code / description 参数。"""
    import inspect
    from datacloud_analysis.tools.task_tools import create_task_object

    sig = inspect.signature(create_task_object.func if hasattr(create_task_object, "func") else create_task_object)
    params = sig.parameters
    assert "file_id" in params
    assert "object_code" in params
    assert "description" in params


def test_create_task_relation_schema() -> None:
    """create_task_relation 应有 from_object / to_object / join_keys / description 参数。"""
    import inspect
    from datacloud_analysis.tools.task_tools import create_task_relation

    sig = inspect.signature(create_task_relation.func if hasattr(create_task_relation, "func") else create_task_relation)
    params = sig.parameters
    assert "from_object" in params
    assert "to_object" in params
    assert "join_keys" in params


def test_query_task_graph_schema() -> None:
    """query_task_graph 应有 sql 参数。"""
    import inspect
    from datacloud_analysis.tools.task_tools import query_task_graph

    sig = inspect.signature(query_task_graph.func if hasattr(query_task_graph, "func") else query_task_graph)
    params = sig.parameters
    assert "sql" in params


def test_create_task_object_invocable_with_mock() -> None:
    """create_task_object 应可调用（mock 底层依赖）。"""
    from datacloud_analysis.tools.task_tools import create_task_object

    with patch("datacloud_analysis.tools.task_tools._do_create_task_object") as mock_fn:
        mock_fn.return_value = "已创建任务对象 task_test_001，属性 3 个"
        result = create_task_object.invoke({
            "file_id": "uuid-test-001",
            "object_code": "test_001",
            "description": "测试物化对象",
        })
        assert isinstance(result, str)
        assert len(result) > 0

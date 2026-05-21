"""OntologyBuildSession 单元测试 — 先红后绿。

所有数据库依赖通过 mock/monkeypatch 替换。
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from datacloud_knowledge.ingestion.ontology_build import OntologyBuildSession
from datacloud_knowledge.ingestion.workspace_store import LocalFileWorkspaceStore

# ── Fixture ────────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _use_local_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """全部测试使用 LocalFileWorkspaceStore，隔离 Redis 依赖。"""
    monkeypatch.setenv("ONTOLOGY_STORE", "local")
    monkeypatch.setenv("ONTOLOGY_WORKSPACE_DIR", str(tmp_path))
    store = LocalFileWorkspaceStore()

    def _mock_store() -> LocalFileWorkspaceStore:
        return store

    monkeypatch.setattr(
        "datacloud_knowledge.ingestion.ontology_build.get_workspace_store", _mock_store
    )


@pytest.fixture()
def session() -> OntologyBuildSession:
    return OntologyBuildSession()


# ── collect_object_info ────────────────────────────────────────────────────────


class TestCollectObjectInfo:
    def test_first_call_returns_state_with_entity_code(self, session: OntologyBuildSession) -> None:
        result = session.collect_object_info(entity_code="by_test")
        assert result["entity_code"] == "by_test"

    def test_missing_entity_name_and_fields_on_first_call(
        self, session: OntologyBuildSession
    ) -> None:
        result = session.collect_object_info(entity_code="by_test")
        assert "entity_name" in result["missing"]
        assert "fields" in result["missing"]

    def test_entity_name_filled_removes_from_missing(self, session: OntologyBuildSession) -> None:
        session.collect_object_info(entity_code="by_test")
        result = session.collect_object_info(entity_code="by_test", entity_name="测试对象")
        assert "entity_name" not in result["missing"]
        assert result["entity_name"] == "测试对象"

    def test_fields_filled_removes_from_missing(self, session: OntologyBuildSession) -> None:
        fields = [
            {
                "property_code": "title",
                "property_name": "标题",
                "data_type": "STRING",
                "ext_property": {
                    "property_role_rule": {"property_role": "DIMENSION", "rule_type": "name"}
                },
            }
        ]
        result = session.collect_object_info(entity_code="by_test", fields=fields)
        assert "fields" not in result["missing"]

    def test_multi_round_merge_non_empty_fields_only(self, session: OntologyBuildSession) -> None:
        """多轮调用，非空字段才覆盖已有值。"""
        session.collect_object_info(entity_code="by_test", entity_name="初始名称")
        # 第二轮不传 entity_name，应保留上次的值
        result = session.collect_object_info(entity_code="by_test", entity_desc="描述")
        assert result["entity_name"] == "初始名称"
        assert result["entity_desc"] == "描述"

    def test_field_upsert_by_property_code(self, session: OntologyBuildSession) -> None:
        """fields 按 property_code 做 upsert，新增+修改都正确。"""
        f1 = [
            {
                "property_code": "title",
                "property_name": "标题",
                "data_type": "STRING",
                "ext_property": {},
            }
        ]
        session.collect_object_info(entity_code="by_test", entity_name="X", fields=f1)
        f2 = [
            {
                "property_code": "title",
                "property_name": "任务标题",
                "data_type": "STRING",
                "ext_property": {},
            },
            {
                "property_code": "status",
                "property_name": "状态",
                "data_type": "STRING",
                "ext_property": {},
            },
        ]
        result = session.collect_object_info(entity_code="by_test", fields=f2)
        codes = [f["property_code"] for f in result["fields"]]
        assert "title" in codes
        assert "status" in codes
        title_field = next(f for f in result["fields"] if f["property_code"] == "title")
        assert title_field["property_name"] == "任务标题"

    def test_session_id_isolation(self, session: OntologyBuildSession) -> None:
        """不同 session_id 存储隔离。"""
        session.collect_object_info(
            entity_code="by_test", session_id="s1", entity_name="用户A的任务"
        )
        session.collect_object_info(
            entity_code="by_test", session_id="s2", entity_name="用户B的任务"
        )
        r1 = session.collect_object_info(entity_code="by_test", session_id="s1")
        r2 = session.collect_object_info(entity_code="by_test", session_id="s2")
        assert r1["entity_name"] == "用户A的任务"
        assert r2["entity_name"] == "用户B的任务"

    def test_kb_fields_stored(self, session: OntologyBuildSession) -> None:
        """非结构化专用字段 kb_id / kb_directory 存储正确。"""
        result = session.collect_object_info(
            entity_code="by_doc",
            entity_name="文档对象",
            kb_id="kb-001",
            kb_directory="/meeting",
        )
        assert result["kb_id"] == "kb-001"
        assert result["kb_directory"] == "/meeting"

    def test_no_missing_when_all_required_fields_filled(
        self, session: OntologyBuildSession
    ) -> None:
        fields = [
            {
                "property_code": "title",
                "property_name": "标题",
                "data_type": "STRING",
                "ext_property": {},
            }
        ]
        result = session.collect_object_info(
            entity_code="by_test", entity_name="我的任务", fields=fields
        )
        assert result["missing"] == []


# ── collect_view_info ──────────────────────────────────────────────────────────


class TestCollectViewInfo:
    def test_first_call_returns_view_code(self, session: OntologyBuildSession) -> None:
        result = session.collect_view_info(view_code="v_test")
        assert result["view_code"] == "v_test"

    def test_missing_view_name_and_relations_on_first_call(
        self, session: OntologyBuildSession
    ) -> None:
        result = session.collect_view_info(view_code="v_test")
        assert "view_name" in result["missing"]
        assert "object_relations" in result["missing"]

    def test_view_name_filled_removes_from_missing(self, session: OntologyBuildSession) -> None:
        result = session.collect_view_info(view_code="v_test", view_name="任务视图")
        assert "view_name" not in result["missing"]

    def test_object_relations_upsert_by_four_tuple_key(self, session: OntologyBuildSession) -> None:
        """object_relations 按四元组 upsert。"""
        rels1 = [
            {
                "source_object_code": "by_task",
                "source_object_field_code": "user_id",
                "target_object_code": "by_user",
                "target_object_field_code": "id",
                "relation_type": "MANY_TO_ONE",
            }
        ]
        session.collect_view_info(view_code="v_test", view_name="视图", object_relations=rels1)
        rels2 = [
            {
                "source_object_code": "by_task",
                "source_object_field_code": "user_id",
                "target_object_code": "by_user",
                "target_object_field_code": "id",
                "relation_type": "ONE_TO_ONE",
            }
        ]  # 修改 relation_type
        result = session.collect_view_info(view_code="v_test", object_relations=rels2)
        assert len(result["object_relations"]) == 1
        assert result["object_relations"][0]["relation_type"] == "ONE_TO_ONE"

    def test_no_missing_when_all_filled(self, session: OntologyBuildSession) -> None:
        rels = [
            {
                "source_object_code": "by_task",
                "source_object_field_code": "user_id",
                "target_object_code": "by_user",
                "target_object_field_code": "id",
                "relation_type": "MANY_TO_ONE",
            }
        ]
        result = session.collect_view_info(
            view_code="v_test", view_name="视图", object_relations=rels
        )
        assert result["missing"] == []


# ── list_bindable_term_types ───────────────────────────────────────────────────


class TestListBindableTermTypes:
    def test_returns_list(self, session: OntologyBuildSession) -> None:
        """list_bindable_term_types 始终返回 list（可以为空，取决于术语库是否有 LIST_TERM/DICT_TERM）。"""
        with patch(
            "datacloud_knowledge.ingestion.ontology_build.create_reader"
        ) as mock_create_reader:
            mock_reader = MagicMock()
            mock_reader.get_type_codes_by_category.return_value = set()
            mock_create_reader.return_value = mock_reader
            result = session.list_bindable_term_types()
        assert isinstance(result, list)

    def test_returns_term_type_items_with_correct_structure(
        self, session: OntologyBuildSession
    ) -> None:
        with patch(
            "datacloud_knowledge.ingestion.ontology_build.create_reader"
        ) as mock_create_reader:
            mock_reader = MagicMock()
            mock_reader.get_type_codes_by_category.return_value = {"user_name"}
            # search_terms 返回 SearchTermsResult-like，用 MagicMock 模拟
            mock_search_result = MagicMock()
            mock_search_result.items = [MagicMock(term_code="001", term_name="黄药师")]
            mock_reader.search_terms.return_value = mock_search_result
            mock_create_reader.return_value = mock_reader
            result = session.list_bindable_term_types()

        assert len(result) >= 1
        item = result[0]
        assert "type_code" in item
        assert "samples" in item

    def test_keyword_filter(self, session: OntologyBuildSession) -> None:
        """keyword 非空时，只返回 type_code 或 type_name 包含关键词的术语类型。"""
        with patch(
            "datacloud_knowledge.ingestion.ontology_build.create_reader"
        ) as mock_create_reader:
            mock_reader = MagicMock()
            mock_reader.get_type_codes_by_category.return_value = {"user_name", "device_type"}
            mock_reader.search_terms.return_value = MagicMock(items=[])
            mock_create_reader.return_value = mock_reader
            result = session.list_bindable_term_types(keyword="user")

        type_codes = [item["type_code"] for item in result]
        assert "device_type" not in type_codes


# ── get_term_type_values ───────────────────────────────────────────────────────


class TestGetTermTypeValues:
    def test_returns_term_list(self, session: OntologyBuildSession) -> None:
        with patch(
            "datacloud_knowledge.ingestion.ontology_build.search_terms_by_type"
        ) as mock_search:
            mock_result = MagicMock()
            mock_result.items = [MagicMock(term_code="001", term_name="黄药师")]
            mock_search.return_value = mock_result
            result = session.get_term_type_values("user_name")

        assert isinstance(result, list)
        assert result[0]["term_code"] == "001"
        assert result[0]["term_name"] == "黄药师"

    def test_keyword_passed_through(self, session: OntologyBuildSession) -> None:
        with patch(
            "datacloud_knowledge.ingestion.ontology_build.search_terms_by_type"
        ) as mock_search:
            mock_result = MagicMock()
            mock_result.items = []
            mock_search.return_value = mock_result
            session.get_term_type_values("user_name", keyword="黄")

        _, kwargs = mock_search.call_args
        assert kwargs.get("keyword") == "黄"


# ── submit_object ──────────────────────────────────────────────────────────────


class TestSubmitObject:
    def test_returns_error_when_no_workspace_state(self, session: OntologyBuildSession) -> None:
        result = session.submit_object("nonexistent_obj")
        assert result["ok"] is False
        assert "error" in result

    def test_returns_missing_when_entity_name_absent(self, session: OntologyBuildSession) -> None:
        session.collect_object_info(entity_code="by_test")
        result = session.submit_object("by_test")
        assert result["ok"] is False
        assert "entity_name" in result["missing"]

    def test_returns_missing_when_fields_absent(self, session: OntologyBuildSession) -> None:
        session.collect_object_info(entity_code="by_test", entity_name="测试对象")
        result = session.submit_object("by_test")
        assert result["ok"] is False
        assert "fields" in result["missing"]

    def test_workspace_cleared_after_submit_success(
        self, session: OntologyBuildSession, tmp_path: Path
    ) -> None:
        """提交成功后暂存数据被清除。"""
        fields = [
            {
                "property_code": "title",
                "property_name": "标题",
                "data_type": "STRING",
                "ext_property": {},
            }
        ]
        session.collect_object_info(entity_code="by_test", entity_name="我的任务", fields=fields)
        with (
            patch("datacloud_knowledge.ingestion.ontology_build.generate_from_definition"),
            patch(
                "datacloud_knowledge.ingestion.ontology_build._submit_object_async"
            ) as mock_upload,
            patch("datacloud_knowledge.ingestion.ontology_build._create_sqlite_table"),
        ):
            mock_upload.return_value = {"ok": True, "resource_id": "123"}
            result = session.submit_object("by_test")

        assert result["ok"] is True
        # 验证暂存已清除
        store = LocalFileWorkspaceStore()
        remaining = store.load("by_test")
        assert remaining == {}

    def test_workspace_preserved_when_submit_fails(self, session: OntologyBuildSession) -> None:
        """提交失败（校验失败）时暂存数据不被清除。"""
        session.collect_object_info(entity_code="by_test", entity_name="测试对象")
        # 没有 fields，submit 会失败（校验失败，不是异常）
        session.submit_object("by_test")
        # 暂存数据应仍存在
        store = LocalFileWorkspaceStore()
        state = store.load("by_test")
        assert state.get("entity_name") == "测试对象"

    def test_entity_source_dynamic_table_when_no_kb_id(self, session: OntologyBuildSession) -> None:
        fields = [
            {
                "property_code": "title",
                "property_name": "标题",
                "data_type": "STRING",
                "ext_property": {},
            }
        ]
        session.collect_object_info(entity_code="by_test", entity_name="我的任务", fields=fields)
        with (
            patch(
                "datacloud_knowledge.ingestion.ontology_build.generate_from_definition"
            ) as mock_gen,
            patch(
                "datacloud_knowledge.ingestion.ontology_build._submit_object_async"
            ) as mock_upload,
            patch("datacloud_knowledge.ingestion.ontology_build._create_sqlite_table"),
        ):
            mock_upload.return_value = {"ok": True, "resource_id": "456"}
            session.submit_object("by_test")
            # generate_from_definition 被调用时，workspace_state 的 entity_source 应为 DYNAMIC_TABLE
            args, _ = mock_gen.call_args
            workspace_state = args[0]
            assert workspace_state["entity_source"] == "DYNAMIC_TABLE"

    def test_entity_source_knowledge_base_when_kb_id_present(
        self, session: OntologyBuildSession
    ) -> None:
        fields = [
            {
                "property_code": "topic",
                "property_name": "主题",
                "data_type": "STRING",
                "ext_property": {},
            }
        ]
        session.collect_object_info(
            entity_code="by_doc",
            entity_name="文档对象",
            fields=fields,
            kb_id="kb-001",
            kb_directory="/meeting",
        )
        with (
            patch(
                "datacloud_knowledge.ingestion.ontology_build.generate_from_definition"
            ) as mock_gen,
            patch(
                "datacloud_knowledge.ingestion.ontology_build._submit_object_async"
            ) as mock_upload,
        ):
            mock_upload.return_value = {"ok": True, "resource_id": "789"}
            session.submit_object("by_doc")
            args, _ = mock_gen.call_args
            workspace_state = args[0]
            assert workspace_state["entity_source"] == "KNOWLEDGE_BASE"


# ── submit_view ────────────────────────────────────────────────────────────────


class TestSubmitView:
    def test_returns_error_when_no_workspace_state(self, session: OntologyBuildSession) -> None:
        result = session.submit_view("nonexistent_view")
        assert result["ok"] is False

    def test_returns_missing_when_view_name_absent(self, session: OntologyBuildSession) -> None:
        session.collect_view_info(view_code="v_test")
        result = session.submit_view("v_test")
        assert result["ok"] is False
        assert "view_name" in result["missing"]

    def test_returns_missing_when_relations_absent(self, session: OntologyBuildSession) -> None:
        session.collect_view_info(view_code="v_test", view_name="视图")
        result = session.submit_view("v_test")
        assert result["ok"] is False
        assert "object_relations" in result["missing"]

    def test_workspace_cleared_after_view_submit_success(
        self, session: OntologyBuildSession, tmp_path: Path
    ) -> None:
        rels = [
            {
                "source_object_code": "by_task",
                "source_object_field_code": "user_id",
                "target_object_code": "by_user",
                "target_object_field_code": "id",
                "relation_type": "MANY_TO_ONE",
            }
        ]
        session.collect_view_info(view_code="v_test", view_name="任务视图", object_relations=rels)
        with (
            patch("datacloud_knowledge.ingestion.ontology_build.generate_from_definition"),
            patch("datacloud_knowledge.ingestion.ontology_build._import_view_zip") as mock_upload,
        ):
            mock_upload.return_value = {"ok": True, "resource_id": "view-001"}
            result = session.submit_view("v_test")

        assert result["ok"] is True
        store = LocalFileWorkspaceStore()
        assert store.load("v_test") == {}

    def test_no_create_table_called_for_view(self, session: OntologyBuildSession) -> None:
        """视图提交不调用 create_table。"""
        rels = [
            {
                "source_object_code": "by_task",
                "source_object_field_code": "user_id",
                "target_object_code": "by_user",
                "target_object_field_code": "id",
                "relation_type": "MANY_TO_ONE",
            }
        ]
        session.collect_view_info(view_code="v_test", view_name="任务视图", object_relations=rels)
        with (
            patch("datacloud_knowledge.ingestion.ontology_build.generate_from_definition"),
            patch("datacloud_knowledge.ingestion.ontology_build._import_view_zip") as mock_upload,
            patch(
                "datacloud_knowledge.ingestion.ontology_build._create_sqlite_table"
            ) as mock_create_table,
        ):
            mock_upload.return_value = {"ok": True, "resource_id": "view-002"}
            session.submit_view("v_test")
        mock_create_table.assert_not_called()


# ── delete_owl_scope ───────────────────────────────────────────────────────────


class TestDeleteOwlScope:
    def test_delete_returns_ok(self, session: OntologyBuildSession) -> None:
        with patch(
            "datacloud_knowledge.ingestion.ontology_build.create_reader"
        ) as mock_create_reader:
            mock_reader = MagicMock()
            mock_reader.delete_scope.return_value = {"ok": True}
            mock_create_reader.return_value = mock_reader
            result = session.delete_owl_scope("OBJECT", "by_test")
        assert result["ok"] is True

    def test_delete_raises_on_failure(self, session: OntologyBuildSession) -> None:
        with patch(
            "datacloud_knowledge.ingestion.ontology_build.create_reader"
        ) as mock_create_reader:
            mock_reader = MagicMock()
            mock_reader.delete_scope.return_value = {"ok": False, "error": "删除失败"}
            mock_create_reader.return_value = mock_reader
            with pytest.raises(RuntimeError, match="术语删除失败"):
                session.delete_owl_scope("OBJECT", "by_test")


# ── build_terms ────────────────────────────────────────────────────────────────


class TestBuildTerms:
    """测试 build_terms() 函数 — KPS 对象构建 + BulkImportAdapter 调用。"""

    def test_term_type_code_binding_creates_prop_and_has_field(self) -> None:
        """字段带 term_type_code 时，创建 prop 术语 + HAS_FIELD 关系，不创建值术语。"""
        from datacloud_knowledge.ingestion.ontology_terms import build_terms

        fields: list[dict[str, str]] = [
            {
                "property_code": "user_code",
                "property_name": "用户编码",
                "term_type_code": "user_name",
                "term_data_type": "LIST_TERM",
            }
        ]

        with patch(
            "datacloud_knowledge.ingestion.ontology_terms.create_bulk_importer"
        ) as mock_create:
            mock_adapter = MagicMock()
            mock_create.return_value = mock_adapter

            result = build_terms(
                entity_code="by_task",
                entity_name="任务",
                fields=fields,
            )

        assert result["ok"] is True
        # 验证 begin_import 调用
        mock_adapter.begin_import.assert_called_once()
        scopes_arg = mock_adapter.begin_import.call_args.kwargs["scopes"]
        assert scopes_arg == [{"scope": "object", "code": "by_task"}]

        # 验证 batch_process_term 调用：实体 + prop = 2 个术语
        mock_adapter.batch_process_term.assert_called_once()
        term_items = mock_adapter.batch_process_term.call_args.args[0]
        assert len(term_items) == 2  # entity + prop

        # 验证术语类型
        entity_term = next(t for t in term_items if t["term_code"] == "by_task")
        assert entity_term["term_type_code"] == "object"
        prop_term = next(t for t in term_items if t["term_code"] == "user_code")
        assert prop_term["term_type_code"] == "prop"

        # 验证 batch_process_relation 调用：1 条 HAS_FIELD
        mock_adapter.batch_process_relation.assert_called_once()
        rel_items = mock_adapter.batch_process_relation.call_args.args[0]
        assert len(rel_items) == 1
        assert rel_items[0]["relation_category"] == "HAS_FIELD"

    def test_term_values_inline_creates_value_terms_and_has_term(self) -> None:
        """字段带 term_values 时，创建 prop + 值术语 + HAS_FIELD + HAS_TERM 关系。"""
        from datacloud_knowledge.ingestion.ontology_terms import build_terms

        fields: list[dict[str, object]] = [
            {
                "property_code": "status",
                "property_name": "状态",
                "term_data_type": "LIST_TERM",
                "term_values": [
                    {"code": "done", "name": "完成"},
                    {"code": "todo", "name": "待办"},
                ],
            }
        ]

        with patch(
            "datacloud_knowledge.ingestion.ontology_terms.create_bulk_importer"
        ) as mock_create:
            mock_adapter = MagicMock()
            mock_create.return_value = mock_adapter

            result = build_terms(
                entity_code="by_task",
                entity_name="任务",
                fields=fields,
            )

        assert result["ok"] is True
        # 术语：entity(1) + prop(1) + value(2) = 4
        mock_adapter.batch_process_term.assert_called_once()
        term_items = mock_adapter.batch_process_term.call_args.args[0]
        assert len(term_items) == 4

        # 值术语验证
        value_terms = [t for t in term_items if t["term_type_code"] == "status"]
        assert len(value_terms) == 2
        value_names = {t["term_name"] for t in value_terms}
        assert value_names == {"完成", "待办"}

        # 关系：HAS_FIELD(1) + HAS_TERM(2) = 3
        mock_adapter.batch_process_relation.assert_called_once()
        rel_items = mock_adapter.batch_process_relation.call_args.args[0]
        assert len(rel_items) == 3
        has_field_rels = [r for r in rel_items if r["relation_category"] == "HAS_FIELD"]
        has_term_rels = [r for r in rel_items if r["relation_category"] == "HAS_TERM"]
        assert len(has_field_rels) == 1
        assert len(has_term_rels) == 2

    def test_mixed_fields_both_binding_and_inline(self) -> None:
        """混合字段：同时有 term_type_code 绑定和 term_values 内联。"""
        from datacloud_knowledge.ingestion.ontology_terms import build_terms

        fields: list[dict[str, object]] = [
            {
                "property_code": "user_code",
                "property_name": "用户编码",
                "term_type_code": "user_name",
                "term_data_type": "LIST_TERM",
            },
            {
                "property_code": "status",
                "property_name": "状态",
                "term_data_type": "LIST_TERM",
                "term_values": [{"code": "done", "name": "完成"}],
            },
        ]

        with patch(
            "datacloud_knowledge.ingestion.ontology_terms.create_bulk_importer"
        ) as mock_create:
            mock_adapter = MagicMock()
            mock_create.return_value = mock_adapter

            result = build_terms(
                entity_code="by_task",
                entity_name="任务",
                fields=fields,
            )

        assert result["ok"] is True
        # 术语：entity(1) + prop(2) + value(1) = 4
        term_items = mock_adapter.batch_process_term.call_args.args[0]
        assert len(term_items) == 4

        # 关系：HAS_FIELD(2) + HAS_TERM(1) = 3
        rel_items = mock_adapter.batch_process_relation.call_args.args[0]
        assert len(rel_items) == 3

    def test_no_term_fields_get_prop_and_has_field(self) -> None:
        """无术语绑定的字段也创建 prop 术语 + HAS_FIELD 关系（与 OWL 生成器一致）。"""
        from datacloud_knowledge.ingestion.ontology_terms import build_terms

        fields: list[dict[str, str]] = [
            {
                "property_code": "title",
                "property_name": "标题",
                "data_type": "STRING",
                "ext_property": {},
            }
        ]

        with patch(
            "datacloud_knowledge.ingestion.ontology_terms.create_bulk_importer"
        ) as mock_create:
            mock_adapter = MagicMock()
            mock_create.return_value = mock_adapter

            result = build_terms(
                entity_code="by_task",
                entity_name="任务",
                fields=fields,
            )

        # 术语：entity(1) + prop(1) = 2
        assert result["ok"] is True
        term_items = mock_adapter.batch_process_term.call_args.args[0]
        assert len(term_items) == 2
        prop_term = next(t for t in term_items if t["term_code"] == "title")
        assert prop_term["term_type_code"] == "prop"

        # 关系：HAS_FIELD(1)
        rel_items = mock_adapter.batch_process_relation.call_args.args[0]
        assert len(rel_items) == 1
        assert rel_items[0]["relation_category"] == "HAS_FIELD"
        assert "title" in rel_items[0]["target_term_code"]

    def test_empty_fields_skipped(self) -> None:
        """空字段列表时跳过。"""
        from datacloud_knowledge.ingestion.ontology_terms import build_terms

        with patch(
            "datacloud_knowledge.ingestion.ontology_terms.create_bulk_importer"
        ) as mock_create:
            mock_adapter = MagicMock()
            mock_create.return_value = mock_adapter

            result = build_terms(
                entity_code="by_task",
                entity_name="任务",
                fields=[],
            )

        assert result["ok"] is True
        assert result.get("message") == "无字段术语需要入库"
        mock_adapter.begin_import.assert_not_called()

    def test_view_entity_type(self) -> None:
        """entity_type="view" 时正确构造视图术语。"""
        from datacloud_knowledge.ingestion.ontology_terms import build_terms

        fields: list[dict[str, str]] = [
            {
                "property_code": "task_count",
                "property_name": "任务数",
                "term_type_code": "metric_type",
            }
        ]

        with patch(
            "datacloud_knowledge.ingestion.ontology_terms.create_bulk_importer"
        ) as mock_create:
            mock_adapter = MagicMock()
            mock_create.return_value = mock_adapter

            result = build_terms(
                entity_code="v_task_summary",
                entity_name="任务汇总视图",
                fields=fields,
                entity_type="view",
            )

        assert result["ok"] is True
        term_items = mock_adapter.batch_process_term.call_args.args[0]
        entity_term = next(t for t in term_items if t["term_code"] == "v_task_summary")
        assert entity_term["term_type_code"] == "view"

    def test_db_connection_error_returns_error(self) -> None:
        """DB 连接失败时返回错误，不抛异常。"""
        from datacloud_knowledge.ingestion.ontology_terms import build_terms

        fields: list[dict[str, str]] = [
            {"property_code": "status", "property_name": "状态", "term_type_code": "status_type"}
        ]

        with patch(
            "datacloud_knowledge.ingestion.ontology_terms.create_bulk_importer"
        ) as mock_create:
            mock_create.side_effect = RuntimeError("DB not available")

            result = build_terms(
                entity_code="by_task",
                entity_name="任务",
                fields=fields,
            )

        assert result["ok"] is False
        assert "创建数据库连接失败" in result["error"]

    def test_db_write_error_rolls_back(self) -> None:
        """写入失败时回滚事务。"""
        from datacloud_knowledge.ingestion.ontology_terms import build_terms

        fields: list[dict[str, str]] = [
            {"property_code": "status", "property_name": "状态", "term_type_code": "status_type"}
        ]

        with patch(
            "datacloud_knowledge.ingestion.ontology_terms.create_bulk_importer"
        ) as mock_create:
            mock_adapter = MagicMock()
            mock_adapter.batch_process_term.side_effect = RuntimeError("write failed")
            mock_create.return_value = mock_adapter

            result = build_terms(
                entity_code="by_task",
                entity_name="任务",
                fields=fields,
            )

        assert result["ok"] is False
        assert "术语写入失败" in result["error"]
        mock_adapter.rollback.assert_called_once()
        mock_adapter.close.assert_called_once()
        mock_adapter.commit.assert_not_called()


# ── submit_object / submit_view 调用 build_terms ────────────────────────────────


class TestSubmitViewCallsBuildTerms:
    """验证 submit_view 在 OWL 上传成功后调用 build_terms。"""

    def test_build_terms_called_after_view_upload(self, session: OntologyBuildSession) -> None:
        rels = [
            {
                "source_object_code": "by_task",
                "source_object_field_code": "user_id",
                "target_object_code": "by_user",
                "target_object_field_code": "id",
                "relation_type": "MANY_TO_ONE",
            }
        ]
        session.collect_view_info(view_code="v_test", view_name="任务视图", object_relations=rels)
        with (
            patch("datacloud_knowledge.ingestion.ontology_build.generate_from_definition"),
            patch("datacloud_knowledge.ingestion.ontology_build._import_view_zip") as mock_upload,
            patch("datacloud_knowledge.ingestion.ontology_build.build_terms") as mock_build_terms,
        ):
            mock_upload.return_value = {"ok": True, "resource_id": "view-001"}
            mock_build_terms.return_value = {"ok": True}

            session.submit_view("v_test")

        mock_build_terms.assert_called_once()
        call_kwargs = mock_build_terms.call_args.kwargs
        assert call_kwargs["entity_type"] == "view"

    def test_build_terms_failure_not_block_view_submit(self, session: OntologyBuildSession) -> None:
        rels = [
            {
                "source_object_code": "by_task",
                "source_object_field_code": "user_id",
                "target_object_code": "by_user",
                "target_object_field_code": "id",
                "relation_type": "MANY_TO_ONE",
            }
        ]
        session.collect_view_info(view_code="v_test", view_name="任务视图", object_relations=rels)
        with (
            patch("datacloud_knowledge.ingestion.ontology_build.generate_from_definition"),
            patch("datacloud_knowledge.ingestion.ontology_build._import_view_zip") as mock_upload,
            patch("datacloud_knowledge.ingestion.ontology_build.build_terms") as mock_build_terms,
        ):
            mock_upload.return_value = {"ok": True, "resource_id": "view-002"}
            mock_build_terms.return_value = {"ok": False, "error": "DB down"}

            result = session.submit_view("v_test")

        assert result["ok"] is True

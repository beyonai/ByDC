"""对象术语同步单元测试 — sync_object_terms / remove_object_terms。

测试 BulkImportAdapter 写入 + 级联删除路径，使用 unittest.mock 替换 DB 依赖。
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from datacloud_knowledge.ingestion.term_sync import remove_object_terms, sync_object_terms


class TestSyncObjectTerms:
    """sync_object_terms() — 验证 BulkImportAdapter 写入路径。"""

    @pytest.fixture
    def _patch_bulk_importer(self) -> MagicMock:
        """返回 patched BulkImportAdapter 实例。"""
        mock_adapter = MagicMock()
        mock_adapter.__enter__ = MagicMock(return_value=mock_adapter)
        mock_adapter.__exit__ = MagicMock(return_value=None)
        return mock_adapter

    def test_sync_with_fields_writes_via_bulk_importer(
        self, _patch_bulk_importer: MagicMock
    ) -> None:
        """有字段时：构建 KPS → 调用 BulkImportAdapter 批量写入。"""
        fields = [
            {"property_code": "name", "property_name": "名称", "data_type": "STRING"},
            {"property_code": "price", "property_name": "价格", "data_type": "DECIMAL"},
        ]

        with (
            patch(
                "datacloud_knowledge.ingestion.ontology_terms.create_bulk_importer",
                return_value=_patch_bulk_importer,
            ) as mock_create,
            patch(
                "datacloud_knowledge.ingestion.ontology_terms.backfill_tsvector",
            ) as mock_tsvector,
            patch(
                "datacloud_knowledge.ingestion.ontology_terms.backfill_embeddings",
            ) as mock_embeddings,
        ):
            result = sync_object_terms(
                entity_code="test_product",
                entity_name="测试产品",
                entity_desc="测试用产品",
                fields=fields,
                backfill_vectors=True,
            )

        assert result.get("ok") is True
        assert "stats" in result

        # 验证 BulkImportAdapter 被创建
        mock_create.assert_called_once()
        _patch_bulk_importer.begin_import.assert_called_once()
        _patch_bulk_importer.batch_process_term_type.assert_called()
        _patch_bulk_importer.batch_process_term.assert_called_once()
        _patch_bulk_importer.batch_process_relation.assert_called_once()
        _patch_bulk_importer.commit.assert_called_once()

        # 验证 terms 写入：1 entity + 2 props = 3 terms
        terms_call = _patch_bulk_importer.batch_process_term.call_args
        assert terms_call is not None
        term_dicts = terms_call[0][0]
        assert len(term_dicts) == 3

        # 验证 relations 写入：2 HAS_FIELD
        rels_call = _patch_bulk_importer.batch_process_relation.call_args
        assert rels_call is not None
        rel_dicts = rels_call[0][0]
        assert len(rel_dicts) == 2

        # 验证 backfill 被调用
        mock_tsvector.assert_called()
        # embeddings 在独立线程中执行，仅验证函数引用被访问
        mock_embeddings.assert_called()

    def test_sync_without_fields_returns_early(self) -> None:
        """无字段或只有 entity 时：不调用 BulkImportAdapter，直接返回 ok。"""
        with (
            patch(
                "datacloud_knowledge.ingestion.ontology_terms.create_bulk_importer"
            ) as mock_create,
        ):
            result = sync_object_terms(
                entity_code="bare_entity",
                entity_name="裸实体",
                fields=None,
            )

        assert result.get("ok") is True
        assert "无字段术语需要入库" in str(result.get("message", ""))
        mock_create.assert_not_called()

    def test_sync_with_empty_fields_list_returns_early(self) -> None:
        """fields=[] 时：不调用 BulkImportAdapter。"""
        with patch(
            "datacloud_knowledge.ingestion.ontology_terms.create_bulk_importer"
        ) as mock_create:
            result = sync_object_terms(
                entity_code="bare_entity",
                entity_name="裸实体",
                fields=[],
            )

        assert result.get("ok") is True
        mock_create.assert_not_called()

    def test_sync_skips_field_without_property_code(self, _patch_bulk_importer: MagicMock) -> None:
        """property_code 为空的字段被跳过。"""
        fields = [
            {"property_code": "valid", "property_name": "有效字段", "data_type": "STRING"},
            {"property_code": "", "property_name": "无编码", "data_type": "STRING"},
        ]

        with (
            patch(
                "datacloud_knowledge.ingestion.ontology_terms.create_bulk_importer",
                return_value=_patch_bulk_importer,
            ),
            patch("datacloud_knowledge.ingestion.ontology_terms.backfill_tsvector"),
            patch("datacloud_knowledge.ingestion.ontology_terms.backfill_embeddings"),
        ):
            result = sync_object_terms(
                entity_code="test_skip",
                entity_name="跳过无编码",
                fields=fields,
                backfill_vectors=False,
            )

        assert result.get("ok") is True
        terms_call = _patch_bulk_importer.batch_process_term.call_args
        assert terms_call is not None
        term_dicts = terms_call[0][0]
        # 只有 1 entity + 1 valid prop = 2 terms
        assert len(term_dicts) == 2

    def test_sync_handles_importer_creation_failure(self) -> None:
        """BulkImportAdapter 创建失败返回 error。"""
        fields = [{"property_code": "name", "property_name": "名称", "data_type": "STRING"}]

        with patch(
            "datacloud_knowledge.ingestion.ontology_terms.create_bulk_importer",
            side_effect=RuntimeError("DB 不可用"),
        ):
            result = sync_object_terms(
                entity_code="test_error",
                entity_name="测试错误",
                fields=fields,
            )

        assert result.get("ok") is False
        assert "创建数据库连接失败" in str(result.get("error", ""))


class TestRemoveObjectTerms:
    """remove_object_terms() — 验证级联删除路径。"""

    def test_remove_delegates_to_reader_delete_scope(self) -> None:
        """成功删除：调用 reader.delete_scope 并返回 ok。"""
        mock_reader = MagicMock()
        mock_reader.delete_scope.return_value = {"ok": True}

        with patch(
            "datacloud_knowledge.ingestion.term_sync.create_reader",
            return_value=mock_reader,
        ):
            result = remove_object_terms("test_entity")

        assert result == {"ok": True}
        mock_reader.delete_scope.assert_called_once_with("object:test_entity")

    def test_remove_returns_error_on_delete_failure(self) -> None:
        """reader.delete_scope 返回 ok=False 时，返回 error。"""
        mock_reader = MagicMock()
        mock_reader.delete_scope.return_value = {"ok": False, "error": "级联删除失败"}

        with patch(
            "datacloud_knowledge.ingestion.term_sync.create_reader",
            return_value=mock_reader,
        ):
            result = remove_object_terms("test_entity")

        assert result.get("ok") is False
        assert "级联删除失败" in str(result.get("error", ""))

    def test_remove_handles_reader_exception(self) -> None:
        """reader 异常时返回 error，不抛出。"""
        mock_reader = MagicMock()
        mock_reader.delete_scope.side_effect = ValueError("连接断开")

        with patch(
            "datacloud_knowledge.ingestion.term_sync.create_reader",
            return_value=mock_reader,
        ):
            result = remove_object_terms("test_entity")

        assert result.get("ok") is False
        assert "连接断开" in str(result.get("error", ""))

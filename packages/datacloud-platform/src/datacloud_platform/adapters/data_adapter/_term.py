"""TermBackend + TermRelation + TermName."""

from __future__ import annotations

import logging
from typing import Any

from datacloud_platform.adapters.data_adapter._base import DataCloudDataBackendBase

logger = logging.getLogger(__name__)


class TermBackendMixin(DataCloudDataBackendBase):
    """TermBackend + TermRelation + TermName."""

    # ── TermBackend ─────────────────────────────────────────────────────────

    def search_terms(
        self,
        *,
        dataset_ids: list[str] | None = None,
        keyword: str | None = None,
        term_name: str | None = None,
        term_type: str | None = None,
        query_type: str = "fulltext",
        parent_term_code: str | None = None,
        label_filters: list[dict[str, Any]] | None = None,
        label_condition: str = "and",
        term_ids: list[str] | None = None,
        top_k: int = 20,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Multi-strategy term search via datacloud_knowledge provider."""
        from datacloud_knowledge.provider import query_terms  # noqa: PLC0415

        return query_terms(  # type: ignore[no-any-return]
            dataset_ids=dataset_ids,
            keyword=keyword,
            term_name=term_name,
            term_type=term_type,
            query_type=query_type,
            parent_term_code=parent_term_code,
            label_filters=label_filters,
            label_condition=label_condition,
            term_ids=term_ids,
            top_k=top_k,
            offset=offset,
        )

    def get_term_detail(
        self, *, dataset_id: str, term_id: str
    ) -> dict[str, Any] | None:
        """Get single term detail via datacloud_knowledge provider."""
        from datacloud_knowledge.provider import (  # noqa: PLC0415
            get_term_detail as sdk_get_term_detail,
        )

        return sdk_get_term_detail(dataset_id=dataset_id, term_id=term_id)  # type: ignore[no-any-return]

    def list_terms(
        self,
        *,
        dataset_id: str,
        term_type: str | None = None,
        term_type_no_eq: str | None = None,
        page_index: int = 1,
        page_size: int = 50,
    ) -> dict[str, Any]:
        """Paginated term listing via datacloud_knowledge provider."""
        from datacloud_knowledge.provider import (  # noqa: PLC0415
            list_terms as sdk_list_terms,
        )

        return sdk_list_terms(  # type: ignore[no-any-return]
            dataset_id=dataset_id,
            term_type=term_type,
            term_type_no_eq=term_type_no_eq,
            page_index=page_index,
            page_size=page_size,
        )

    def create_term(self, *, term: dict[str, Any]) -> dict[str, Any]:
        """Create a single term — wraps import_terms.

        支持 camelCase 和 snake_case 两种 dict 格式：
        - termName / term_name
        - termCode / term_code
        - termTypeCode / term_type_code
        - parentTermCode / parent_term_code
        ``dataset_id`` 优先从 dict 中取，缺省时使用 ``""``（provider 层有 fallback）。
        """
        dataset_id = term.get("datasetId") or term.get("dataset_id") or "default_term"
        return self.import_terms(dataset_id=dataset_id, terms=[term])

    def import_terms(
        self, *, dataset_id: str, terms: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Batch import terms via datacloud_knowledge provider.

        ``terms`` 为 dict 列表，支持 camelCase 和 snake_case 两种 key 格式。
        内部自动转换为 ``TermCreate`` 对象再传给 sdk。
        """
        from datacloud_knowledge.provider import (  # noqa: PLC0415
            import_terms as sdk_import_terms,
        )

        term_creates = [_dict_to_term_create(t) for t in terms]
        result = sdk_import_terms(dataset_id=dataset_id, terms=term_creates)
        return {"created": result.created, "term_ids": result.term_ids, "errors": result.errors}

    def update_term(
        self, *, dataset_id: str, term_id: str, updates: dict[str, Any]
    ) -> None:
        """Update a term via datacloud_knowledge provider."""
        from datacloud_knowledge.provider import (  # noqa: PLC0415
            update_term as sdk_update_term,
        )

        sdk_update_term(dataset_id=dataset_id, term_id=term_id, updates=updates)

    def delete_term(self, *, term_id: str) -> None:
        """Delete a term via datacloud_knowledge writer."""
        from datacloud_knowledge.adapters import create_writer  # noqa: PLC0415

        writer = create_writer()
        writer.delete_term(term_id=term_id)

    # ── TermSyncHandler 协议实现 ────────────────────────────────────────────
    # 供 term_sync_worker 注入使用，不依赖 BulkImportAdapter。

    def ensure_term_type(self, *, type_code: str, type_name: str) -> None:
        """确保术语类型存在（幂等）。实现 TermSyncHandler.ensure_term_type。"""
        try:
            self.create_term_type(
                term_type={
                    "typeCode": type_code,
                    "typeName": type_name,
                    "typeDesc": "",
                    "typeCategory": 1,
                }
            )
        except Exception:
            logger.debug("ensure_term_type: type_code=%s already exists or failed", type_code)

    def upsert_terms(self, *, terms: list[dict[str, Any]]) -> list[str]:
        """批量 upsert 术语，返回 term_id 列表。实现 TermSyncHandler.upsert_terms。

        ``terms`` 每条包含：term_code, term_name, term_desc,
        term_type_code, library_code, domain_code。
        使用 writer.upsert_term 实现真正的 INSERT-or-UPDATE 语义，
        避免 import_terms（纯 INSERT）在 update 事件时静默失败。
        """
        from datacloud_knowledge.adapters import create_writer  # noqa: PLC0415

        if not terms:
            return []
        term_ids: list[str] = []
        with create_writer() as writer:
            for t in terms:
                term_code = t.get("term_code") or ""
                term_name = t.get("term_name") or ""
                term_type_code = t.get("term_type_code") or ""
                library_id = t.get("library_code") or t.get("library_id") or None
                if not term_code or not term_name or not term_type_code:
                    continue
                try:
                    term_id = writer.upsert_term(
                        term_code=term_code,
                        term_name=term_name,
                        term_type_code=term_type_code,
                        library_id=library_id,
                        backfill_vectors=False,  # 批量时关闭单条向量回填，避免阻塞
                    )
                    term_ids.append(term_id)
                except Exception:
                    logger.warning(
                        "upsert_terms: failed term_code=%s type=%s",
                        term_code,
                        term_type_code,
                        exc_info=True,
                    )
        return term_ids

    def delete_terms(
        self,
        *,
        term_ids: list[str] | None = None,
        terms: list[dict[str, Any]] | None = None,
    ) -> None:
        """批量删除术语，支持两种入参，均有值时全部执行。

        Args:
            term_ids: 数据库 UUID 列表，直接按主键删除。
            terms:    业务三元组 dict 列表（term_code, term_type_code, library_code），
                      先通过 reader.get_term_by_ids 反查 UUID 再删除。
        """
        from datacloud_knowledge.adapters import create_reader, create_writer  # noqa: PLC0415

        ids_to_delete: list[str] = list(term_ids) if term_ids else []

        # ── 业务三元组 → UUID ────────────────────────────────────────────
        if terms:
            keys: list[tuple[str, str, str]] = []
            for t in terms:
                library_id = t.get("library_code") or t.get("library_id") or ""
                term_type_code = t.get("term_type_code") or ""
                term_code = t.get("term_code") or ""
                if library_id and term_type_code and term_code:
                    keys.append((library_id, term_type_code, term_code))
                else:
                    logger.warning("delete_terms: 缺少必要字段，跳过 term=%s", t)

            if keys:
                try:
                    reader = create_reader()
                    id_map: dict[tuple[str, str, str], str] = reader.get_term_by_ids(keys=keys)
                    ids_to_delete.extend(id_map.values())
                except Exception:
                    logger.warning("delete_terms: 查询 term_id 失败", exc_info=True)

        if not ids_to_delete:
            logger.debug("delete_terms: 无需删除")
            return

        with create_writer() as writer:
            for db_id in ids_to_delete:
                try:
                    writer.delete_term(term_id=db_id)
                except Exception:
                    logger.warning("delete_terms: failed db_term_id=%s", db_id, exc_info=True)

    def query_term_relations(
        self,
        *,
        term_id: str,
        relation_category: str | None = None,
        direction: str = "both",
        depth: int = 1,
    ) -> dict[str, Any]:
        """Query term relations via knowledge reader."""
        reader = self._get_knowledge_reader()
        try:
            return reader.query_term_relations(  # type: ignore[no-any-return]
                term_id=term_id,
                relation_category=relation_category,
                direction=direction,
                depth=depth,
            )
        except Exception:
            logger.exception("query_term_relations failed term_id=%s", term_id)
            return {"data": [], "totalCount": 0}

    # ── TermRelation ────────────────────────────────────────────────────

    def list_term_relations(
        self,
        *,
        source_term_id: str | None = None,
        target_term_id: str | None = None,
        relation_category: str | None = None,
    ) -> list[dict[str, Any]]:
        reader = self._get_knowledge_reader()
        try:
            return reader.list_term_relations(  # type: ignore[no-any-return]
                source_term_id=source_term_id,
                target_term_id=target_term_id,
                relation_category=relation_category,
            )
        except Exception:
            logger.exception("list_term_relations failed")
            return []

    def get_term_relation(self, *, relation_id: str) -> dict[str, Any] | None:
        reader = self._get_knowledge_reader()
        try:
            return reader.get_term_relation(relation_id=relation_id)  # type: ignore[no-any-return]
        except Exception:
            logger.exception("get_term_relation failed relation_id=%s", relation_id)
            return None

    def create_term_relation(self, *, relation: dict[str, Any]) -> dict[str, Any]:
        from datacloud_knowledge.adapters import create_writer  # noqa: PLC0415

        writer = create_writer()
        return writer.create_term_relation(relation=relation)  # type: ignore[no-any-return]

    def update_term_relation(
        self, *, relation_id: str, updates: dict[str, Any]
    ) -> None:
        from datacloud_knowledge.adapters import create_writer  # noqa: PLC0415

        writer = create_writer()
        writer.update_term_relation(relation_id=relation_id, updates=updates)

    def delete_term_relation(self, *, relation_id: str) -> None:
        from datacloud_knowledge.adapters import create_writer  # noqa: PLC0415

        writer = create_writer()
        writer.delete_term_relation(relation_id=relation_id)

    # ── TermName ────────────────────────────────────────────────────────

    def list_term_names(
        self, *, term_id: str | None = None, name_text: str | None = None
    ) -> list[dict[str, Any]]:
        reader = self._get_knowledge_reader()
        try:
            return reader.list_term_names(term_id=term_id, name_text=name_text)  # type: ignore[no-any-return]
        except Exception:
            logger.exception("list_term_names failed")
            return []

    def get_term_name(self, *, name_id: str) -> dict[str, Any] | None:
        reader = self._get_knowledge_reader()
        try:
            return reader.get_term_name(name_id=name_id)  # type: ignore[no-any-return]
        except Exception:
            logger.exception("get_term_name failed name_id=%s", name_id)
            return None

    def create_term_name(self, *, name: dict[str, Any]) -> dict[str, Any]:
        from datacloud_knowledge.adapters import create_writer  # noqa: PLC0415

        writer = create_writer()
        return writer.create_term_name(name=name)  # type: ignore[no-any-return]

    def update_term_name(self, *, name_id: str, updates: dict[str, Any]) -> None:
        from datacloud_knowledge.adapters import create_writer  # noqa: PLC0415

        writer = create_writer()
        writer.update_term_name(name_id=name_id, updates=updates)

    def delete_term_name(self, *, name_id: str) -> None:
        from datacloud_knowledge.adapters import create_writer  # noqa: PLC0415

        writer = create_writer()
        writer.delete_term_name(name_id=name_id)


# ── 模块级辅助函数 ──────────────────────────────────────────────────────────────


def _dict_to_term_create(term: dict[str, Any]) -> "TermCreate":
    """将 camelCase 或 snake_case dict 转换为 TermCreate dataclass。

    支持的 key 格式（优先 camelCase）：
        termName / term_name
        termCode / term_code
        termTypeCode / term_type_code
        parentTermCode / parent_term_code
        termDesc / term_desc / desc
    """
    from datacloud_knowledge.contracts.term_provider_types import TermCreate  # noqa: PLC0415

    return TermCreate(
        term_name=term.get("termName") or term.get("term_name", ""),
        term_code=term.get("termCode") or term.get("term_code", ""),
        term_type=term.get("termTypeCode") or term.get("term_type_code") or term.get("term_type", ""),
        parent_term_code=term.get("parentTermCode") or term.get("parent_term_code", ""),
        desc=term.get("termDesc") or term.get("term_desc") or term.get("desc", ""),
        labels=term.get("labels", {}),
        ext_attrs=term.get("extAttrs") or term.get("ext_attrs", {}),
        synonyms=term.get("synonyms", []),
    )

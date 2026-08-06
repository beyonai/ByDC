"""Thin Platform routing layer for DocumentLibraryBackend operations."""

from __future__ import annotations

from typing import Any

from datacloud_platform.backends._contracts import _HasDocumentLibraryBackend
from datacloud_platform.models.document import MetadataSearchPage


class DocumentLibraryBackendMixin:
    """Route file operations to the base's DocumentLibraryBackend."""

    async def search_knowledge_item_metadata(
        self: _HasDocumentLibraryBackend,
        base_id: str,
        *,
        payload: dict[str, Any],
    ) -> MetadataSearchPage:
        return await self._document_library_for(base_id).search_knowledge_item_metadata(
            payload=payload
        )

    async def read_knowledge_document(
        self: _HasDocumentLibraryBackend,
        base_id: str,
        *,
        resource_id: str,
        file_path: str,
    ) -> str:
        return await self._document_library_for(base_id).read_knowledge_document(
            resource_id=resource_id, file_path=file_path
        )

    async def search_knowledge_items(
        self: _HasDocumentLibraryBackend,
        base_id: str,
        *,
        payload: dict[str, Any],
    ) -> tuple[dict[str, Any], ...]:
        return await self._document_library_for(base_id).search_knowledge_items(
            payload=payload
        )

"""DocumentLibraryBackend protocol — external document-library operations."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from datacloud_platform.models.document import MetadataSearchPage


class DocumentLibraryError(RuntimeError):
    """Raised when a document-library operation cannot return a valid result."""


class DocumentLibraryBackend(Protocol):
    """File-level operations provided by the configured knowledge service."""

    async def search_knowledge_item_metadata(
        self, *, payload: dict[str, Any]
    ) -> MetadataSearchPage:
        """Search file metadata through the knowledgeItems metadataSearch API."""
        ...

    async def read_knowledge_document(self, *, resource_id: str, file_path: str) -> str:
        """Download the complete text of one knowledge document."""
        ...

    async def search_knowledge_items(
        self, *, payload: dict[str, Any]
    ) -> tuple[dict[str, Any], ...]:
        """Search chunk-level knowledge items."""
        ...

"""Vector backend — embed, embed_batch, search_by_embedding."""

from __future__ import annotations

from typing import Any

from datacloud_platform.adapters.data_adapter._base import DataCloudDataBackendBase


class VectorBackendMixin(DataCloudDataBackendBase):
    """Vector backend — embed, embed_batch, search_by_embedding."""

    # ── Vector ──────────────────────────────────────────────────────────

    def embed(self, text: str) -> list[float]:
        """Text → embedding vector."""
        svc = self._get_embedding()
        return svc.get_text_embedding(text)  # type: ignore[no-any-return]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Batch text → embedding vectors."""
        svc = self._get_embedding()
        return svc.get_text_embedding_batch(texts)  # type: ignore[no-any-return]

    def search_by_embedding(
        self, vector: list[float], term_types: list[str], limit: int = 20
    ) -> list[Any]:
        """Vector similarity search for terms."""
        engine = self._get_search_engine()
        raw: list[dict[str, Any]] = engine.search_terms_by_embedding(
            vector=vector,
            term_types=term_types,
            limit=limit,
        )
        from datacloud_platform.models.shared import EmbeddingHit

        return [
            EmbeddingHit(
                term_code=str(h["term_code"]),
                term_type_code=str(h["term_type_code"]),
                name_text=str(h.get("name_text", h.get("term_name", ""))),
                score=round(float(h["score"]), 4),
            )
            for h in raw
        ]

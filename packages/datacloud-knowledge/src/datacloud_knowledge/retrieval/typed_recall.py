"""Typed multi-path recall orchestration with managed session."""

from __future__ import annotations

import logging
import os
from typing import Any

# TODO: replace with public adapter session API when available
from datacloud_knowledge.adapters.opengauss._db.connection import get_session
from datacloud_knowledge.adapters.opengauss.vector_validation import (
    TermVectorValidationError,
    validate_term_vector_readiness,
)
from datacloud_knowledge.retrieval.embedding import get_embedding_service
from datacloud_knowledge.retrieval.recall import (
    ScopeRecallLayer,
)
from datacloud_knowledge.retrieval.recall import (
    typed_multi_recall_batch as _typed_multi_recall_batch,
)

logger = logging.getLogger(__name__)

_VECTOR_ENABLE_ENV = "DATACLOUD_INTENT_ENABLE_VECTOR"
_FALSE_VALUES = frozenset({"0", "false", "no", "off"})


def _vector_search_enabled() -> bool:
    """Return whether intent vector recall is enabled; defaults to enabled."""
    raw = os.getenv(_VECTOR_ENABLE_ENV, "1").strip().lower()
    return raw not in _FALSE_VALUES


def _get_validated_embedding_service(session: Any) -> Any:
    if not _vector_search_enabled():
        logger.error("知识库向量召回被环境变量 %s 关闭，服务将降级运行", _VECTOR_ENABLE_ENV)
        return None

    try:
        embedding_svc = get_embedding_service()
        validate_term_vector_readiness(session, embedding_svc)
    except TermVectorValidationError as exc:
        logger.error("知识库向量校验失败，向量召回将跳过: %s", exc)
        return None
    except Exception as exc:
        logger.error("知识库向量服务初始化失败，向量召回将跳过: %s", exc)
        return None
    return embedding_svc


def typed_multi_recall_with_session(
    items: list[Any],
    *,
    user_id: str | None = None,
    top_k: int = 5,
    scope_code: str | None = None,
    scope_layers: list[ScopeRecallLayer] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Run typed multi-path recall with a managed DB session.

    Accepts TypedKeywordState items from paradigm_builder and returns
    dict[keyword, list[CandidateDict]] compatible with the existing
    paradigm resolution interface.
    """
    with get_session() as session:
        embedding_svc = _get_validated_embedding_service(session)
        if embedding_svc is None:
            return _typed_multi_recall_batch(
                items,
                session=session,
                top_k=top_k,
                rrf_k=60,
                enable_vector=False,
                wv_per_type=top_k,
                scope_code=scope_code,
                scope_layers=scope_layers,
            )

        return _typed_multi_recall_batch(
            items,
            session=session,
            top_k=top_k,
            rrf_k=60,
            enable_vector=True,
            wv_per_type=top_k,
            scope_code=scope_code,
            scope_layers=scope_layers,
        )

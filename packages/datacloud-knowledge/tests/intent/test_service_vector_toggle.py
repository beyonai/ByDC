from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from datacloud_knowledge.adapters.opengauss.vector_validation import (
    TermVectorValidationError,
    get_validated_embedding_service,
)


def _get_service_module() -> Any:
    from datacloud_knowledge.retrieval import candidate_search as service

    return service


@pytest.mark.intent
def test_search_candidates_runs_vector_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """When an embedding_service is passed, strict→bm25→vector pipeline runs."""
    service = _get_service_module()
    monkeypatch.delenv("DATACLOUD_INTENT_ENABLE_VECTOR", raising=False)
    monkeypatch.setattr(service, "_build_global_name_index", dict)

    vector_candidate = SimpleNamespace(
        term_id="TERM_001",
        term_name="企业综合分析表",
        term_type_code="DB_TABLE",
        match_type="vector",
        confidence=0.91,
        score=0.0,
    )

    def _fake_convert_hits(
        *, word: str, hits: tuple[Any, ...], user_id: str | None
    ) -> list[dict[str, Any]]:
        del user_id
        return [
            {
                "term_id": c.term_id,
                "term_name": c.term_name or word,
                "term_type_code": c.term_type_code,
                "match_type": c.match_type,
                "confidence": c.confidence,
                "score": c.score,
                "name_id": None,
            }
            for c in hits
        ]

    search_modes: list[str] = []

    def _fake_match(
        mentions: tuple[Any, ...],
        _session: Any,
        **kwargs: Any,
    ) -> dict[str, tuple[Any, ...]]:
        mode = str(kwargs.get("search_mode"))
        search_modes.append(mode)
        if mode == "vector":
            return {m.text: (vector_candidate,) for m in mentions}
        return {m.text: () for m in mentions}

    monkeypatch.setattr(service, "match_mentions_with_search", _fake_match)
    monkeypatch.setattr(service, "_convert_hits", _fake_convert_hits)

    # Pass a dummy embedding service so vector path is taken.
    out = service.search_all_candidates_with_name_id(
        ["企业综合分析表"],
        embedding_service=object(),
    )

    assert search_modes == ["strict", "bm25", "vector"]
    assert out["企业综合分析表"][0]["match_type"] == "vector"


@pytest.mark.intent
def test_search_candidates_skips_vector_when_no_service(monkeypatch: pytest.MonkeyPatch) -> None:
    """When embedding_service is None, vector recall is skipped entirely."""
    service = _get_service_module()
    monkeypatch.setenv("DATACLOUD_INTENT_ENABLE_VECTOR", "0")
    monkeypatch.setattr(service, "_build_global_name_index", dict)

    search_modes: list[str] = []

    def _fake_match(
        mentions: tuple[Any, ...],
        _session: Any,
        **kwargs: Any,
    ) -> dict[str, tuple[Any, ...]]:
        mode = str(kwargs.get("search_mode"))
        search_modes.append(mode)
        return {m.text: () for m in mentions}

    monkeypatch.setattr(service, "match_mentions_with_search", _fake_match)

    # embedding_service defaults to None — vector should be skipped.
    out = service.search_all_candidates_with_name_id(["企业综合分析表"])

    assert out == {"企业综合分析表": []}
    assert search_modes == ["strict", "bm25"]


@pytest.mark.intent
def test_get_validated_embedding_service_logs_on_validation_failure(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """get_validated_embedding_service logs an error when validation fails."""
    monkeypatch.setenv("DATACLOUD_INTENT_ENABLE_VECTOR", "1")
    # Ensure the env-check passes.
    monkeypatch.setattr(
        "datacloud_knowledge.adapters.opengauss.vector_validation.is_vector_recall_available",
        lambda: True,
    )

    def _raise_validation_error(*_args: Any) -> None:
        raise TermVectorValidationError("缺少必需列 whale_datacloud.term_name.name_embedding")

    monkeypatch.setattr(
        "datacloud_knowledge.adapters.opengauss.vector_validation.validate_term_vector_readiness",
        _raise_validation_error,
    )
    monkeypatch.setattr(
        "datacloud_knowledge.adapters.opengauss.vector_validation.get_embedding_service",
        object,
    )

    with caplog.at_level("ERROR"):
        result = get_validated_embedding_service(None)

    assert result is None
    assert "知识库向量校验失败" in caplog.text
    assert "缺少必需列" in caplog.text

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from datacloud_knowledge.adapters.opengauss.vector_validation import TermVectorValidationError


def _get_service_module() -> Any:
    from datacloud_knowledge.retrieval import candidate_search as service

    return service


@pytest.mark.intent
def test_search_candidates_runs_vector_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    service = _get_service_module()
    monkeypatch.delenv("DATACLOUD_INTENT_ENABLE_VECTOR", raising=False)
    monkeypatch.setattr(service, "_build_global_name_index", dict)
    monkeypatch.setattr(service, "validate_term_vector_readiness", lambda *_args: None)
    monkeypatch.setattr(service, "get_embedding_service", object)

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

    out = service.search_all_candidates_with_name_id(["企业综合分析表"])

    assert search_modes == ["strict", "bm25", "vector"]
    assert out["企业综合分析表"][0]["match_type"] == "vector"


@pytest.mark.intent
def test_search_candidates_skips_vector_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
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

    get_svc_called = {"value": False}

    def _track_get_svc() -> Any:
        get_svc_called["value"] = True
        raise AssertionError("embedding service should not be requested when vector is disabled")

    monkeypatch.setattr(service, "match_mentions_with_search", _fake_match)
    monkeypatch.setattr(service, "get_embedding_service", _track_get_svc)

    out = service.search_all_candidates_with_name_id(["企业综合分析表"])

    assert out == {"企业综合分析表": []}
    assert search_modes == ["strict", "bm25"]
    assert get_svc_called["value"] is False


@pytest.mark.intent
def test_search_candidates_logs_error_when_vector_validation_fails(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    service = _get_service_module()
    monkeypatch.setattr(service, "_build_global_name_index", dict)

    def _raise_validation_error(*_args: Any) -> None:
        raise TermVectorValidationError("缺少必需列 whale_datacloud.term_name.name_embedding")

    def _fake_match(
        mentions: tuple[Any, ...],
        _session: Any,
        **kwargs: Any,
    ) -> dict[str, tuple[Any, ...]]:
        del kwargs
        return {m.text: () for m in mentions}

    monkeypatch.setattr(service, "validate_term_vector_readiness", _raise_validation_error)
    monkeypatch.setattr(service, "match_mentions_with_search", _fake_match)
    monkeypatch.setattr(service, "get_embedding_service", object)

    with caplog.at_level("ERROR"):
        out = service.search_all_candidates_with_name_id(["企业综合分析表"])

    assert out == {"企业综合分析表": []}
    assert "知识库向量校验失败" in caplog.text
    assert "缺少必需列" in caplog.text

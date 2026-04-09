# ruff: noqa: S101
from __future__ import annotations

from importlib import import_module
from types import SimpleNamespace
from typing import Any

import pytest


def _get_service_module() -> Any:
    return import_module("datacloud_knowledge.intent.service")


class _DummySessionCtx:
    def __enter__(self) -> object:
        return object()

    def __exit__(self, _exc_type: object, _exc: object, _tb: object) -> None:
        return None


def _empty_hits_converter(**_kwargs: Any) -> list[dict[str, Any]]:
    return []


@pytest.mark.intent
def test_search_candidates_skips_vector_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    service = _get_service_module()
    monkeypatch.delenv("DATACLOUD_INTENT_ENABLE_VECTOR", raising=False)
    monkeypatch.setattr(service, "get_session", _DummySessionCtx)
    monkeypatch.setattr(service, "_build_global_name_index", dict)
    monkeypatch.setattr(service, "_convert_hits", _empty_hits_converter)

    search_modes: list[str] = []

    def _fake_match(
        mentions: tuple[Any, ...],
        _session: Any,
        **kwargs: Any,
    ) -> dict[str, tuple[Any, ...]]:
        mode = str(kwargs.get("search_mode"))
        search_modes.append(mode)
        return {m.text: () for m in mentions}

    import_called = {"value": False}

    class _EmbeddingModule:
        @staticmethod
        def get_embedding_service() -> object:
            return object()

    def _track_import(_module_name: str) -> Any:
        import_called["value"] = True
        return _EmbeddingModule

    monkeypatch.setattr(service, "match_mentions_with_search", _fake_match)
    monkeypatch.setattr(service, "import_module", _track_import)

    out = service.search_all_candidates_with_name_id(["企业综合分析表"])

    assert out == {"企业综合分析表": []}
    assert search_modes == ["strict", "bm25"]
    assert import_called["value"] is False


@pytest.mark.intent
def test_search_candidates_runs_vector_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    service = _get_service_module()
    monkeypatch.setenv("DATACLOUD_INTENT_ENABLE_VECTOR", "1")
    monkeypatch.setattr(service, "get_session", _DummySessionCtx)
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

    class _EmbeddingModule:
        @staticmethod
        def get_embedding_service() -> object:
            return object()

    def _import_embedding(_name: str) -> type[_EmbeddingModule]:
        return _EmbeddingModule

    monkeypatch.setattr(service, "match_mentions_with_search", _fake_match)
    monkeypatch.setattr(service, "_convert_hits", _fake_convert_hits)
    monkeypatch.setattr(service, "import_module", _import_embedding)

    out = service.search_all_candidates_with_name_id(["企业综合分析表"])

    assert search_modes == ["strict", "bm25", "vector"]
    assert out["企业综合分析表"][0]["match_type"] == "vector"

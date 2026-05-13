from __future__ import annotations

import re
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast

import pytest
from datacloud_knowledge.search import vector_validation
from datacloud_knowledge.search.vector_validation import (
    TermVectorValidationError,
    validate_term_vector_readiness,
)

if TYPE_CHECKING:
    from datacloud_knowledge.search.vector_validation import EmbeddingServiceLike
    from sqlalchemy.orm import Session


class _FakeResult:
    def __init__(self, value: Any) -> None:
        self._value = value

    def scalar_one(self) -> Any:
        return self._value

    def one(self) -> Any:
        return self._value

    def one_or_none(self) -> Any:
        return self._value


class _FakeSession:
    def __init__(self, values: list[Any]) -> None:
        self._values = values
        self._bind = object()

    def get_bind(self) -> object:
        return self._bind

    def execute(self, *_args: Any, **_kwargs: Any) -> _FakeResult:
        return _FakeResult(self._values.pop(0))


class _FakeEmbeddingService:
    def __init__(self, vector: list[float]) -> None:
        self._vector = vector

    @property
    def model_name(self) -> str:
        return "bge-m3"

    def get_text_embedding(self, _text: str) -> list[float]:
        return self._vector


@pytest.fixture(autouse=True)
def _reset_validation_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    vector_validation.reset_term_vector_validation_cache()
    monkeypatch.setattr(
        vector_validation,
        "parse_env_database_url",
        lambda: SimpleNamespace(
            db_type="postgresql",
            host="localhost",
            port=5432,
            database="postgres",
        ),
    )
    monkeypatch.setattr(vector_validation, "resolve_knowledge_schema", lambda: "whale_datacloud")


def test_missing_vector_column_raises() -> None:
    session = _FakeSession([False])

    with pytest.raises(TermVectorValidationError, match="缺少必需列"):
        validate_term_vector_readiness(
            cast("Session", session),
            cast("EmbeddingServiceLike", _FakeEmbeddingService([1.0, 0.0])),
        )


def test_all_vectors_empty_raises() -> None:
    session = _FakeSession([True, SimpleNamespace(total_count=12, vector_count=0)])

    with pytest.raises(TermVectorValidationError, match="全部为空"):
        validate_term_vector_readiness(
            cast("Session", session),
            cast("EmbeddingServiceLike", _FakeEmbeddingService([1.0, 0.0])),
        )


def test_top_hit_mismatch_raises() -> None:
    session = _FakeSession(
        [
            True,
            SimpleNamespace(total_count=12, vector_count=1),
            SimpleNamespace(name_id="N1", term_id="T1", name_text="企业"),
            SimpleNamespace(name_id="N2", term_id="T2", name_text="学校", similarity=0.999),
        ]
    )

    with pytest.raises(TermVectorValidationError, match="top1 未命中"):
        validate_term_vector_readiness(
            cast("Session", session),
            cast("EmbeddingServiceLike", _FakeEmbeddingService([1.0, 0.0])),
        )


def test_low_similarity_raises() -> None:
    session = _FakeSession(
        [
            True,
            SimpleNamespace(total_count=12, vector_count=1),
            SimpleNamespace(name_id="N1", term_id="T1", name_text="企业"),
            SimpleNamespace(name_id="N1", term_id="T1", name_text="企业", similarity=0.97),
        ]
    )

    with pytest.raises(TermVectorValidationError, match=re.escape("similarity=0.970000")):
        validate_term_vector_readiness(
            cast("Session", session),
            cast("EmbeddingServiceLike", _FakeEmbeddingService([1.0, 0.0])),
        )


def test_matching_top_hit_above_threshold_passes() -> None:
    session = _FakeSession(
        [
            True,
            SimpleNamespace(total_count=12, vector_count=1),
            SimpleNamespace(name_id="N1", term_id="T1", name_text="企业"),
            SimpleNamespace(name_id="N1", term_id="T1", name_text="企业", similarity=0.999),
        ]
    )

    validate_term_vector_readiness(
        cast("Session", session),
        cast("EmbeddingServiceLike", _FakeEmbeddingService([1.0, 0.0])),
    )


def test_same_text_top_hit_with_different_name_id_passes() -> None:
    session = _FakeSession(
        [
            True,
            SimpleNamespace(total_count=12, vector_count=1),
            SimpleNamespace(name_id="N1", term_id="T1", name_text="高端功能材料及关键基础元器件"),
            SimpleNamespace(
                name_id="N2",
                term_id="T2",
                name_text="高端功能材料及关键基础元器件",
                similarity=1.0,
            ),
        ]
    )

    validate_term_vector_readiness(
        cast("Session", session),
        cast("EmbeddingServiceLike", _FakeEmbeddingService([1.0, 0.0])),
    )

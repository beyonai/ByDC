"""Runtime smoke validation for term-name vector search readiness."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from sqlalchemy import text

from datacloud_knowledge.db_url import parse_env_database_url, resolve_knowledge_schema

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


class EmbeddingServiceLike(Protocol):
    """Minimum embedding interface needed by vector validation."""

    @property
    def model_name(self) -> str: ...

    def get_text_embedding(self, text: str) -> list[float]: ...


VECTOR_COLUMN = "name_embedding"
VECTOR_SIMILARITY_THRESHOLD = 0.98
_TERM_NAME_TABLE = "term_name"

# 进程级单次校验：None=未校验，True=通过，False=失败
_validation_result: bool | None = None


@dataclass(frozen=True, slots=True)
class VectorValidationDbInfo:
    """Database target used in vector validation error messages."""

    db_type: str
    host: str
    port: int
    database: str
    schema_name: str
    table_name: str = _TERM_NAME_TABLE

    def as_text(self) -> str:
        """Return a concise DB identity string safe for logs and exceptions."""
        return (
            f"db_type={self.db_type}, host={self.host}, port={self.port}, "
            f"database={self.database}, schema={self.schema_name}, table={self.table_name}"
        )


@dataclass(frozen=True, slots=True)
class VectorSample:
    """A persisted term-name vector sample for smoke validation."""

    name_id: str
    term_id: str
    name_text: str


@dataclass(frozen=True, slots=True)
class VectorSmokeHit:
    """Top vector hit for the runtime smoke check."""

    name_id: str
    term_id: str
    name_text: str
    similarity: float


class TermVectorValidationError(RuntimeError):
    """Raised when the knowledge DB cannot satisfy vector recall expectations."""


def _is_equivalent_top_hit(sample: VectorSample, hit: VectorSmokeHit) -> bool:
    """Return whether the top hit is an acceptable match for smoke validation."""
    return hit.name_id == sample.name_id or hit.name_text == sample.name_text


def validate_term_vector_readiness(
    session: Session,
    embedding_service: EmbeddingServiceLike,
) -> None:
    """Validate term vectors by real-time embedding and vector retrieval.

    Process-level once-only check. After first successful validation, subsequent
    calls return immediately. On failure, raises TermVectorValidationError.
    """
    global _validation_result

    if _validation_result is True:
        return
    if _validation_result is False:
        raise TermVectorValidationError("术语知识库向量校验此前已失败，进程级缓存拒绝重试")

    schema_name = resolve_knowledge_schema()
    db_info = _build_db_info(schema_name)

    try:
        _validate_column_exists(session, db_info, VECTOR_COLUMN)
    except TermVectorValidationError:
        _validation_result = False
        raise

    total_count, vector_count = _load_vector_counts(session, schema_name)
    if vector_count == 0:
        _validation_result = False
        raise TermVectorValidationError(
            "术语知识库向量校验失败: term_name.name_embedding 全部为空; "
            f"total_terms={total_count}, vector_terms={vector_count}; {db_info.as_text()}"
        )

    sample = _load_vector_sample(session, schema_name)
    if sample is None:
        _validation_result = False
        raise TermVectorValidationError(
            "术语知识库向量校验失败: 未找到可用于实时检索校验的非空向量样本; "
            f"total_terms={total_count}, vector_terms={vector_count}; {db_info.as_text()}"
        )

    vector = embedding_service.get_text_embedding(sample.name_text)
    hit = _load_top_vector_hit(session, schema_name, vector)
    if hit is None:
        _validation_result = False
        raise TermVectorValidationError(
            "术语知识库向量校验失败: 实时向量检索没有返回候选; "
            f"sample_name_id={sample.name_id}, sample_text={sample.name_text!r}; {db_info.as_text()}"
        )
    if not _is_equivalent_top_hit(sample, hit):
        _validation_result = False
        raise TermVectorValidationError(
            "术语知识库向量校验失败: 实时向量检索 top1 未命中原始术语; "
            f"sample_name_id={sample.name_id}, sample_term_id={sample.term_id}, "
            f"sample_text={sample.name_text!r}, hit_name_id={hit.name_id}, "
            f"hit_term_id={hit.term_id}, hit_text={hit.name_text!r}, "
            f"similarity={hit.similarity:.6f}; {db_info.as_text()}"
        )
    if hit.similarity < VECTOR_SIMILARITY_THRESHOLD:
        _validation_result = False
        raise TermVectorValidationError(
            "术语知识库向量校验失败: 实时向量检索相似度低于阈值; "
            f"sample_name_id={sample.name_id}, sample_text={sample.name_text!r}, "
            f"similarity={hit.similarity:.6f}, threshold={VECTOR_SIMILARITY_THRESHOLD:.2f}; "
            f"{db_info.as_text()}"
        )

    _validation_result = True


def reset_term_vector_validation_cache() -> None:
    """Clear validation cache, mainly for tests and refreshed DB connections."""
    global _validation_result
    _validation_result = None


def _build_db_info(schema_name: str) -> VectorValidationDbInfo:
    parsed = parse_env_database_url()
    return VectorValidationDbInfo(
        db_type=parsed.db_type,
        host=parsed.host,
        port=parsed.port,
        database=parsed.database,
        schema_name=schema_name,
    )


def _validate_column_exists(
    session: Session,
    db_info: VectorValidationDbInfo,
    column_name: str,
) -> None:
    exists = session.execute(
        text(
            """
            SELECT EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = :schema_name
                  AND table_name = :table_name
                  AND column_name = :column_name
            )
            """
        ),
        {
            "schema_name": db_info.schema_name,
            "table_name": db_info.table_name,
            "column_name": column_name,
        },
    ).scalar_one()
    if not exists:
        raise TermVectorValidationError(
            "术语知识库向量校验失败: 缺少必需列 "
            f"{db_info.schema_name}.{db_info.table_name}.{column_name}; {db_info.as_text()}"
        )


def _load_vector_counts(session: Session, schema_name: str) -> tuple[int, int]:
    row = session.execute(
        text(
            f"""
            SELECT COUNT(*) AS total_count,
                   COUNT({VECTOR_COLUMN}) AS vector_count
            FROM {schema_name}.{_TERM_NAME_TABLE}
            """
        )
    ).one()
    return int(row.total_count), int(row.vector_count)


def _load_vector_sample(session: Session, schema_name: str) -> VectorSample | None:
    row = session.execute(
        text(
            f"""
            SELECT name_id, term_id, name_text
            FROM {schema_name}.{_TERM_NAME_TABLE}
            WHERE {VECTOR_COLUMN} IS NOT NULL
            ORDER BY updated_time DESC, name_id ASC
            LIMIT 1
            """
        )
    ).one_or_none()
    if row is None:
        return None
    return VectorSample(
        name_id=str(row.name_id), term_id=str(row.term_id), name_text=str(row.name_text)
    )


def _load_top_vector_hit(
    session: Session,
    schema_name: str,
    query_vector: list[float],
) -> VectorSmokeHit | None:
    vector_text = "[" + ",".join(map(str, query_vector)) + "]"
    row = session.execute(
        text(
            f"""
            SELECT name_id,
                   term_id,
                   name_text,
                   1 - ({VECTOR_COLUMN} <=> CAST(:vector AS vector)) AS similarity
            FROM {schema_name}.{_TERM_NAME_TABLE}
            WHERE {VECTOR_COLUMN} IS NOT NULL
            ORDER BY {VECTOR_COLUMN} <=> CAST(:vector AS vector)
            LIMIT 1
            """
        ),
        {"vector": vector_text},
    ).one_or_none()
    if row is None:
        return None
    return VectorSmokeHit(
        name_id=str(row.name_id),
        term_id=str(row.term_id),
        name_text=str(row.name_text),
        similarity=float(row.similarity),
    )

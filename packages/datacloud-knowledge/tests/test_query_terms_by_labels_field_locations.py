"""字段落点验收。

锁定/验证三键下推落点假设：
  kb_id / kb_resource_id → ext_attrs（主落点）
  kb_file_path           → term_tags（与 label_filters 现状一致）

用例 A（主落点）：数据按 kb_search_executor 写入形态（ext_attrs + labels 双写同值）
  → kb_ids / kb_resource_ids 下推命中（ext_attrs）；kb_file_paths 经 term_tags 命中。
用例 B（兜底）：数据仅落 term_tags（模拟存量/异构，如 test_term_co_occurrence_writer
  形态）→ kb_file_paths 仍命中；kb_ids / kb_resource_ids 不命中（返回空）且不报错。
  用例 B 通过即锁定落点假设；失败则触发升级评估（双列 OR / 数据迁移）。

注：生产抽查 SQL 已独立执行（三键「ext_attrs 缺失但 term_tags 存在」计数均 = 0，
落点假设维持），执行记录见审计 SQL 文档。
"""

from __future__ import annotations

import pytest
from datacloud_knowledge.adapters.opengauss._readers import _base as _reader_base
from datacloud_knowledge.adapters.opengauss.reader import PostgresTermReader
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

# 用例 A：双写同值（ext_attrs + term_tags 均含三键，与 kb_search_executor 写入一致）
# 用例 B：仅 term_tags 落点（ext_attrs 为空对象）
_TERMS: list[tuple[str, str, str]] = [
    # (term_id, ext_attrs_json, term_tags_json)
    (
        "ta1",
        '{"kb_id": "k1", "kb_resource_id": "r1", "kb_file_path": "/a/p1.md"}',
        '{"kb_file_path": "/a/p1.md", "kb_id": "k1", "kb_resource_id": "r1"}',
    ),
    (
        "tb1",
        "{}",
        '{"kb_file_path": "/x/p5.md", "kb_id": "k9", "kb_resource_id": "r9"}',
    ),
]


@pytest.fixture()
def loc_reader(monkeypatch: pytest.MonkeyPatch) -> PostgresTermReader:
    monkeypatch.setattr(_reader_base, "_SCHEMA_CHECKED", True)
    engine = create_engine("sqlite:///:memory:")
    with engine.connect() as conn:
        conn.execute(
            text(
                """CREATE TABLE term (
                    term_id TEXT PRIMARY KEY,
                    term_code TEXT NOT NULL,
                    term_name TEXT NOT NULL,
                    term_type_code TEXT NOT NULL,
                    desc_summary TEXT,
                    parent_term_id TEXT,
                    library_id TEXT,
                    term_tags TEXT,
                    ext_attrs TEXT,
                    created_time TEXT,
                    updated_time TEXT
                )"""
            )
        )
        for tid, ext, tags in _TERMS:
            conn.execute(
                text(
                    "INSERT INTO term (term_id, term_code, term_name, term_type_code, "
                    "desc_summary, parent_term_id, library_id, term_tags, ext_attrs, "
                    "created_time, updated_time) VALUES "
                    "(:tid, :code, :name, 'T1', NULL, NULL, 'lib1', :tags, :ext, 'ts', 'ts')"
                ),
                {"tid": tid, "code": tid.upper(), "name": f"名称-{tid}", "tags": tags, "ext": ext},
            )
        conn.commit()
    factory = sessionmaker(bind=engine, class_=Session, expire_on_commit=False, autoflush=False)
    return PostgresTermReader(session_factory=factory)


def _ids(items: list[dict[str, object]]) -> set[str]:
    return {str(item["term_id"]) for item in items}


# ═════════════════════════════════════════════════════════════════════════════
# 用例 A [P1]：主落点 —— 双写同值数据，三键下推均命中
# ═════════════════════════════════════════════════════════════════════════════


def test_t8_case_a_kb_ids_hits(loc_reader: PostgresTermReader) -> None:
    """kb_ids=["k1"] → 命中双写行 ta1（ext_attrs 主落点）。"""
    result = loc_reader.query_terms_by_labels(kb_ids=["k1"])
    assert _ids(result) == {"ta1"}


def test_t8_case_a_kb_resource_ids_hits(loc_reader: PostgresTermReader) -> None:
    """kb_resource_ids=["r1"] → 命中 ta1（ext_attrs 主落点）。"""
    result = loc_reader.query_terms_by_labels(kb_resource_ids=["r1"])
    assert _ids(result) == {"ta1"}


def test_t8_case_a_kb_file_paths_hits_via_term_tags(
    loc_reader: PostgresTermReader,
) -> None:
    """kb_file_paths=["/a/p1.md"] → 命中 ta1（term_tags 落点，与 label_filters 现状一致）。"""
    result = loc_reader.query_terms_by_labels(kb_file_paths=["/a/p1.md"])
    assert _ids(result) == {"ta1"}


# ═════════════════════════════════════════════════════════════════════════════
# 用例 B [P1]：兜底 —— 数据仅落 term_tags
# ═════════════════════════════════════════════════════════════════════════════


def test_t8_case_b_file_path_still_hits(loc_reader: PostgresTermReader) -> None:
    """仅 term_tags 落点 → kb_file_paths 仍命中 tb1（term_tags 查询不依赖 ext_attrs）。"""
    result = loc_reader.query_terms_by_labels(kb_file_paths=["/x/p5.md"])
    assert _ids(result) == {"tb1"}


def test_t8_case_b_kb_ids_miss_without_error(
    loc_reader: PostgresTermReader,
) -> None:
    """仅 term_tags 落点 → kb_ids=["k9"] 不命中（返回空），不报错。

    通过即锁定落点假设：kb_id 只查 ext_attrs，term_tags 存量不产生虚假命中。
    """
    result = loc_reader.query_terms_by_labels(kb_ids=["k9"])
    assert result == []


def test_t8_case_b_kb_resource_ids_miss_without_error(
    loc_reader: PostgresTermReader,
) -> None:
    """仅 term_tags 落点 → kb_resource_ids=["r9"] 不命中（返回空），不报错。"""
    result = loc_reader.query_terms_by_labels(kb_resource_ids=["r9"])
    assert result == []

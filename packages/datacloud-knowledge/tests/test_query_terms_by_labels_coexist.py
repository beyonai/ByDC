"""label_filters × filters 共存验收。

锁定兼容通道（label_filters / term_type_codes）与通用通道（filters）并存语义：
  1. A/C 点调用形态（label_filters 通道）与 filters 同传 →
     SQL 片段顺序 = (label OR 组) → term_type_codes → filters 元素；
     label 组内 OR/AND 语义与既有实现逐项一致。
  2. label 组 kb_file_path 与 filters kb_file_path 同 field 共存 →
     各自独立 AND（交集正确，不合并不冲突）。
  3. label_filters=None/[] + filters 生效 → label 维度跳过、filters 正常过滤。

基建：sqlite 内存库 + 真实 SQL（复用 behavior 种子基建）。
"""

from __future__ import annotations

import re
from typing import Any

import pytest
from datacloud_knowledge.adapters.opengauss._readers import _base as _reader_base
from datacloud_knowledge.adapters.opengauss.reader import PostgresTermReader
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker

_TERMS: list[tuple[str, str, str, str]] = [
    ("t1", "C1", "T1", "lib1"),
    ("t2", "C2", "T1", "lib1"),
    ("t3", "C3", "T1", "lib2"),
    ("t4", "C4", "T2", "lib2"),
    ("t5", "C5", "T2", "lib1"),
    ("t6", "C6", "T3", "lib1"),
    ("t7", "C7", "T3", "lib1"),
    ("t8", "C8", "T3", "lib1"),
]

_ATTRS: dict[str, tuple[str, str]] = {
    "t1": (
        '{"kb_id": "k1", "kb_resource_id": "r1"}',
        '{"kb_file_path": "/a/p1.md"}',
    ),
    "t2": (
        '{"kb_id": "k1", "kb_resource_id": "r1"}',
        '{"kb_file_path": "/a/p2.md"}',
    ),
    "t3": (
        '{"kb_id": "k2", "kb_resource_id": "r2"}',
        '{"kb_file_path": "/b/p3.md"}',
    ),
    "t4": (
        '{"kb_id": "k2", "kb_resource_id": "r2"}',
        '{"kb_file_path": "/b/p4.md"}',
    ),
    "t5": ('{"kb_id": "k3"}', "{}"),
    "t6": ("{}", '{"kb_file_path": "/x/p5.md"}'),
    "t7": (
        '{"kb_id": "k1", "kb_resource_id": "r9"}',
        '{"kb_file_path": "/a/p1.md"}',
    ),
    "t8": ('{"kb_id": "k9"}', '{"kb_file_path": "/a/p1.md"}'),
}


@pytest.fixture()
def co_reader(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[PostgresTermReader, list[str]]:
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
        for tid, code, ttype, lib in _TERMS:
            ext, tags = _ATTRS[tid]
            conn.execute(
                text(
                    "INSERT INTO term (term_id, term_code, term_name, term_type_code, "
                    "desc_summary, parent_term_id, library_id, term_tags, ext_attrs, "
                    "created_time, updated_time) "
                    "VALUES (:tid, :code, :name, :ttype, NULL, NULL, :lib, :tags, :ext, 'ts', 'ts')"
                ),
                {
                    "tid": tid,
                    "code": code,
                    "name": f"名称-{tid}",
                    "ttype": ttype,
                    "lib": lib,
                    "tags": tags,
                    "ext": ext,
                },
            )
        conn.commit()

    statements: list[str] = []

    @event.listens_for(engine, "before_cursor_execute")
    def _capture(
        conn: Any,
        cursor: Any,
        statement: str,
        parameters: Any,
        context: Any,
        executemany: bool,
    ) -> None:
        statements.append(str(statement))

    factory = sessionmaker(bind=engine, class_=Session, expire_on_commit=False, autoflush=False)
    reader = PostgresTermReader(session_factory=factory)
    return reader, statements


def _ids(items: list[dict[str, Any]]) -> set[str]:
    return {str(item["term_id"]) for item in items}


# ═════════════════════════════════════════════════════════════════════════════
# A/C 点形态（label_filters OR 组）+ filters 同传 → 全 AND + 顺序
# ═════════════════════════════════════════════════════════════════════════════


def test_t12_label_or_group_and_filters_combined(
    co_reader: tuple[PostgresTermReader, list[str]],
) -> None:
    """(label OR 组) AND term_type_codes AND filters 元素 → 片段顺序固定。"""
    reader, statements = co_reader
    result = reader.query_terms_by_labels(
        label_filters=[
            {"field_code": "kb_file_path", "filter_value": "/a/p1.md"},
            {"field_code": "kb_file_path", "filter_value": "/b/p3.md"},
        ],
        label_condition="or",
        term_type_codes=["T1"],
        filters=[
            {"field": "kb_id", "op": "in", "values": ["k1"]},
        ],
    )
    # label OR 命中 p1/p3 → {t1,t3,t7,t8}；AND T1 → {t1,t3}；AND kb_id=k1 → {t1}
    assert _ids(result) == {"t1"}

    sql = statements[-1]
    # label OR 组带括号最前（方言无关）
    assert re.search(
        r"WHERE \(t\.term_tags->>'kb_file_path' = (?::_lbl_0|\?) "
        r"OR t\.term_tags->>'kb_file_path' = (?::_lbl_1|\?)\)",
        sql,
    )
    # 片段顺序：label 组 → term_type_codes → filters 元素（kb_id）
    idx_label = sql.index("WHERE (")
    idx_tt = sql.index("term_type_code IN")
    idx_kbid = sql.index("kb_id' IN")
    assert idx_label < idx_tt < idx_kbid


def test_t12_label_and_chain_with_filters_combined(
    co_reader: tuple[PostgresTermReader, list[str]],
) -> None:
    """label_condition="and" 时 label 组为 AND 链，与 filters 元素全 AND。"""
    reader, statements = co_reader
    result = reader.query_terms_by_labels(
        label_filters=[
            {"field_code": "kb_file_path", "filter_value": "/a/p1.md"},
            {"field_code": "kb_file_path", "filter_value": "/b/p3.md"},
        ],
        label_condition="and",
        filters=[{"field": "kb_id", "op": "in", "values": ["k1"]}],
    )
    # label AND 链恒空（同一行不可能两个 path 同时命中）
    assert result == []
    sql = statements[-1]
    assert re.search(
        r"WHERE t\.term_tags->>'kb_file_path' = (?::_lbl_0|\?) "
        r"AND t\.term_tags->>'kb_file_path' = (?::_lbl_1|\?)",
        sql,
    )


# ═════════════════════════════════════════════════════════════════════════════
# 同 field 双通道共存：label kb_file_path × filters kb_file_path
# ═════════════════════════════════════════════════════════════════════════════


def test_t12_same_field_both_channels_independent_and(
    co_reader: tuple[PostgresTermReader, list[str]],
) -> None:
    """label 组 kb_file_path 与 filters kb_file_path 共存 → 各自独立 AND（交集）。"""
    reader, statements = co_reader
    result = reader.query_terms_by_labels(
        label_filters=[
            {"field_code": "kb_file_path", "filter_value": "/a/p1.md"},
        ],
        label_condition="or",
        filters=[
            {"field": "kb_file_path", "op": "in", "values": ["/a/p1.md", "/b/p3.md"]},
            {"field": "kb_id", "op": "in", "values": ["k1", "k9"]},
        ],
    )
    # label: path=/a/p1.md → {t1,t7,t8}
    # AND filters kb_file_path ∈ {/a/p1.md,/b/p3.md} → {t1,t7,t8}
    # AND filters kb_id ∈ {k1,k9} → {t1,t7,t8}
    assert _ids(result) == {"t1", "t7", "t8"}

    sql = statements[-1]
    # 两条独立片段：label 等值 + filters IN（互不合并）
    assert "term_tags->>'kb_file_path' =" in sql  # label 片段
    assert "term_tags->>'kb_file_path' IN" in sql  # filters 片段


# ═════════════════════════════════════════════════════════════════════════════
# label_filters=None/[] + filters 生效 → label 跳过、filters 正常
# ═════════════════════════════════════════════════════════════════════════════


def test_t12_label_none_filters_active(
    co_reader: tuple[PostgresTermReader, list[str]],
) -> None:
    """label_filters=None + filters 生效 → label 维度跳过、filters 正常过滤。"""
    reader, statements = co_reader
    result = reader.query_terms_by_labels(
        label_filters=None,
        filters=[{"field": "kb_id", "op": "in", "values": ["k1"]}],
    )
    assert _ids(result) == {"t1", "t2", "t7"}
    sql = statements[-1]
    assert "term_tags->>" not in sql  # 无 label 片段
    assert "ext_attrs->>'kb_id' IN" in sql


def test_t12_label_empty_filters_active(
    co_reader: tuple[PostgresTermReader, list[str]],
) -> None:
    """label_filters=[] + filters 生效 → label 跳过、filters 正常过滤（4.6 回归）。"""
    reader, _ = co_reader
    result = reader.query_terms_by_labels(
        label_filters=[],
        filters=[{"field": "kb_file_path", "op": "in", "values": ["/a/p1.md"]}],
    )
    assert _ids(result) == {"t1", "t7", "t8"}

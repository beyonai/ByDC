"""query_terms_by_labels 底层行为验收。

覆盖 B1 结构化 kwargs 扩展的核心行为契约：
  label_filters 空语义：None/[] → 跳过维度（行为变更，原为全滤 return []）
  空列表全滤 / None 忽略（kb 三键 + term_type_codes）
  全维度空 → return []（不执行无 WHERE 查询）
  多维度全 AND 组合 + label OR 组与三新参共存（片段顺序固定）

基建：sqlite 内存库 + 真实 SQL（sqlite 3.38+ 支持 ->> 运算符，与
test_enumerate_object_instances 同模式）；SQLAlchemy before_cursor_execute
事件捕获生成的 SQL 文本用于形状断言。

种子数据（8 行）:
  t1  T1  ext={kb_id:k1, kb_resource_id:r1} tags={kb_file_path:/a/p1.md}
  t2  T1  ext={kb_id:k1, kb_resource_id:r1} tags={kb_file_path:/a/p2.md}
  t3  T1  ext={kb_id:k2, kb_resource_id:r2} tags={kb_file_path:/b/p3.md}
  t4  T2  ext={kb_id:k2, kb_resource_id:r2} tags={kb_file_path:/b/p4.md}
  t5  T2  ext={kb_id:k3}                    tags={}
  t6  T3  ext={}                            tags={kb_file_path:/x/p5.md}
  t7  T3  ext={kb_id:k1, kb_resource_id:r9} tags={kb_file_path:/a/p1.md}
  t8  T3  ext={kb_id:k9}                    tags={kb_file_path:/a/p1.md}
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
    # (term_id, term_code, term_type_code, library_id)
    ("t1", "C1", "T1", "lib1"),
    ("t2", "C2", "T1", "lib1"),
    ("t3", "C3", "T1", "lib2"),
    ("t4", "C4", "T2", "lib2"),
    ("t5", "C5", "T2", "lib1"),
    ("t6", "C6", "T3", "lib1"),
    ("t7", "C7", "T3", "lib1"),
    ("t8", "C8", "T3", "lib1"),
]

# term_id -> (ext_attrs_json, term_tags_json)
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
def qreader(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[PostgresTermReader, list[str]]:
    """sqlite 内存库 reader + 捕获 SQL 语句的列表。"""
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
# label_filters 空语义：None/[] → 跳过维度（不再 return []）
# ═════════════════════════════════════════════════════════════════════════════


def test_t1_label_filters_none_skips_dimension(
    qreader: tuple[PostgresTermReader, list[str]],
) -> None:
    """label_filters=None + term_type_codes=["T1"] → 按 term_type 过滤，非空。"""
    reader, statements = qreader
    result = reader.query_terms_by_labels(
        label_filters=None,
        term_type_codes=["T1"],
    )
    assert len(result) == 3
    assert _ids(result) == {"t1", "t2", "t3"}
    # SQL 不含 label 片段
    sql = statements[-1]
    assert "term_tags->>" not in sql
    assert "term_type_code IN" in sql


def test_t1_label_filters_empty_list_skips_dimension(
    qreader: tuple[PostgresTermReader, list[str]],
) -> None:
    """label_filters=[] + kb_ids=["k1"] → 按 kb_id 过滤，非空（不再 return []）。"""
    reader, statements = qreader
    result = reader.query_terms_by_labels(
        label_filters=[],
        kb_ids=["k1"],
    )
    assert _ids(result) == {"t1", "t2", "t7"}
    sql = statements[-1]
    assert "term_tags->>" not in sql
    assert "ext_attrs->>'kb_id' IN" in sql


def test_t1_all_invalid_label_entries_skip_dimension(
    qreader: tuple[PostgresTermReader, list[str]],
) -> None:
    """label_filters 全部条目无效（field_code 空 / filter_value None）→ 跳过维度。"""
    reader, _ = qreader
    result = reader.query_terms_by_labels(
        label_filters=[
            {"field_code": "", "filter_value": "x"},
            {"field_code": "kb_file_path", "filter_value": None},
        ],
        kb_ids=["k1"],
    )
    assert _ids(result) == {"t1", "t2", "t7"}


# ═════════════════════════════════════════════════════════════════════════════
# 空列表全滤 / None 忽略（kb 三键 + term_type_codes）
# ═════════════════════════════════════════════════════════════════════════════


def test_t2_kb_ids_empty_means_full_filter(
    qreader: tuple[PostgresTermReader, list[str]],
) -> None:
    """kb_ids=[]（其余正常）→ 返回 []，且不生成 IN () 片段（无 SQLAlchemy 语法异常）。"""
    reader, statements = qreader
    result = reader.query_terms_by_labels(
        kb_ids=[],
        kb_file_paths=["/a/p1.md"],
    )
    assert result == []
    # 不得出现 IN () 空括号
    assert not any("IN ()" in sql for sql in statements)
    # 全滤短路发生在 SQL 执行前：无查询语句被提交
    assert not statements


def test_t2_kb_ids_none_ignored(
    qreader: tuple[PostgresTermReader, list[str]],
) -> None:
    """kb_ids=None → 按其他维度过滤，SQL 不含 kb_id 片段。"""
    reader, statements = qreader
    result = reader.query_terms_by_labels(
        kb_ids=None,
        kb_file_paths=["/a/p1.md"],
    )
    assert _ids(result) == {"t1", "t7", "t8"}
    sql = statements[-1]
    assert "ext_attrs->>'kb_id'" not in sql
    assert "term_tags->>'kb_file_path' IN" in sql


def test_t2_kb_resource_ids_empty_full_filter(
    qreader: tuple[PostgresTermReader, list[str]],
) -> None:
    """kb_resource_ids=[] → 全滤 []。"""
    reader, _ = qreader
    result = reader.query_terms_by_labels(
        kb_resource_ids=[],
        kb_ids=["k1"],
    )
    assert result == []


def test_t2_kb_file_paths_empty_full_filter(
    qreader: tuple[PostgresTermReader, list[str]],
) -> None:
    """kb_file_paths=[] → 全滤 []。"""
    reader, _ = qreader
    result = reader.query_terms_by_labels(
        kb_file_paths=[],
        kb_ids=["k1"],
    )
    assert result == []


def test_t2_term_type_codes_empty_full_filter_regression(
    qreader: tuple[PostgresTermReader, list[str]],
) -> None:
    """term_type_codes=[] → []（现状语义回归锁定）。"""
    reader, _ = qreader
    result = reader.query_terms_by_labels(
        label_filters=[{"field_code": "kb_file_path", "filter_value": "/a/p1.md"}],
        term_type_codes=[],
    )
    assert result == []


def test_t2_single_dimension_kb_resource_ids(
    qreader: tuple[PostgresTermReader, list[str]],
) -> None:
    """单维度：kb_resource_ids=["r2"] → 仅返回 ext_attrs.kb_resource_id ∈ {r2} 的行。"""
    reader, _ = qreader
    result = reader.query_terms_by_labels(kb_resource_ids=["r2"])
    assert _ids(result) == {"t3", "t4"}


def test_t2_single_dimension_kb_file_paths(
    qreader: tuple[PostgresTermReader, list[str]],
) -> None:
    """单维度：kb_file_paths=["/a/p1.md"] → 仅返回 term_tags.kb_file_path 命中行。"""
    reader, _ = qreader
    result = reader.query_terms_by_labels(kb_file_paths=["/a/p1.md"])
    assert _ids(result) == {"t1", "t7", "t8"}


# ═════════════════════════════════════════════════════════════════════════════
# 全维度空 → []（不执行无 WHERE 查询）
# ═════════════════════════════════════════════════════════════════════════════


def test_t3_all_dimensions_none_returns_empty_without_query(
    qreader: tuple[PostgresTermReader, list[str]],
) -> None:
    """五维度全 None → []，且不执行任何 SQL（execute 未被调用）。"""
    reader, statements = qreader
    result = reader.query_terms_by_labels(
        label_filters=None,
        term_type_codes=None,
        kb_ids=None,
        kb_resource_ids=None,
        kb_file_paths=None,
    )
    assert result == []
    assert statements == []


# ═════════════════════════════════════════════════════════════════════════════
# 组合规则：多维度全 AND
# ═════════════════════════════════════════════════════════════════════════════


def test_t4_four_dimensions_and_combined(
    qreader: tuple[PostgresTermReader, list[str]],
) -> None:
    """四维同传 → SQL 含 4 个片段且 AND 连接；结果行同时满足四维。"""
    reader, statements = qreader
    result = reader.query_terms_by_labels(
        kb_ids=["k1", "k2"],
        kb_resource_ids=["r1"],
        kb_file_paths=["/a/p1.md"],
        term_type_codes=["T1"],
    )
    # k1 且 r1 且 /a/p1.md 且 T1 → t1；t7 是 T3 被 type 排除
    assert _ids(result) == {"t1"}

    sql = statements[-1]
    assert "ext_attrs->>'kb_id' IN" in sql
    assert "ext_attrs->>'kb_resource_id' IN" in sql
    assert "term_tags->>'kb_file_path' IN" in sql
    assert "term_type_code IN" in sql
    # 4 个片段以 AND 连接，顺序固定：label 组 → term_type → kb_id → kb_resource_id → kb_file_path
    idx_tt = sql.index("term_type_code IN")
    idx_kbid = sql.index("kb_id' IN")
    idx_kbrid = sql.index("kb_resource_id' IN")
    idx_kbp = sql.index("kb_file_path' IN")
    assert idx_tt < idx_kbid < idx_kbrid < idx_kbp
    assert "AND" in sql
    # LIMIT 在全部过滤之后（方言无关：OpenGauss 命名参数 / sqlite qmark）
    assert re.search(r"LIMIT\s+(?::_lbl_limit|\?)\s*$", sql)


def test_t4_label_or_group_coexists_with_kb_dims(
    qreader: tuple[PostgresTermReader, list[str]],
) -> None:
    """label 生效时与三新参共存 → (label OR 组) AND kb_id IN ...，片段顺序固定。"""
    reader, statements = qreader
    result = reader.query_terms_by_labels(
        label_filters=[
            {"field_code": "kb_file_path", "filter_value": "/a/p1.md"},
            {"field_code": "kb_file_path", "filter_value": "/b/p3.md"},
        ],
        label_condition="or",
        kb_ids=["k1"],
        kb_resource_ids=["r1"],
        term_type_codes=["T1"],
    )
    # label OR 命中 p1/p3 → {t1,t3,t7,t8}；AND kb_id=k1 → {t1,t7}；AND r1 → {t1}；AND T1 → {t1}
    assert _ids(result) == {"t1"}

    sql = statements[-1]
    # label OR 组带括号且在最前（方言无关：OpenGauss 命名参数 / sqlite qmark）
    assert re.search(
        r"WHERE \(t\.term_tags->>'kb_file_path' = (?::_lbl_0|\?) "
        r"OR t\.term_tags->>'kb_file_path' = (?::_lbl_1|\?)\)",
        sql,
    )
    idx_label = sql.index("WHERE (")
    idx_tt = sql.index("term_type_code IN")
    idx_kbid = sql.index("kb_id' IN")
    idx_kbrid = sql.index("kb_resource_id' IN")
    assert idx_label < idx_tt < idx_kbid < idx_kbrid


def test_t4_label_and_chain_with_kb_dims(
    qreader: tuple[PostgresTermReader, list[str]],
) -> None:
    """label_condition="and" 时 label 组为 AND 链，与 kb 维度全 AND。"""
    reader, statements = qreader
    result = reader.query_terms_by_labels(
        label_filters=[
            {"field_code": "kb_file_path", "filter_value": "/a/p1.md"},
            {"field_code": "kb_file_path", "filter_value": "/b/p3.md"},
        ],
        label_condition="and",
        kb_ids=["k1"],
    )
    # label AND 链：同一行不可能两个 path 同时命中 → 空
    assert result == []
    sql = statements[-1]
    assert re.search(
        r"WHERE t\.term_tags->>'kb_file_path' = (?::_lbl_0|\?) "
        r"AND t\.term_tags->>'kb_file_path' = (?::_lbl_1|\?)",
        sql,
    )

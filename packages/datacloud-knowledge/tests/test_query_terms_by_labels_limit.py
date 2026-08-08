"""LIMIT 截断语义验收（filters 形态）。

验证 filters 通道下 LIMIT 位于全部 WHERE 过滤**之后**（截断点后移修复）：

  1. SQL 形状断言：LIMIT 是最后一个片段（固定顺序，_flt_* 占位符位于 LIMIT 前）。
  2. 机制断言：构造「按返回序前 top_k 行均不满足 kb 维度、第 top_k+1 行起满足」
     的数据 → 底层函数返回**非空**（命中行不被截断丢弃）。
  3. filters 形态与三参数形态同数据下行为一致（回归确认）。

sqlite 无 ORDER BY 时按 rowid（插入序）返回 —— 本测试依赖该行为构造
「前 1000 行不匹配、后 200 行匹配」的数据形态。
"""

from __future__ import annotations

import re
from typing import Any

import pytest
from datacloud_knowledge.adapters.opengauss._readers import _base as _reader_base
from datacloud_knowledge.adapters.opengauss.reader import PostgresTermReader
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

_MATCH_KW = "k1"
_MATCH_PATH = "/a/p1.md"
_N_MISMATCH = 1000  # 前 1000 行：path 匹配但 kb_id 不匹配（现状 LIMIT 会截到这里）
_N_MATCH = 500  # 后 500 行：path + kb_id 均匹配


@pytest.fixture()
def limit_reader(monkeypatch: pytest.MonkeyPatch) -> PostgresTermReader:
    """sqlite 内存库：前 1000 行 path=/a/p1.md 但 kb_id='other'，后 500 行完全匹配。"""
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
        for i in range(_N_MISMATCH):
            conn.execute(
                text(
                    "INSERT INTO term (term_id, term_code, term_name, term_type_code, "
                    "desc_summary, parent_term_id, library_id, term_tags, ext_attrs, "
                    "created_time, updated_time) VALUES "
                    "(:tid, :code, :name, 'T1', NULL, NULL, 'lib1', :tags, :ext, 'ts', 'ts')"
                ),
                {
                    "tid": f"m{i}",
                    "code": f"MC{i}",
                    "name": f"path匹配kb不匹配-{i}",
                    "tags": '{"kb_file_path": "/a/p1.md"}',
                    "ext": '{"kb_id": "other", "kb_resource_id": "rother"}',
                },
            )
        for i in range(_N_MATCH):
            conn.execute(
                text(
                    "INSERT INTO term (term_id, term_code, term_name, term_type_code, "
                    "desc_summary, parent_term_id, library_id, term_tags, ext_attrs, "
                    "created_time, updated_time) VALUES "
                    "(:tid, :code, :name, 'T1', NULL, NULL, 'lib1', :tags, :ext, 'ts', 'ts')"
                ),
                {
                    "tid": f"h{i}",
                    "code": f"HC{i}",
                    "name": f"完全命中-{i}",
                    "tags": '{"kb_file_path": "/a/p1.md"}',
                    "ext": '{"kb_id": "k1", "kb_resource_id": "r1"}',
                },
            )
        conn.commit()
    factory = sessionmaker(bind=engine, class_=Session, expire_on_commit=False, autoflush=False)
    return PostgresTermReader(session_factory=factory)


# ═════════════════════════════════════════════════════════════════════════════
# 1. SQL 形状：LIMIT 位于全部 WHERE 过滤之后
# ═════════════════════════════════════════════════════════════════════════════


def test_t5_limit_is_last_clause(monkeypatch: pytest.MonkeyPatch) -> None:
    """生成的 SQL 中 LIMIT 出现在所有维度谓词之后（最后一个位置）。"""
    from sqlalchemy import create_engine, event, text
    from sqlalchemy.orm import Session, sessionmaker

    monkeypatch.setattr(_reader_base, "_SCHEMA_CHECKED", True)
    engine = create_engine("sqlite:///:memory:")
    with engine.connect() as conn:
        conn.execute(
            text(
                """CREATE TABLE term (
                    term_id TEXT PRIMARY KEY, term_code TEXT NOT NULL,
                    term_name TEXT NOT NULL, term_type_code TEXT NOT NULL,
                    desc_summary TEXT, parent_term_id TEXT, library_id TEXT,
                    term_tags TEXT, ext_attrs TEXT,
                    created_time TEXT, updated_time TEXT
                )"""
            )
        )
        conn.execute(
            text(
                "INSERT INTO term VALUES ('t1','C1','n','T1',NULL,NULL,'lib1',"
                '\'{"kb_file_path": "/a/p1.md"}\',\'{"kb_id": "k1", '
                "\"kb_resource_id\": \"r1\"}','ts','ts')"
            )
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
    reader.query_terms_by_labels(
        filters=[
            {"field": "kb_id", "op": "in", "values": ["k1"]},
            {"field": "kb_resource_id", "op": "in", "values": ["r1"]},
            {"field": "kb_file_path", "op": "in", "values": ["/a/p1.md"]},
            {"field": "term_type_code", "op": "in", "values": ["T1"]},
        ],
        top_k=1000,
    )
    sql = statements[-1]
    # LIMIT 位于全部 4 个维度片段之后（方言无关：OpenGauss 命名参数 / sqlite qmark）
    assert re.search(r"LIMIT\s+(?::_lbl_limit|\?)\s*$", sql)
    limit_pos = sql.rfind("LIMIT")
    assert limit_pos > sql.rfind("term_type_code IN")
    assert limit_pos > sql.rfind("kb_id' IN")
    assert limit_pos > sql.rfind("kb_resource_id' IN")
    assert limit_pos > sql.rfind("kb_file_path' IN")
    # filters 占位符 _flt_{idx}_{n} 全部位于 LIMIT 之前
    assert "_flt_0_0" in sql or sql.count("?") >= 4
    for token in ("_flt_0_0", "_flt_1_0", "_flt_2_0", "_flt_3_0"):
        if token in sql:
            assert sql.rfind(token) < limit_pos


# ═════════════════════════════════════════════════════════════════════════════
# 2. 机制断言：截断发生在过滤后 → 命中行不被丢弃
# ═════════════════════════════════════════════════════════════════════════════


def test_t5_truncation_after_filter_returns_hits(
    limit_reader: PostgresTermReader,
) -> None:
    """前 1000 行不满足 kb 维度、后 200 行满足 → 返回 200 行（非空）。"""
    result = limit_reader.query_terms_by_labels(
        filters=[
            {"field": "kb_id", "op": "in", "values": ["k1"]},
            {"field": "kb_file_path", "op": "in", "values": ["/a/p1.md"]},
        ],
        top_k=1000,
    )
    assert len(result) == _N_MATCH
    assert all(str(item["term_id"]).startswith("h") for item in result)


# ═════════════════════════════════════════════════════════════════════════════
# 3. 现状对比基线：过滤前截断缺陷复现 → 修复后不再复现
# ═════════════════════════════════════════════════════════════════════════════


def test_t5_legacy_shape_returns_empty_but_merged_shape_nonempty(
    limit_reader: PostgresTermReader,
) -> None:
    """同一数据：现状形态（label OR 通道 + top_k=1000 + 内存 kb_id 过滤）→ 空；
    filters 形态（kb 维度下推）→ 非空。证明截断点后移修复有效。"""
    # 现状形态：B 点改造前 per-kb 循环等价 —— label_filters 只下推 path，
    # kb_id 靠内存过滤；LIMIT 1000 在内存过滤前截断
    legacy = limit_reader.query_terms_by_labels(
        label_filters=[{"field_code": "kb_file_path", "filter_value": _MATCH_PATH}],
        label_condition="or",
        top_k=1000,
    )
    # 内存过滤（等价 B 点现状：result_kb_id != kb_id 则 continue）
    legacy_hits = [
        item
        for item in legacy
        if str((item.get("ext_attrs") or {}).get("kb_id") or "") == _MATCH_KW
    ]
    assert legacy_hits == []  # 过滤前截断：LIMIT 内 1000 行全被内存滤掉 → 空

    # 合并形态：kb 维度下推 → 截断后移 → 命中行返回（filters 通道）
    merged = limit_reader.query_terms_by_labels(
        filters=[
            {"field": "kb_id", "op": "in", "values": [_MATCH_KW]},
            {"field": "kb_file_path", "op": "in", "values": [_MATCH_PATH]},
        ],
        top_k=1000,
    )
    assert len(merged) == _N_MATCH  # 非空：修复生效

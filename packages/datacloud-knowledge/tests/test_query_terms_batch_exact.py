"""query_terms_batch(query_type="exact") — 批量精确检索分支。

回归背景：e2e 验证发现 ``query_terms_batch`` 只实现 BM25/jieba/vector 三路
（Phase 1/2/3），``query_type="exact"`` 时 tsquery_map/vec_map 全空 → 恒返回
全空结果，导致对象发现锚定批量精确查询（``search_terms_batch(query_type="exact")``）
全部落空 → 全走新实例创建 → RPC 超时。

语义对齐单条 ``query_terms(exact)``（_term.py:2219 注释）：TermName.name_text
精确 + Term.term_code 精确（含 TermName 别名行参与匹配；不 ilike、不 BM25、
不 jieba）。

本测试用 sqlite 内存库执行真实 SQL（与 test_enumerate_object_instances 同模式），
验证 exact 批量分支：
- term_name 精确命中
- term_code 精确命中
- TermName 别名精确命中
- 未命中返回空
- 混合（部分命中部分未命中）结果与 keywords 一一对应
- term_type_codes 过滤生效
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from datacloud_knowledge.adapters.opengauss._readers import _base as _reader_base
from datacloud_knowledge.adapters.opengauss.reader import PostgresTermReader
from datacloud_knowledge.contracts.term_provider_types import QueryResult
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

# ─────────────────────────────────────────────────────────────────────────────
# 种子数据：5 个 term + term_name（主名与别名）
#   t1 T1 头痛   Medical   别名: 无
#   t2 T2 胃痛   Medical   别名: 胃疼
#   t3 T3 合同   Legal     别名: 无
#   t4 T4 发烧   Medical   别名: 发热
#   t5 T5 发票   Finance   别名: 无
# ─────────────────────────────────────────────────────────────────────────────

_TS = datetime(2026, 8, 8, 12, 0, 0, tzinfo=UTC)

_TERMS = [
    ("t1", "T1", "头痛", "Medical", "lib1"),
    ("t2", "T2", "胃痛", "Medical", "lib1"),
    ("t3", "T3", "合同", "Legal", "lib1"),
    ("t4", "T4", "发烧", "Medical", "lib1"),
    ("t5", "T5", "发票", "Finance", "lib1"),
]

# (name_id, term_id, name_text)
_TERM_NAMES = [
    ("n1", "t1", "头痛"),
    ("n2", "t2", "胃痛"),
    ("n3", "t2", "胃疼"),  # 别名
    ("n4", "t3", "合同"),
    ("n5", "t4", "发烧"),
    ("n6", "t4", "发热"),  # 别名
    ("n7", "t5", "发票"),
]


@pytest.fixture()
def exact_reader(monkeypatch: pytest.MonkeyPatch) -> PostgresTermReader:
    """构造 sqlite 内存库 + 种子数据，返回注入 session_factory 的 reader。

    注入 session_factory 后跳过惰性 schema 检查（测试库不连真实 opengauss）；
    monkeypatch 保证测试结束后还原全局标志。
    """
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
        conn.execute(
            text(
                """CREATE TABLE term_name (
                    name_id TEXT PRIMARY KEY,
                    term_id TEXT NOT NULL,
                    name_text TEXT NOT NULL,
                    search_scope TEXT,
                    created_time TEXT,
                    updated_time TEXT
                )"""
            )
        )
        for tid, code, name, ttype, lib in _TERMS:
            conn.execute(
                text(
                    "INSERT INTO term (term_id, term_code, term_name, term_type_code, "
                    "desc_summary, parent_term_id, library_id, term_tags, ext_attrs, "
                    "created_time, updated_time) "
                    "VALUES (:tid, :code, :name, :ttype, NULL, NULL, :lib, '{}', '{}', :ts, :ts)"
                ),
                {
                    "tid": tid,
                    "code": code,
                    "name": name,
                    "ttype": ttype,
                    "lib": lib,
                    "ts": _TS,
                },
            )
        for nid, tid, ntext in _TERM_NAMES:
            conn.execute(
                text(
                    "INSERT INTO term_name (name_id, term_id, name_text, search_scope, "
                    "created_time, updated_time) VALUES (:nid, :tid, :ntext, NULL, :ts, :ts)"
                ),
                {"nid": nid, "tid": tid, "ntext": ntext, "ts": _TS},
            )
        conn.commit()

    factory = sessionmaker(bind=engine, class_=Session, expire_on_commit=False, autoflush=False)
    return PostgresTermReader(session_factory=factory)


def _single(result: QueryResult) -> dict[str, Any]:
    """取单条命中结果归一化为可断言 dict（term_id/code/name/type/score）。"""
    assert result.total >= 1 and result.items
    item = result.items[0]
    return {
        "term_id": item.term_id,
        "term_code": item.term_code,
        "term_name": item.term_name,
        "term_type": item.term_type,
        "score": item.score,
    }


# ═════════════════════════════════════════════════════════════════════════════
# 1. term_name 精确命中
# ═════════════════════════════════════════════════════════════════════════════


def test_exact_batch_hits_term_name(exact_reader: PostgresTermReader) -> None:
    """kw == term.term_name（term_name 表主名行）→ 精确命中，score=1.0。"""
    results = exact_reader.query_terms_batch(
        keywords=["头痛"],
        query_type="exact",
    )
    assert len(results) == 1
    hit = _single(results[0])
    assert hit["term_id"] == "t1"
    assert hit["term_code"] == "T1"
    assert hit["term_name"] == "头痛"
    assert hit["term_type"] == "Medical"
    assert hit["score"] == 1.0


# ═════════════════════════════════════════════════════════════════════════════
# 2. term_code 精确命中
# ═════════════════════════════════════════════════════════════════════════════


def test_exact_batch_hits_term_code(exact_reader: PostgresTermReader) -> None:
    """kw == term.term_code → 精确命中（不依赖 term_name 词面）。"""
    results = exact_reader.query_terms_batch(
        keywords=["T2"],
        query_type="exact",
    )
    assert len(results) == 1
    hit = _single(results[0])
    assert hit["term_id"] == "t2"
    assert hit["term_code"] == "T2"
    assert hit["term_name"] == "胃痛"
    assert hit["score"] == 1.0


# ═════════════════════════════════════════════════════════════════════════════
# 3. TermName 别名精确命中
# ═════════════════════════════════════════════════════════════════════════════


def test_exact_batch_hits_alias(exact_reader: PostgresTermReader) -> None:
    """kw == TermName 别名 name_text（"胃疼"）→ 命中其 term t2。"""
    results = exact_reader.query_terms_batch(
        keywords=["胃疼"],
        query_type="exact",
    )
    assert len(results) == 1
    hit = _single(results[0])
    assert hit["term_id"] == "t2"
    assert hit["term_code"] == "T2"
    assert hit["term_name"] == "胃痛"  # 返回标准名，别名不覆盖 term_name
    assert hit["score"] == 1.0


def test_exact_batch_alias_and_primary_do_not_duplicate(
    exact_reader: PostgresTermReader,
) -> None:
    """同一 term 的主名与别名行均命中时，结果只出现一次（set 去重）。"""
    results = exact_reader.query_terms_batch(
        keywords=["发烧", "发热"],
        query_type="exact",
    )
    assert len(results) == 2
    assert results[0].total == 1
    assert results[1].total == 1
    assert results[0].items[0].term_id == "t4"
    assert results[1].items[0].term_id == "t4"


# ═════════════════════════════════════════════════════════════════════════════
# 4. 未命中返回空
# ═════════════════════════════════════════════════════════════════════════════


def test_exact_batch_miss_returns_empty(exact_reader: PostgresTermReader) -> None:
    """kw 既非任何 name_text 也非任何 term_code → total=0 / items=[]。"""
    results = exact_reader.query_terms_batch(
        keywords=["不存在的词XYZ"],
        query_type="exact",
    )
    assert len(results) == 1
    assert results[0].total == 0
    assert results[0].items == []


def test_exact_batch_substring_is_not_exact(exact_reader: PostgresTermReader) -> None:
    """子串重叠不算命中（exact 语义：不 ilike、不模糊）。"""
    results = exact_reader.query_terms_batch(
        keywords=["头"],
        query_type="exact",
    )
    assert len(results) == 1
    assert results[0].total == 0
    assert results[0].items == []


# ═════════════════════════════════════════════════════════════════════════════
# 5. 混合：部分命中部分未命中 — 结果与 keywords 一一对应
# ═════════════════════════════════════════════════════════════════════════════


def test_exact_batch_mixed_hit_and_miss(exact_reader: PostgresTermReader) -> None:
    """[命中, 未命中, 命中] → 三个 QueryResult 与 keywords 对齐。"""
    results = exact_reader.query_terms_batch(
        keywords=["头痛", "不存在的词XYZ", "合同"],
        query_type="exact",
    )
    assert len(results) == 3
    assert results[0].total == 1
    assert results[0].items[0].term_id == "t1"
    assert results[1].total == 0
    assert results[1].items == []
    assert results[2].total == 1
    assert results[2].items[0].term_id == "t3"


# ═════════════════════════════════════════════════════════════════════════════
# 6. term_type_codes 过滤生效
# ═════════════════════════════════════════════════════════════════════════════


def test_exact_batch_term_type_filter_keeps_matching(
    exact_reader: PostgresTermReader,
) -> None:
    """term_type_codes 命中类型 → 正常返回。"""
    results = exact_reader.query_terms_batch(
        keywords=["头痛"],
        term_type_codes=["Medical"],
        query_type="exact",
    )
    assert len(results) == 1
    assert results[0].total == 1
    assert results[0].items[0].term_id == "t1"


def test_exact_batch_term_type_filter_blocks_other(
    exact_reader: PostgresTermReader,
) -> None:
    """term_type_codes 不含目标类型 → 空结果（过滤在批量 SQL 内生效）。"""
    results = exact_reader.query_terms_batch(
        keywords=["头痛"],
        term_type_codes=["Finance"],
        query_type="exact",
    )
    assert len(results) == 1
    assert results[0].total == 0
    assert results[0].items == []


def test_exact_batch_term_type_filter_multiple(
    exact_reader: PostgresTermReader,
) -> None:
    """term_type_codes 多值 IN 过滤 → 仅命中范围内的类型。"""
    results = exact_reader.query_terms_batch(
        keywords=["头痛", "合同", "发票"],
        term_type_codes=["Medical", "Legal"],
        query_type="exact",
    )
    assert len(results) == 3
    assert results[0].total == 1
    assert results[0].items[0].term_id == "t1"  # Medical 命中
    assert results[1].total == 1
    assert results[1].items[0].term_id == "t3"  # Legal 命中
    assert results[2].total == 0  # Finance 被滤掉


# ═════════════════════════════════════════════════════════════════════════════
# 7. 空 keywords / 空 term_type_codes 边界
# ═════════════════════════════════════════════════════════════════════════════


def test_exact_batch_empty_keywords_returns_empty(exact_reader: PostgresTermReader) -> None:
    """keywords=[] → []（不触达 DB）。"""
    results = exact_reader.query_terms_batch(
        keywords=[],
        query_type="exact",
    )
    assert results == []


def test_exact_batch_empty_term_type_codes_returns_empty(
    exact_reader: PostgresTermReader,
) -> None:
    """term_type_codes=[] → 空结果列表（与 fulltext 路径一致）。"""
    results = exact_reader.query_terms_batch(
        keywords=["头痛"],
        term_type_codes=[],
        query_type="exact",
    )
    assert len(results) == 1
    assert results[0].total == 0
    assert results[0].items == []

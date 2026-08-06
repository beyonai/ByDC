"""T-51: enumerate_object_instances similarity 排序 — _SORT_REGISTRY + 核心 SQL + 已知小图行为。

三层覆盖（verify gate 对应）：

A. 注册表形状：``_SORT_REGISTRY`` 仅 similarity；SortSpecEntry 含 validate/build/requires_name_join。
B. 已知小图行为（sqlite 真实执行；monkeypatch 注册表条目注入 sqlite 兼容分数列，
   真实验证 GROUP BY + MAX + NULLS LAST + 双键的排序机制）：
   - 相似度降序 + 双键（score DESC, term_id ASC）
   - NULL embedding 排尾（NULLS LAST）
   - 1:N 最佳 name 聚合（MAX）
   - 分页不重不漏 + total 恒 = 过滤后全量 + 响应 6 字段无 score
C. SQL 形态（mock session 捕获 SQL，真实 build/validate）：
   - 向量路径余弦表达式（参照 _build_vector_sql）
   - Embedding 失败 → 静默降级 BM25 单字（不 500）
   - 空 query → 退化 term_id ASC（无 JOIN、无排序表达式）
   - 未知 by / params 非 dict / query 非 str → ValueError
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
from datacloud_knowledge.adapters.opengauss._readers import _base as _reader_base
from datacloud_knowledge.adapters.opengauss._readers._term import (
    _SORT_REGISTRY,
    SortSpecEntry,
)
from datacloud_knowledge.adapters.opengauss.reader import PostgresTermReader
from datacloud_knowledge.contracts.term_provider_types import (
    EnumeratedObjectInstances,
    ObjectInstanceItem,
)
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

# ─────────────────────────────────────────────────────────────────────────────
# fixture: sqlite 内存库 + 已知小图（term 8 个 + term_name 1:N 分数列）
# ─────────────────────────────────────────────────────────────────────────────

_TERMS = [
    ("t1", "E1", "One", "Event", '{"kb_resource_id": "kb1"}'),
    ("t2", "E2", "Two", "Event", '{"kb_resource_id": "kb1"}'),
    ("t3", "E3", "Three", "Document", '{"kb_resource_id": "kb2"}'),
    ("t4", "E4", "Four", "Event", '{"kb_resource_id": "kb1"}'),
    ("t5", "E5", "Five", "Event", "{}"),
    ("t6", "E6", "Six", "Event", '{"kb_resource_id": "kb1"}'),
    ("t7", "E7", "Seven", "Event", '{"kb_resource_id": "kb1"}'),
    ("t8", "E8", "Eight", "Event", '{"kb_resource_id": "kb2"}'),
]

# (name_id, term_id, name_text, name_embedding 分数, name_keywords)
# 分数列语义：排序机制测试的注入键（sqlite 无法执行 pgvector <=>，机制层
# 通过注册表条目替换注入 sqlite 兼容表达式；真实余弦表达式见 C 层 SQL 断言）
_NAMES = [
    ("n1", "t1", "One", 0.9, "one"),
    ("n2", "t1", "One Alias", 0.3, "one alias"),  # 1:N：t1 最佳 name = 0.9（MAX 聚合）
    ("n3", "t2", "Two", 0.75, "two"),
    ("n4", "t3", "Three", None, "three"),  # name 行存在但 embedding NULL
    ("n5", "t4", "Four", 0.8, "four"),
    ("n6", "t4", "Four Alias", 0.2, "four alias"),  # 1:N：t4 最佳 name = 0.8
    ("n7", "t5", "Five", None, "five"),  # embedding NULL
    ("n8", "t6", "Six", 0.95, "six"),
    ("n9", "t8", "Eight", 0.75, "eight"),  # 与 t2 同 0.75 → 双键按 term_id ASC
    # t7 无 name 行（LEFT JOIN 不丢行，视为 NULL 排尾）
]

# 期望全序（分数 DESC NULLS LAST, term_id ASC）:
#   0.95: t6 → 0.9: t1 → 0.8: t4 → 0.75: t2(t2<t8) → 0.75: t8 → NULL: t3,t5,t7
EXPECTED_ORDER = ["t6", "t1", "t4", "t2", "t8", "t3", "t5", "t7"]


@pytest.fixture()
def known_graph_reader(monkeypatch: pytest.MonkeyPatch) -> PostgresTermReader:
    """构造 sqlite 内存库 + 已知小图（term + term_name），返回注入 session_factory 的 reader。"""
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
                    ext_attrs TEXT NOT NULL
                )"""
            )
        )
        conn.execute(
            text(
                """CREATE TABLE term_name (
                    name_id TEXT PRIMARY KEY,
                    term_id TEXT NOT NULL,
                    name_text TEXT NOT NULL,
                    name_embedding REAL,
                    name_keywords TEXT
                )"""
            )
        )
        for row in _TERMS:
            conn.execute(
                text(
                    "INSERT INTO term (term_id, term_code, term_name, term_type_code, ext_attrs) "
                    "VALUES (:tid, :code, :name, :type, :attrs)"
                ),
                {"tid": row[0], "code": row[1], "name": row[2], "type": row[3], "attrs": row[4]},
            )
        for row in _NAMES:
            conn.execute(
                text(
                    "INSERT INTO term_name (name_id, term_id, name_text, name_embedding, "
                    "name_keywords) VALUES (:nid, :tid, :ntext, :emb, :kw)"
                ),
                {"nid": row[0], "tid": row[1], "ntext": row[2], "emb": row[3], "kw": row[4]},
            )
        conn.commit()

    factory = sessionmaker(bind=engine, class_=Session, expire_on_commit=False, autoflush=False)
    return PostgresTermReader(session_factory=factory)


def _install_sqlite_sort(monkeypatch: pytest.MonkeyPatch) -> None:
    """把 similarity 条目替换为 sqlite 可执行版本（分数列 = name_embedding）。

    排序机制（GROUP BY + MAX + NULLS LAST + 双键）真实验证；真实余弦表达式
    由 C 层 SQL 形态测试钉死（本文件 test_similarity_vector_sql_shape）。
    """
    monkeypatch.setitem(
        _SORT_REGISTRY,
        "similarity",
        SortSpecEntry(
            validate=lambda params: None,
            build=lambda params: ("MAX(tn.name_embedding) DESC NULLS LAST", {}),
            requires_name_join=True,
        ),
    )


def _similarity_sort(query: str = "query") -> dict[str, Any]:
    return {"by": "similarity", "params": {"query": query}}


def _item_ids(result: EnumeratedObjectInstances) -> list[str]:
    return [item.term_id for item in result.items]


# ─────────────────────────────────────────────────────────────────────────────
# A. 注册表形状
# ─────────────────────────────────────────────────────────────────────────────


def test_sort_registry_only_similarity() -> None:
    """_SORT_REGISTRY 仅 similarity 一个条目（verify gate 钉死），validate/build 可调用。"""
    assert sorted(_SORT_REGISTRY) == ["similarity"]
    entry = _SORT_REGISTRY["similarity"]
    assert callable(entry.validate)
    assert callable(entry.build)
    assert entry.requires_name_join is True, "similarity 排序依赖 term_name（name 级特征）"


# ─────────────────────────────────────────────────────────────────────────────
# B. 已知小图行为（sqlite 真实执行排序机制）
# ─────────────────────────────────────────────────────────────────────────────


def test_similarity_sort_orders_by_score_desc(
    known_graph_reader: PostgresTermReader, monkeypatch: pytest.MonkeyPatch
) -> None:
    """similarity 排序：分数 DESC 全序正确（含 NULL 组排尾）。"""
    _install_sqlite_sort(monkeypatch)
    result = known_graph_reader.enumerate_object_instances(
        object_codes=["Event", "Document"],
        kb_resource_ids=[],
        sort=_similarity_sort(),
    )
    assert _item_ids(result) == EXPECTED_ORDER
    assert result.total == 8, "total 恒 = 过滤后全量（排序不改 total 语义）"


def test_similarity_sort_null_embedding_trailing(
    known_graph_reader: PostgresTermReader, monkeypatch: pytest.MonkeyPatch
) -> None:
    """NULL embedding（t3/t5）与无 name 行（t7）排尾部，按 term_id ASC。"""
    _install_sqlite_sort(monkeypatch)
    result = known_graph_reader.enumerate_object_instances(
        object_codes=["Event", "Document"],
        kb_resource_ids=[],
        sort=_similarity_sort(),
    )
    assert _item_ids(result)[-3:] == ["t3", "t5", "t7"]


def test_similarity_sort_best_name_aggregation(
    known_graph_reader: PostgresTermReader, monkeypatch: pytest.MonkeyPatch
) -> None:
    """term↔term_name 1:N：按最佳匹配 name 聚合（MAX），t1 键 = 0.9 而非 0.3。"""
    _install_sqlite_sort(monkeypatch)
    result = known_graph_reader.enumerate_object_instances(
        object_codes=["Event", "Document"],
        kb_resource_ids=[],
        sort=_similarity_sort(),
    )
    ids = _item_ids(result)
    # t1(0.9) 排在 t4(0.8) 前：若误取最差 name（0.3）或平均值，t1 不会在此位
    assert ids.index("t1") == 1
    assert ids.index("t4") == 2
    assert ids.index("t1") < ids.index("t4")


def test_similarity_sort_tie_break_term_id_asc(
    known_graph_reader: PostgresTermReader, monkeypatch: pytest.MonkeyPatch
) -> None:
    """双键：同分（t2/t8 = 0.75）按 term_id ASC。"""
    _install_sqlite_sort(monkeypatch)
    result = known_graph_reader.enumerate_object_instances(
        object_codes=["Event", "Document"],
        kb_resource_ids=[],
        sort=_similarity_sort(),
    )
    ids = _item_ids(result)
    assert ids.index("t2") < ids.index("t8"), "同分双键必须 term_id ASC（t2 < t8）"


def test_similarity_sort_pagination_and_envelope(
    known_graph_reader: PostgresTermReader, monkeypatch: pytest.MonkeyPatch
) -> None:
    """分页不重不漏 + total 诚实 + 响应 6 字段无 score（verify gate）。"""
    _install_sqlite_sort(monkeypatch)
    page1 = known_graph_reader.enumerate_object_instances(
        object_codes=["Event", "Document"], kb_resource_ids=[], sort=_similarity_sort(),
        page=1, page_size=3,
    )
    page2 = known_graph_reader.enumerate_object_instances(
        object_codes=["Event", "Document"], kb_resource_ids=[], sort=_similarity_sort(),
        page=2, page_size=3,
    )
    page3 = known_graph_reader.enumerate_object_instances(
        object_codes=["Event", "Document"], kb_resource_ids=[], sort=_similarity_sort(),
        page=3, page_size=3,
    )
    assert (page1.total, page2.total, page3.total) == (8, 8, 8)
    assert _item_ids(page1) + _item_ids(page2) + _item_ids(page3) == EXPECTED_ORDER
    item = page1.items[0]
    assert isinstance(item, ObjectInstanceItem)
    assert not hasattr(item, "score"), "响应项不得新增 score 字段（verify gate 钉死）"


# ─────────────────────────────────────────────────────────────────────────────
# C. SQL 形态（mock session 捕获 SQL，真实 build/validate）
# ─────────────────────────────────────────────────────────────────────────────


class _FakeRows:
    """空结果行集合：主查询 fetchall 空 + total scalar 0。"""

    def fetchall(self) -> list[Any]:
        return []

    def scalar(self) -> int:
        return 0


class _FakeSession:
    """捕获 SQL 文本与绑定参数的假 session（真实 with 上下文支持）。"""

    def __init__(self, captured: dict[str, Any]) -> None:
        self._captured = captured

    def __enter__(self) -> _FakeSession:
        return self

    def __exit__(self, *args: Any) -> bool:
        return False

    def execute(self, stmt: Any, params: Any = None) -> _FakeRows:
        self._captured["sqls"].append(str(stmt))
        self._captured["params_list"].append(params)
        return _FakeRows()


def _capture_with(reader: PostgresTermReader, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    captured: dict[str, Any] = {"sqls": [], "params_list": []}
    fake = _FakeSession(captured)
    monkeypatch.setattr(reader, "_get_session", lambda: fake)
    return captured


def test_similarity_vector_sql_shape(
    known_graph_reader: PostgresTermReader, monkeypatch: pytest.MonkeyPatch
) -> None:
    """向量路径 SQL：余弦表达式 + NULLS LAST + 双键 + 分页 LIMIT + total 无排序。"""
    captured = _capture_with(known_graph_reader, monkeypatch)
    with patch(
        "datacloud_knowledge.adapters.opengauss._readers._term._embed_query_vector",
        return_value=[0.1, 0.2, 0.3],
    ):
        known_graph_reader.enumerate_object_instances(
            object_codes=["Event"],
            kb_resource_ids=["kb1"],
            sort=_similarity_sort("退货单"),
        )
    sql = captured["sqls"][0]
    assert "LEFT JOIN term_name tn" in sql
    assert (
        "ORDER BY MAX(1 - (tn.name_embedding <=> CAST(:vector AS vector))) "
        "DESC NULLS LAST, t.term_id ASC" in sql
    ), "相似度双键表达式必须与 _build_vector_sql 同形"
    assert "LIMIT :limit OFFSET :offset" in sql, "分页 LIMIT 保留（排序不截断候选集）"
    vector = captured["params_list"][0]["vector"]
    assert vector == "[0.1,0.2,0.3]"
    total_sql = captured["sqls"][1]
    assert "ORDER BY" not in total_sql, "total 变体不含排序（语义诚实）"


def test_similarity_embedding_failure_falls_back_to_bm25(
    known_graph_reader: PostgresTermReader, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Embedding API 缺失/失败 → 静默降级 BM25 单字（ts_rank_cd），不 500。"""
    captured = _capture_with(known_graph_reader, monkeypatch)
    with patch(
        "datacloud_knowledge.retrieval.embedding.service.EmbeddingService.get_text_embedding",
        side_effect=RuntimeError("Missing embedding configuration"),
    ):
        result = known_graph_reader.enumerate_object_instances(
            object_codes=["Event"],
            kb_resource_ids=[],
            sort=_similarity_sort("退货单"),
        )
    assert result.items == [] and result.total == 0, "Embedding 失败必须静默降级，不抛 500"
    sql = captured["sqls"][0]
    assert "to_tsquery('simple', :tsquery) q" in sql
    assert (
        "ORDER BY MAX(ts_rank_cd(tn.name_keywords, q, 32)) DESC NULLS LAST, t.term_id ASC"
        in sql
    ), "降级路径必须走 BM25 单字 ts_rank_cd"
    tsquery = captured["params_list"][0]["tsquery"]
    assert "退" in tsquery and "货" in tsquery, "tsquery 为单字 OR 组合"


def test_similarity_embedding_failure_is_quiet(
    known_graph_reader: PostgresTermReader, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Embedding 失败时日志 warning 且不抛出（返回空结果）。"""
    captured = _capture_with(known_graph_reader, monkeypatch)
    with patch(
        "datacloud_knowledge.adapters.opengauss._readers._term._embed_query_vector",
        return_value=None,
    ):
        result = known_graph_reader.enumerate_object_instances(
            object_codes=["Event"],
            kb_resource_ids=[],
            sort=_similarity_sort("退货单"),
        )
    assert result.items == []
    sql = captured["sqls"][0]
    assert "ts_rank_cd(tn.name_keywords, q, 32)" in sql


def test_similarity_empty_query_degrades_term_id_asc(
    known_graph_reader: PostgresTermReader, monkeypatch: pytest.MonkeyPatch
) -> None:
    """query 空串 → 退化 term_id ASC（无排序表达式、无 term_name JOIN、无向量/BM25）。"""
    captured = _capture_with(known_graph_reader, monkeypatch)
    known_graph_reader.enumerate_object_instances(
        object_codes=["Event"],
        kb_resource_ids=[],
        sort=_similarity_sort(""),
    )
    sql = captured["sqls"][0]
    assert "ORDER BY t.term_id ASC" in sql
    assert "term_name tn" not in sql, "空 query 退化不得 JOIN term_name"
    assert "<=>" not in sql
    assert "ts_rank_cd" not in sql
    assert "to_tsquery" not in sql


def test_similarity_none_query_degrades_term_id_asc(
    known_graph_reader: PostgresTermReader, monkeypatch: pytest.MonkeyPatch
) -> None:
    """query 显式 None（validate 放行）→ 与空串同语义：退化 term_id ASC（防 str(None)）。"""
    captured = _capture_with(known_graph_reader, monkeypatch)
    known_graph_reader.enumerate_object_instances(
        object_codes=["Event"],
        kb_resource_ids=[],
        sort=_similarity_sort(None),  # type: ignore[arg-type]
    )
    sql = captured["sqls"][0]
    assert "ORDER BY t.term_id ASC" in sql
    assert "<=>" not in sql
    assert "ts_rank_cd" not in sql
    assert "None" not in captured["params_list"][0].get("vector", ""), "不得 embed 字符串 'None'"


def test_no_sort_does_not_join_term_name(
    known_graph_reader: PostgresTermReader, monkeypatch: pytest.MonkeyPatch
) -> None:
    """无 sort → 不 JOIN term_name（防相似度排序泄漏到默认路径）。"""
    captured = _capture_with(known_graph_reader, monkeypatch)
    known_graph_reader.enumerate_object_instances(
        object_codes=["Event"],
        kb_resource_ids=[],
    )
    sql = captured["sqls"][0]
    assert "term_name tn" not in sql, "无 sort 不得 JOIN term_name"
    assert "ORDER BY t.term_id ASC" in sql


# ─────────────────────────────────────────────────────────────────────────────
# 校验：未知 by / 形状非法 / query 类型非法 → ValueError（→400）
# ─────────────────────────────────────────────────────────────────────────────


def test_unknown_sort_by_raises_value_error(
    known_graph_reader: PostgresTermReader,
) -> None:
    """未知 sort by（不在注册表）→ ValueError。"""
    with pytest.raises(ValueError, match="未知 sort by"):
        known_graph_reader.enumerate_object_instances(
            object_codes=["Event"],
            kb_resource_ids=[],
            sort={"by": "relevance", "params": {}},
        )


def test_sort_must_be_dict(known_graph_reader: PostgresTermReader) -> None:
    """sort 非 dict → ValueError。"""
    with pytest.raises(ValueError, match="sort 必须是 dict"):
        known_graph_reader.enumerate_object_instances(
            object_codes=["Event"],
            kb_resource_ids=[],
            sort="similarity",  # type: ignore[arg-type]
        )


def test_sort_params_must_be_dict(known_graph_reader: PostgresTermReader) -> None:
    """sort.params 非 dict → ValueError。"""
    with pytest.raises(ValueError, match="params 必须是 dict"):
        known_graph_reader.enumerate_object_instances(
            object_codes=["Event"],
            kb_resource_ids=[],
            sort={"by": "similarity", "params": "退货单"},  # type: ignore[dict-item]
        )


def test_similarity_query_must_be_str(known_graph_reader: PostgresTermReader) -> None:
    """similarity params.query 非 str → ValueError（数字等非法）。"""
    with pytest.raises(ValueError, match="query 必须是字符串"):
        known_graph_reader.enumerate_object_instances(
            object_codes=["Event"],
            kb_resource_ids=[],
            sort={"by": "similarity", "params": {"query": 123}},  # type: ignore[dict-item]
        )

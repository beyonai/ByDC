"""T-45: enumerate_object_instances — 已知小图集成测试 + 注册表校验。

使用 sqlite 内存库执行生成的 SQL（sqlite 3.38+ 支持 ``->>`` 运算符），
验证度数语义 / 条件过滤 / 范围过滤 / 分页 / 动态排序 / 注册表校验。

已知小图（8 个 term + 12 条 relation）：

    term:
      t1 Event    kb1    t2 Event  kb1    t3 Document kb2
      t4 Event    kb1    t5 Event  (无kb)  t6 Event  kb1
      t7 Event    kb1    t8 Event  kb2

    term_relation（全图度数期望）:
      r1  t1→t2  BUSINESS      r2  t1→t3  BUSINESS
      r3  t2→t1  BUSINESS      r4  t4→t4  BUSINESS   (自环)
      r5  t4→t1  BUSINESS      r6  t2→t4  BUSINESS
      r7  t5→t6  BUSINESS      r8  t1→t8  BUSINESS
      r9  t1→t2  HAS_FIELD     (非 BUSINESS — 不计入)
      r10 t1→t8  仅类型级      (source_term_id NULL — 不计入)
      r11 t2→t6  BUSINESS      r12 t5→t8  BUSINESS

    期望度数:
      t1 (3,2)  t2 (3,1)  t3 (0,1)  t4 (2,2)
      t5 (2,0)  t6 (0,2)  t7 (0,0)  t8 (0,2)
"""

from __future__ import annotations

from typing import Any
from unittest.mock import Mock, patch

import pytest
from datacloud_knowledge.adapters.opengauss._readers import _base as _reader_base
from datacloud_knowledge.adapters.opengauss._readers._term import _FILTER_REGISTRY
from datacloud_knowledge.adapters.opengauss.reader import PostgresTermReader
from datacloud_knowledge.contracts.term_provider_types import (
    EnumeratedObjectInstances,
    ObjectInstanceItem,
)
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

# ─────────────────────────────────────────────────────────────────────────────
# fixture: sqlite 内存库 + 已知小图
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

# (relation_id, source_term_id, target_term_id, source_type, target_type, category)
_RELATIONS = [
    ("r1", "t1", "t2", None, None, "BUSINESS"),
    ("r2", "t1", "t3", None, None, "BUSINESS"),
    ("r3", "t2", "t1", None, None, "BUSINESS"),
    ("r4", "t4", "t4", None, None, "BUSINESS"),  # 自环
    ("r5", "t4", "t1", None, None, "BUSINESS"),
    ("r6", "t2", "t4", None, None, "BUSINESS"),
    ("r7", "t5", "t6", None, None, "BUSINESS"),
    ("r8", "t1", "t8", None, None, "BUSINESS"),
    ("r9", "t1", "t2", None, None, "HAS_FIELD"),  # 非 BUSINESS — 不计入
    ("r10", None, "t8", "Event", None, "BUSINESS"),  # 类型级边 — 不计入
    ("r11", "t2", "t6", None, None, "BUSINESS"),
    ("r12", "t5", "t8", None, None, "BUSINESS"),
]

# 期望全图度数 (term_id -> (out, in))
EXPECTED_DEGREES: dict[str, tuple[int, int]] = {
    "t1": (3, 2),
    "t2": (3, 1),
    "t3": (0, 1),
    "t4": (2, 2),
    "t5": (2, 0),
    "t6": (0, 2),
    "t7": (0, 0),
    "t8": (0, 2),
}


@pytest.fixture()
def known_graph_reader(monkeypatch: pytest.MonkeyPatch) -> PostgresTermReader:
    """构造 sqlite 内存库 + 已知小图，返回注入 session_factory 的 reader。

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
                    ext_attrs TEXT NOT NULL
                )"""
            )
        )
        conn.execute(
            text(
                """CREATE TABLE term_relation (
                    relation_id TEXT PRIMARY KEY,
                    source_term_id TEXT,
                    target_term_id TEXT,
                    source_term_type_code TEXT,
                    target_term_type_code TEXT,
                    relation_category TEXT NOT NULL
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
        for row in _RELATIONS:
            conn.execute(
                text(
                    "INSERT INTO term_relation (relation_id, source_term_id, target_term_id, "
                    "source_term_type_code, target_term_type_code, relation_category) "
                    "VALUES (:rid, :src, :tgt, :src_type, :tgt_type, :cat)"
                ),
                {
                    "rid": row[0],
                    "src": row[1],
                    "tgt": row[2],
                    "src_type": row[3],
                    "tgt_type": row[4],
                    "cat": row[5],
                },
            )
        conn.commit()

    factory = sessionmaker(bind=engine, class_=Session, expire_on_commit=False, autoflush=False)
    return PostgresTermReader(session_factory=factory)


def _degree_filter(metric: str, op: str, value: Any) -> list[dict]:
    """构造 degree filter 请求形状。"""
    return [{"type": "degree", "params": {"metric": metric, "op": op, "value": value}}]


def _item_map(result: EnumeratedObjectInstances) -> dict[str, ObjectInstanceItem]:
    return {item.term_id: item for item in result.items}


def _item_ids(result: EnumeratedObjectInstances) -> list[str]:
    return [item.term_id for item in result.items]


# ═════════════════════════════════════════════════════════════════════════════
# 1. 度数正确性（已知图精确断言）
# ═════════════════════════════════════════════════════════════════════════════


def test_degree_correctness_known_graph(known_graph_reader: PostgresTermReader) -> None:
    """已知小图：每节点 out_degree/in_degree 精确值（含类型级边排除 + BUSINESS 过滤 + 自环）。"""
    # out >= 0 全通过，触发 JOIN → 返回全部 8 节点 + 真实度数
    result = known_graph_reader.enumerate_object_instances(
        object_codes=["Event", "Document"],
        kb_resource_ids=[],
        filters=_degree_filter("out", "gte", 0),
    )
    assert result.total == 8
    by_id = _item_map(result)
    for tid, (out_deg, in_deg) in EXPECTED_DEGREES.items():
        item = by_id[tid]
        assert (item.out_degree, item.in_degree) == (out_deg, in_deg), (
            f"{tid} 度数错误: 期望 ({out_deg},{in_deg}) 实际 ({item.out_degree},{item.in_degree})"
        )


# ═════════════════════════════════════════════════════════════════════════════
# 2. 类型级边排除 3. BUSINESS 过滤 4. 自环
# ═════════════════════════════════════════════════════════════════════════════


def test_type_level_edges_excluded(known_graph_reader: PostgresTermReader) -> None:
    """仅 term_type_code 的类型级边（r10）不计入度数。"""
    result = known_graph_reader.enumerate_object_instances(
        object_codes=["Event"],
        kb_resource_ids=["kb2"],
        filters=_degree_filter("in", "gte", 0),
    )
    item = _item_map(result)["t8"]
    # 仅 r8 + r12（BUSINESS 实例级）→ in=2；r10（类型级，source_term_id NULL）若计入则 3
    assert item.in_degree == 2


def test_non_business_relations_excluded(known_graph_reader: PostgresTermReader) -> None:
    """HAS_FIELD 等非 BUSINESS 关系不计入度数。"""
    result = known_graph_reader.enumerate_object_instances(
        object_codes=["Event"],
        kb_resource_ids=["kb1"],
        filters=_degree_filter("in", "gte", 0),
    )
    item = _item_map(result)["t2"]
    # r9（t1→t2 HAS_FIELD）若计入则 in=2；实际仅 r1 → in=1
    assert item.in_degree == 1


def test_self_loop_counts_in_out_each_once(known_graph_reader: PostgresTermReader) -> None:
    """自环（r4: t4→t4）出度与入度各计一次。"""
    result = known_graph_reader.enumerate_object_instances(
        object_codes=["Event"],
        kb_resource_ids=["kb1"],
        filters=_degree_filter("out", "gte", 0),
    )
    item = _item_map(result)["t4"]
    # out = {r4 自环, r5} = 2; in = {r4 自环, r6} = 2
    assert (item.out_degree, item.in_degree) == (2, 2)


# ═════════════════════════════════════════════════════════════════════════════
# 5. 条件过滤（含除零边界）
# ═════════════════════════════════════════════════════════════════════════════


def test_out_minus_in_condition(known_graph_reader: PostgresTermReader) -> None:
    """out_minus_in >= 0 → 只留出度不少于入度的节点。"""
    result = known_graph_reader.enumerate_object_instances(
        object_codes=["Event", "Document"],
        kb_resource_ids=[],
        filters=_degree_filter("out_minus_in", "gte", 0),
    )
    # t1(1) t2(2) t4(0) t5(2) t7(0) 通过；t3(-1) t6(-2) t8(-2) 排除
    assert sorted(_item_ids(result)) == ["t1", "t2", "t4", "t5", "t7"]
    assert result.total == 5


def test_out_ratio_in_condition(known_graph_reader: PostgresTermReader) -> None:
    """out_ratio_in >= 2 → t2(3.0) 与 t5(+∞) 通过。"""
    result = known_graph_reader.enumerate_object_instances(
        object_codes=["Event", "Document"],
        kb_resource_ids=[],
        filters=_degree_filter("out_ratio_in", "gte", 2),
    )
    assert sorted(_item_ids(result)) == ["t2", "t5"]
    assert result.total == 2


def test_ratio_division_by_zero_boundary(known_graph_reader: PostgresTermReader) -> None:
    """除零边界：in=0 且 out>0（t5）→ +∞ 恒通过 gt；in=0 且 out=0（t7）→ 不参与。"""
    result = known_graph_reader.enumerate_object_instances(
        object_codes=["Event", "Document"],
        kb_resource_ids=[],
        filters=_degree_filter("out_ratio_in", "gt", 3),
    )
    assert _item_ids(result) == ["t5"], "只有 t5（in=0, out>0 → +∞）通过 gt 3（t2=3.0 不过）"
    assert result.total == 1


# ═════════════════════════════════════════════════════════════════════════════
# 6. 范围过滤：类型 IN / kb IN / 两者 AND
# ═════════════════════════════════════════════════════════════════════════════


def test_range_type_only(known_graph_reader: PostgresTermReader) -> None:
    """单维：仅类型过滤。"""
    result = known_graph_reader.enumerate_object_instances(
        object_codes=["Event"],
        kb_resource_ids=[],
    )
    assert sorted(_item_ids(result)) == ["t1", "t2", "t4", "t5", "t6", "t7", "t8"]
    assert result.total == 7


def test_range_kb_only(known_graph_reader: PostgresTermReader) -> None:
    """单维：仅 kb 过滤（ext_attrs->>'kb_resource_id'）。"""
    result = known_graph_reader.enumerate_object_instances(
        object_codes=[],
        kb_resource_ids=["kb1"],
    )
    assert sorted(_item_ids(result)) == ["t1", "t2", "t4", "t6", "t7"]
    assert result.total == 5


def test_range_type_and_kb_are_anded(known_graph_reader: PostgresTermReader) -> None:
    """双维：类型与 kb 取交集（AND）。"""
    result = known_graph_reader.enumerate_object_instances(
        object_codes=["Event"],
        kb_resource_ids=["kb2"],
    )
    assert sorted(_item_ids(result)) == ["t8"]
    assert result.total == 1


# ═════════════════════════════════════════════════════════════════════════════
# 7. 全缺省范围（含 filters 有值）→ 空
# ═════════════════════════════════════════════════════════════════════════════


def test_empty_range_returns_empty_even_with_filters(
    known_graph_reader: PostgresTermReader,
) -> None:
    """object_codes 与 kb_resource_ids 全空 → 空结果，即使 filters 有值（filters 不代替范围）。"""
    result = known_graph_reader.enumerate_object_instances(
        object_codes=[],
        kb_resource_ids=[],
        filters=_degree_filter("out", "gte", 0),
    )
    assert result.items == []
    assert result.total == 0


# ═════════════════════════════════════════════════════════════════════════════
# 8. 分页：total 诚实 / offset 越界 / tie-break 稳定
# ═════════════════════════════════════════════════════════════════════════════


def test_pagination_total_and_no_overlap(known_graph_reader: PostgresTermReader) -> None:
    """分页：total 诚实（8），三页不重不漏。"""
    page1 = known_graph_reader.enumerate_object_instances(
        object_codes=["Event", "Document"], kb_resource_ids=[], page=1, page_size=3
    )
    page2 = known_graph_reader.enumerate_object_instances(
        object_codes=["Event", "Document"], kb_resource_ids=[], page=2, page_size=3
    )
    page3 = known_graph_reader.enumerate_object_instances(
        object_codes=["Event", "Document"], kb_resource_ids=[], page=3, page_size=3
    )
    assert (page1.total, page2.total, page3.total) == (8, 8, 8)
    all_ids = _item_ids(page1) + _item_ids(page2) + _item_ids(page3)
    assert sorted(all_ids) == ["t1", "t2", "t3", "t4", "t5", "t6", "t7", "t8"]
    assert len(set(all_ids)) == 8, "跨页不重不漏"


def test_pagination_offset_out_of_range(known_graph_reader: PostgresTermReader) -> None:
    """offset 越界 → 空 items + 正确 total。"""
    result = known_graph_reader.enumerate_object_instances(
        object_codes=["Event", "Document"], kb_resource_ids=[], page=10, page_size=3
    )
    assert result.items == []
    assert result.total == 8


def test_pagination_tie_break_stable(known_graph_reader: PostgresTermReader) -> None:
    """tie-break 稳定：同度数（out=0）跨页按 term_id ASC，两页拼接 == 全量一次取回。"""
    all_at_once = known_graph_reader.enumerate_object_instances(
        object_codes=["Event", "Document"],
        kb_resource_ids=[],
        filters=_degree_filter("out", "gte", 0),
        page=1,
        page_size=100,
    )
    # out desc + term_id ASC：t1,t2(3) → t4(2) → t5(2) → t3,t6,t7,t8(0 按 term_id)
    expected_order = ["t1", "t2", "t4", "t5", "t3", "t6", "t7", "t8"]
    assert _item_ids(all_at_once) == expected_order

    page1 = known_graph_reader.enumerate_object_instances(
        object_codes=["Event", "Document"],
        kb_resource_ids=[],
        filters=_degree_filter("out", "gte", 0),
        page=1,
        page_size=5,
    )
    page2 = known_graph_reader.enumerate_object_instances(
        object_codes=["Event", "Document"],
        kb_resource_ids=[],
        filters=_degree_filter("out", "gte", 0),
        page=2,
        page_size=5,
    )
    assert _item_ids(page1) + _item_ids(page2) == expected_order


# ═════════════════════════════════════════════════════════════════════════════
# 9. 动态排序
# ═════════════════════════════════════════════════════════════════════════════


def test_sort_term_id_asc_without_degree_filter(known_graph_reader: PostgresTermReader) -> None:
    """无 degree filter → term_id ASC；且不做 JOIN（度数恒 0）。"""
    result = known_graph_reader.enumerate_object_instances(
        object_codes=["Event", "Document"],
        kb_resource_ids=[],
    )
    assert _item_ids(result) == ["t1", "t2", "t3", "t4", "t5", "t6", "t7", "t8"]
    for item in result.items:
        assert (item.out_degree, item.in_degree) == (0, 0)


def test_sort_metric_desc_with_degree_filter(known_graph_reader: PostgresTermReader) -> None:
    """有 degree filter → metric 值降序 + term_id ASC tie-break。"""
    result = known_graph_reader.enumerate_object_instances(
        object_codes=["Event", "Document"],
        kb_resource_ids=[],
        filters=_degree_filter("out", "gte", 0),
    )
    assert _item_ids(result) == ["t1", "t2", "t4", "t5", "t3", "t6", "t7", "t8"]


# ═════════════════════════════════════════════════════════════════════════════
# 10. 注册表校验
# ═════════════════════════════════════════════════════════════════════════════


def test_registry_has_degree_as_first_entry() -> None:
    """_FILTER_REGISTRY 存在，degree 为首个条目（stage=having, required_joins={out,in}）。"""
    assert next(iter(_FILTER_REGISTRY)) == "degree"
    spec = _FILTER_REGISTRY["degree"]
    assert spec.stage == "having"
    assert spec.required_joins == frozenset({"out", "in"})


def test_unknown_filter_type_raises(known_graph_reader: PostgresTermReader) -> None:
    """非法 filter type（不在注册表）→ ValueError。"""
    with pytest.raises(ValueError, match="未知 filter type"):
        known_graph_reader.enumerate_object_instances(
            object_codes=["Event"],
            kb_resource_ids=["kb1"],
            filters=[{"type": "bogus_filter", "params": {}}],
        )


def test_invalid_metric_raises(known_graph_reader: PostgresTermReader) -> None:
    """metric 白名单非法 → ValueError。"""
    with pytest.raises(ValueError, match="metric"):
        known_graph_reader.enumerate_object_instances(
            object_codes=["Event"],
            kb_resource_ids=["kb1"],
            filters=_degree_filter("bogus_metric", "gte", 0),
        )


def test_invalid_op_raises(known_graph_reader: PostgresTermReader) -> None:
    """op 白名单非法 → ValueError。"""
    with pytest.raises(ValueError, match="op"):
        known_graph_reader.enumerate_object_instances(
            object_codes=["Event"],
            kb_resource_ids=["kb1"],
            filters=_degree_filter("out", "bogus_op", 0),
        )


def test_non_numeric_value_raises(known_graph_reader: PostgresTermReader) -> None:
    """value 非数字 → ValueError。"""
    with pytest.raises(ValueError, match="value"):
        known_graph_reader.enumerate_object_instances(
            object_codes=["Event"],
            kb_resource_ids=["kb1"],
            filters=_degree_filter("out", "gte", "abc"),
        )


# ═════════════════════════════════════════════════════════════════════════════
# 11. provider 入口委托 + http adapter 转发
# ═════════════════════════════════════════════════════════════════════════════


def test_provider_delegates_to_reader() -> None:
    """provider.enumerate_object_instances 委托 reader（filters 透传）。"""
    expected = EnumeratedObjectInstances(
        items=[
            ObjectInstanceItem(
                term_id="t1", term_code="E1", term_name="One", term_type_code="Event"
            )
        ],
        total=1,
    )
    with patch(
        "datacloud_knowledge.provider.create_reader",
        return_value=Mock(enumerate_object_instances=Mock(return_value=expected)),
    ) as mock_create:
        from datacloud_knowledge.provider import enumerate_object_instances

        result = enumerate_object_instances(
            object_codes=["Event"],
            kb_resource_ids=["kb1"],
            filters=_degree_filter("out", "gte", 0),
            page=2,
            page_size=5,
        )
    assert result == expected
    mock_create.return_value.enumerate_object_instances.assert_called_once_with(
        object_codes=["Event"],
        kb_resource_ids=["kb1"],
        filters=_degree_filter("out", "gte", 0),
        page=2,
        page_size=5,
    )


def test_http_adapter_forwards_filters() -> None:
    """http adapter 远程转发，filters 原样透传。"""
    from datacloud_knowledge.adapters.http.adapter import HttpTermAdapter

    adapter = HttpTermAdapter(base_url="http://remote.test", pid="p1")
    filters = _degree_filter("out_ratio_in", "gte", 2)
    adapter._client = Mock()  # type: ignore[assignment]
    resp = Mock()
    resp.json.return_value = {
        "resultObject": {
            "items": [
                {
                    "term_id": "t2",
                    "term_code": "E2",
                    "term_name": "Two",
                    "term_type_code": "Event",
                    "out_degree": 3,
                    "in_degree": 1,
                }
            ],
            "total": 1,
        }
    }
    adapter._client.post.return_value = resp  # type: ignore[attr-defined]

    result = adapter.enumerate_object_instances(
        object_codes=["Event"],
        kb_resource_ids=["kb1"],
        filters=filters,
        page=1,
        page_size=20,
    )

    payload = adapter._client.post.call_args[1]["json"]  # type: ignore[attr-defined]
    assert payload["filters"] == filters
    assert payload["objectCodes"] == ["Event"]
    assert payload["kbResourceIds"] == ["kb1"]
    assert payload["page"] == 1
    assert payload["pageSize"] == 20
    assert result.total == 1
    assert result.items[0].term_id == "t2"
    assert result.items[0].out_degree == 3

"""query_terms_by_labels 底层行为验收（filters 形态）。

覆盖 filters 通用过滤通道的核心行为契约：
  label_filters 空语义回归：None/[]/全部条目无效 → 跳过维度（不 return []）
  filters 空值契约：None=忽略 / [] =全滤（不执行含 IN () 的 SQL）/
       元素 in+values=[] =全滤 / eq+values=[] =契约错误（抛 ValueError）/
       term_type_codes=[] =全滤延续
  全维度空 → return []（不执行无 WHERE 查询）
  组合规则：label 组 → term_type_codes → filters 元素（按传入序）固定顺序、
       全 AND、重复 field 元素各自独立 AND（交集正确）

三参数用例改造为 filters 形态（无静默保留）；
T1/T3 保留回归（调用形态调整为四参数）。

基建：sqlite 内存库 + 真实 SQL（sqlite 3.38+ 支持 ->> 运算符）；SQLAlchemy
before_cursor_execute 事件捕获生成的 SQL 文本用于形状断言。
sqlite 将命名参数转 qmark（?），断言用正则兼容（OpenGauss 命名参数 / sqlite qmark）。

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
# label_filters 空语义回归：None/[] → 跳过维度（不 return []）
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
    """label_filters=[] + filters kb_id → 按 kb_id 过滤，非空（不再 return []）。"""
    reader, statements = qreader
    result = reader.query_terms_by_labels(
        label_filters=[],
        filters=[{"field": "kb_id", "op": "in", "values": ["k1"]}],
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
        filters=[{"field": "kb_id", "op": "in", "values": ["k1"]}],
    )
    assert _ids(result) == {"t1", "t2", "t7"}


# ═════════════════════════════════════════════════════════════════════════════
# filters 空值契约
# ═════════════════════════════════════════════════════════════════════════════


def test_t2_filters_empty_list_full_filter(
    qreader: tuple[PostgresTermReader, list[str]],
) -> None:
    """filters=[]（其余正常）→ 返回 []，且不执行任何 SQL（无 IN () 片段）。"""
    reader, statements = qreader
    result = reader.query_terms_by_labels(
        filters=[],
        label_filters=[{"field_code": "kb_file_path", "filter_value": "/a/p1.md"}],
    )
    assert result == []
    # 不得出现 IN () 空括号
    assert not any("IN ()" in sql for sql in statements)
    # 全滤短路发生在 SQL 执行前：无查询语句被提交
    assert not statements


def test_t2_filters_none_ignored(
    qreader: tuple[PostgresTermReader, list[str]],
) -> None:
    """filters=None → 忽略 filters 维度，按其他维度过滤，SQL 无 filters 片段。"""
    reader, statements = qreader
    result = reader.query_terms_by_labels(
        filters=None,
        # 其他维度生效：filters=None 时按 label 通道过滤
        label_filters=[{"field_code": "kb_file_path", "filter_value": "/a/p1.md"}],
    )
    assert _ids(result) == {"t1", "t7", "t8"}
    sql = statements[-1]
    assert "_flt_" not in sql
    assert "term_tags->>'kb_file_path' =" in sql


def test_t2_element_in_empty_values_full_filter(
    qreader: tuple[PostgresTermReader, list[str]],
) -> None:
    """元素 op="in" 且 values=[] → 该维度生效但集合为空 → 全滤 []。"""
    reader, statements = qreader
    result = reader.query_terms_by_labels(
        filters=[
            {"field": "kb_resource_id", "op": "in", "values": []},
        ],
        label_filters=[{"field_code": "kb_file_path", "filter_value": "/a/p1.md"}],
    )
    assert result == []
    assert not any("IN ()" in sql for sql in statements)


def test_t2_term_type_codes_empty_full_filter_regression(
    qreader: tuple[PostgresTermReader, list[str]],
) -> None:
    """term_type_codes=[] → []（延续全滤契约）。"""
    reader, _ = qreader
    result = reader.query_terms_by_labels(
        label_filters=[{"field_code": "kb_file_path", "filter_value": "/a/p1.md"}],
        term_type_codes=[],
    )
    assert result == []


def test_t2_element_eq_empty_values_raises_value_error(
    qreader: tuple[PostgresTermReader, list[str]],
) -> None:
    """元素 op="eq" 且 values=[] → 契约错误抛 ValueError（4.4，不被兜底吞掉）。"""
    reader, statements = qreader
    with pytest.raises(ValueError):
        reader.query_terms_by_labels(
            filters=[{"field": "kb_id", "op": "eq", "values": []}],
            label_filters=[{"field_code": "kb_file_path", "filter_value": "/a/p1.md"}],
        )
    # 契约错误在 try 外抛 → 无任何 SQL 执行
    assert not statements


def test_t2_single_dimension_kb_resource_ids_via_filters(
    qreader: tuple[PostgresTermReader, list[str]],
) -> None:
    """单维度：filters kb_resource_id=["r2"] → 仅返回 ext_attrs.kb_resource_id ∈ {r2} 的行。"""
    reader, _ = qreader
    result = reader.query_terms_by_labels(
        filters=[{"field": "kb_resource_id", "op": "in", "values": ["r2"]}],
    )
    assert _ids(result) == {"t3", "t4"}


def test_t2_single_dimension_kb_file_paths_via_filters(
    qreader: tuple[PostgresTermReader, list[str]],
) -> None:
    """单维度：filters kb_file_path=["/a/p1.md"] → 仅返回 term_tags.kb_file_path 命中行。"""
    reader, _ = qreader
    result = reader.query_terms_by_labels(
        filters=[{"field": "kb_file_path", "op": "in", "values": ["/a/p1.md"]}],
    )
    assert _ids(result) == {"t1", "t7", "t8"}


def test_t2_eq_single_value_matches(
    qreader: tuple[PostgresTermReader, list[str]],
) -> None:
    """元素 op="eq" 恰 1 值 → 单值等值过滤（等价于 in 单元素）。"""
    reader, statements = qreader
    result = reader.query_terms_by_labels(
        filters=[{"field": "kb_id", "op": "eq", "values": ["k1"]}],
    )
    assert _ids(result) == {"t1", "t2", "t7"}
    sql = statements[-1]
    assert re.search(r"ext_attrs->>'kb_id' = (?:_flt_0_0|\?)", sql)


# ═════════════════════════════════════════════════════════════════════════════
# 全维度空 → []（不执行无 WHERE 查询）
# ═════════════════════════════════════════════════════════════════════════════


def test_t3_all_dimensions_none_returns_empty_without_query(
    qreader: tuple[PostgresTermReader, list[str]],
) -> None:
    """四参数全 None（label/term_type/filters 均未生效）→ []，且不执行任何 SQL。"""
    reader, statements = qreader
    result = reader.query_terms_by_labels(
        label_filters=None,
        term_type_codes=None,
        filters=None,
    )
    assert result == []
    assert statements == []


# ═════════════════════════════════════════════════════════════════════════════
# 组合规则：label 组 → term_type_codes → filters 元素（按传入序）全 AND
# ═════════════════════════════════════════════════════════════════════════════


def test_t4_filters_elements_and_combined_in_order(
    qreader: tuple[PostgresTermReader, list[str]],
) -> None:
    """filters 三元素（kb_id, kb_file_path, term_type_code）+ term_type_codes 同传
    → SQL 片段顺序 = term_type_codes → 三元素按传入序，全 AND；结果行同时满足。"""
    reader, statements = qreader
    result = reader.query_terms_by_labels(
        filters=[
            {"field": "kb_id", "op": "in", "values": ["k1", "k2"]},
            {"field": "kb_file_path", "op": "in", "values": ["/a/p1.md"]},
            {"field": "term_type_code", "op": "in", "values": ["T1"]},
        ],
        term_type_codes=["T1"],
    )
    # kb ∈ {k1,k2} 且 path=/a/p1.md 且 T1 → t1；t7 是 T3 被 type 排除
    assert _ids(result) == {"t1"}

    sql = statements[-1]
    assert "ext_attrs->>'kb_id' IN" in sql
    assert "term_tags->>'kb_file_path' IN" in sql
    assert "term_type_code IN" in sql
    # 片段顺序：独立参数 term_type_codes 在前 → filters 三元素按传入序
    idx_tt = sql.index("term_type_code IN")
    idx_kbid = sql.index("kb_id' IN")
    idx_kbp = sql.index("kb_file_path' IN")
    assert idx_tt < idx_kbid < idx_kbp
    # filters 元素占位符 _flt_{idx}_{n} 命名（OpenGauss 命名参数）或 qmark（sqlite）
    assert re.search(r"_flt_0_0", sql) or sql.count("?") >= 4
    # LIMIT 在全部过滤之后（方言无关）
    assert re.search(r"LIMIT\s+(?::_lbl_limit|\?)\s*$", sql)


def test_t4_repeated_field_elements_independent_and(
    qreader: tuple[PostgresTermReader, list[str]],
) -> None:
    """重复 field（两个 kb_id 元素）→ 各自独立 AND，交集正确（不合并不去重）。"""
    reader, statements = qreader
    result = reader.query_terms_by_labels(
        filters=[
            {"field": "kb_id", "op": "in", "values": ["k1", "k2"]},
            {"field": "kb_id", "op": "eq", "values": ["k1"]},
        ],
    )
    # kb ∈ {k1,k2} 且 kb == k1 → {t1, t2, t7}
    assert _ids(result) == {"t1", "t2", "t7"}
    sql = statements[-1]
    # 两个独立 kb_id 片段，各自占位符（_flt_0_* 与 _flt_1_0）无悬空
    assert sql.count("kb_id' IN") == 1
    assert re.search(r"kb_id' IN", sql)
    assert re.search(r"ext_attrs->>'kb_id' = (?:_flt_1_0|\?)", sql)


def test_t4_label_or_group_coexists_with_filters(
    qreader: tuple[PostgresTermReader, list[str]],
) -> None:
    """label 生效时与 filters 共存 → (label OR 组) AND filters 元素，片段顺序固定。"""
    reader, statements = qreader
    result = reader.query_terms_by_labels(
        label_filters=[
            {"field_code": "kb_file_path", "filter_value": "/a/p1.md"},
            {"field_code": "kb_file_path", "filter_value": "/b/p3.md"},
        ],
        label_condition="or",
        filters=[
            {"field": "kb_id", "op": "in", "values": ["k1"]},
            {"field": "term_type_code", "op": "in", "values": ["T1"]},
        ],
    )
    # label OR 命中 p1/p3 → {t1,t3,t7,t8}；AND kb_id=k1 → {t1,t7}；AND T1 → {t1}
    assert _ids(result) == {"t1"}

    sql = statements[-1]
    # label OR 组带括号且在最前（方言无关）
    assert re.search(
        r"WHERE \(t\.term_tags->>'kb_file_path' = (?::_lbl_0|\?) "
        r"OR t\.term_tags->>'kb_file_path' = (?::_lbl_1|\?)\)",
        sql,
    )
    # 片段顺序：label 组 → filters 元素（按传入序：kb_id 在前，term_type_code 在后）
    idx_label = sql.index("WHERE (")
    idx_kbid = sql.index("kb_id' IN")
    idx_tt = sql.index("term_type_code IN")
    assert idx_label < idx_kbid < idx_tt


def test_t4_label_and_chain_with_filters(
    qreader: tuple[PostgresTermReader, list[str]],
) -> None:
    """label_condition="and" 时 label 组为 AND 链，与 filters 元素全 AND。"""
    reader, statements = qreader
    result = reader.query_terms_by_labels(
        label_filters=[
            {"field_code": "kb_file_path", "filter_value": "/a/p1.md"},
            {"field_code": "kb_file_path", "filter_value": "/b/p3.md"},
        ],
        label_condition="and",
        filters=[{"field": "kb_id", "op": "in", "values": ["k1"]}],
    )
    # label AND 链：同一行不可能两个 path 同时命中 → 空
    assert result == []
    sql = statements[-1]
    assert re.search(
        r"WHERE t\.term_tags->>'kb_file_path' = (?::_lbl_0|\?) "
        r"AND t\.term_tags->>'kb_file_path' = (?::_lbl_1|\?)",
        sql,
    )

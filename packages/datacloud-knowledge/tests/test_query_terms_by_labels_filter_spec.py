"""filters 结构校验与白名单验收。

锁定结构契约 + 白名单扩展机制：
  1. 未知 field（如 "kb_name"）→ 抛 ValueError（不被异常兜底 return [] 吞掉）
  2. 非法 op（如 "like"）→ 抛 ValueError
  3. 缺 values / field / op 任一键 → 抛 ValueError
  4. eq 值数 ≠ 1（含 eq+[]）→ 抛 ValueError
  5. 非 dict 元素 → 抛 ValueError
  6. 白名单扩展模拟：向 _FILTER_FIELD_MAP 注入新维度（如 kb_name）→
     SQL 列表达式只来自映射表取值（生成片段正确、无拼接代码路径）、
     值归一化器生效
  7. 契约错误在 try/except 兜底外抛出（断言 ValueError 而非 [] 返回）

基建：sqlite 内存库（复用 behavior 种子基建，仅需 term 表结构）。
"""

from __future__ import annotations

import re
from typing import Any

import pytest
from datacloud_knowledge.adapters.opengauss._readers import _base as _reader_base
from datacloud_knowledge.adapters.opengauss._readers import _term as _term_module
from datacloud_knowledge.adapters.opengauss.reader import PostgresTermReader
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker


@pytest.fixture()
def spec_reader(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[PostgresTermReader, list[str]]:
    """sqlite 内存库 reader + 捕获 SQL 语句的列表（1 行种子）。"""
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
                "INSERT INTO term (term_id, term_code, term_name, term_type_code, "
                "desc_summary, parent_term_id, library_id, term_tags, ext_attrs, "
                "created_time, updated_time) VALUES "
                "('t1', 'C1', 'n', 'T1', NULL, NULL, 'lib1', "
                '\'{"kb_file_path": "/a/p1.md", "kb_name": "客户档案"}\', '
                '\'{"kb_id": "k1", "kb_resource_id": "r1", "kb_name": "客户档案"}\', '
                "'ts', 'ts')"
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
    return reader, statements


# ═════════════════════════════════════════════════════════════════════════════
# 结构契约错误 → ValueError（不被兜底吞掉）
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    ("filters", "err_fragment"),
    [
        # 未知 field（白名单外）
        ([{"field": "kb_name", "op": "in", "values": ["x"]}], "未知 field"),
        # 非法 op
        ([{"field": "kb_id", "op": "like", "values": ["x"]}], "非法 op"),
        # 缺 field 键
        ([{"op": "in", "values": ["x"]}], "缺少 field"),
        # 缺 op 键
        ([{"field": "kb_id", "values": ["x"]}], "缺少 op"),
        # 缺 values 键
        ([{"field": "kb_id", "op": "in"}], "缺少 values"),
        # eq 值数 ≠ 1（0 个）
        ([{"field": "kb_id", "op": "eq", "values": []}], "需要恰 1 个值"),
        # eq 值数 ≠ 1（2 个）
        ([{"field": "kb_id", "op": "eq", "values": ["a", "b"]}], "需要恰 1 个值"),
        # 非 dict 元素
        (["not-a-dict"], "必须是 dict"),
    ],
)
def test_t11_contract_violations_raise_value_error(
    spec_reader: tuple[PostgresTermReader, list[str]],
    filters: list[Any],
    err_fragment: str,
) -> None:
    """结构契约错误 → ValueError（含关键信息），且不执行任何 SQL。"""
    reader, statements = spec_reader
    with pytest.raises(ValueError) as exc:
        reader.query_terms_by_labels(filters=filters)
    assert err_fragment in str(exc.value)
    # 契约错误在 try/except 兜底外抛 → 无 SQL 执行、不静默返回 []
    assert not statements


def test_t11_contract_error_not_swallowed_by_db_exception_fallback(
    monkeypatch: pytest.MonkeyPatch,
    spec_reader: tuple[PostgresTermReader, list[str]],
) -> None:
    """契约错误先于数据层兜底：即使 DB 不可达，契约错误仍抛 ValueError 而非 []。

    模拟 _get_session 抛异常（DB 不可达路径）——契约校验在 try 外，先抛。
    """
    reader, _ = spec_reader

    def _boom(self: Any) -> Any:  # pragma: no cover - 模拟 DB 不可达
        raise RuntimeError("db unreachable")

    monkeypatch.setattr(type(reader), "_get_session", _boom)
    # 契约错误（未知 field）在 _get_session 之前校验 → ValueError
    with pytest.raises(ValueError):
        reader.query_terms_by_labels(filters=[{"field": "kb_unknown", "op": "in", "values": ["x"]}])


def test_t11_valid_filters_not_affected_by_validation(
    spec_reader: tuple[PostgresTermReader, list[str]],
) -> None:
    """合法 filters（白名单 field + eq/in）正常执行，不被校验误伤。"""
    reader, statements = spec_reader
    result = reader.query_terms_by_labels(
        filters=[
            {"field": "kb_id", "op": "eq", "values": ["k1"]},
            {"field": "kb_resource_id", "op": "in", "values": ["r1"]},
        ]
    )
    assert [str(i["term_id"]) for i in result] == ["t1"]
    assert statements  # 正常执行 SQL


# ═════════════════════════════════════════════════════════════════════════════
# 白名单扩展机制：映射表 +1 行 → SQL 正确、归一化生效、无拼接路径
# ═════════════════════════════════════════════════════════════════════════════


def test_t11_whitelist_extension_new_field_via_map(
    monkeypatch: pytest.MonkeyPatch,
    spec_reader: tuple[PostgresTermReader, list[str]],
) -> None:
    """模拟向 _FILTER_FIELD_MAP 注入新维度 kb_name → SQL 列表达式只来自映射表。

    映射表 value = (SQL 列表达式, 归一化器)。扩展新维度 = 映射表 +1 行，
    SQL 生成零拼接代码（断言生成的片段 == 映射表取值）。
    """
    reader, statements = spec_reader

    def _normalize_kb_name(v: str) -> str:
        return v.strip()

    monkeypatch.setattr(
        _term_module,
        "_FILTER_FIELD_MAP",
        {
            **_term_module._FILTER_FIELD_MAP,
            "kb_name": ("t.ext_attrs->>'kb_name'", _normalize_kb_name),
        },
    )
    result = reader.query_terms_by_labels(
        filters=[{"field": "kb_name", "op": "in", "values": [" 客户档案 "]}]  # 归一化 strip
    )
    assert [str(i["term_id"]) for i in result] == ["t1"]
    sql = statements[-1]
    # 列表达式来自映射表（t.ext_attrs->>'kb_name'），占位符命名规范
    assert re.search(r"ext_attrs->>'kb_name' IN", sql)


def test_t11_whitelist_extension_normalizer_applied(
    monkeypatch: pytest.MonkeyPatch,
    spec_reader: tuple[PostgresTermReader, list[str]],
) -> None:
    """扩展维度的值归一化器生效：映射表注册的 normalizer 被应用于绑定值。

    归一化器把值改写后仍能命中（证明组装前统一归一化时机正确）。
    """
    reader, _ = spec_reader

    def _norm(v: str) -> str:
        return f"kb:{v}"

    monkeypatch.setattr(
        _term_module,
        "_FILTER_FIELD_MAP",
        {
            **_term_module._FILTER_FIELD_MAP,
            "kb_id": ("t.ext_attrs->>'kb_id'", _norm),
        },
    )
    # 种子数据 kb_id="k1"；归一化后绑定 "kb:k1" → 不命中（无虚假命中）
    result = reader.query_terms_by_labels(
        filters=[{"field": "kb_id", "op": "in", "values": ["k1"]}]
    )
    assert result == []


def test_t11_whitelist_extension_no_dynamic_concat_path(
    monkeypatch: pytest.MonkeyPatch,
    spec_reader: tuple[PostgresTermReader, list[str]],
) -> None:
    """SQL 组装无拼接路径：生成的 SQL 中列表达式只能来自映射表。

    构造一个「列名与 field 名不同」的映射（如 field=kb_alias → 列 ext_attrs->>'kb_id'），
    断言生成的 SQL 用映射值而非 field 名拼接（field 名本身不出现在 SQL 中）。
    """
    reader, statements = spec_reader
    monkeypatch.setattr(
        _term_module,
        "_FILTER_FIELD_MAP",
        {
            **_term_module._FILTER_FIELD_MAP,
            "kb_alias": ("t.ext_attrs->>'kb_id'", None),
        },
    )
    reader.query_terms_by_labels(filters=[{"field": "kb_alias", "op": "in", "values": ["k1"]}])
    sql = statements[-1]
    # 列表达式来自映射表值（ext_attrs->>'kb_id'）；field 名 kb_alias 绝不进入 SQL
    assert "ext_attrs->>'kb_id'" in sql
    assert "kb_alias" not in sql

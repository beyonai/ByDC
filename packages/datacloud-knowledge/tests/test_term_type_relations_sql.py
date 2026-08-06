"""list_term_type_relations SQL 构建单元测试 — JOIN term 表做类型过滤（ADR-006 修复）。

背景：term_relation 冗余列 source/target_term_type_code 全部为 NULL，旧的按冗余列
过滤方案导致 termType/getRelations 永远返回空。本测试验证修复后的 SQL 结构：

- outgoing  → term_relation JOIN term（source 端），WHERE term.term_type_code = :ttc
- incoming  → term_relation JOIN term（target 端），WHERE term.term_type_code = :ttc
- both      → 双别名 LEFT OUTER JOIN term，WHERE (src 命中 OR tgt 命中)
- type_code 为空 → 不 JOIN 不过滤（向后兼容）
- count 查询与主查询共用同一 JOIN + WHERE（totalCount 不失真）

无 DB 集成测试基建（opengauss 需真实连接），这里用捕获 session 的方式拦截
reader 构建的 statement 并编译为 SQL 文本断言。
"""

from __future__ import annotations

from typing import Any

from datacloud_knowledge.adapters.opengauss._readers._relation import _RelationReader


class _FakeResult:
    """模拟 session.execute() 的返回值：count 走 scalar_one，主查询走 all。"""

    def __init__(self, captured: list[Any]) -> None:
        self._captured = captured

    def scalar_one(self) -> int:
        """count 查询返回 1，让主查询继续执行。"""
        return 1

    def all(self) -> list[Any]:
        """主查询返回空行集。"""
        return []


class _FakeSession:
    """捕获 reader 提交的 statements，不触碰真实数据库。"""

    def __init__(self) -> None:
        self.statements: list[Any] = []

    def execute(self, stmt: Any, params: dict[str, Any] | None = None) -> _FakeResult:
        self.statements.append(stmt)
        return _FakeResult(self.statements)

    def __enter__(self) -> _FakeSession:
        return self

    def __exit__(self, *exc: Any) -> bool:
        return False


def _build_sql(type_code: str, direction: str) -> tuple[str, str]:
    """调用 reader 并返回 (count_sql, rows_sql) 编译文本。"""
    fake = _FakeSession()
    reader = _RelationReader(session_factory=lambda: fake)
    reader._get_session = lambda: fake  # type: ignore[method-assign]  # 跳过 schema 检查
    reader.list_term_type_relations(
        library_id="lib-a",
        type_code=type_code,
        direction=direction,
        page_index=1,
        page_size=20,
    )
    assert len(fake.statements) == 2, "应恰好执行 count + 主查询两个 statement"
    count_stmt, rows_stmt = fake.statements
    compile_kwargs = {"literal_binds": True}
    return (
        str(count_stmt.compile(compile_kwargs=compile_kwargs)),
        str(rows_stmt.compile(compile_kwargs=compile_kwargs)),
    )


def _shared_fragment(sql: str) -> str:
    """提取 FROM … ORDER BY 之前的片段（FROM/JOIN/WHERE），用于比对 count 与主查询。"""
    start = sql.index("FROM")
    end = sql.find("ORDER BY")
    fragment = sql[start:] if end == -1 else sql[start:end]
    return fragment.strip()


class TestOutgoing:
    """direction=outgoing：JOIN source 端 term，按 term.term_type_code 过滤。"""

    def test_joins_term_on_source(self) -> None:
        count_sql, rows_sql = _build_sql("prop", "outgoing")

        assert "JOIN term AS term_1" in count_sql
        assert "term_relation.source_term_id = term_1.term_id" in count_sql
        assert "term_1.term_type_code = 'prop'" in count_sql

        assert "JOIN term AS term_1" in rows_sql
        assert "term_relation.source_term_id = term_1.term_id" in rows_sql
        assert "term_1.term_type_code = 'prop'" in rows_sql
        assert "src_join_type" in rows_sql

    def test_count_shares_join_and_where_with_main(self) -> None:
        count_sql, rows_sql = _build_sql("prop", "outgoing")
        assert _shared_fragment(count_sql) == _shared_fragment(rows_sql)


class TestIncoming:
    """direction=incoming：JOIN target 端 term，按 term.term_type_code 过滤。"""

    def test_joins_term_on_target(self) -> None:
        count_sql, rows_sql = _build_sql("object", "incoming")

        assert "JOIN term AS term_1" in count_sql
        assert "term_relation.target_term_id = term_1.term_id" in count_sql
        assert "term_1.term_type_code = 'object'" in count_sql

        assert "JOIN term AS term_1" in rows_sql
        assert "term_relation.target_term_id = term_1.term_id" in rows_sql
        assert "term_1.term_type_code = 'object'" in rows_sql
        assert "tgt_join_type" in rows_sql

    def test_count_shares_join_and_where_with_main(self) -> None:
        count_sql, rows_sql = _build_sql("object", "incoming")
        assert _shared_fragment(count_sql) == _shared_fragment(rows_sql)


class TestBoth:
    """direction=both：双别名 LEFT OUTER JOIN，任一端类型匹配即命中。"""

    def test_uses_two_left_outer_joins(self) -> None:
        count_sql, rows_sql = _build_sql("relation", "both")

        assert "LEFT OUTER JOIN term AS term_1" in count_sql
        assert "LEFT OUTER JOIN term AS term_2" in count_sql
        assert (
            "term_1.term_type_code = 'relation' OR term_2.term_type_code = 'relation'" in count_sql
        )

        assert "LEFT OUTER JOIN term AS term_1" in rows_sql
        assert "LEFT OUTER JOIN term AS term_2" in rows_sql
        assert "src_join_type" in rows_sql
        assert "tgt_join_type" in rows_sql
        # 两个 JOIN 都必须是 LEFT OUTER，避免 INNER 误删单端命中的行
        assert rows_sql.count("LEFT OUTER JOIN term") == 2

    def test_count_shares_join_and_where_with_main(self) -> None:
        count_sql, rows_sql = _build_sql("relation", "both")
        assert _shared_fragment(count_sql) == _shared_fragment(rows_sql)


class TestNoTypeCode:
    """type_code 为空：不 JOIN 不过滤，返回全部关系（向后兼容）。"""

    def test_no_join_and_no_type_filter(self) -> None:
        count_sql, rows_sql = _build_sql("", "both")

        assert "JOIN term" not in count_sql
        assert "JOIN term" not in rows_sql
        # select 列仍保留 source/target_term_type_code 冗余字段（返回结构不变），
        # 但不得出现基于 term.term_type_code 的过滤条件
        assert "term_type_code =" not in count_sql
        assert "term_type_code =" not in rows_sql

    def test_count_still_shares_where_with_main(self) -> None:
        count_sql, rows_sql = _build_sql("", "both")
        assert _shared_fragment(count_sql) == _shared_fragment(rows_sql)

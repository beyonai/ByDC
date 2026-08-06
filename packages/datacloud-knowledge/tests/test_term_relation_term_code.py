"""term_code 补齐的 reader 级单元测试（无 DB 集成测试基建，用假 session 拦截）。

背景：上一轮修复 termType/getRelations（list_term_type_relations）后，source/target
嵌套结构里 term_code 恒为 None —— reader 只批量取了 term_name，没查 term_code 字段。
本轮补齐：

- list_term_type_relations（termType/getRelations）：
  source/target 的 term 分支 term_code 填入真实值；term_type 分支保持原样；
  term 表中查不到的行保持 None。
- query_term_relations（term/getRelations）：
  扁平结构新增 source_term_code/target_term_code（与 source_term_name 对称）。
- 无 N+1：name/code 必须由同一条批量 SQL 取出（SELECT term_id, term_name,
  term_code），批量语句仅执行一次。

假 session 按编译后 SQL 文本分发：count → 1；FROM term_relation → 主查询行；
FROM term_type → 类型批量行；FROM term → 术语批量行。
"""

from __future__ import annotations

from typing import Any

from datacloud_knowledge.adapters.opengauss._readers._relation import _RelationReader
from datacloud_knowledge.adapters.opengauss._readers._term import _TermReader


class _FakeResult:
    """模拟 session.execute() 的返回值：count 走 scalar_one，其余走 all。"""

    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def scalar_one(self) -> int:
        """count 查询返回 1，让主查询继续执行。"""
        return 1

    def all(self) -> list[Any]:
        return self._rows


class _FakeRow:
    """模拟 SQLAlchemy Row：位置下标 + _mapping（带 label 的 join 列）。"""

    def __init__(self, values: list[Any], keys: list[str]) -> None:
        self._values = values
        self._keys = keys

    def __getitem__(self, index: int) -> Any:
        return self._values[index]

    @property
    def _mapping(self) -> dict[str, Any]:
        return dict(zip(self._keys, self._values, strict=False))


class _FakeSession:
    """按语句类型分发数据，并记录全部 statements 供无 N+1 断言。"""

    def __init__(
        self,
        relation_rows: list[Any],
        term_rows: list[tuple[str, str, str]],
        *,
        type_rows: list[tuple[str, str]] | None = None,
        keys: list[str] | None = None,
    ) -> None:
        self._relation_rows = relation_rows
        self._term_rows = term_rows
        self._type_rows = type_rows or []
        self._keys = keys
        self.statements: list[Any] = []

    def execute(self, stmt: Any, params: dict[str, Any] | None = None) -> _FakeResult:
        self.statements.append(stmt)
        sql = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        if "count(" in sql:
            return _FakeResult([])
        if "FROM term_relation" in sql:
            if self._keys is None:
                return _FakeResult(self._relation_rows)
            return _FakeResult([_FakeRow(list(r), self._keys) for r in self._relation_rows])
        if "FROM term_type" in sql:
            return _FakeResult(self._type_rows)
        return _FakeResult(self._term_rows)

    def __enter__(self) -> _FakeSession:
        return self

    def __exit__(self, *exc: Any) -> bool:
        return False


def _compiled(fake: _FakeSession) -> list[str]:
    return [str(s.compile(compile_kwargs={"literal_binds": True})) for s in fake.statements]


def _term_batch_sql(fake: _FakeSession) -> list[str]:
    """筛选术语批量查询语句（纯 term 表、无 JOIN 的那一条）。"""
    return [sql for sql in _compiled(fake) if "FROM term " in sql]


def _build_relation_reader(fake: _FakeSession) -> _RelationReader:
    reader = _RelationReader(session_factory=lambda: fake)
    reader._get_session = lambda: fake  # type: ignore[method-assign]  # 跳过 schema 检查
    return reader


def _build_term_reader(fake: _FakeSession) -> _TermReader:
    reader = _TermReader(session_factory=lambda: fake)
    reader._get_session = lambda: fake  # type: ignore[method-assign]  # 跳过 schema 检查
    return reader


# list_term_type_relations 主查询列（direction=both 且带 type_code → 追加 join 列）
_TTR_KEYS = [
    "relation_id",
    "source_term_id",
    "source_term_type_code",
    "target_term_id",
    "target_term_type_code",
    "relation_name",
    "relation_category",
    "cardinality",
    "created_time",
    "updated_time",
    "src_join_type",
    "tgt_join_type",
]


class TestListTermTypeRelationsTermCode:
    """termType/getRelations：嵌套结构 term 分支的 term_code 补齐。"""

    def test_term_code_filled_and_type_branch_unchanged(self) -> None:
        """source 为 term（填 code/name），target 为 term_type（保持原样）。"""
        fake = _FakeSession(
            relation_rows=[
                [
                    "rel-1",
                    "t1",
                    None,
                    None,
                    "TPY-2",
                    "引用",
                    "ASSOC",
                    "1:1",
                    None,
                    None,
                    "TPY-1",
                    None,
                ]
            ],
            term_rows=[("t1", "概念一", "TC-001")],
            type_rows=[("TPY-2", "属性")],
            keys=_TTR_KEYS,
        )
        result = _build_relation_reader(fake).list_term_type_relations(
            library_id="lib-a",
            type_code="TPY-1",
            direction="both",
            page_index=1,
            page_size=20,
        )

        assert result["totalCount"] == 1
        (item,) = result["data"]
        assert item["source"] == {
            "type": "term",
            "term_id": "t1",
            "term_code": "TC-001",
            "term_name": "概念一",
        }
        # term_type 分支保持原样（本轮不涉及）
        assert item["target"] == {
            "type": "term_type",
            "type_code": "TPY-2",
            "type_name": "属性",
        }

    def test_term_code_none_when_term_row_missing(self) -> None:
        """term 表中查不到该 term_id 时，term_code 保持 None（不抛错）。"""
        fake = _FakeSession(
            relation_rows=[
                [
                    "rel-2",
                    "ghost",
                    None,
                    None,
                    "TPY-2",
                    "引用",
                    "ASSOC",
                    "1:1",
                    None,
                    None,
                    "TPY-1",
                    None,
                ]
            ],
            term_rows=[],
            type_rows=[("TPY-2", "属性")],
            keys=_TTR_KEYS,
        )
        result = _build_relation_reader(fake).list_term_type_relations(
            library_id="lib-a",
            type_code="TPY-1",
            direction="both",
            page_index=1,
            page_size=20,
        )

        (item,) = result["data"]
        assert item["source"] == {
            "type": "term",
            "term_id": "ghost",
            "term_code": None,
            "term_name": None,
        }

    def test_batch_query_single_select_with_name_and_code(self) -> None:
        """无 N+1：术语批量查询恰好一次，name/code 同一条 SQL 取出。"""
        fake = _FakeSession(
            relation_rows=[
                [
                    "rel-1",
                    "t1",
                    None,
                    None,
                    "TPY-2",
                    "引用",
                    "ASSOC",
                    "1:1",
                    None,
                    None,
                    "TPY-1",
                    None,
                ]
            ],
            term_rows=[("t1", "概念一", "TC-001")],
            type_rows=[("TPY-2", "属性")],
            keys=_TTR_KEYS,
        )
        _build_relation_reader(fake).list_term_type_relations(
            library_id="lib-a",
            type_code="TPY-1",
            direction="both",
            page_index=1,
            page_size=20,
        )

        # count + 主查询 + 术语批量 + 类型批量 = 4 条语句，无逐行查询
        assert len(fake.statements) == 4
        term_sql = _term_batch_sql(fake)
        assert len(term_sql) == 1
        assert "term.term_id" in term_sql[0]
        assert "term.term_name" in term_sql[0]
        assert "term.term_code" in term_sql[0]
        # 纯 term 表查询：不 JOIN term_relation，不出现 term_type 表
        assert "term_relation" not in term_sql[0]
        assert "term_type" not in term_sql[0]


class TestQueryTermRelationsTermCode:
    """term/getRelations：扁平结构新增 source/target_term_code。"""

    def test_adds_flat_source_target_term_code(self) -> None:
        """与 source_term_name/target_term_name 对称补齐 code 字段。"""
        fake = _FakeSession(
            relation_rows=[("rel-1", "t1", "t2", "引用", "ASSOC", "1:N", None, None)],
            term_rows=[("t1", "概念一", "TC-001"), ("t2", "概念二", "TC-002")],
        )
        result = _build_term_reader(fake).query_term_relations(
            term_id="t1",
            direction="both",
            page_index=1,
            page_size=20,
        )

        assert result["totalCount"] == 1
        (item,) = result["data"]
        assert item["relation_id"] == "rel-1"
        assert item["source_term_id"] == "t1"
        assert item["target_term_id"] == "t2"
        assert item["source_term_name"] == "概念一"
        assert item["source_term_code"] == "TC-001"
        assert item["target_term_name"] == "概念二"
        assert item["target_term_code"] == "TC-002"

    def test_term_code_none_when_term_row_missing(self) -> None:
        """一端查不到 term 行时，对应 code/name 均为 None（对称行为）。"""
        fake = _FakeSession(
            relation_rows=[("rel-2", "ghost", "t2", "引用", "ASSOC", "1:N", None, None)],
            term_rows=[("t2", "概念二", "TC-002")],
        )
        result = _build_term_reader(fake).query_term_relations(
            term_id="ghost",
            direction="both",
            page_index=1,
            page_size=20,
        )

        (item,) = result["data"]
        assert item["source_term_name"] is None
        assert item["source_term_code"] is None
        assert item["target_term_name"] == "概念二"
        assert item["target_term_code"] == "TC-002"

    def test_batch_query_single_select_with_name_and_code(self) -> None:
        """无 N+1：count + 主查询 + 一次术语批量 = 3 条语句。"""
        fake = _FakeSession(
            relation_rows=[("rel-1", "t1", "t2", "引用", "ASSOC", "1:N", None, None)],
            term_rows=[("t1", "概念一", "TC-001"), ("t2", "概念二", "TC-002")],
        )
        _build_term_reader(fake).query_term_relations(
            term_id="t1",
            direction="both",
            page_index=1,
            page_size=20,
        )

        assert len(fake.statements) == 3
        term_sql = _term_batch_sql(fake)
        assert len(term_sql) == 1
        assert "term.term_name" in term_sql[0]
        assert "term.term_code" in term_sql[0]


class TestListTermRelationsRegression:
    """list_term_relations（term/termRelation）：helper 改名/改结构后 name 仍正确。"""

    def test_names_still_resolved(self) -> None:
        fake = _FakeSession(
            relation_rows=[
                (
                    "rel-1",
                    "t1",
                    None,
                    "t2",
                    None,
                    "引用",
                    "ASSOC",
                    "1:N",
                    {"kb_id": "kb-1"},
                    None,
                    None,
                )
            ],
            term_rows=[("t1", "概念一", "TC-001"), ("t2", "概念二", "TC-002")],
        )
        result = _build_relation_reader(fake).list_term_relations(
            page_index=1,
            page_size=20,
        )

        (item,) = result["data"]
        assert item["source_term_name"] == "概念一"
        assert item["target_term_name"] == "概念二"
        # 该接口未暴露 term_code 字段，字段集合保持不变
        assert "source_term_code" not in item
        assert "target_term_code" not in item

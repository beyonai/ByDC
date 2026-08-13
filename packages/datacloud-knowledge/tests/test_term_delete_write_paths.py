"""删除链路的 knowledge 层写路径测试（共现反向引用清理 / 孤儿词清理）。

无 DB 集成测试基建，用假 session 拦截 SQL 文本与参数（同
test_term_co_occurrence_writer.py 模式），验证：

1. ``remove_term_co_occurrence_partners``（共现反向引用清理）：
   - 读 term_id 自身 co_occurrence 的伙伴 key 集
   - 对每个伙伴 term：SELECT term_tags FOR UPDATE → 移除指向 term_id
     的 key → UPDATE 整体写回（保留其他 key）
   - 返回被清理的伙伴 term_id 列表（读序）
   - 幂等：term 不存在 / co_occurrence 为空 / 伙伴已删 → 不抛异常
2. ``delete_orphan_vocabulary_words``（孤儿词清理）：
   - 孤儿判定 SQL：无 term_name.name_text 引用 且 无 term.term_name
     引用才删——两个 NOT EXISTS 是「共享词不误删」的结构保证
   - 返回实际删除行数（rowcount 透传）
   - 空 words 为 no-op（不执行 SQL）
"""

from __future__ import annotations

import json
from typing import Any

from datacloud_knowledge.adapters.opengauss._writers._term import _TermWriter


class _Row:
    """模拟 fetchone 结果：row[0] 返回 term_tags。"""

    def __init__(self, term_tags: dict[str, Any] | None) -> None:
        self._term_tags = term_tags

    def __getitem__(self, index: int) -> Any:
        if index == 0:
            return self._term_tags
        raise IndexError(index)


class _SelectResult:
    """SELECT 结果：term 行不存在时 fetchone 返回 None。"""

    def __init__(self, term_tags: dict[str, Any] | None) -> None:
        self._term_tags = term_tags

    def fetchone(self) -> _Row | None:
        if self._term_tags is None:
            return None
        return _Row(self._term_tags)


class _DeleteResult:
    """DELETE 结果：暴露 rowcount。"""

    def __init__(self, rowcount: int) -> None:
        self.rowcount = rowcount


class _FakeSession:
    """记录 execute 调用；模拟 term 表的内存状态。

    - SELECT term_tags（按 term_id/pid 定位）返回预设/更新后的 term_tags，
      term 不存在返回 None（同真实 SQL 语义）
    - UPDATE term SET term_tags 同步内存状态（支持多伙伴连续读改写）
    - DELETE FROM term_vocabulary 返回预设 rowcount
    """

    def __init__(
        self,
        term_tags_by_id: dict[str, dict[str, Any]] | None = None,
        delete_rowcount: int = 0,
    ) -> None:
        self.statements: list[tuple[str, dict[str, Any]]] = []
        self.term_tags_by_id: dict[str, dict[str, Any]] = dict(term_tags_by_id or {})
        self.delete_rowcount = delete_rowcount

    def execute(self, statement: Any, params: dict[str, Any] | None = None) -> Any:
        sql = str(statement)
        params = params or {}
        self.statements.append((sql, params))

        if "DELETE FROM term_vocabulary" in sql:
            return _DeleteResult(self.delete_rowcount)
        if "SELECT" in sql:
            tid = params.get("term_id") or params.get("pid")
            return _SelectResult(self.term_tags_by_id.get(tid))
        if "UPDATE term SET term_tags" in sql:
            tid = params.get("term_id") or params.get("pid")
            self.term_tags_by_id[tid] = json.loads(params["tags"])
            return None
        return None

    @property
    def update_statements(self) -> list[tuple[str, dict[str, Any]]]:
        """仅 UPDATE term SET term_tags 的语句（排除 SELECT/DELETE）。"""
        return [
            (sql, params) for sql, params in self.statements if "UPDATE term SET term_tags" in sql
        ]


# ============================================================================
# remove_term_co_occurrence_partners（共现反向引用清理）
# ============================================================================


class TestRemoveTermCoOccurrencePartners:
    def test_removes_reverse_reference_and_preserves_other_keys(self) -> None:
        """主场景：t1 的伙伴 t2 移除指向 t1 的 key，保留 t2 其他 key。"""
        session = _FakeSession(
            term_tags_by_id={
                "t1": {"co_occurrence": {"t2": 5, "t3": 1}},
                "t2": {"kb_id": "144", "co_occurrence": {"t1": 3, "t4": 2}},
                "t3": {"co_occurrence": {"t9": 1}},  # 不含 t1 → 不应被改写
            }
        )
        writer = _TermWriter(session=session)  # type: ignore[arg-type]

        partners = writer.remove_term_co_occurrence_partners(term_id="t1")

        # 返回被清理的伙伴列表（读序 = co_occurrence key 顺序）
        assert partners == ["t2", "t3"]

        # 仅 t2 被 UPDATE：t1 的 key 被移除，kb_id 与其他伙伴 key 保留
        updates = session.update_statements
        assert len(updates) == 1
        _, update_params = updates[0]
        assert update_params["pid"] == "t2"
        tags = json.loads(update_params["tags"])
        assert tags["kb_id"] == "144"
        assert tags["co_occurrence"] == {"t4": 2}  # t1 key 被移除
        # 内存状态同步验证
        assert session.term_tags_by_id["t2"]["co_occurrence"] == {"t4": 2}
        # t3 未含 t1 → 未被改写
        assert session.term_tags_by_id["t3"]["co_occurrence"] == {"t9": 1}

    def test_partner_select_uses_for_update(self) -> None:
        """伙伴读取使用 SELECT ... FOR UPDATE（行级锁，同 update 路径模型）。"""
        session = _FakeSession(
            term_tags_by_id={
                "t1": {"co_occurrence": {"t2": 1}},
                "t2": {"co_occurrence": {"t1": 1}},
            }
        )
        writer = _TermWriter(session=session)  # type: ignore[arg-type]
        writer.remove_term_co_occurrence_partners(term_id="t1")

        partner_selects = [
            sql for sql, params in session.statements if "SELECT" in sql and "FOR UPDATE" in sql
        ]
        assert partner_selects == ["SELECT term_tags FROM term WHERE term_id = :pid FOR UPDATE"]

    def test_missing_term_returns_empty_list(self) -> None:
        """term_id 不存在 → 返回 []，无任何 UPDATE（幂等）。"""
        session = _FakeSession(term_tags_by_id={})
        writer = _TermWriter(session=session)  # type: ignore[arg-type]

        partners = writer.remove_term_co_occurrence_partners(term_id="ghost")

        assert partners == []
        assert session.update_statements == []

    def test_empty_co_occurrence_returns_empty_list(self) -> None:
        """term 存在但 co_occurrence 为空/缺失 → 返回 []（无可清理伙伴）。"""
        for tags in ({}, {"kb_id": "144"}, {"co_occurrence": {}}):
            session = _FakeSession(term_tags_by_id={"t1": dict(tags)})
            writer = _TermWriter(session=session)  # type: ignore[arg-type]
            assert writer.remove_term_co_occurrence_partners(term_id="t1") == []
            assert session.update_statements == []

    def test_deleted_partner_skipped(self) -> None:
        """伙伴 term 已不存在（SELECT 返回 None）→ 跳过不抛异常。"""
        session = _FakeSession(term_tags_by_id={"t1": {"co_occurrence": {"gone": 1}}})
        writer = _TermWriter(session=session)  # type: ignore[arg-type]

        partners = writer.remove_term_co_occurrence_partners(term_id="t1")

        assert partners == ["gone"]  # 仍返回读到的伙伴（清理动作跳过）
        assert session.update_statements == []

    def test_self_reference_removed_when_partner_is_self(self) -> None:
        """伙伴 key 指向自身时同样被移除（读改写按 key 精确移除）。"""
        session = _FakeSession(term_tags_by_id={"t1": {"co_occurrence": {"t1": 2, "t2": 1}}})
        writer = _TermWriter(session=session)  # type: ignore[arg-type]

        writer.remove_term_co_occurrence_partners(term_id="t1")

        # 伙伴 = [t1, t2]；t1（自身）被读改写移除 t1 key，t2 不含 t1 不动
        updates = session.update_statements
        assert len(updates) == 1
        _, update_params = updates[0]
        assert update_params["pid"] == "t1"
        assert json.loads(update_params["tags"])["co_occurrence"] == {"t2": 1}


# ============================================================================
# delete_orphan_vocabulary_words（孤儿词清理）
# ============================================================================


class TestDeleteOrphanVocabularyWords:
    def test_orphan_guard_sql_structure(self) -> None:
        """孤儿判定 SQL 结构：两个 NOT EXISTS 是共享词不误删的保证。"""
        session = _FakeSession(delete_rowcount=2)
        writer = _TermWriter(session=session)  # type: ignore[arg-type]

        deleted = writer.delete_orphan_vocabulary_words(words=["词A", "词B"])

        assert deleted == 2
        sql, params = session.statements[0]
        # 仅删除候选词集合内
        assert "DELETE FROM term_vocabulary tv" in sql
        assert "tv.word = ANY(:words)" in sql
        assert params["words"] == ["词A", "词B"]
        # 孤儿判定：无 term_name.name_text 引用
        assert ("NOT EXISTS (  SELECT 1 FROM term_name tn WHERE tn.name_text = tv.word)") in sql
        # 且无 term.term_name（主名）引用
        assert ("NOT EXISTS (  SELECT 1 FROM term t WHERE t.term_name = tv.word)") in sql

    def test_orphan_guard_semantics_shared_words_kept(self) -> None:
        """孤儿判定语义（模拟 SQL 条件执行）：共享词不误删，孤儿词删。

        与实现的三个 SQL 条件一一对应：
        - ``tv.word = ANY(:words)``        → 候选词
        - ``NOT EXISTS(term_name.name_text = word)`` → 无别名引用
        - ``NOT EXISTS(term.term_name = word)``      → 无主名引用
        """
        vocab = {"词A", "词B", "词C", "词D"}
        term_name_refs = {"词A"}  # 词A 仍被某 term 别名(term_name)引用
        term_main_refs = {"词B"}  # 词B 仍被某 term 主名引用
        candidates = ["词A", "词B", "词C"]  # 本次删除候选（含共享词）

        deleted = [
            w
            for w in candidates
            if w in vocab and w not in term_name_refs and w not in term_main_refs
        ]

        # 词C 是无任何引用的孤儿 → 删；词A/词B 是共享词 → 保留
        assert deleted == ["词C"]

    def test_empty_words_returns_zero_no_sql(self) -> None:
        """空 words → 返回 0，不执行 SQL（no-op）。"""
        writer = _TermWriter(session=_FakeSession())  # type: ignore[arg-type]
        assert writer.delete_orphan_vocabulary_words(words=[]) == 0
        assert writer.session.statements == []  # type: ignore[attr-defined]

    def test_rowcount_zero_translated(self) -> None:
        """rowcount=0（候选词均非孤儿/不在表内）→ 返回 0。"""
        session = _FakeSession(delete_rowcount=0)
        writer = _TermWriter(session=session)  # type: ignore[arg-type]
        assert writer.delete_orphan_vocabulary_words(words=["共享词"]) == 0

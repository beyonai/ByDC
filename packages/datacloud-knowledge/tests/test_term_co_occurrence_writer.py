"""共现存储：term_tags.co_occurrence 新写路径（读改写 + FOR UPDATE + Top-50）。

无 DB 集成测试基建，用假 session 拦截 SQL 文本与参数，验证：
- **实现取舍**：首选原地拼接 jsonb_object_agg / jsonb || jsonb
  在 OpenGauss 2.x 不存在（实测确认），采用 Spec 备选读改写 + SELECT ... FOR UPDATE：
  - 读：SELECT term_tags ... FOR UPDATE（行级锁）
  - 合并：已存在 key 计数累加、新 key 插入（Python 侧）
  - 写：UPDATE term_tags 整体写回（保留其他 key）
  - Top-50 固定上限按 count 降序（Python 侧裁剪）
- 空 patch 为 no-op（不执行 SQL）
- 该路径独立于 update_term（不经其 ext_attrs/term_tags 整列替换怪癖）
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


class _Result:
    def __init__(self, term_tags: dict[str, Any] | None) -> None:
        self._term_tags = term_tags

    def fetchone(self) -> _Row:
        return _Row(self._term_tags)


class _FakeSession:
    """记录 execute 调用（SQL 文本 + 参数），SELECT 返回预设 term_tags。"""

    def __init__(self, term_tags: dict[str, Any] | None = None) -> None:
        self.statements: list[tuple[str, dict[str, Any]]] = []
        self.term_tags = term_tags

    def execute(self, statement: Any, params: dict[str, Any] | None = None) -> Any:
        sql = str(statement)
        self.statements.append((sql, params or {}))
        if "SELECT" in sql and "FOR UPDATE" in sql:
            return _Result(self.term_tags)
        return None


class TestTermCoOccurrenceWriter:
    def test_read_modify_write_merge_accumulate_top50(self) -> None:
        """读改写形态：SELECT FOR UPDATE 锁行 → Python 合并累加 → UPDATE 写回。"""
        session = _FakeSession(
            term_tags={
                "kb_id": "144",
                "co_occurrence": {"t2": 5, "t9": 1},
            }
        )
        writer = _TermWriter(session=session)  # type: ignore[arg-type]
        writer.update_term_co_occurrence(term_id="t1", patch={"t2": 1, "t3": 2})

        assert len(session.statements) == 2  # SELECT + UPDATE
        select_sql, select_params = session.statements[0]
        assert "SELECT term_tags FROM term" in select_sql
        assert "FOR UPDATE" in select_sql  # 行级锁（Spec 备选）
        assert select_params["term_id"] == "t1"

        update_sql, update_params = session.statements[1]
        assert "UPDATE term SET term_tags = :tags" in update_sql
        assert update_params["term_id"] == "t1"
        tags = json.loads(update_params["tags"])
        # 保留 kb 元数据（非整列替换）
        assert tags["kb_id"] == "144"
        # 已存在 key 计数累加：t2 5+1=6
        assert tags["co_occurrence"]["t2"] == 6
        # 新 key 插入：t3 2
        assert tags["co_occurrence"]["t3"] == 2
        assert tags["co_occurrence"]["t9"] == 1

    def test_top50_truncation(self) -> None:
        """Top-50 固定上限：超过 50 个伙伴按 count 降序裁剪。"""
        patch = {f"p{i}": 1 for i in range(60)}
        session = _FakeSession(term_tags={"co_occurrence": {}})
        writer = _TermWriter(session=session)  # type: ignore[arg-type]
        writer.update_term_co_occurrence(term_id="t1", patch=patch)

        _, update_params = session.statements[1]
        tags = json.loads(update_params["tags"])
        co = tags["co_occurrence"]
        assert len(co) == 50  # Top-50 固定上限

    def test_existing_other_keys_preserved(self) -> None:
        """term_tags 其他 key（如 kb 元数据）保留，不被 co_occurrence 覆盖。"""
        session = _FakeSession(term_tags={"kb_file_path": "/Document/x.md", "co_occurrence": {}})
        writer = _TermWriter(session=session)  # type: ignore[arg-type]
        writer.update_term_co_occurrence(term_id="t1", patch={"p1": 1})

        _, update_params = session.statements[1]
        tags = json.loads(update_params["tags"])
        assert tags["kb_file_path"] == "/Document/x.md"
        assert tags["co_occurrence"] == {"p1": 1}

    def test_no_term_row_creates_fresh_co_occurrence(self) -> None:
        """term 行不存在（term_tags 为 None）→ 以空字典合并，不报错。"""
        session = _FakeSession(term_tags=None)
        writer = _TermWriter(session=session)  # type: ignore[arg-type]
        writer.update_term_co_occurrence(term_id="missing", patch={"p1": 2})

        _, update_params = session.statements[1]
        tags = json.loads(update_params["tags"])
        assert tags["co_occurrence"] == {"p1": 2}

    def test_empty_patch_is_noop(self) -> None:
        """空 patch → 不执行 SQL（无读无写）。"""
        writer = _TermWriter(session=_FakeSession())  # type: ignore[arg-type]
        writer.update_term_co_occurrence(term_id="t1", patch={})
        assert writer.session.statements == []  # type: ignore[attr-defined]

"""T11 共现存储：term_tags.co_occurrence 新写路径（JSONB 原地合并 + Top-50）SQL 形态。

无 DB 集成测试基建，用假 session 拦截 SQL 文本与参数，验证：
- 首选 (b) 原地拼接语义：已存在 key 计数累加、新 key 插入（jsonb_each + SUM + UNION ALL）
- Top-50 固定上限按 count 降序（LIMIT 50 + ORDER BY value DESC）
- 空 patch 为 no-op（不执行 SQL）
- 该路径独立于 update_term（不经其 ext_attrs/term_tags 整列替换怪癖）
"""

from __future__ import annotations

import json
from typing import Any

from datacloud_knowledge.adapters.opengauss._writers._term import _TermWriter


class _FakeSession:
    """记录 execute 调用（SQL 文本 + 参数）。"""

    def __init__(self) -> None:
        self.statements: list[tuple[str, dict[str, Any]]] = []

    def execute(self, statement: Any, params: dict[str, Any] | None = None) -> None:
        self.statements.append((str(statement), params or {}))


class TestTermCoOccurrenceWriter:
    def test_sql_shape_merge_accumulate_top50(self) -> None:
        """SQL 形态：jsonb_each 展开 + SUM 累加 + Top-50 降序裁剪 + patch 参数透传。"""
        writer = _TermWriter(session=_FakeSession())  # type: ignore[arg-type]
        writer.update_term_co_occurrence(term_id="t1", patch={"t2": 1, "t3": 2})

        assert len(writer.session.statements) == 1  # type: ignore[attr-defined]
        sql, params = writer.session.statements[0]  # type: ignore[attr-defined]
        # 原地合并（非整列替换）→ 展开现有 + patch
        assert "jsonb_each" in sql
        assert "UNION ALL" in sql
        assert "SUM" in sql  # 计数累加（非 || 覆盖）
        assert "LIMIT 50" in sql  # Top-50 固定上限
        assert "ORDER BY" in sql and "DESC" in sql  # 按 count 降序
        assert "term_tags" in sql
        assert "WHERE term_id = :term_id" in sql
        assert params["term_id"] == "t1"
        assert json.loads(params["patch"]) == {"t2": 1, "t3": 2}

    def test_empty_patch_is_noop(self) -> None:
        """空 patch → 不执行 SQL（无写）。"""
        writer = _TermWriter(session=_FakeSession())  # type: ignore[arg-type]
        writer.update_term_co_occurrence(term_id="t1", patch={})
        assert writer.session.statements == []  # type: ignore[attr-defined]

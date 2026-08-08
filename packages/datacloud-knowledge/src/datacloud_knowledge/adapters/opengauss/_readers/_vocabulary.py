"""_VocabularyReader — term_vocabulary read-side Mixin.

与写入侧 ``_writers/_term.py::batch_create_vocabulary`` 对称的读取通道
（term_vocabulary 单表为唯一词典数据源，本任务只读）。
"""

from __future__ import annotations

import logging

from sqlalchemy import text

from datacloud_knowledge.adapters.opengauss._readers._base import _ReaderBase

logger = logging.getLogger(__name__)


class _VocabularyReader(_ReaderBase):
    """Mixin providing term_vocabulary read operations."""

    def list_vocabulary(self) -> list[str]:
        """读取 term_vocabulary 全量去重词表。

        term_vocabulary 为 TermName 主名+别名的触发器投影
        （``trg_term_name_vocab``，去重写 word），唯一索引 ``idx_vocab_word``
        保障命中判定极速，无需实时 DISTINCT。

        Returns:
            词表 word 列表。
        """
        try:
            with self._get_session() as session:
                rows = session.execute(text("SELECT word FROM term_vocabulary")).all()
        except Exception:
            logger.exception("list_vocabulary failed")
            raise
        return [str(row[0]) for row in rows]

"""term_vocabulary 批量插入处理器。"""

from __future__ import annotations

from psycopg import Cursor


def _batch_insert_vocabulary_words(cur: Cursor, words: list[str]) -> None:
    """向 term_vocabulary 批量插入词汇，自动跳过已存在的词。"""
    if not words:
        return
    cur.execute(
        """INSERT INTO term_vocabulary (word)
           SELECT w FROM unnest(%s::text[]) AS t(w)
           WHERE NOT EXISTS (
               SELECT 1 FROM term_vocabulary v WHERE v.word = t.w
           )""",
        (words,),
    )

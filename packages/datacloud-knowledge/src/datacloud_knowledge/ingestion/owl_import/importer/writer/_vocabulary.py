"""term_vocabulary 批量插入处理器。"""

from __future__ import annotations

from psycopg import Cursor


def _batch_insert_vocabulary_words(cur: Cursor, words: list[str]) -> None:
    """向 term_vocabulary 批量插入词汇，自动跳过已存在的词。

    先同步序列（修复因手动插入导致序列落后于数据的常见问题），
    再通过 ``WHERE NOT EXISTS`` 跳过已存在的 word。
    """
    if not words:
        return

    # 修复 vocab_id 序列不同步：setval 将 last_value 设为当前最大 ID，
    # 确保 nextval 不会返回已占用的值。空表时退化为 setval(1, false) 使 nextval 从 1 开始。
    max_id: int | None = None
    cur.execute("SELECT MAX(vocab_id) FROM term_vocabulary")
    row = cur.fetchone()
    if row is not None:
        max_id = row[0]
    if max_id is not None and max_id > 0:
        cur.execute("SELECT setval('term_vocabulary_vocab_id_seq', %s, true)", (max_id,))
    else:
        cur.execute("SELECT setval('term_vocabulary_vocab_id_seq', 1, false)")

    cur.execute(
        """INSERT INTO term_vocabulary (word)
           SELECT w FROM unnest(%s::text[]) AS t(w)
           WHERE NOT EXISTS (
               SELECT 1 FROM term_vocabulary v WHERE v.word = t.w
           )""",
        (words,),
    )

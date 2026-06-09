"""OpenGauss 后端适配器 — 术语读、搜、写的完整实现。

实现 capabilities/ 层的 TermStore + TermStoreExtended 协议，以及
contracts/ 层的 TermReader / TermWriter 协议：
- store.py: PostgresTermStore ← TermStore + TermStoreExtended
- reader.py: PostgresTermReader ← TermReader
- engine.py: PostgresSearchEngine（BM25/子串/向量多路召回引擎）
- writer.py: PostgresTermWriter ← TermWriter

私有基础设施在 _db/ 子包中，外部不应直接导入。
"""

from .engine import PostgresSearchEngine
from .reader import PostgresTermReader
from .store import PostgresTermStore
from .writer import PostgresTermWriter

__all__ = [
    "PostgresSearchEngine",
    "PostgresTermReader",
    "PostgresTermStore",
    "PostgresTermWriter",
]

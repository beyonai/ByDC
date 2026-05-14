"""批量并发术语召回子包 — 已下沉到 retrieval.recall，此文件保留向后兼容重导出。"""

# 重导出以保证向后兼容
from datacloud_knowledge.retrieval.recall import (
    PreparedBatch,
    RecallRequest,
    ScopeRecallLayer,
    TypedKeywordState,
    typed_multi_recall_batch,
)

__all__ = [
    "PreparedBatch",
    "RecallRequest",
    "ScopeRecallLayer",
    "TypedKeywordState",
    "typed_multi_recall_batch",
]

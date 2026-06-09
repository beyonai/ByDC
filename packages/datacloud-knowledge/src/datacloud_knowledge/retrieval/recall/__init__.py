"""知识检索-批量召回子包 [兼容层]。

本目录是已迁移至 adapters/opengauss/recall/ 的兼容性转发模块。
所有导入在新版代码中应直接引用 datacloud_knowledge.adapters.opengauss.recall。
"""

from datacloud_knowledge.adapters.opengauss.recall import *  # noqa: F403

__all__ = [  # noqa: F405
    "PreparedBatch",
    "RecallRequest",
    "ScopeRecallLayer",
    "TypedKeywordState",
    "typed_multi_recall_batch",
]

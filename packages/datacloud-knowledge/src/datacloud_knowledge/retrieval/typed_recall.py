"""Typed multi-path recall [兼容层]。

本文件已迁移至 adapters/opengauss/recall/typed_recall.py。
新版代码应直接引用 datacloud_knowledge.adapters.opengauss.recall.typed_recall。
"""

from datacloud_knowledge.adapters.opengauss.recall.typed_recall import (
    typed_multi_recall_with_session,
)

__all__ = [
    "typed_multi_recall_with_session",
]

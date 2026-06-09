"""知识检索-统一召回 [兼容层]。

本文件已迁移至 adapters/opengauss/recall/_recall.py。
新版代码应直接引用 datacloud_knowledge.adapters.opengauss.recall._recall。
"""

from datacloud_knowledge.adapters.opengauss.recall._recall import (
    build_scope_recall_layers,
    unified_recall,
)

__all__ = [
    "build_scope_recall_layers",
    "unified_recall",
]

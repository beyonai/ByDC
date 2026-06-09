"""RRF (Reciprocal Rank Fusion) 工具函数 [兼容层]。

本文件已迁移至 adapters/opengauss/recall/rrf.py。
新版代码应直接引用 datacloud_knowledge.adapters.opengauss.recall.rrf。
"""

from datacloud_knowledge.adapters.opengauss.recall.rrf import RRFCandidate, rrf_fuse

__all__ = ["RRFCandidate", "rrf_fuse"]

"""召回共享常量和工具函数 [兼容层]。

本文件已迁移至 adapters/opengauss/recall/_recall_common.py。
新版代码应直接引用 datacloud_knowledge.adapters.opengauss.recall._recall_common。
"""

from datacloud_knowledge.adapters.opengauss.recall._recall_common import (  # noqa: F401
    KTYPE_CATEGORY_MAP,
    CandidateDict,
    _diversify_by_type,
    _load_type_codes_by_category,
    _shape_candidates,
)

__all__ = [
    "KTYPE_CATEGORY_MAP",
    "CandidateDict",
]

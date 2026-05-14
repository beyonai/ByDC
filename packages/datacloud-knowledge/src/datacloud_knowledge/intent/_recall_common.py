"""召回共享常量和工具函数 — 已下沉到 retrieval._recall_common，此文件保留向后兼容重导出。"""

# 重导出以保证向后兼容
from datacloud_knowledge.retrieval._recall_common import (
    KTYPE_CATEGORY_MAP,
    CandidateDict,
    _diversify_by_type,
    _load_type_codes_by_category,
    _shape_candidates,
)

__all__ = [
    "KTYPE_CATEGORY_MAP",
    "CandidateDict",
    "_diversify_by_type",
    "_load_type_codes_by_category",
    "_shape_candidates",
]

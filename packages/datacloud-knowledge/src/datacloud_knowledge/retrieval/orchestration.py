"""DEPRECATED — 降级逻辑已合并至 term_search.py。

请使用 datacloud_knowledge.retrieval.term_search.search_terms_with_fallback。
本文件将在后续重构中删除。
"""

from .term_search import search_terms_with_fallback

__all__ = ["search_terms_with_fallback"]

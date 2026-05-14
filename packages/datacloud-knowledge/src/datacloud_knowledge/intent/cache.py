"""用户级 LRU+TTL 缓存 — 已下沉到 retrieval.name_cache，此文件保留向后兼容重导出。"""

from datacloud_knowledge.retrieval.name_cache import UserNameCache

__all__ = ["UserNameCache"]

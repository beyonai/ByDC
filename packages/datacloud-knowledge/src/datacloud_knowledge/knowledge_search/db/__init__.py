"""向后兼容 shim — 请使用 datacloud_knowledge.db。"""

from datacloud_knowledge.db.connection import get_session

__all__ = ["get_session"]

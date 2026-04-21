"""向后兼容 shim。"""

from datacloud_knowledge.db.connection import _get_engine, _get_session_local, get_session

__all__ = ["_get_engine", "_get_session_local", "get_session"]

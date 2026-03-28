"""knowledge_search 数据库层（同步 SQLAlchemy）。"""

from .connection import get_session

__all__ = ["get_session"]

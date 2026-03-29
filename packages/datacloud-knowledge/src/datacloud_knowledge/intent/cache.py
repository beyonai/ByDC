"""用户级 LRU+TTL 缓存 — 算法 B 二级缓存。"""

from __future__ import annotations

import logging
import time
from contextlib import suppress
from typing import Any

from sqlalchemy import text

log = logging.getLogger(__name__)

NameIndexEntry = tuple[str, str, str, float]
NameIndex = dict[str, list[NameIndexEntry]]


class UserNameCache:
    """用户级别名缓存，LRU + TTL 策略。

    二级缓存：为每个活跃用户维护轻量 name_index，
    仅存该用户的专属 TermName 记录（scope_user_id = user_id）。
    """

    def __init__(self, max_users: int = 100, ttl_seconds: int = 3600) -> None:
        self._max_users = max_users
        self._ttl_seconds = ttl_seconds
        # {user_id: (name_index, loaded_at_monotonic)}
        self._store: dict[str, tuple[NameIndex, float]] = {}
        # LRU order tracking: most recently used at end
        self._access_order: list[str] = []

    def get(self, user_id: str) -> NameIndex | None:
        """Return cached name_index for user, or None if missing/expired."""
        entry = self._store.get(user_id)
        if entry is None:
            return None

        name_index, loaded_at = entry
        if time.monotonic() - loaded_at > self._ttl_seconds:
            self._remove(user_id)
            return None

        self._touch(user_id)
        return name_index

    def put(self, user_id: str, name_index: NameIndex) -> None:
        """Store name_index for user, evicting LRU if needed."""
        if user_id in self._store:
            self._remove(user_id)

        while len(self._store) >= self._max_users:
            oldest = self._access_order[0]
            self._remove(oldest)
            log.debug("LRU evicted user cache: %s", oldest)

        self._store[user_id] = (name_index, time.monotonic())
        self._access_order.append(user_id)

    def load(self, user_id: str, session: Any) -> NameIndex:
        """Load user's scoped aliases from DB and cache them.

        Args:
            user_id: The user ID to load aliases for.
            session: SQLAlchemy Session instance.

        Returns:
            name_index for this user: {name_text: [(term_id, term_type_code, match_type, score), ...]}
        """
        sql = text(
            "SELECT tn.name_text, t.term_id, t.term_type_code, tn.name_tags "
            "FROM whale_datacloud.term_name tn "
            "JOIN whale_datacloud.term t ON tn.term_id = t.term_id "
            "WHERE tn.name_tags->>'scope_user_id' = :user_id"
        )
        rows = session.execute(sql, {"user_id": user_id}).fetchall()

        name_index: NameIndex = {}
        for name_text, term_id, term_type_code, name_tags in rows:
            score = float(name_tags.get("score", 0.0)) if isinstance(name_tags, dict) else 0.0
            entry_list = name_index.setdefault(name_text, [])
            entry_list.append((term_id, term_type_code, "alias", score))

        self.put(user_id, name_index)
        log.debug(
            "Loaded %d aliases for user %s",
            sum(len(entries) for entries in name_index.values()),
            user_id,
        )
        return name_index

    def invalidate(self, user_id: str) -> None:
        """Remove cached data for a specific user."""
        self._remove(user_id)

    def clear(self) -> None:
        """Clear all cached data."""
        self._store.clear()
        self._access_order.clear()

    def _remove(self, user_id: str) -> None:
        """Remove user from store and access order."""
        self._store.pop(user_id, None)
        with suppress(ValueError):
            self._access_order.remove(user_id)

    def _touch(self, user_id: str) -> None:
        """Move user to end of access order (most recently used)."""
        with suppress(ValueError):
            self._access_order.remove(user_id)
        self._access_order.append(user_id)

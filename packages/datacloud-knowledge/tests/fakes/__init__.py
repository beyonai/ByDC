"""可复用测试 Fake — 实现 caps/contracts 中的 Protocol，无 IO。"""

from __future__ import annotations

from .fake_term_store import FakeTermStore

__all__ = ["FakeTermStore"]

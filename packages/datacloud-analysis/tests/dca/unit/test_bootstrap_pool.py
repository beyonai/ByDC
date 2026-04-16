from __future__ import annotations

from collections.abc import Generator
from types import SimpleNamespace
from typing import Any

import datacloud_analysis.bootstrap as bootstrap
import pytest


class _FakePool:
    instances: list[_FakePool] = []

    def __init__(self, conninfo: str, **kwargs: Any) -> None:
        self.conninfo = conninfo
        self.kwargs = kwargs
        self.closed = False
        _FakePool.instances.append(self)

    async def close(self, *_args: Any, **_kwargs: Any) -> None:
        self.closed = True


class _FakeSettings:
    def __init__(self) -> None:
        self.pg = SimpleNamespace(checkpoint_uri="postgresql://user:pwd@localhost:5432/test_db")


@pytest.fixture(autouse=True)
def _reset_bootstrap_state() -> Generator[None, None, None]:
    bootstrap._pg_pool = None  # noqa: SLF001
    bootstrap._pg_checkpoint_cm = None  # noqa: SLF001
    yield
    bootstrap._pg_pool = None  # noqa: SLF001
    bootstrap._pg_checkpoint_cm = None  # noqa: SLF001


def test_get_pg_pool_caches_singleton(monkeypatch: pytest.MonkeyPatch) -> None:
    import datacloud_analysis.config.env as env_mod

    _FakePool.instances.clear()
    monkeypatch.setattr(env_mod, "Settings", _FakeSettings)
    monkeypatch.setattr(bootstrap, "AsyncConnectionPool", _FakePool)

    first = bootstrap.get_pg_pool()
    second = bootstrap.get_pg_pool()

    assert first is second
    assert len(_FakePool.instances) == 1
    created = _FakePool.instances[0]
    assert created.conninfo == "postgresql://user:pwd@localhost:5432/test_db"
    assert created.kwargs["open"] is False


@pytest.mark.asyncio
async def test_teardown_closes_cached_pool(monkeypatch: pytest.MonkeyPatch) -> None:
    import datacloud_analysis.config.env as env_mod

    _FakePool.instances.clear()
    monkeypatch.setattr(env_mod, "Settings", _FakeSettings)
    monkeypatch.setattr(bootstrap, "AsyncConnectionPool", _FakePool)

    pool = bootstrap.get_pg_pool()
    await bootstrap.teardown()

    assert isinstance(pool, _FakePool)
    assert pool.closed is True
    assert bootstrap._pg_pool is None  # noqa: SLF001

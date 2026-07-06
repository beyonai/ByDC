"""Tests for ByClawSyncAdapter — instantiation, hook methods, resync_all stub."""

from __future__ import annotations

import pytest


class TestByClawSyncAdapter:
    """Tests for ByClawSyncAdapter lifecycle and hook methods."""

    @pytest.fixture
    def adapter(self) -> object:
        """Create a ByClawSyncAdapter instance.

        Import is optional — gracefully skip if byclaw_sync module is not available.
        """
        try:
            from datacloud_platform.adapters.byclaw_sync import ByClawSyncAdapter

            return ByClawSyncAdapter()
        except ImportError:
            pytest.skip("byclaw_sync module not importable")

    def test_adapter_instantiated(self, adapter: object) -> None:
        """Adapter can be instantiated successfully."""
        assert adapter is not None

    def test_on_create_no_raise(self, adapter: object) -> None:
        """on_create does not raise exceptions."""
        adapter.on_create(  # type: ignore[attr-defined]
            "OBJECT",
            {
                "resourceCode": "obj1",
                "resourceName": "Test Object",
                "ontologyBaseCode": "default",
            },
        )

    def test_on_update_no_raise(self, adapter: object) -> None:
        """on_update does not raise exceptions."""
        adapter.on_update(  # type: ignore[attr-defined]
            "OBJECT",
            {
                "resourceCode": "obj1",
                "resourceName": "Updated Object",
                "ontologyBaseCode": "default",
            },
        )

    def test_on_delete_no_raise(self, adapter: object) -> None:
        """on_delete does not raise exceptions."""
        adapter.on_delete(  # type: ignore[attr-defined]
            "OBJECT", "obj1", "default"
        )

    @pytest.mark.asyncio
    async def test_resync_all_returns_stub_counts(self, adapter: object) -> None:
        """resync_all returns stub counts: {created: 0, updated: 0, deleted: 0}."""
        result = await adapter.resync_all("test-base")  # type: ignore[attr-defined]
        assert isinstance(result, dict)
        assert result["created"] == 0
        assert result["updated"] == 0
        assert result["deleted"] == 0

    @pytest.mark.asyncio
    async def test_resync_all_accepts_base_id(self, adapter: object) -> None:
        """resync_all accepts any base_id string."""
        result = await adapter.resync_all("my-custom-base")  # type: ignore[attr-defined]
        assert result == {"created": 0, "updated": 0, "deleted": 0}

"""CRUD sync hook protocol — called after every C/U/D operation to sync resources to ByClaw."""

from __future__ import annotations

from typing import Any, Protocol


class ResourceSyncHook(Protocol):
    """Post-CRUD callback for syncing resources to ByClaw resource table.

    All methods are fire-and-forget — the implementation is responsible for
    async execution. Failures must not propagate to the caller.
    """

    def on_create(self, resource_type: str, payload: dict[str, Any]) -> None: ...
    def on_update(self, resource_type: str, payload: dict[str, Any]) -> None: ...
    def on_delete(
        self, resource_type: str, resource_code: str, base_code: str
    ) -> None: ...

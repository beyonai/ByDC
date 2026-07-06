"""ByClawSyncAdapter — syncs ontology resources to ByClaw via service discovery."""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

import httpx

from datacloud_platform.adapters.data_adapter._hooks import ResourceSyncHook

logger = logging.getLogger(__name__)

# Resource type constants
RESOURCE_TYPE_ONTOLOGY_BASE = "ONTOLOGY_BASE"
RESOURCE_TYPE_SCENE = "SCENE"
RESOURCE_TYPE_VIEW = "VIEW"
RESOURCE_TYPE_OBJECT = "OBJECT"
RESOURCE_TYPE_ACTION = "ACTION"
RESOURCE_TYPE_RELATION = "RELATION"
RESOURCE_TYPE_DATASOURCE = "DATASOURCE"


class ByClawSyncAdapter(ResourceSyncHook):
    """Sync ontology resources to ByClaw resource table via service discovery.

    Uses asyncio.create_task for fire-and-forget async execution.
    ByClaw API is idempotent on resourceCode — repeated create = update.
    """

    def __init__(self, beyond_token: str | None = None) -> None:
        self._token: str = beyond_token or os.getenv("BEYOND_TOKEN") or ""
        self._system_code = "byclaw-datacloud"
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(5.0))
        self._discovery: Any = None  # DiscoveryClient | False | None

    def _ensure_discovery(self) -> None:
        """Lazy-init the DiscoveryClient."""
        if self._discovery is not None:
            return
        try:
            from by_framework.core.discovery import DiscoveryClient

            self._discovery = DiscoveryClient(cache_interval=30)
        except ImportError:
            logger.warning("by_framework.core.discovery not available — sync disabled")
            self._discovery = False

    @staticmethod
    def _fire_and_forget(coro: object) -> None:
        """Schedule a coroutine as a fire-and-forget task if an event loop is running.

        Gracefully no-ops when called outside an async context (e.g. tests).
        """
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(coro)  # type: ignore[arg-type]
        except RuntimeError:
            logger.debug("No running event loop — sync skipped")

    def on_create(self, resource_type: str, payload: dict[str, Any]) -> None:
        """Fire-and-forget create/update sync to ByClaw."""
        self._fire_and_forget(self._post_async("/v1/ontology/resource/create", payload))

    def on_update(self, resource_type: str, payload: dict[str, Any]) -> None:
        """Fire-and-forget update sync to ByClaw (idempotent via resourceCode)."""
        self._fire_and_forget(self._post_async("/v1/ontology/resource/create", payload))

    def on_delete(self, resource_type: str, resource_code: str, base_code: str) -> None:
        """Fire-and-forget delete sync to ByClaw."""
        payload: dict[str, Any] = {
            "systemCode": self._system_code,
            "resourceBizType": resource_type,
            "resourceCode": resource_code,
            "ontologyBaseCode": base_code,
        }
        self._fire_and_forget(self._post_async("/v1/ontology/resource/delete", payload))

    async def resync_all(self, base_id: str) -> dict[str, int]:
        """Full resync of all resources under a base to ByClaw.

        Returns dict with counts: {"created": N, "updated": N, "deleted": N}.
        Currently a stub — implementation requires scanning EntityStore.
        """
        logger.info("resync_all called for base_id=%s (not yet implemented)", base_id)
        return {"created": 0, "updated": 0, "deleted": 0}

    async def _post_async(self, path: str, payload: dict[str, Any]) -> None:
        """Post payload to ByClaw open API via service discovery."""
        self._ensure_discovery()
        if not self._discovery:
            return
        try:
            base_url = await self._discover()
            url = f"{base_url}/byaiService/open/api{path}"
            resp = await self._client.post(
                url,
                json=payload,
                headers={
                    "Beyond-Token": self._token,
                    "Content-Type": "application/json",
                },
            )
            resp.raise_for_status()
        except Exception:
            logger.warning(
                "ByClaw sync failed: %s resourceCode=%s",
                path,
                payload.get("resourceCode", ""),
            )

    async def _discover(self) -> str:
        """Discover ByClaw service URL from Redis."""
        if self._discovery is False:
            return ""
        # discovery_client.get_service("byclaw-datacloud") → (host, port)
        try:
            instance = await self._discovery.get_service("byclaw-datacloud")
            return f"http://{instance[0]}:{instance[1]}"
        except Exception:
            logger.warning("Failed to discover byclaw-datacloud service")
            return ""

"""ByClawSyncAdapter — syncs ontology resources to ByClaw via service discovery."""

from __future__ import annotations

import asyncio
import logging
import os
from contextvars import ContextVar
from typing import Any

import httpx

from datacloud_platform.adapters.data_adapter._hooks import ResourceSyncHook

logger = logging.getLogger(__name__)

# Per-request hook context carried automatically across async Task boundaries.
# Routes set ``hook_ctx.set({"beyond_token": header_value})``;
# _post_async reads it as an override for the process-level BEYOND_TOKEN env var.
# Keys: beyond_token (str | None)
hook_ctx: ContextVar[dict[str, Any]] = ContextVar("hook_ctx", default={})

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

    The Java API requires an ONTOLOGY_BASE parent resource to exist before
    any child resource (SCENE/OBJECT/VIEW/etc.) can be created.  This adapter
    automatically creates the ONTOLOGY_BASE resource on first use per base.
    """

    def __init__(self, beyond_token: str | None = None) -> None:
        from datacloud_platform.constants import DEFAULT_SYSTEM_CODE

        self._token: str = beyond_token or os.getenv("BEYOND_TOKEN") or ""
        self._system_code = DEFAULT_SYSTEM_CODE
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(5.0))
        self._discovery: Any = None  # DiscoveryClient | False | None
        self._synced_bases: set[str] = set()  # bases already synced to ByClaw

    def _ensure_discovery(self) -> None:
        """Lazy-init the DiscoveryClient.

        Initializes the global by_framework Redis client from
        DATACLOUD_GATEWAY_REDIS_* (or REDIS_*) env vars before creating
        the DiscoveryClient, so that service discovery connects to the
        configured Redis instead of defaulting to localhost.
        """
        if self._discovery is not None:
            return
        try:
            from by_framework.common.redis_client import init_redis  # noqa: PLC0415
            from by_framework.core.discovery import DiscoveryClient  # noqa: PLC0415

            init_redis(
                host=os.getenv(
                    "DATACLOUD_GATEWAY_REDIS_HOST", os.getenv("REDIS_HOST", "localhost")
                ),
                port=int(
                    os.getenv(
                        "DATACLOUD_GATEWAY_REDIS_PORT", os.getenv("REDIS_PORT", "6379")
                    )
                ),
                db=int(
                    os.getenv(
                        "DATACLOUD_GATEWAY_REDIS_DB", os.getenv("REDIS_DATABASE", "0")
                    )
                ),
                password=os.getenv(
                    "DATACLOUD_GATEWAY_REDIS_PASSWORD", os.getenv("REDIS_PASSWORD")
                )
                or None,
                username=os.getenv(
                    "DATACLOUD_GATEWAY_REDIS_USERNAME", os.getenv("REDIS_USERNAME")
                )
                or None,
            )
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
            logger.warning("No running event loop — ByClaw sync skipped")

    def on_create(self, resource_type: str, payload: dict[str, Any]) -> None:
        """Fire-and-forget create/update sync to ByClaw.

        Ensures the ONTOLOGY_BASE parent resource exists before syncing
        child resources (SCENE, OBJECT, VIEW, etc.).
        """
        self._fire_and_forget(self._sync_with_base(payload))

    def on_update(self, resource_type: str, payload: dict[str, Any]) -> None:
        """Fire-and-forget update sync to ByClaw (idempotent via resourceCode).

        Ensures the ONTOLOGY_BASE parent resource exists before syncing
        child resources (SCENE, OBJECT, VIEW, etc.).
        """
        self._fire_and_forget(self._sync_with_base(payload))

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

    async def _sync_with_base(self, payload: dict[str, Any]) -> None:
        """Ensure ONTOLOGY_BASE parent exists, then sync the child resource.

        The Java API requires an ONTOLOGY_BASE parent resource to exist
        before any SCENE/OBJECT/VIEW child can be created.  This method
        creates the base resource first (idempotent), then the child.
        """
        resource_code = payload.get("resourceCode", "?")
        resource_type = payload.get("resourceBizType", "?")
        await self._ensure_base_async(payload)
        try:
            await self._post_async("/v1/ontology/resource/create", payload)
        except Exception:
            logger.warning(
                "ByClaw sync failed: type=%s code=%s",
                resource_type,
                resource_code,
                exc_info=True,
            )

    async def _ensure_base_async(self, payload: dict[str, Any]) -> None:
        """Ensure the ONTOLOGY_BASE resource exists in ByClaw for this payload.

        Only creates the base resource once per base_code per adapter lifetime.
        The ByClaw API is idempotent on resourceCode, so duplicate calls are
        harmless — the ``_synced_bases`` set is an optimisation, not a
        correctness requirement.
        """
        base_code: str = payload.get("ontologyBaseCode", "")
        if not base_code or base_code in self._synced_bases:
            return
        self._synced_bases.add(base_code)
        base_payload: dict[str, Any] = {
            "systemCode": self._system_code,
            "resourceBizType": "ONTOLOGY_BASE",
            "resourceCode": base_code,
            "resourceName": base_code,
            "resourceDesc": "",
            "ontologyBaseCode": "",
            "ownerType": "enterprise",
        }
        await self._post_async("/v1/ontology/resource/create", base_payload)

    async def _post_async(self, path: str, payload: dict[str, Any]) -> None:
        """Post payload to ByClaw open API via service discovery."""
        ctx = hook_ctx.get()
        beyond_token: str = ctx.get("beyond_token") or self._token
        self._ensure_discovery()
        if not self._discovery:
            logger.warning(
                "ByClaw sync skipped (discovery unavailable): %s type=%s code=%s",
                path,
                payload.get("resourceBizType", "?"),
                payload.get("resourceCode", "?"),
            )
            return
        try:
            base_url = await self._discover()
            if not base_url:
                logger.warning(
                    "ByClaw sync skipped (no service instance): %s type=%s code=%s",
                    path,
                    payload.get("resourceBizType", "?"),
                    payload.get("resourceCode", "?"),
                )
                return
            url = f"{base_url}/byaiService/open/api{path}"
            resp = await self._client.post(
                url,
                json=payload,
                headers={
                    "Beyond-Token": beyond_token,
                    "Content-Type": "application/json",
                },
            )
            resp.raise_for_status()
        except Exception:
            logger.warning(
                "ByClaw sync HTTP error: %s type=%s code=%s",
                path,
                payload.get("resourceBizType", "?"),
                payload.get("resourceCode", "?"),
                exc_info=True,
            )

    async def _discover(self) -> str:
        """Discover ByClaw service URL from Redis."""
        if self._discovery is False:
            return ""
        service_name = os.getenv("BE_DOMAINNAME", "ByaiService").strip()
        try:
            instance = await self._discovery.discover(service_name)
            if instance is None:
                logger.warning("No %s instance found", service_name)
                return ""
            return f"http://{instance.host}:{instance.port}"
        except Exception:
            logger.warning("Failed to discover %s service", service_name)
            return ""

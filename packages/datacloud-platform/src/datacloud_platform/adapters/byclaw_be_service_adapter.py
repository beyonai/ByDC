"""Service-discovery adapter for ByClaw BE operational APIs."""

from __future__ import annotations

import inspect
import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx

from datacloud_platform.backends.byclaw_be_service import ByClawBeServiceError
from datacloud_platform.redis_client import create_async_redis_client
from datacloud_platform.services.kb_document_reader import (
    _build_discovered_url,
    _build_headers,
)

SAVE_OR_UPDATE_OBJECT_FILES_PATH = (
    "/byaiService/devloop/operation/saveOrUpdateObjectFiles"
)
_TIMEOUT_SECONDS = 30.0
PostJson = Callable[[str, dict[str, Any], dict[str, str]], object]


@dataclass(frozen=True, slots=True)
class ServiceDiscoveryByClawBeServiceBackend:
    """Call ByClaw BE through the runtime service registry."""

    post_json: PostJson | None = None

    async def save_or_update_object_files(
        self, *, object_files: list[dict[str, Any]]
    ) -> None:
        if not object_files:
            return
        payload = {"objectFiles": object_files}
        headers = _build_headers()
        if self.post_json is not None:
            response = self.post_json(
                SAVE_OR_UPDATE_OBJECT_FILES_PATH, payload, headers
            )
            raw = await response if inspect.isawaitable(response) else response
        else:
            raw = await self._post_by_discovery(payload=payload, headers=headers)
        _validate_response(raw)

    async def _post_by_discovery(
        self, *, payload: dict[str, Any], headers: dict[str, str]
    ) -> Any:
        service_name = os.getenv("BE_DOMAINNAME", "ByaiService").strip()
        try:
            from by_framework.core.discovery import DiscoveryClient  # noqa: PLC0415
        except ImportError as exc:
            raise ByClawBeServiceError(
                "ByClaw BE service discovery dependencies are unavailable"
            ) from exc
        redis_client = create_async_redis_client()
        discovery_client = DiscoveryClient(redis_client=redis_client, cache_interval=5)
        try:
            instance = await discovery_client.discover(
                service_name, health_threshold_ms=-1
            )
            if not instance:
                raise ByClawBeServiceError(
                    f"No available instances for service: {service_name}"
                )
            url = _build_discovered_url(instance, SAVE_OR_UPDATE_OBJECT_FILES_PATH)
            async with httpx.AsyncClient(
                timeout=_TIMEOUT_SECONDS, headers=headers
            ) as client:
                response = await client.post(url, json=payload)
                try:
                    raw: Any = response.json()
                except ValueError as exc:
                    raise ByClawBeServiceError(
                        "saveOrUpdateObjectFiles response must be JSON"
                    ) from exc
                if not response.is_success:
                    raise ByClawBeServiceError(
                        f"saveOrUpdateObjectFiles returned HTTP {response.status_code}: {raw}"
                    )
                return raw
        except httpx.HTTPError as exc:
            raise ByClawBeServiceError(
                f"saveOrUpdateObjectFiles HTTP error: {exc}"
            ) from exc
        finally:
            await discovery_client.close()
            await redis_client.aclose()


def _validate_response(raw: Any) -> None:
    if not isinstance(raw, dict):
        raise ByClawBeServiceError("saveOrUpdateObjectFiles response must be an object")
    code = raw.get("code", raw.get("resultCode", 0))
    if str(code) not in {"0", "200"}:
        raise ByClawBeServiceError(str(raw.get("msg") or raw.get("resultMsg") or raw))

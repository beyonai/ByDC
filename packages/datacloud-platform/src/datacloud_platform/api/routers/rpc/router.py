"""RPC-like unified router for datacloud-platform.

Pattern: POST /api/v1/rpc/{service}/{method}
Dispatch via handler lookup table — one route, many methods.
"""

from __future__ import annotations

import inspect
import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from starlette import status

from datacloud_platform.api.deps import extract_beyond_token
from datacloud_platform.constants import DEFAULT_BASE_ID
from datacloud_platform.models.common import ok

if TYPE_CHECKING:
    from datacloud_platform.platform import DatacloudPlatform

logger = logging.getLogger(__name__)

# ── HTTP status codes ────────────────────────────────────────────────────────

HTTP_200 = status.HTTP_200_OK
HTTP_400 = status.HTTP_400_BAD_REQUEST
HTTP_403 = status.HTTP_403_FORBIDDEN
HTTP_404 = status.HTTP_404_NOT_FOUND
HTTP_409 = status.HTTP_409_CONFLICT
HTTP_500 = status.HTTP_500_INTERNAL_SERVER_ERROR
HTTP_501 = status.HTTP_501_NOT_IMPLEMENTED

# ── Handler signature ────────────────────────────────────────────────────────

RpcHandler = Callable[..., Any]

# ── Exception → (http_status, err_code) mapping ──────────────────────────────

_EXCEPTION_MAP: dict[type[Exception], tuple[int, str]] = {
    KeyError: (HTTP_404, "not_found"),
    ValueError: (HTTP_400, "invalid_params"),
    PermissionError: (HTTP_403, "permission_denied"),
    NotImplementedError: (HTTP_501, "not_implemented"),
}


def _wrap_error(exc: Exception) -> Any:
    """Map a Python exception to a unified ok() error response."""
    status_code, err_code = _EXCEPTION_MAP.get(type(exc), (HTTP_500, "internal_error"))
    return ok(code=status_code, message=str(exc) or err_code, data=None)


# ── Service → {method → handler} lookup ──────────────────────────────────────


def _build_registry() -> dict[str, dict[str, RpcHandler]]:
    """Build a lookup table: service_name → {method_name → handler}.

    Each handler module declares a module-level ``REGISTRY`` dict.
    """
    from datacloud_platform.api.routers.rpc.handlers import (
        action as action_handlers,
        datasource as datasource_handlers,
        object_type,
        ontology,
        ontology_build,
        query as query_handlers,
        relation as relation_handlers,
        scene,
        search as search_handlers,
        skills as skills_handlers,
        term as term_handlers,
        term_options,
        view as view_handlers,
        workspace as workspace_handlers,
    )

    return {
        "ontology": ontology.REGISTRY,
        "scene": scene.REGISTRY,
        "objectType": object_type.REGISTRY,
        "view": view_handlers.REGISTRY,
        "relation": relation_handlers.REGISTRY,
        "datasource": datasource_handlers.REGISTRY,
        "action": action_handlers.REGISTRY,
        "search": search_handlers.REGISTRY,
        "graph": search_handlers.GRAPH_REGISTRY,
        "termLibrary": term_handlers.LIBRARY_REGISTRY,
        "termType": term_handlers.TYPE_REGISTRY,
        "term": term_handlers.TERM_REGISTRY,
        "termRelation": term_handlers.RELATION_REGISTRY,
        "termName": term_handlers.NAME_REGISTRY,
        "termKnowledge": term_handlers.KNOWLEDGE_REGISTRY,
        "domain": term_handlers.DOMAIN_REGISTRY,
        "termOptions": term_options.REGISTRY,
        "query": query_handlers.REGISTRY,
        "skills": skills_handlers.REGISTRY,
        "ontologyBuild": ontology_build.REGISTRY,
        "workspace": workspace_handlers.REGISTRY,
    }


# ── Factory ──────────────────────────────────────────────────────────────────


def create_rpc_router(platform: DatacloudPlatform) -> APIRouter:
    """Create the unified RPC-like APIRouter.

    Returns:
        APIRouter with prefix ``/api/v1/rpc``, a single dispatch route
        ``/{service}/{method}``, plus special routes for multipart file upload.
    """
    router = APIRouter(prefix="/api/v1/rpc")
    registry = _build_registry()

    @router.post("/{service}/{method}")
    async def rpc_dispatch(
        service: str,
        method: str,
        body: dict[str, Any],
        request: Request,
        _bt: None = Depends(extract_beyond_token),
    ) -> Any:
        request.state.rpc_service = service
        request.state.rpc_method = method
        logger.info("RPC dispatch: %s/%s", service, method)

        svc_registry = registry.get(service)
        if svc_registry is None:
            return ok(code=HTTP_404, message=f"Unknown service: {service}", data=None)

        handler = svc_registry.get(method)
        if handler is None:
            return ok(
                code=HTTP_404,
                message=f"Unknown method: {service}/{method}",
                data=None,
            )

        try:
            params = body.get("params", {})

            # ── system_code → base_id compatibility ────────────────────────
            # All handlers accept ``base_id``; ``system_code`` is an alias that
            # takes priority.  The two are mutually exclusive — passing both
            # returns 400.  This mapping is applied at the dispatch layer so
            # individual handlers never need to think about ``system_code``.
            system_code = params.get("system_code")
            if system_code is not None:
                if "base_id" in params:
                    return ok(
                        code=HTTP_400,
                        message="system_code and base_id are mutually exclusive",
                        data=None,
                    )
                params["base_id"] = system_code

            result = handler(platform, params, request)
            if inspect.isawaitable(result):
                result = await result
            return result
        except tuple(_EXCEPTION_MAP) as e:
            logger.warning(
                "RPC %s/%s failed: %s - %s", service, method, type(e).__name__, e
            )
            return _wrap_error(e)
        except Exception:
            logger.exception("RPC handler %s/%s unexpected error", service, method)
            return ok(code=HTTP_500, message="Internal error", data=None)

    # ── Special: multipart file upload (OWL import) ───────────────────────
    _register_import_routes(router, platform)

    return router


# ── Multipart file upload routes (outside wildcard dispatch) ─────────────────


def _register_import_routes(router: APIRouter, platform: DatacloudPlatform) -> None:
    """Register OWL import endpoints as dedicated routes.

    Multipart file upload cannot pass through the generic ``body: dict[str, Any]``
    dispatch — ``UploadFile`` requires ``multipart/form-data``, not JSON.
    """

    @router.post("/import/importOwl")
    async def rpc_import_owl(
        file: UploadFile = File(...),  # noqa: B008
        base_id: str = Form(DEFAULT_BASE_ID),
        _bt: None = Depends(extract_beyond_token),
    ) -> Any:
        try:
            zip_bytes = await file.read()
            result = platform.import_owl(base_id, "", zip_bytes)
            return ok(data=result, message="imported")
        except tuple(_EXCEPTION_MAP) as e:
            return _wrap_error(e)

    @router.post("/import/importOwlToScene")
    async def rpc_import_owl_to_scene(
        file: UploadFile = File(...),  # noqa: B008
        base_id: str = Form(...),
        scene_id: str = Form(...),
        _bt: None = Depends(extract_beyond_token),
    ) -> Any:
        try:
            zip_bytes = await file.read()
            result = platform.import_owl(base_id, scene_id, zip_bytes)
            return ok(data=result, message="imported")
        except tuple(_EXCEPTION_MAP) as e:
            return _wrap_error(e)

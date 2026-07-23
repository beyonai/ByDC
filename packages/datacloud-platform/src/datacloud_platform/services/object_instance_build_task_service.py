"""Request service for asynchronous object instance build jobs.

The build queue is the ``ontology_doc_fragment`` table itself.  This module does
not create or persist a separate task table.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from types import TracebackType
from typing import Any, Protocol
from uuid import uuid4

from datacloud_platform.adapters.byclaw_sync import hook_ctx

logger = logging.getLogger(__name__)

_SERVICE_ATTR = "_object_instance_build_task_service"


@dataclass(frozen=True)
class SubmitObjectInstanceBuildTaskRequest:
    """Input accepted by the Platform build service."""

    instance_ids: list[str]
    batch_size: int
    operator: str
    beyond_token: str = ""


@dataclass(frozen=True)
class ObjectInstanceBuildRunRequest:
    """Runtime request used by the object instance build orchestrator."""

    request_id: str
    instance_ids: list[str]
    batch_size: int
    operator: str
    beyond_token: str = ""


@dataclass(frozen=True)
class ObjectInstanceBuildAccepted:
    """Accepted response for an asynchronous object instance build request."""

    instance_ids: list[str]
    batch_size: int
    operator: str
    status: str = "accepted"

    def to_dict(self) -> dict[str, object]:
        """Serialize the accepted response for RPC callers."""
        return {
            "instance_ids": list(self.instance_ids),
            "batch_size": self.batch_size,
            "created_by": self.operator,
            "status": self.status,
        }


class ObjectInstanceBuildTaskRunner(Protocol):
    """Runner protocol for object instance build work."""

    async def submit(self, request: ObjectInstanceBuildRunRequest) -> None: ...


class InlineObjectInstanceBuildTaskRunner:
    """Run object instance build work in the current async flow."""

    def __init__(self, *, orchestrator: object) -> None:
        self._orchestrator = orchestrator

    async def submit(self, request: ObjectInstanceBuildRunRequest) -> None:
        await self._orchestrator.run(request)  # type: ignore[attr-defined]


class ObjectInstanceBuildTaskService:
    """Application service for object instance build request lifecycle."""

    def __init__(self, *, task_runner: ObjectInstanceBuildTaskRunner) -> None:
        self._task_runner = task_runner

    def accept(
        self,
        request: SubmitObjectInstanceBuildTaskRequest,
    ) -> tuple[ObjectInstanceBuildAccepted, ObjectInstanceBuildRunRequest]:
        """Validate a request and return accepted metadata plus runtime input."""
        instance_ids = _normalize_instance_ids(request.instance_ids)
        if not request.operator.strip():
            raise ValueError("operator is required")
        if request.batch_size < 1 or request.batch_size > 100:
            raise ValueError("batch_size must be between 1 and 100")

        accepted = ObjectInstanceBuildAccepted(
            instance_ids=instance_ids,
            batch_size=request.batch_size,
            operator=request.operator,
        )
        run_request = ObjectInstanceBuildRunRequest(
            request_id=str(uuid4()),
            instance_ids=instance_ids,
            batch_size=request.batch_size,
            operator=request.operator,
            beyond_token=request.beyond_token,
        )
        return accepted, run_request

    async def submit(
        self,
        request: SubmitObjectInstanceBuildTaskRequest,
    ) -> ObjectInstanceBuildAccepted:
        """Validate and run a build request."""
        accepted, run_request = self.accept(request)
        await self.run(run_request)
        return accepted

    async def run(self, request: ObjectInstanceBuildRunRequest) -> None:
        """Run a previously accepted build request with restored request context."""
        with _ObjectInstanceBuildRuntimeContext(request):
            await self._task_runner.submit(request)

    def get_task(self, task_id: str) -> None:
        """Task table queries are intentionally unsupported."""
        raise NotImplementedError(
            "getObjectInstanceBuildTask is no longer supported; "
            "check ontology_doc_fragment.status and service logs instead"
        )


class _ObjectInstanceBuildRuntimeContext:
    def __init__(self, request: ObjectInstanceBuildRunRequest) -> None:
        self._request = request
        self._hook_token: Any = None
        self._invocation_ctx: Any = None
        self._userfs_token: Any = None
        self._reset_userfs_headers: Any = None

    def __enter__(self) -> _ObjectInstanceBuildRuntimeContext:
        self._hook_token = hook_ctx.set({"beyond_token": self._request.beyond_token})
        self._enter_invocation_context()
        self._enter_userfs_context()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._userfs_token is not None and self._reset_userfs_headers is not None:
            self._reset_userfs_headers(self._userfs_token)
        if self._invocation_ctx is not None:
            self._invocation_ctx.__exit__(exc_type, exc, tb)
        if self._hook_token is not None:
            hook_ctx.reset(self._hook_token)

    def _enter_invocation_context(self) -> None:
        try:
            from datacloud_data_sdk.context import InvocationContext
        except ImportError:
            logger.debug("datacloud_data_sdk InvocationContext unavailable")
            return
        self._invocation_ctx = InvocationContext(
            user_id=self._request.operator,
            token=self._request.beyond_token,
        )
        self._invocation_ctx.__enter__()

    def _enter_userfs_context(self) -> None:
        try:
            from byclaw_userfs_storage import (
                reset_byclaw_userfs_headers,
                set_byclaw_userfs_headers,
            )
        except ImportError:
            logger.debug("byclaw_userfs_storage context unavailable")
            return
        self._reset_userfs_headers = reset_byclaw_userfs_headers
        self._userfs_token = set_byclaw_userfs_headers(
            {"beyond-token": self._request.beyond_token}
        )


def _normalize_instance_ids(instance_ids: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw_id in instance_ids:
        item = str(raw_id or "").strip()
        if not item:
            raise ValueError("instance_ids must not contain empty value")
        if item in seen:
            continue
        normalized.append(item)
        seen.add(item)
    return normalized


def get_object_instance_build_task_service(
    platform: object,
) -> ObjectInstanceBuildTaskService:
    """Return the per-platform object instance build service."""
    existing = getattr(platform, _SERVICE_ATTR, None)
    if isinstance(existing, ObjectInstanceBuildTaskService):
        return existing

    from datacloud_platform.services.object_instance_build_orchestrator import (
        ObjectInstanceBuildOrchestrator,
    )

    orchestrator = ObjectInstanceBuildOrchestrator(
        platform=platform,  # type: ignore[arg-type]
    )
    service = ObjectInstanceBuildTaskService(
        task_runner=InlineObjectInstanceBuildTaskRunner(orchestrator=orchestrator),
    )
    setattr(platform, _SERVICE_ATTR, service)
    return service

"""Task service for asynchronous object instance build jobs."""

from __future__ import annotations

import asyncio
import copy
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from threading import Lock
from typing import Any, Literal, Protocol, cast
from uuid import uuid4

logger = logging.getLogger(__name__)

TaskStatus = Literal["queued", "running", "succeeded", "failed", "partial_failed"]
_SERVICE_ATTR = "_object_instance_build_task_service"


@dataclass(frozen=True)
class SubmitObjectInstanceBuildTaskRequest:
    """Input accepted by the Platform task service."""

    instance_ids: list[str]
    batch_size: int
    operator: str


@dataclass
class ObjectInstanceBuildTask:
    """Runtime state for one object instance build job."""

    task_id: str
    instance_ids: list[str]
    batch_size: int
    operator: str
    status: TaskStatus = "queued"
    total_count: int = 0
    success_count: int = 0
    failed_count: int = 0
    error_message: str = ""
    errors: list[dict[str, Any]] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, object]:
        """Serialize task state for RPC responses."""
        return {
            "task_id": self.task_id,
            "instance_ids": list(self.instance_ids),
            "batch_size": self.batch_size,
            "created_by": self.operator,
            "status": self.status,
            "total_count": self.total_count,
            "success_count": self.success_count,
            "failed_count": self.failed_count,
            "error_message": self.error_message,
            "errors": list(self.errors),
            "created_time": self.created_at.isoformat(),
            "updated_time": self.updated_at.isoformat(),
        }


class ObjectInstanceBuildTaskRepository(Protocol):
    """Repository protocol used by task service and orchestrator."""

    def create(
        self,
        *,
        instance_ids: list[str],
        batch_size: int,
        operator: str,
    ) -> ObjectInstanceBuildTask: ...

    def get(self, task_id: str) -> ObjectInstanceBuildTask: ...

    def update(
        self,
        task_id: str,
        *,
        status: TaskStatus | None = None,
        total_count: int | None = None,
        success_count: int | None = None,
        failed_count: int | None = None,
        error_message: str | None = None,
        errors: list[dict[str, Any]] | None = None,
    ) -> ObjectInstanceBuildTask: ...


class ObjectInstanceBuildTaskAdapter(Protocol):
    """Storage adapter protocol for SQL-backed task repository."""

    def create(self, record: dict[str, Any]) -> dict[str, Any]: ...

    def get(self, task_id: str) -> dict[str, Any] | None: ...

    def update(self, task_id: str, updates: dict[str, Any]) -> dict[str, Any]: ...


class InMemoryObjectInstanceBuildTaskRepository:
    """In-process task repository for Platform async job state."""

    def __init__(self) -> None:
        self._tasks: dict[str, ObjectInstanceBuildTask] = {}
        self._lock = Lock()

    def create(
        self,
        *,
        instance_ids: list[str],
        batch_size: int,
        operator: str,
    ) -> ObjectInstanceBuildTask:
        now = datetime.now(UTC)
        task = ObjectInstanceBuildTask(
            task_id=str(uuid4()),
            instance_ids=list(instance_ids),
            batch_size=batch_size,
            operator=operator,
            created_at=now,
            updated_at=now,
        )
        with self._lock:
            self._tasks[task.task_id] = task
        return copy.deepcopy(task)

    def get(self, task_id: str) -> ObjectInstanceBuildTask:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                raise KeyError(f"object instance build task not found: {task_id}")
            return copy.deepcopy(task)

    def update(
        self,
        task_id: str,
        *,
        status: TaskStatus | None = None,
        total_count: int | None = None,
        success_count: int | None = None,
        failed_count: int | None = None,
        error_message: str | None = None,
        errors: list[dict[str, Any]] | None = None,
    ) -> ObjectInstanceBuildTask:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                raise KeyError(f"object instance build task not found: {task_id}")
            if status is not None:
                task.status = status
            if total_count is not None:
                task.total_count = total_count
            if success_count is not None:
                task.success_count = success_count
            if failed_count is not None:
                task.failed_count = failed_count
            if error_message is not None:
                task.error_message = error_message
            if errors is not None:
                task.errors = list(errors)
            task.updated_at = datetime.now(UTC)
            return copy.deepcopy(task)


class SqlObjectInstanceBuildTaskRepository:
    """Task repository backed by object_instance_build_task table."""

    def __init__(self, adapter: ObjectInstanceBuildTaskAdapter | None = None) -> None:
        if adapter is None:
            from datacloud_platform.adapters.data_adapter._object_instance_build_task import (
                ObjectInstanceBuildTaskAdapter as SqlTaskAdapter,
            )

            adapter = SqlTaskAdapter()
        self._adapter = adapter

    def create(
        self,
        *,
        instance_ids: list[str],
        batch_size: int,
        operator: str,
    ) -> ObjectInstanceBuildTask:
        now = datetime.now(UTC)
        record = {
            "task_id": str(uuid4()),
            "status": "queued",
            "instance_ids": list(instance_ids),
            "batch_size": batch_size,
            "total_count": 0,
            "success_count": 0,
            "failed_count": 0,
            "error_message": "",
            "errors": [],
            "created_by": operator,
            "created_time": now,
            "updated_time": now,
        }
        return _task_from_record(self._adapter.create(record))

    def get(self, task_id: str) -> ObjectInstanceBuildTask:
        record = self._adapter.get(task_id)
        if record is None:
            raise KeyError(f"object instance build task not found: {task_id}")
        return _task_from_record(record)

    def update(
        self,
        task_id: str,
        *,
        status: TaskStatus | None = None,
        total_count: int | None = None,
        success_count: int | None = None,
        failed_count: int | None = None,
        error_message: str | None = None,
        errors: list[dict[str, Any]] | None = None,
    ) -> ObjectInstanceBuildTask:
        updates: dict[str, Any] = {}
        if status is not None:
            updates["status"] = status
        if total_count is not None:
            updates["total_count"] = total_count
        if success_count is not None:
            updates["success_count"] = success_count
        if failed_count is not None:
            updates["failed_count"] = failed_count
        if error_message is not None:
            updates["error_message"] = error_message
        if errors is not None:
            updates["errors"] = errors
        return _task_from_record(self._adapter.update(task_id, updates))


class ObjectInstanceBuildTaskRunner(Protocol):
    """Runner protocol for scheduling object instance build work."""

    async def submit(self, task_id: str) -> None: ...


class InlineObjectInstanceBuildTaskRunner:
    """Deterministic runner used by unit tests."""

    def __init__(self, *, orchestrator: object) -> None:
        self._orchestrator = orchestrator

    async def submit(self, task_id: str) -> None:
        await self._orchestrator.run(task_id)  # type: ignore[attr-defined]


class AsyncioObjectInstanceBuildTaskRunner:
    """Schedule object instance build jobs on the current event loop."""

    def __init__(self, *, orchestrator: object) -> None:
        self._orchestrator = orchestrator

    async def submit(self, task_id: str) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            await self._orchestrator.run(task_id)  # type: ignore[attr-defined]
            return
        loop.create_task(self._run(task_id))

    async def _run(self, task_id: str) -> None:
        try:
            await self._orchestrator.run(task_id)  # type: ignore[attr-defined]
        except Exception:
            logger.exception("object instance build task failed: %s", task_id)


class ObjectInstanceBuildTaskService:
    """Application service for object instance build task lifecycle."""

    def __init__(
        self,
        *,
        task_repository: ObjectInstanceBuildTaskRepository,
        task_runner: ObjectInstanceBuildTaskRunner,
    ) -> None:
        self._task_repository = task_repository
        self._task_runner = task_runner

    async def submit(
        self,
        request: SubmitObjectInstanceBuildTaskRequest,
    ) -> ObjectInstanceBuildTask:
        """Create a task and schedule execution."""
        instance_ids = _normalize_instance_ids(request.instance_ids)
        if not request.operator.strip():
            raise ValueError("operator is required")
        if request.batch_size < 1 or request.batch_size > 100:
            raise ValueError("batch_size must be between 1 and 100")

        accepted = self._task_repository.create(
            instance_ids=instance_ids,
            batch_size=request.batch_size,
            operator=request.operator,
        )
        await self._task_runner.submit(accepted.task_id)
        return accepted

    def get_task(self, task_id: str) -> ObjectInstanceBuildTask:
        """Return current task state."""
        if not task_id.strip():
            raise ValueError("task_id is required")
        return self._task_repository.get(task_id)


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


def _task_from_record(record: dict[str, Any]) -> ObjectInstanceBuildTask:
    return ObjectInstanceBuildTask(
        task_id=str(record["task_id"]),
        instance_ids=[str(item) for item in record.get("instance_ids") or []],
        batch_size=int(record.get("batch_size") or 20),
        operator=str(record.get("created_by") or record.get("operator") or ""),
        status=_task_status(str(record.get("status") or "queued")),
        total_count=int(record.get("total_count") or 0),
        success_count=int(record.get("success_count") or 0),
        failed_count=int(record.get("failed_count") or 0),
        error_message=str(record.get("error_message") or ""),
        errors=list(record.get("errors") or []),
        created_at=_datetime_value(
            record.get("created_time") or record.get("created_at")
        ),
        updated_at=_datetime_value(
            record.get("updated_time") or record.get("updated_at")
        ),
    )


def _task_status(value: str) -> TaskStatus:
    if value in {"queued", "running", "succeeded", "failed", "partial_failed"}:
        return cast(TaskStatus, value)
    raise ValueError(f"unsupported task status: {value}")


def _datetime_value(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    if isinstance(value, str) and value:
        parsed = datetime.fromisoformat(value)
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
    return datetime.now(UTC)


def get_object_instance_build_task_service(
    platform: object,
) -> ObjectInstanceBuildTaskService:
    """Return the per-platform object instance build task service."""
    existing = getattr(platform, _SERVICE_ATTR, None)
    if isinstance(existing, ObjectInstanceBuildTaskService):
        return existing

    from datacloud_platform.services.object_instance_build_orchestrator import (
        ObjectInstanceBuildOrchestrator,
    )

    repository = SqlObjectInstanceBuildTaskRepository()
    orchestrator = ObjectInstanceBuildOrchestrator(
        platform=platform,  # type: ignore[arg-type]
        task_repository=repository,
    )
    service = ObjectInstanceBuildTaskService(
        task_repository=repository,
        task_runner=AsyncioObjectInstanceBuildTaskRunner(orchestrator=orchestrator),
    )
    setattr(platform, _SERVICE_ATTR, service)
    return service

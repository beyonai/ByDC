from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Mapping, cast

TaskStatus = Literal["success", "failed", "blocked"]
BlockedReason = Literal["missing_dependency"] | str | None


def _coerce_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        if isinstance(item, str):
            text = item.strip()
        else:
            text = str(item).strip()
        if text:
            result.append(text)
    return result


def _coerce_bool_dict(value: Any) -> dict[str, bool]:
    if not isinstance(value, Mapping):
        return {}
    result: dict[str, bool] = {}
    for key, flag in value.items():
        str_key = str(key).strip()
        if not str_key:
            continue
        result[str_key] = bool(flag)
    return result


def _coerce_str_dict(value: Any) -> dict[str, str]:
    if not isinstance(value, Mapping):
        return {}
    result: dict[str, str] = {}
    for key, raw_value in value.items():
        str_key = str(key).strip()
        if not str_key:
            continue
        result[str_key] = str(raw_value)
    return result


@dataclass(slots=True)
class PlanTask:
    todo_id: str
    goal: str
    required_tools: list[str] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)
    inputs_from: dict[str, str] = field(default_factory=dict)
    required_inputs: dict[str, bool] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "todo_id": self.todo_id,
            "goal": self.goal,
            "required_tools": list(self.required_tools),
            "depends_on": list(self.depends_on),
            "inputs_from": dict(self.inputs_from),
            "required_inputs": dict(self.required_inputs),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> PlanTask:
        todo_id = str(payload.get("todo_id") or "").strip()
        if not todo_id:
            raise ValueError("PlanTask requires todo_id")

        goal = str(payload.get("goal") or "").strip()
        required_tools = _coerce_str_list(payload.get("required_tools"))
        depends_on = _coerce_str_list(payload.get("depends_on"))
        inputs_from = _coerce_str_dict(payload.get("inputs_from"))
        required_inputs = _coerce_bool_dict(payload.get("required_inputs"))

        return cls(
            todo_id=todo_id,
            goal=goal,
            required_tools=required_tools,
            depends_on=depends_on,
            inputs_from=inputs_from,
            required_inputs=required_inputs,
        )


@dataclass(slots=True)
class ArtifactRef:
    todo_id: str
    path: str
    name: str
    mime: str | None = None
    size: int | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "todo_id": self.todo_id,
            "path": self.path,
            "name": self.name,
        }
        if self.mime:
            data["mime"] = self.mime
        if self.size is not None:
            data["size"] = self.size
        return data

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ArtifactRef:
        todo_id = str(payload.get("todo_id") or "").strip()
        path = str(payload.get("path") or "").strip()
        name = str(payload.get("name") or "").strip()
        if not todo_id or not path:
            raise ValueError("ArtifactRef requires todo_id and path")
        if not name:
            name = path.split("/")[-1]
        mime = payload.get("mime")
        size_value = payload.get("size")
        size: int | None = None
        if size_value is not None:
            try:
                size = int(size_value)
            except (TypeError, ValueError):
                size = None
        return cls(todo_id=todo_id, path=path, name=name, mime=str(mime) if mime else None, size=size)


@dataclass(slots=True)
class TaskError:
    code: str
    message: str
    tool: str | None = None
    trace_id: str | None = None
    remediation: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.tool:
            payload["tool"] = self.tool
        if self.trace_id:
            payload["trace_id"] = self.trace_id
        if self.remediation:
            payload["remediation"] = self.remediation
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> TaskError:
        code = str(payload.get("code") or "").strip()
        message = str(payload.get("message") or "").strip()
        if not code or not message:
            raise ValueError("TaskError requires code and message")
        tool = payload.get("tool")
        trace_id = payload.get("trace_id")
        remediation = payload.get("remediation")
        return cls(
            code=code,
            message=message,
            tool=str(tool).strip() or None if tool else None,
            trace_id=str(trace_id).strip() or None if trace_id else None,
            remediation=str(remediation).strip() or None if remediation else None,
        )


@dataclass(slots=True)
class TaskResult:
    todo_id: str
    status: TaskStatus
    result_meta: dict[str, Any] = field(default_factory=dict)
    artifact_refs: list[ArtifactRef] = field(default_factory=list)
    error_detail: TaskError | None = None
    blocked_by: BlockedReason = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "todo_id": self.todo_id,
            "status": self.status,
            "result_meta": dict(self.result_meta),
            "artifact_refs": [ref.to_dict() for ref in self.artifact_refs],
        }
        if self.error_detail:
            payload["error_detail"] = self.error_detail.to_dict()
        if self.blocked_by:
            payload["blocked_by"] = self.blocked_by
        return payload

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> TaskResult:
        todo_id = str(payload.get("todo_id") or "").strip()
        if not todo_id:
            raise ValueError("TaskResult requires todo_id")
        status_value = str(payload.get("status") or "").strip().lower()
        if status_value not in {"success", "failed", "blocked"}:
            raise ValueError(f"Unsupported task status: {status_value}")
        result_meta = (
            dict(payload.get("result_meta")) if isinstance(payload.get("result_meta"), Mapping) else {}
        )
        raw_refs = payload.get("artifact_refs") or []
        artifact_refs: list[ArtifactRef] = []
        if isinstance(raw_refs, list):
            for entry in raw_refs:
                if isinstance(entry, Mapping):
                    artifact_refs.append(ArtifactRef.from_dict(entry))
        error_detail = None
        raw_error = payload.get("error_detail")
        if isinstance(raw_error, Mapping):
            error_detail = TaskError.from_dict(raw_error)
        blocked_by_value = payload.get("blocked_by")
        blocked_by = str(blocked_by_value).strip() or None if blocked_by_value else None
        if blocked_by == "":
            blocked_by = None
        return cls(
            todo_id=todo_id,
            status=cast(TaskStatus, status_value),
            result_meta=result_meta,
            artifact_refs=artifact_refs,
            error_detail=error_detail,
            blocked_by=blocked_by,
        )

"""Data models for object instance build SDK."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ObjectInstanceFragment:
    """Fragment input belonging to one object instance build group."""

    fragment_id: str
    content: str
    origin_file: dict[str, Any]
    sort_key: int | str | None = None


@dataclass(frozen=True)
class ObjectInstanceBuildRequest:
    """Request consumed by the object instance build SDK."""

    instance_id: str
    origin_instance_id: str | None
    term_detail: dict[str, Any]
    object_schema: dict[str, Any]
    label_schema: dict[str, Any]
    source_content: str
    fragments: list[ObjectInstanceFragment]
    related_docs: dict[str, Any] = field(default_factory=dict)
    existing_content: str = ""
    object_template: str = ""
    template_constraints: str = ""


@dataclass(frozen=True)
class ObjectInstanceBuildResult:
    """Parsed object instance build result returned to Platform."""

    content: str
    labels: dict[str, Any] = field(default_factory=dict)
    file_description: str = ""
    confidence: float | None = None
    model_name: str | None = None
    diagnostics: dict[str, Any] = field(default_factory=dict)

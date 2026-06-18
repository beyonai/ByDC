"""Tests for Action execution error scenarios."""

from __future__ import annotations

from typing import Any

import pytest
from datacloud_platform import (
    DatacloudPlatform,
    OntologyBaseEntry,
    OntologyBaseRegistry,
)
from datacloud_platform.backends.presets import register_preset
from datacloud_platform.backends.registry import (
    register_backend_type,
    register_implementation,
)
from fakes import (
    FakeKnowledgeBackend,
    FakeOntologyBackend,
    FakeStorageBackend,
)


class PermissionDeniedError(Exception):
    """Raised when an Action execution is forbidden."""


class FailingExecutionBackend:
    """Execution backend that always raises PermissionDeniedError."""

    def __init__(self) -> None:
        self._executed: list[dict[str, Any]] = []

    def execute_action(  # type: ignore[override]
        self,
        _action: Any,
        context: Any,  # noqa: ARG002
        **_params: Any,
    ) -> Any:
        raise PermissionDeniedError("用户无权执行此 Action")

    def generate_action_tools(
        self,
        loader: Any,  # noqa: ARG002
        mounted_objects: list[str],  # noqa: ARG002
    ) -> list[dict[str, Any]]:
        return []


def test_execute_action_permission_denied() -> None:
    """platform.execute_action propagates PermissionDeniedError from backend."""
    onto = FakeOntologyBackend()
    know = FakeKnowledgeBackend()
    failing = FailingExecutionBackend()
    stor = FakeStorageBackend()

    register_backend_type("ontology", "fake-data")
    register_backend_type("knowledge", "fake-knowledge")
    register_backend_type("execution", "fake-exec")
    register_backend_type("storage", "fake-data")

    register_implementation("ontology", "fake-data", lambda: onto)
    register_implementation("knowledge", "fake-knowledge", lambda: know)
    register_implementation("execution", "fake-exec", lambda: failing)
    register_implementation("storage", "fake-data", lambda: stor)
    register_implementation("execution", "none", lambda: None)  # type: ignore[arg-type,return-value]
    register_implementation("storage", "none", lambda: None)  # type: ignore[arg-type,return-value]

    register_preset("LOCAL", {})

    registry = OntologyBaseRegistry()
    registry.register(
        OntologyBaseEntry(
            base_id="local-base",
            display_name="本地库",
            source_type="LOCAL",
        )
    )

    p = DatacloudPlatform(_base_registry=registry)
    with pytest.raises(PermissionDeniedError, match="用户无权执行此 Action"):
        p.execute_action("local-base", action=None, context=None)

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from datacloud_knowledge.object_instance_build import ObjectInstanceBuildResult
from datacloud_platform.api.routers.rpc.router import create_rpc_router
from datacloud_platform.constants import DEFAULT_BASE_ID
from datacloud_platform.services import (
    object_instance_build_orchestrator as orchestrator_module,
)
from datacloud_platform.services.object_action import (
    invoke_object_action,
    invoke_object_write_action,
)
from datacloud_platform.services.object_instance_build_orchestrator import (
    ObjectInstanceBuildOrchestrator,
)
from datacloud_platform.services.object_instance_build_task_service import (
    InMemoryObjectInstanceBuildTaskRepository,
    InlineObjectInstanceBuildTaskRunner,
    ObjectInstanceBuildTaskService,
    SqlObjectInstanceBuildTaskRepository,
    SubmitObjectInstanceBuildTaskRequest,
)


class FakeBuildKnowledgeClient:
    def __init__(self) -> None:
        self.requests: list[Any] = []

    async def build_object_instance(self, request: Any) -> ObjectInstanceBuildResult:
        self.requests.append(request)
        return ObjectInstanceBuildResult(
            content="# Agent\n\nBuilt content.",
            labels={"name": "Agent", "owner_type": "public"},
            file_description="Agent object instance",
            confidence=0.91,
        )


class FailingSecondBuildKnowledgeClient:
    def __init__(self) -> None:
        self.requests: list[Any] = []

    async def build_object_instance(self, request: Any) -> ObjectInstanceBuildResult:
        self.requests.append(request)
        if request.instance_id == "term-2":
            raise RuntimeError("LLM output exhausted retries")
        return ObjectInstanceBuildResult(
            content=f"# {request.instance_id}",
            labels={"name": request.instance_id, "owner_type": "public"},
            file_description="object instance",
        )


class FakeAcceptedTask:
    def __init__(self, *, status: str = "queued") -> None:
        self.task_id = "task-agent"
        self.status = status

    def to_dict(self) -> dict[str, object]:
        return {
            "task_id": self.task_id,
            "status": self.status,
            "total_count": 1,
            "success_count": 1 if self.status == "succeeded" else 0,
            "failed_count": 0,
        }


class FakeRpcTaskService:
    def __init__(self) -> None:
        self.submitted: Any | None = None

    async def submit(self, request: Any) -> FakeAcceptedTask:
        self.submitted = request
        return FakeAcceptedTask()

    def get_task(self, task_id: str) -> FakeAcceptedTask:
        assert task_id == "task-agent"
        return FakeAcceptedTask(status="succeeded")


class FakeBuildPlatform:
    def __init__(self, fragments: list[dict[str, Any]]) -> None:
        self.fragments = fragments
        self.list_calls: list[dict[str, Any]] = []
        self.term_calls: list[dict[str, Any]] = []
        self.list_for_build_calls: list[dict[str, Any]] = []
        self.updated_status: list[dict[str, Any]] = []
        self.executed_actions: list[dict[str, Any]] = []
        self.injected_loader_count = 0

    def list_fragments_by_instance_ids(
        self,
        base_id: str,
        *,
        instance_ids: list[str],
        page_index: int,
        page_size: int,
        status: int | None = None,
    ) -> dict[str, Any]:
        self.list_calls.append(
            {
                "base_id": base_id,
                "instance_ids": instance_ids,
                "page_index": page_index,
                "page_size": page_size,
                "status": status,
            }
        )
        selected = [
            item
            for item in self.fragments
            if item["instance_id"] in instance_ids
            and (status is None or item["status"] == status)
        ]
        start = (page_index - 1) * page_size
        end = start + page_size
        return {"total": len(selected), "data": selected[start:end]}

    def list_fragments_for_build(
        self,
        base_id: str,
        *,
        instance_ids: list[str],
        page_index: int,
        page_size: int,
        status: int = 0,
    ) -> dict[str, Any]:
        self.list_for_build_calls.append(
            {
                "base_id": base_id,
                "instance_ids": instance_ids,
                "page_index": page_index,
                "page_size": page_size,
                "status": status,
            }
        )
        selected = [
            item
            for item in self.fragments
            if (not instance_ids or item["instance_id"] in instance_ids)
            and item["status"] == status
        ]
        start = (page_index - 1) * page_size
        end = start + page_size
        return {"total": len(selected), "data": selected[start:end]}

    def get_term_detail(
        self,
        base_id: str,
        *,
        library_id: str,
        term_id: str,
    ) -> dict[str, Any] | None:
        return {
            "term_id": term_id,
            "term_code": "Agent",
            "term_name": "Agent",
            "term_type": "Concept",
            "term_type_code": "Concept",
            "library_id": library_id,
        }

    def get_object_detail(self, base_id: str, object_code: str) -> dict[str, Any]:
        return {
            "object_code": object_code,
            "object_name": object_code,
            "properties": [
                {
                    "property_code": "name",
                    "property_name": "Name",
                    "data_type": "STRING",
                    "required": True,
                },
                {
                    "property_code": "owner_type",
                    "property_name": "Owner Type",
                    "data_type": "STRING",
                    "required": True,
                    "terminology": {
                        "termField": "owner_type",
                        "termTypeCode": "Concept_owner_type",
                        "termMasterType": "DICT_TERM",
                    },
                },
            ],
        }

    def list_terms(self, base_id: str, **kwargs: Any) -> dict[str, Any]:
        self.term_calls.append({"base_id": base_id, **kwargs})
        if kwargs.get("library_id") == DEFAULT_BASE_ID:
            return {"total": 0, "data": []}
        return {
            "total": 1,
            "data": [
                {
                    "term_id": "term-public",
                    "term_code": "public",
                    "term_name": "Common concept",
                    "term_type_code": "Concept_owner_type",
                    "aliases": ["public concept"],
                }
            ],
        }

    def read_source_document(
        self,
        base_id: str,
        origin_file: dict[str, Any],
    ) -> str:
        return f"Full source from {base_id}: {origin_file['file_path']}"

    def update_fragment_status_by_ids(
        self,
        base_id: str,
        *,
        ids: list[int],
        status: int,
        updated_by: str,
    ) -> int:
        self.updated_status.append(
            {
                "base_id": base_id,
                "ids": ids,
                "status": status,
                "updated_by": updated_by,
            }
        )
        return len(ids)

    def _load_ontology_cached(self, base_id: str) -> object:
        return object()

    def inject_virtual_actions(self, base_id: str, loader: object) -> None:
        self.injected_loader_count += 1

    async def execute_action(
        self,
        base_id: str,
        loader: object,
        object_code: str,
        action_code: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        self.executed_actions.append(
            {
                "base_id": base_id,
                "object_code": object_code,
                "action_code": action_code,
                "arguments": arguments,
            }
        )
        return {"data": {"records": [{"id": "kb-agent"}], "total": 1}}


def _fragment(
    row_id: int,
    instance_id: str,
    origin_instance_id: str = "origin-agent",
) -> dict[str, Any]:
    return {
        "id": row_id,
        "instance_id": instance_id,
        "instance_name": "Agent",
        "origin_instance_id": origin_instance_id,
        "origin_file": {
            "file_path": "/Concept/Agent.md",
            "kb_resource_id": "10000795",
        },
        "content": f"fragment {row_id}",
        "status": 0,
    }


def test_sql_task_repository_maps_protocol_fields_to_task_rows() -> None:
    class FakeTaskAdapter:
        def __init__(self) -> None:
            self.rows: dict[str, dict[str, Any]] = {}

        def create(self, record: dict[str, Any]) -> dict[str, Any]:
            self.rows[str(record["task_id"])] = dict(record)
            return dict(record)

        def get(self, task_id: str) -> dict[str, Any] | None:
            row = self.rows.get(task_id)
            return dict(row) if row is not None else None

        def update(self, task_id: str, updates: dict[str, Any]) -> dict[str, Any]:
            self.rows[task_id].update(updates)
            return dict(self.rows[task_id])

    adapter = FakeTaskAdapter()
    repository = SqlObjectInstanceBuildTaskRepository(adapter=adapter)

    task = repository.create(instance_ids=[], batch_size=20, operator="alice")
    updated = repository.update(task.task_id, status="running", total_count=3)

    assert adapter.rows[task.task_id]["created_by"] == "alice"
    assert adapter.rows[task.task_id]["instance_ids"] == []
    assert updated.status == "running"
    assert updated.total_count == 3
    assert repository.get(task.task_id).operator == "alice"


def test_orchestrator_label_schema_keeps_multi_enum_marker() -> None:
    platform = FakeBuildPlatform(fragments=[])
    repository = InMemoryObjectInstanceBuildTaskRepository()
    orchestrator = ObjectInstanceBuildOrchestrator(
        platform=platform,
        task_repository=repository,
        knowledge_client=FakeBuildKnowledgeClient(),
    )

    label_schema = orchestrator._build_label_schema(  # noqa: SLF001
        {
            "properties": [
                {
                    "property_code": "tags",
                    "property_name": "Tags",
                    "data_type": "LIST",
                    "isMultiple": True,
                    "terminology": {
                        "termField": "tags",
                        "termTypeCode": "Concept_tag",
                        "termMasterType": "DICT_TERM",
                    },
                }
            ]
        }
    )

    assert label_schema["tags"]["multiple"] is True


def test_orchestrator_reads_source_content_from_storage_result() -> None:
    class StorageOnlyPlatform:
        def get_result(self, base_id: str, file_id: str) -> bytes:
            assert base_id == DEFAULT_BASE_ID
            assert file_id == "10000795"
            return b"Full source bytes"

    orchestrator = ObjectInstanceBuildOrchestrator(
        platform=StorageOnlyPlatform(),  # type: ignore[arg-type]
        task_repository=InMemoryObjectInstanceBuildTaskRepository(),
        knowledge_client=FakeBuildKnowledgeClient(),
    )
    group = orchestrator_module._FragmentGroup(  # noqa: SLF001
        instance_id="term-agent",
        origin_instance_id="origin-agent",
        fragments=[_fragment(101, "term-agent")],
    )

    assert orchestrator._read_source_content(group) == "Full source bytes"  # noqa: SLF001


@pytest.mark.asyncio
async def test_task_service_builds_instance_and_marks_fragments_merged() -> None:
    platform = FakeBuildPlatform(
        fragments=[_fragment(101, "term-agent"), _fragment(102, "term-agent")]
    )
    repository = InMemoryObjectInstanceBuildTaskRepository()
    knowledge_client = FakeBuildKnowledgeClient()
    orchestrator = ObjectInstanceBuildOrchestrator(
        platform=platform,
        task_repository=repository,
        knowledge_client=knowledge_client,
    )
    service = ObjectInstanceBuildTaskService(
        task_repository=repository,
        task_runner=InlineObjectInstanceBuildTaskRunner(orchestrator=orchestrator),
    )

    accepted = await service.submit(
        SubmitObjectInstanceBuildTaskRequest(
            instance_ids=["term-agent"],
            batch_size=20,
            operator="alice",
        )
    )
    task = repository.get(accepted.task_id)

    assert accepted.status == "queued"
    assert task.status == "succeeded"
    assert task.total_count == 1
    assert task.success_count == 1
    assert task.failed_count == 0
    assert platform.updated_status == [
        {
            "base_id": DEFAULT_BASE_ID,
            "ids": [101, 102],
            "status": 1,
            "updated_by": "alice",
        }
    ]
    assert platform.executed_actions[0]["object_code"] == "Concept"
    assert platform.executed_actions[0]["action_code"] == "write_Concept"
    assert platform.executed_actions[0]["arguments"]["labels"]["owner_type"] == "public"
    assert knowledge_client.requests[0].label_schema["owner_type"]["enum_values"] == [
        {
            "term_id": "term-public",
            "code": "public",
            "name": "Common concept",
            "aliases": ["public concept"],
        }
    ]
    assert platform.term_calls[0]["library_id"] == DEFAULT_BASE_ID
    assert platform.term_calls[1]["library_id"] == "default_term"


@pytest.mark.asyncio
async def test_orchestrator_fetches_unmerged_fragments_page_by_page() -> None:
    fragments = [_fragment(index, f"term-{index}") for index in range(1, 6)]
    platform = FakeBuildPlatform(fragments=fragments)
    repository = InMemoryObjectInstanceBuildTaskRepository()
    task = repository.create(
        instance_ids=[f"term-{index}" for index in range(1, 6)],
        batch_size=2,
        operator="alice",
    )
    knowledge_client = FakeBuildKnowledgeClient()
    orchestrator = ObjectInstanceBuildOrchestrator(
        platform=platform,
        task_repository=repository,
        knowledge_client=knowledge_client,
    )

    await orchestrator.run(task.task_id)

    assert [call["page_index"] for call in platform.list_calls] == [1, 2, 3]
    assert len(platform.executed_actions) == 5
    assert repository.get(task.task_id).success_count == 5


@pytest.mark.asyncio
async def test_empty_instance_ids_processes_all_unmerged_fragments() -> None:
    fragments = [_fragment(1, "term-1"), _fragment(2, "term-2")]
    platform = FakeBuildPlatform(fragments=fragments)
    repository = InMemoryObjectInstanceBuildTaskRepository()
    orchestrator = ObjectInstanceBuildOrchestrator(
        platform=platform,
        task_repository=repository,
        knowledge_client=FakeBuildKnowledgeClient(),
    )
    service = ObjectInstanceBuildTaskService(
        task_repository=repository,
        task_runner=InlineObjectInstanceBuildTaskRunner(orchestrator=orchestrator),
    )

    accepted = await service.submit(
        SubmitObjectInstanceBuildTaskRequest(
            instance_ids=[],
            batch_size=10,
            operator="alice",
        )
    )
    task = repository.get(accepted.task_id)

    assert accepted.instance_ids == []
    assert task.status == "succeeded"
    assert task.total_count == 2
    assert [call["page_index"] for call in platform.list_for_build_calls] == [1]


@pytest.mark.asyncio
async def test_orchestrator_records_partial_failed_status_and_error_details() -> None:
    fragments = [_fragment(1, "term-1"), _fragment(2, "term-2")]
    platform = FakeBuildPlatform(fragments=fragments)
    repository = InMemoryObjectInstanceBuildTaskRepository()
    task = repository.create(
        instance_ids=["term-1", "term-2"],
        batch_size=10,
        operator="alice",
    )
    orchestrator = ObjectInstanceBuildOrchestrator(
        platform=platform,
        task_repository=repository,
        knowledge_client=FailingSecondBuildKnowledgeClient(),
    )

    await orchestrator.run(task.task_id)
    final_task = repository.get(task.task_id)

    assert final_task.status == "partial_failed"
    assert final_task.success_count == 1
    assert final_task.failed_count == 1
    assert final_task.errors == [
        {
            "instance_id": "term-2",
            "origin_instance_id": "origin-agent",
            "fragment_ids": [2],
            "stage": "process_group",
            "message": "LLM output exhausted retries",
        }
    ]


@pytest.mark.asyncio
async def test_invoke_object_write_action_uses_datacloud_data_action_pipeline() -> None:
    platform = FakeBuildPlatform(fragments=[])

    result = await invoke_object_write_action(
        platform=platform,
        base_id=DEFAULT_BASE_ID,
        object_code="Concept",
        content="# Agent",
        labels={"owner_type": "public"},
        file_description="Agent object instance",
        source_path="/Concept/Agent.md",
    )

    assert result["records"] == [{"id": "kb-agent"}]
    assert platform.injected_loader_count == 1
    assert platform.executed_actions == [
        {
            "base_id": DEFAULT_BASE_ID,
            "object_code": "Concept",
            "action_code": "write_Concept",
            "arguments": {
                "source_path": "/Concept/Agent.md",
                "content": "# Agent",
                "labels": {"owner_type": "public"},
                "file_description": "Agent object instance",
            },
        }
    ]


@pytest.mark.asyncio
async def test_invoke_object_action_calls_loader_object_invoke_action() -> None:
    class FakeTargetObject:
        def __init__(self) -> None:
            self.calls: list[dict[str, Any]] = []

        async def invoke_action(
            self,
            action_code: str,
            arguments: dict[str, Any],
        ) -> dict[str, Any]:
            self.calls.append({"action_code": action_code, "arguments": arguments})
            return {"records": [{"id": "direct"}], "total": 1}

    class FakeLoader:
        def __init__(self, target: FakeTargetObject) -> None:
            self.target = target
            self.object_codes: list[str] = []

        def get_object(self, object_code: str) -> FakeTargetObject:
            self.object_codes.append(object_code)
            return self.target

    class DirectPlatform:
        def __init__(self) -> None:
            self.target = FakeTargetObject()
            self.loader = FakeLoader(self.target)
            self.injected = 0

        def _load_ontology_cached(self, base_id: str) -> FakeLoader:
            return self.loader

        def inject_virtual_actions(self, base_id: str, loader: FakeLoader) -> None:
            self.injected += 1

        async def execute_action(
            self,
            base_id: str,
            loader: FakeLoader,
            object_code: str,
            action_code: str,
            arguments: dict[str, Any],
        ) -> dict[str, Any]:
            raise AssertionError("execute_action fallback should not be used")

    platform = DirectPlatform()

    result = await invoke_object_action(
        platform=platform,  # type: ignore[arg-type]
        base_id=DEFAULT_BASE_ID,
        object_code="Concept",
        action_code="write_Concept",
        arguments={"content": "# Agent"},
    )

    assert result == {"records": [{"id": "direct"}], "total": 1}
    assert platform.injected == 1
    assert platform.loader.object_codes == ["Concept"]
    assert platform.target.calls == [
        {"action_code": "write_Concept", "arguments": {"content": "# Agent"}}
    ]


def test_rpc_build_object_instance_and_query_task_protocol(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from datacloud_platform.api.routers.rpc.handlers import ontology_doc_fragment

    service = FakeRpcTaskService()
    monkeypatch.setattr(
        ontology_doc_fragment,
        "get_object_instance_build_task_service",
        lambda platform: service,
        raising=False,
    )
    app = FastAPI()
    app.include_router(create_rpc_router(platform=object()))  # type: ignore[arg-type]
    client = TestClient(app)

    build_resp = client.post(
        "/api/v1/rpc/ontologyDocFragment/buildObjectInstance",
        json={"params": {"instance_ids": ["term-agent"], "batch_size": 20}},
        headers={"X-User-Code": "alice"},
    )
    build_body = build_resp.json()

    assert build_body["success"] is True
    assert build_body["message"] == "accepted"
    assert build_body["data"]["task_id"] == "task-agent"
    assert service.submitted.instance_ids == ["term-agent"]
    assert service.submitted.batch_size == 20
    assert service.submitted.operator == "alice"

    task_resp = client.post(
        "/api/v1/rpc/ontologyDocFragment/getObjectInstanceBuildTask",
        json={"params": {"task_id": "task-agent"}},
    )
    task_body = task_resp.json()

    assert task_body["success"] is True
    assert task_body["data"]["status"] == "succeeded"

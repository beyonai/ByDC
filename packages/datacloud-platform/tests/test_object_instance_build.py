from __future__ import annotations

import logging
from importlib.util import find_spec
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from datacloud_knowledge.contracts.term_provider_types import TermDetail
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
    InlineObjectInstanceBuildTaskRunner,
    ObjectInstanceBuildRunRequest,
    ObjectInstanceBuildTaskService,
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


class FrontmatterDroppingKnowledgeClient:
    def __init__(self) -> None:
        self.requests: list[Any] = []

    async def build_object_instance(self, request: Any) -> ObjectInstanceBuildResult:
        self.requests.append(request)
        return ObjectInstanceBuildResult(
            content=(
                "---\n"
                'name: "Ontology"\n'
                'product_code: "BYCLAW_DATACLOUD"\n'
                "---\n\n"
                "# Ontology\n\n"
                "Merged content."
            ),
            labels={"name": "Ontology", "product_code": "BYCLAW_DATACLOUD"},
            file_description="Ontology object instance",
        )


class FakeAcceptedTask:
    def __init__(self, *, status: str = "accepted") -> None:
        self.status = status

    def to_dict(self) -> dict[str, object]:
        return {
            "instance_ids": ["term-agent"],
            "batch_size": 20,
            "created_by": "alice",
            "status": self.status,
        }


class FakeRpcTaskService:
    def __init__(self) -> None:
        self.accepted: Any | None = None
        self.started: list[Any] = []

    def accept(self, request: Any) -> tuple[FakeAcceptedTask, Any]:
        self.accepted = request
        run_request = ObjectInstanceBuildRunRequest(
            request_id="request-agent",
            instance_ids=request.instance_ids,
            batch_size=request.batch_size,
            operator=request.operator,
            beyond_token="token-alice",
        )
        return FakeAcceptedTask(), run_request

    async def run(self, run_request: Any) -> None:
        self.started.append(run_request)


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
            "ext_attrs": {
                "kb_resource_id": "target-resource",
                "kb_file_path": "/Concept/Agent.md",
            },
        }

    def get_object_detail(self, base_id: str, object_code: str) -> dict[str, Any]:
        return {
            "object_code": object_code,
            "object_name": object_code,
            "extProperty": {
                "template": (
                    "---\n"
                    "template_type: object_instance_template\n"
                    "---\n\n"
                    "# Concept 实例卡片模板\n\n"
                    "## 1. 模板说明\n\n"
                    "本模板用于编写 Concept 对象实例卡片。\n\n"
                    "## 2. 头部字段填写说明\n\n"
                    "字段必须与 object.schema.yaml 保持一致。\n\n"
                    "## 5. 实例卡片模板\n\n"
                    "```markdown\n"
                    "---\n"
                    'name: "{{value}}"\n'
                    'owner_type: "{{value}}"\n'
                    "---\n\n"
                    "# {{name}}\n\n"
                    "## 对象说明\n\n"
                    "{{object_description}}\n"
                    "```\n\n"
                    "## 6. 常见错误与检查清单\n\n"
                    "- 使用了 object.schema.yaml 中未声明的头部字段。\n"
                )
            },
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
        if origin_file.get("kb_resource_id") == "target-resource":
            return "# Agent\n\n## 投标标签\n\n原有投标标签内容。"
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


class FrontmatterBuildPlatform(FakeBuildPlatform):
    def get_term_detail(
        self,
        base_id: str,
        *,
        library_id: str,
        term_id: str,
    ) -> dict[str, Any] | None:
        if term_id == "term-reasoning":
            return {
                "term_id": term_id,
                "term_code": "Ontology Reasoning",
                "term_name": "Ontology Reasoning",
                "term_type": "Concept",
                "term_type_code": "Concept",
                "library_id": library_id,
            }
        if term_id == "term-bydc":
            return {
                "term_id": term_id,
                "term_code": "byDC",
                "term_name": "byDC",
                "term_type": "Product",
                "term_type_code": "Product",
                "library_id": library_id,
            }
        return {
            "term_id": term_id,
            "term_code": "Ontology",
            "term_name": "Ontology",
            "term_type": "Methodology",
            "term_type_code": "Methodology",
            "library_id": library_id,
            "ext_attrs": {
                "kb_resource_id": "target-resource",
                "kb_file_path": "/Methodology/Ontology.md",
            },
        }

    def get_object_detail(self, base_id: str, object_code: str) -> dict[str, Any]:
        return {
            "object_code": object_code,
            "object_name": object_code,
            "extProperty": {},
            "properties": [
                {
                    "property_code": "name",
                    "property_name": "Name",
                    "data_type": "STRING",
                    "required": True,
                },
                {
                    "property_code": "product_code",
                    "property_name": "Product Code",
                    "data_type": "STRING",
                    "required": True,
                },
            ],
        }

    def read_source_document(
        self,
        base_id: str,
        origin_file: dict[str, Any],
    ) -> str:
        if origin_file.get("kb_resource_id") == "target-resource":
            return "# Ontology\n\nExisting content without frontmatter."
        return f"Full source from {base_id}: {origin_file['file_path']}"

    def list_term_relations(self, base_id: str, **kwargs: Any) -> dict[str, Any]:
        if kwargs.get("source_term_id") != "term-ontology":
            return {"data": [], "totalCount": 0}
        return {
            "data": [
                {
                    "source_term_id": "term-ontology",
                    "target_term_id": "term-reasoning",
                    "relation_name": "maps-to",
                    "relation_category": "BUSINESS",
                },
                {
                    "source_term_id": "term-ontology",
                    "target_term_id": "term-bydc",
                    "relation_name": "所属产品",
                    "relation_category": "ONTOLOGY",
                },
            ],
            "totalCount": 2,
        }


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


def _run_request(
    *,
    instance_ids: list[str],
    batch_size: int = 20,
    operator: str = "alice",
    request_id: str = "request-test",
    beyond_token: str = "token-alice",
) -> ObjectInstanceBuildRunRequest:
    return ObjectInstanceBuildRunRequest(
        request_id=request_id,
        instance_ids=instance_ids,
        batch_size=batch_size,
        operator=operator,
        beyond_token=beyond_token,
    )


def test_object_instance_build_task_table_adapter_is_removed() -> None:
    assert (
        find_spec(
            "datacloud_platform.adapters.data_adapter._object_instance_build_task"
        )
        is None
    )


def test_orchestrator_extracts_object_code_from_slots_term_detail_dataclass() -> None:
    term_detail = TermDetail(
        term_id="74e82f0a-b5bc-47ce-b0ef-deef7f6c14d4",
        term_code="本体论",
        term_name="本体论",
        term_type="Methodology",
        dataset_id=DEFAULT_BASE_ID,
        library_id=DEFAULT_BASE_ID,
    )

    detail_dict = orchestrator_module._to_dict(term_detail)  # noqa: SLF001

    assert orchestrator_module._object_code_from_term(detail_dict) == "Methodology"  # noqa: SLF001


def test_orchestrator_label_schema_keeps_multi_enum_marker() -> None:
    platform = FakeBuildPlatform(fragments=[])
    orchestrator = ObjectInstanceBuildOrchestrator(
        platform=platform,
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
        knowledge_client=FakeBuildKnowledgeClient(),
    )
    group = orchestrator_module._FragmentGroup(  # noqa: SLF001
        instance_id="term-agent",
        origin_instance_id="origin-agent",
        fragments=[_fragment(101, "term-agent")],
    )

    assert orchestrator._read_source_content(group) == "Full source bytes"  # noqa: SLF001


def test_orchestrator_falls_back_to_fragment_content_when_source_file_missing() -> None:
    class MissingStoragePlatform:
        def get_result(self, base_id: str, file_id: str) -> bytes:
            assert base_id == DEFAULT_BASE_ID
            assert file_id == "10000795"
            raise FileNotFoundError("Result file not found: 10000795")

    orchestrator = ObjectInstanceBuildOrchestrator(
        platform=MissingStoragePlatform(),  # type: ignore[arg-type]
        knowledge_client=FakeBuildKnowledgeClient(),
    )
    group = orchestrator_module._FragmentGroup(  # noqa: SLF001
        instance_id="term-agent",
        origin_instance_id="origin-agent",
        fragments=[_fragment(101, "term-agent"), _fragment(102, "term-agent")],
    )

    assert orchestrator._read_source_content(group) == "fragment 101\n\nfragment 102"  # noqa: SLF001


def test_orchestrator_reads_existing_content_from_runtime_file_storage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class RuntimeFileStorage:
        storage_type = "byclaw_api"

        def __init__(self) -> None:
            self.calls: list[str] = []

        def read_text(
            self,
            file_path: str,
            begin_line: int = 0,
            end_line: int = -1,
        ) -> str:
            assert begin_line == 0
            assert end_line == -1
            self.calls.append(file_path)
            return "# Agent\n\nExisting target content."

    storage = RuntimeFileStorage()
    monkeypatch.setattr(
        orchestrator_module,
        "_build_runtime_result_file_storage",
        lambda: storage,
        raising=False,
    )

    orchestrator = ObjectInstanceBuildOrchestrator(
        platform=object(),  # type: ignore[arg-type]
        knowledge_client=FakeBuildKnowledgeClient(),
    )

    content = orchestrator._read_existing_content(  # noqa: SLF001
        {
            "ext_attrs": {
                "kb_resource_id": "target-resource",
                "kb_file_path": "/Concept/Agent.md",
            }
        }
    )

    assert content == "# Agent\n\nExisting target content."
    assert storage.calls == ["/Concept/Agent.md"]


@pytest.mark.asyncio
async def test_orchestrator_reads_existing_content_from_kb_document_reader(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class KbExistingDocumentPlatform(FakeBuildPlatform):
        def get_term_detail(
            self,
            base_id: str,
            *,
            library_id: str,
            term_id: str,
        ) -> dict[str, Any] | None:
            detail = super().get_term_detail(
                base_id,
                library_id=library_id,
                term_id=term_id,
            )
            assert detail is not None
            detail["ext_attrs"] = {
                "kb_id": "97",
                "kb_file_path": "/Concept/Agent.md",
            }
            return detail

        def read_source_document(
            self,
            base_id: str,
            origin_file: dict[str, Any],
        ) -> str:
            if origin_file.get("kb_id") == "97":
                raise AssertionError("KB document reader must be used first")
            return f"Full source from {base_id}: {origin_file['file_path']}"

    class FakeKbDocumentReader:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str]] = []

        def read_text(self, *, kn_code: str, file_path: str) -> str:
            self.calls.append((kn_code, file_path))
            return "# Agent\n\nExisting KB target content."

    kb_reader = FakeKbDocumentReader()
    monkeypatch.setattr(
        orchestrator_module,
        "_build_kb_document_reader",
        lambda: kb_reader,
        raising=False,
    )
    platform = KbExistingDocumentPlatform(fragments=[_fragment(101, "term-agent")])
    knowledge_client = FakeBuildKnowledgeClient()
    orchestrator = ObjectInstanceBuildOrchestrator(
        platform=platform,
        knowledge_client=knowledge_client,
    )

    await orchestrator.run(_run_request(instance_ids=["term-agent"]))

    assert kb_reader.calls == [("97", "/Concept/Agent.md")]
    assert knowledge_client.requests[0].existing_content == (
        "# Agent\n\nExisting KB target content."
    )


@pytest.mark.asyncio
async def test_task_service_builds_instance_and_marks_fragments_merged() -> None:
    platform = FakeBuildPlatform(
        fragments=[_fragment(101, "term-agent"), _fragment(102, "term-agent")]
    )
    knowledge_client = FakeBuildKnowledgeClient()
    orchestrator = ObjectInstanceBuildOrchestrator(
        platform=platform,
        knowledge_client=knowledge_client,
    )
    service = ObjectInstanceBuildTaskService(
        task_runner=InlineObjectInstanceBuildTaskRunner(orchestrator=orchestrator),
    )

    accepted = await service.submit(
        SubmitObjectInstanceBuildTaskRequest(
            instance_ids=["term-agent"],
            batch_size=20,
            operator="alice",
        )
    )

    assert accepted.status == "accepted"
    assert accepted.instance_ids == ["term-agent"]
    assert accepted.batch_size == 20
    assert accepted.operator == "alice"
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
async def test_orchestrator_preserves_relation_frontmatter_and_product_code() -> None:
    platform = FrontmatterBuildPlatform(fragments=[_fragment(101, "term-ontology")])
    knowledge_client = FrontmatterDroppingKnowledgeClient()
    orchestrator = ObjectInstanceBuildOrchestrator(
        platform=platform,
        knowledge_client=knowledge_client,
    )

    await orchestrator.run(_run_request(instance_ids=["term-ontology"]))

    written_arguments = platform.executed_actions[0]["arguments"]
    written_content = written_arguments["content"]
    assert 'product_code: "BYCLAW_DATACLOUD"' not in written_content
    assert "product_code: byDC" in written_content
    assert "relations:" in written_content
    assert "maps-to:" in written_content
    assert "- Concept:" in written_content
    assert "  - Ontology Reasoning" in written_content
    assert written_arguments["labels"]["product_code"] == "byDC"
    assert written_arguments["labels"]["relations"] == {
        "maps-to": {"Concept": ["Ontology Reasoning"]}
    }


@pytest.mark.asyncio
async def test_orchestrator_logs_task_stage_summaries(
    caplog: pytest.LogCaptureFixture,
) -> None:
    platform = FakeBuildPlatform(fragments=[_fragment(101, "term-agent")])
    orchestrator = ObjectInstanceBuildOrchestrator(
        platform=platform,
        knowledge_client=FakeBuildKnowledgeClient(),
    )
    caplog.set_level(logging.INFO, logger=orchestrator_module.logger.name)

    await orchestrator.run(
        _run_request(instance_ids=["term-agent"], request_id="request-agent")
    )

    messages = "\n".join(record.getMessage() for record in caplog.records)
    assert "request_id=request-agent" in messages
    for stage in (
        "run_start",
        "load_fragment_groups",
        "load_term_detail",
        "load_object_schema",
        "build_label_schema",
        "read_source_content",
        "split_object_template",
        "knowledge_build",
        "validate_build_result",
        "write_object_action",
        "update_fragment_status",
        "run_finish",
    ):
        assert f"stage={stage}" in messages
    assert '"fragment_ids": [101]' in messages
    assert '"content_length": 23' in messages
    assert '"labels": {"name": "Agent", "owner_type": "public"}' in messages


@pytest.mark.asyncio
async def test_orchestrator_passes_existing_target_document_to_knowledge_request() -> (
    None
):
    platform = FakeBuildPlatform(fragments=[_fragment(101, "term-agent")])
    knowledge_client = FakeBuildKnowledgeClient()
    orchestrator = ObjectInstanceBuildOrchestrator(
        platform=platform,
        knowledge_client=knowledge_client,
    )

    await orchestrator.run(_run_request(instance_ids=["term-agent"]))

    request = knowledge_client.requests[0]
    assert "## 投标标签" in request.existing_content
    assert (
        request.source_content
        == f"Full source from {DEFAULT_BASE_ID}: /Concept/Agent.md"
    )


@pytest.mark.asyncio
async def test_orchestrator_does_not_write_when_existing_target_document_is_missing() -> (
    None
):
    class MissingExistingDocumentPlatform(FakeBuildPlatform):
        def read_source_document(
            self,
            base_id: str,
            origin_file: dict[str, Any],
        ) -> str:
            if origin_file.get("kb_resource_id") == "target-resource":
                return ""
            return super().read_source_document(base_id, origin_file)

        def get_result(self, base_id: str, file_id: str) -> bytes:
            raise FileNotFoundError(f"Result file not found: {file_id}")

    platform = MissingExistingDocumentPlatform(fragments=[_fragment(101, "term-agent")])
    orchestrator = ObjectInstanceBuildOrchestrator(
        platform=platform,
        knowledge_client=FakeBuildKnowledgeClient(),
    )

    await orchestrator.run(_run_request(instance_ids=["term-agent"]))

    assert platform.executed_actions == []
    assert platform.updated_status == []


@pytest.mark.asyncio
async def test_orchestrator_passes_object_template_from_object_ext_property() -> None:
    platform = FakeBuildPlatform(fragments=[_fragment(101, "term-agent")])
    knowledge_client = FakeBuildKnowledgeClient()
    orchestrator = ObjectInstanceBuildOrchestrator(
        platform=platform,
        knowledge_client=knowledge_client,
    )

    await orchestrator.run(_run_request(instance_ids=["term-agent"]))

    request = knowledge_client.requests[0]
    assert request.object_template == ""
    assert "# {{name}}" not in request.object_template
    assert "## 2. 头部字段填写说明" in request.template_constraints
    assert "## 6. 常见错误与检查清单" in request.template_constraints
    assert "```markdown" not in request.template_constraints


@pytest.mark.asyncio
async def test_orchestrator_fetches_unmerged_fragments_page_by_page() -> None:
    fragments = [_fragment(index, f"term-{index}") for index in range(1, 6)]
    platform = FakeBuildPlatform(fragments=fragments)
    knowledge_client = FakeBuildKnowledgeClient()
    orchestrator = ObjectInstanceBuildOrchestrator(
        platform=platform,
        knowledge_client=knowledge_client,
    )

    await orchestrator.run(
        _run_request(
            instance_ids=[f"term-{index}" for index in range(1, 6)],
            batch_size=2,
        )
    )

    assert [call["page_index"] for call in platform.list_calls] == [1, 2, 3]
    assert len(platform.executed_actions) == 5


@pytest.mark.asyncio
async def test_empty_instance_ids_processes_all_unmerged_fragments() -> None:
    fragments = [_fragment(1, "term-1"), _fragment(2, "term-2")]
    platform = FakeBuildPlatform(fragments=fragments)
    orchestrator = ObjectInstanceBuildOrchestrator(
        platform=platform,
        knowledge_client=FakeBuildKnowledgeClient(),
    )
    service = ObjectInstanceBuildTaskService(
        task_runner=InlineObjectInstanceBuildTaskRunner(orchestrator=orchestrator),
    )

    accepted = await service.submit(
        SubmitObjectInstanceBuildTaskRequest(
            instance_ids=[],
            batch_size=10,
            operator="alice",
        )
    )

    assert accepted.instance_ids == []
    assert [call["page_index"] for call in platform.list_for_build_calls] == [1]


@pytest.mark.asyncio
async def test_orchestrator_logs_partial_failed_error_details(
    caplog: pytest.LogCaptureFixture,
) -> None:
    fragments = [_fragment(1, "term-1"), _fragment(2, "term-2")]
    platform = FakeBuildPlatform(fragments=fragments)
    orchestrator = ObjectInstanceBuildOrchestrator(
        platform=platform,
        knowledge_client=FailingSecondBuildKnowledgeClient(),
    )
    caplog.set_level(logging.INFO, logger=orchestrator_module.logger.name)

    await orchestrator.run(
        _run_request(
            instance_ids=["term-1", "term-2"],
            batch_size=10,
            request_id="request-partial",
        )
    )

    messages = "\n".join(record.getMessage() for record in caplog.records)
    assert "request_id=request-partial" in messages
    assert "status=partial_failed" in messages
    assert "LLM output exhausted retries" in messages


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


def test_rpc_build_object_instance_returns_accepted_without_task_id(
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
        headers={"X-User-Code": "alice", "beyond-token": "token-alice"},
    )
    build_body = build_resp.json()

    assert build_body["success"] is True
    assert build_body["message"] == "accepted"
    assert build_body["data"] == {
        "instance_ids": ["term-agent"],
        "batch_size": 20,
        "created_by": "alice",
        "status": "accepted",
    }
    assert service.accepted.instance_ids == ["term-agent"]
    assert service.accepted.batch_size == 20
    assert service.accepted.operator == "alice"
    assert len(service.started) == 1
    assert service.started[0].beyond_token == "token-alice"

    task_resp = client.post(
        "/api/v1/rpc/ontologyDocFragment/getObjectInstanceBuildTask",
        json={"params": {"task_id": "task-agent"}},
    )
    task_body = task_resp.json()

    assert task_body["code"] == 501
    assert task_body["data"] is None
    assert "no longer supported" in task_body["message"]


def test_rpc_build_object_instance_requires_beyond_token(
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

    response = client.post(
        "/api/v1/rpc/ontologyDocFragment/buildObjectInstance",
        json={"params": {"instance_ids": ["term-agent"], "batch_size": 20}},
        headers={"X-User-Code": "alice"},
    )
    body = response.json()

    assert body["code"] == 400
    assert body["message"] == "Request header 'beyond-token' is required"
    assert body["data"] is None
    assert service.accepted is None
    assert service.started == []

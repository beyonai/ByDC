"""测试 discoverObjectInstancesUnstructured — 非结构化对象实例发现接口。

T1 骨架范围：模型默认值、①参数校验、②管道异常上抛（不降级）、③④ TODO 占位
（NotImplementedError）、平台接线可达性、RPC 501 / X-Session-Id 校验。
后续 T2/T3/T4 在同类扩展。
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from datacloud_platform.api.routers.rpc.router import create_rpc_router
from datacloud_platform.mixins import ObjectInstanceDiscoveryMixin
from datacloud_platform.mixins import object_instance_discovery as discovery_module
from datacloud_platform.mixins.object_instance_discovery import _extract_written_term_id
from datacloud_platform.models.document import DocumentContentResult
from datacloud_platform.models.shared import (
    ObjectInstanceDiscoveryHit,
    ObjectInstanceDiscoveryResult,
    ObjectInstanceWriteMissingTermIdError,
)

BASE_ID = "BYCLAW_DATACLOUD"


# ============================================================================
# 假平台：继承 mixin 并绑定 _ObjectInstanceDiscoveryPlatform 协议方法
# ============================================================================


class _FakePlatform(ObjectInstanceDiscoveryMixin):
    """测试用假平台：实现协议声明的四个平台能力。"""

    def __init__(self) -> None:
        self.document: DocumentContentResult | None = None
        self.incomplete_location: bool = False
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.relations: list[dict[str, Any]] = []
        self.created_relations: list[dict[str, Any]] = []
        self.object_files: list[list[dict[str, Any]]] = []

    async def get_document_content_by_term_id(
        self, base_id: str, *, term_id: str
    ) -> DocumentContentResult:
        self.calls.append(
            (
                "get_document_content_by_term_id",
                {"base_id": base_id, "term_id": term_id},
            )
        )
        if self.document is None:
            raise KeyError(f"term not found: {term_id}")
        if self.incomplete_location:
            raise ValueError(
                f"term knowledge location is incomplete: term_id={term_id}"
            )
        return self.document

    def list_term_relations(self, base_id: str, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("list_term_relations", {"base_id": base_id, **kwargs}))
        return {"data": list(self.relations)}

    def create_term_relation(
        self, base_id: str, *, relation: dict[str, Any]
    ) -> dict[str, Any]:
        self.calls.append(
            ("create_term_relation", {"base_id": base_id, "relation": relation})
        )
        self.created_relations.append(relation)
        return {"relationId": "rel-x"}

    async def save_or_update_object_files(
        self, base_id: str, *, object_files: list[dict[str, Any]]
    ) -> None:
        self.calls.append(
            (
                "save_or_update_object_files",
                {"base_id": base_id, "object_files": object_files},
            )
        )
        self.object_files.append(object_files)


def _make_document(term_id: str = "term-input") -> DocumentContentResult:
    return DocumentContentResult(
        termId=term_id,
        kbResourceId="kb-res-1",
        filePath="/Methodology/输入实例.md",
        content="# 输入实例\n\n正文内容。",
    )


# ============================================================================
# 模型测试
# ============================================================================


class TestObjectInstanceDiscoveryHitModel:
    def test_default_relation_name_and_evidence(self) -> None:
        hit = ObjectInstanceDiscoveryHit(
            instance_id="t1",
            instance_code="c1",
            instance_name="测试实例",
            object_code="by_opportunity",
            file_name="/docs/1.md",
            kb_resource_id="kr1",
            kb_id="kb1",
            is_new=True,
        )
        assert hit.relation_name == "提及"
        assert hit.evidence is None

    def test_hit_is_frozen(self) -> None:
        hit = ObjectInstanceDiscoveryHit(
            instance_id="t1",
            instance_code="c1",
            instance_name="测试实例",
            object_code="by_opportunity",
            file_name="/docs/1.md",
            kb_resource_id="kr1",
            kb_id="kb1",
            is_new=True,
        )
        with pytest.raises(Exception):
            hit.is_new = False  # type: ignore[misc]

    def test_result_envelope(self) -> None:
        result = ObjectInstanceDiscoveryResult(
            items=[
                ObjectInstanceDiscoveryHit(
                    instance_id="t1",
                    instance_code="c1",
                    instance_name="A",
                    object_code="by_opportunity",
                    file_name="/a.md",
                    kb_resource_id=None,
                    kb_id=None,
                    is_new=False,
                )
            ]
        )
        assert result.items[0].instance_id == "t1"


# ============================================================================
# ① 参数校验
# ============================================================================


class TestDiscoverParameterValidation:
    @pytest.mark.asyncio
    async def test_empty_instance_id_raises_value_error(self) -> None:
        platform = _FakePlatform()
        with pytest.raises(ValueError, match="instance_id"):
            await platform.discover_object_instances_unstructured(
                BASE_ID,
                instance_id="",
                object_codes=["by_opportunity"],
                session_id="session-1",
            )

    @pytest.mark.asyncio
    async def test_missing_object_codes_raises_value_error(self) -> None:
        platform = _FakePlatform()
        with pytest.raises(ValueError, match="object_codes"):
            await platform.discover_object_instances_unstructured(
                BASE_ID,
                instance_id="term-input",
                object_codes=[],
                session_id="session-1",
            )


# ============================================================================
# ② 管道异常上抛（无降级）
# ============================================================================


class TestDiscoverPipelineErrors:
    @pytest.mark.asyncio
    async def test_missing_term_raises_key_error(self) -> None:
        platform = _FakePlatform()
        with pytest.raises(KeyError, match="term not found"):
            await platform.discover_object_instances_unstructured(
                BASE_ID,
                instance_id="missing",
                object_codes=["by_opportunity"],
                session_id="session-1",
            )

    @pytest.mark.asyncio
    async def test_incomplete_kb_location_raises_value_error(self) -> None:
        platform = _FakePlatform()
        platform.document = _make_document()
        platform.incomplete_location = True
        with pytest.raises(ValueError, match="knowledge location is incomplete"):
            await platform.discover_object_instances_unstructured(
                BASE_ID,
                instance_id="term-input",
                object_codes=["by_opportunity"],
                session_id="session-1",
            )


# ============================================================================
# ③④ TODO 占位
# ============================================================================


class TestDiscoverTodoPlaceholders:
    def test_existing_discovery_raises_not_implemented(self) -> None:
        platform = _FakePlatform()
        with pytest.raises(NotImplementedError, match="not implemented"):
            platform._discover_existing_object_instances(
                BASE_ID, content="正文", object_codes=["by_opportunity"]
            )

    def test_new_discovery_raises_not_implemented(self) -> None:
        platform = _FakePlatform()
        with pytest.raises(NotImplementedError, match="not implemented"):
            platform._discover_new_object_instances(
                BASE_ID, content="正文", object_codes=["by_opportunity"]
            )

    @pytest.mark.asyncio
    async def test_main_flow_short_circuits_at_existing_placeholder(self) -> None:
        platform = _FakePlatform()
        platform.document = _make_document()
        with pytest.raises(NotImplementedError, match="not implemented"):
            await platform.discover_object_instances_unstructured(
                BASE_ID,
                instance_id="term-input",
                object_codes=["by_opportunity"],
                session_id="session-1",
            )


# ============================================================================
# ⑤ 新实例创建 + ⑥ term_id 强校验
# ============================================================================


class TestExtractWrittenTermId:
    def test_snake_case_term_id(self) -> None:
        assert _extract_written_term_id({"records": [{"term_id": "t1"}]}) == "t1"

    def test_camel_case_term_id(self) -> None:
        assert _extract_written_term_id({"records": [{"termId": "t1"}]}) == "t1"

    def test_missing_records_raises(self) -> None:
        with pytest.raises(
            ObjectInstanceWriteMissingTermIdError, match="missing term_id"
        ):
            _extract_written_term_id({"records": []})

    def test_blank_term_id_raises(self) -> None:
        with pytest.raises(
            ObjectInstanceWriteMissingTermIdError, match="missing term_id"
        ):
            _extract_written_term_id({"records": [{"termId": "   "}]})

    def test_strips_term_id(self) -> None:
        assert (
            _extract_written_term_id({"records": [{"term_id": "  term-x  "}]})
            == "term-x"
        )

    def test_raw_envelope_is_normalized(self) -> None:
        raw = {
            "content": [
                {"text": '{"code": 200, "data": {"records": [{"termId": "t9"}]}}'}
            ]
        }
        assert _extract_written_term_id(raw) == "t9"


class TestCreateDiscoveredInstance:
    @pytest.mark.asyncio
    async def test_invokes_write_action_with_expected_arguments(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        platform = _FakePlatform()
        captured: dict[str, Any] = {}

        async def fake_write_action(**kwargs: Any) -> dict[str, Any]:
            captured.update(kwargs)
            return {"records": [{"termId": "term-new-1"}], "total": 1, "meta": {}}

        monkeypatch.setattr(
            discovery_module, "invoke_object_write_action", fake_write_action
        )
        term_id = await platform._create_discovered_instance(
            base_id=BASE_ID,
            object_code="by_opportunity",
            term_name="张三",
            session_id="session-1",
        )
        assert term_id == "term-new-1"
        assert captured["base_id"] == BASE_ID
        assert captured["object_code"] == "by_opportunity"
        assert captured["labels"]["dc_status"] == "待整理"
        assert captured["source_path"] == "/by_opportunity/张三.md"
        assert "张三" in captured["content"]
        assert captured["file_description"] == "张三对象实例文档"

    @pytest.mark.asyncio
    async def test_write_response_missing_term_id_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        platform = _FakePlatform()

        async def fake_write_action(**kwargs: Any) -> dict[str, Any]:
            return {"records": [{"fileName": "张三.md"}], "total": 1, "meta": {}}

        monkeypatch.setattr(
            discovery_module, "invoke_object_write_action", fake_write_action
        )
        with pytest.raises(
            ObjectInstanceWriteMissingTermIdError, match="missing term_id"
        ):
            await platform._create_discovered_instance(
                base_id=BASE_ID,
                object_code="by_opportunity",
                term_name="张三",
                session_id="session-1",
            )

    @pytest.mark.asyncio
    async def test_write_response_term_id_returns_strict_value(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        platform = _FakePlatform()

        async def fake_write_action(**kwargs: Any) -> dict[str, Any]:
            return {"records": [{"term_id": "  term-strict  "}]}

        monkeypatch.setattr(
            discovery_module, "invoke_object_write_action", fake_write_action
        )
        term_id = await platform._create_discovered_instance(
            base_id=BASE_ID,
            object_code="by_opportunity",
            term_name="张三",
            session_id="session-1",
        )
        assert term_id == "term-strict"


# ============================================================================
# ⑦ 文件登记
# ============================================================================


class TestRegisterObjectFile:
    @pytest.mark.asyncio
    async def test_registers_file_with_session_and_strict_term_id(self) -> None:
        platform = _FakePlatform()
        await platform._register_object_file(
            base_id=BASE_ID,
            object_code="by_opportunity",
            term_name="张三",
            term_id="term-new-1",
            session_id="session-1",
            action_result={
                "records": [{"termId": "term-new-1", "fileName": "张三.md"}]
            },
        )
        assert len(platform.object_files) == 1
        entry = platform.object_files[0][0]
        assert entry["sessionId"] == "session-1"
        assert entry["objectCode"] == "by_opportunity"
        assert entry["statusCd"] == "待整理"
        ext = json.loads(entry["extContent"])
        assert ext["term_id"] == "term-new-1"

    @pytest.mark.asyncio
    async def test_registers_file_falls_back_to_strict_term_id(self) -> None:
        platform = _FakePlatform()
        await platform._register_object_file(
            base_id=BASE_ID,
            object_code="by_opportunity",
            term_name="张三",
            term_id="term-new-1",
            session_id="session-1",
            action_result={"records": [{"fileName": "张三.md"}]},
        )
        entry = platform.object_files[0][0]
        ext = json.loads(entry["extContent"])
        assert ext["term_id"] == "term-new-1"


# ============================================================================
# ⑧ 「提及」关系（源→目标，单向幂等）
# ============================================================================


class TestEstablishMentionRelation:
    def test_existing_relation_skips_create(self) -> None:
        platform = _FakePlatform()
        platform.relations = [
            {
                "relation_name": "提及",
                "source_term_id": "term-input",
                "target_term_id": "term-new-1",
            }
        ]
        created = platform._establish_mention_relation(
            base_id=BASE_ID,
            source_term_id="term-input",
            target_term_id="term-new-1",
        )
        assert created is False
        assert platform.created_relations == []
        assert platform.calls[-1][0] == "list_term_relations"

    def test_missing_relation_creates_camel_case(self) -> None:
        platform = _FakePlatform()
        created = platform._establish_mention_relation(
            base_id=BASE_ID,
            source_term_id="term-input",
            target_term_id="term-new-1",
        )
        assert created is True
        assert platform.created_relations == [
            {
                "sourceTermId": "term-input",
                "targetTermId": "term-new-1",
                "relationName": "提及",
            }
        ]

    def test_same_name_different_target_still_creates(self) -> None:
        platform = _FakePlatform()
        platform.relations = [
            {
                "relation_name": "提及",
                "source_term_id": "term-input",
                "target_term_id": "term-other",
            }
        ]
        created = platform._establish_mention_relation(
            base_id=BASE_ID,
            source_term_id="term-input",
            target_term_id="term-new-1",
        )
        assert created is True
        assert len(platform.created_relations) == 1
        assert platform.created_relations[0]["targetTermId"] == "term-new-1"

    def test_camel_case_rows_are_matched(self) -> None:
        platform = _FakePlatform()
        platform.relations = [{"relationName": "提及", "targetTermId": "term-new-1"}]
        created = platform._establish_mention_relation(
            base_id=BASE_ID,
            source_term_id="term-input",
            target_term_id="term-new-1",
        )
        assert created is False

    def test_only_source_to_target_direction(self) -> None:
        platform = _FakePlatform()
        created = platform._establish_mention_relation(
            base_id=BASE_ID,
            source_term_id="term-input",
            target_term_id="term-new-1",
        )
        assert created is True
        assert platform.created_relations == [
            {
                "sourceTermId": "term-input",
                "targetTermId": "term-new-1",
                "relationName": "提及",
            }
        ]
        relation_calls = [c for c in platform.calls if c[0] == "create_term_relation"]
        assert len(relation_calls) == 1


# ============================================================================
# 平台接线
# ============================================================================


class TestPlatformWiring:
    def test_mixin_is_exported(self) -> None:
        assert ObjectInstanceDiscoveryMixin is not None

    def test_assembled_platform_has_discover_method(self, platform: Any) -> None:
        assert hasattr(platform, "discover_object_instances_unstructured")


# ============================================================================
# RPC handler（T1：501 短路 + X-Session-Id 校验）
# ============================================================================


class _RpcFakePlatform:
    """RPC 级假平台：按 behavior 抛出对应异常。"""

    def __init__(self, behavior: str = "not_implemented") -> None:
        self.behavior = behavior

    async def discover_object_instances_unstructured(
        self,
        base_id: str,
        *,
        instance_id: str,
        object_codes: list[str],
        session_id: str,
    ) -> ObjectInstanceDiscoveryResult:
        if self.behavior == "not_implemented":
            raise NotImplementedError("existing instance discovery is not implemented")
        if self.behavior == "not_found":
            raise KeyError(f"term not found: {instance_id}")
        if self.behavior == "invalid_params":
            raise ValueError("term knowledge location is incomplete")
        if self.behavior == "permission_denied":
            raise PermissionError("no permission")
        raise RuntimeError("boom")


def _rpc_client(platform: Any) -> TestClient:
    app = FastAPI()
    app.include_router(create_rpc_router(platform=platform))
    return TestClient(app)


class TestDiscoverRpc:
    def test_normal_input_returns_501_not_implemented(self) -> None:
        client = _rpc_client(_RpcFakePlatform("not_implemented"))
        resp = client.post(
            "/api/v1/rpc/search/discoverObjectInstancesUnstructured",
            json={
                "params": {
                    "base_id": BASE_ID,
                    "instance_id": "term-input",
                    "object_codes": ["by_opportunity"],
                }
            },
            headers={"X-Session-Id": "session-1"},
        )
        body = resp.json()
        assert body["code"] == 501
        assert "not implemented" in body["message"]

    def test_missing_session_id_returns_400(self) -> None:
        client = _rpc_client(_RpcFakePlatform("not_implemented"))
        resp = client.post(
            "/api/v1/rpc/search/discoverObjectInstancesUnstructured",
            json={
                "params": {
                    "base_id": BASE_ID,
                    "instance_id": "term-input",
                    "object_codes": ["by_opportunity"],
                }
            },
        )
        body = resp.json()
        assert body["code"] == 400
        assert "X-Session-Id" in body["message"]

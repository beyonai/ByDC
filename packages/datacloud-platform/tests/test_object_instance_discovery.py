"""测试 discoverObjectInstancesUnstructured — 非结构化对象实例发现接口。

T1 骨架范围：模型默认值、①参数校验、②管道异常上抛（不降级）、③④ TODO 占位
（NotImplementedError）、平台接线可达性、RPC 501 / X-Session-Id 校验。
后续 T2/T3/T4 在同类扩展。
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from datacloud_platform.api.routers.rpc.router import create_rpc_router
from datacloud_platform.mixins import ObjectInstanceDiscoveryMixin
from datacloud_platform.models.document import DocumentContentResult
from datacloud_platform.models.shared import (
    ObjectInstanceDiscoveryHit,
    ObjectInstanceDiscoveryResult,
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
        return {"data": []}

    def create_term_relation(
        self, base_id: str, *, relation: dict[str, Any]
    ) -> dict[str, Any]:
        self.calls.append(
            ("create_term_relation", {"base_id": base_id, "relation": relation})
        )
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

"""T-46: enumerateObjectInstances RPC handler + platform 链路透传测试。

覆盖验收点（对齐 T-46 Acceptance Criteria）：
1. handler fake 注入（duck-typed fake platform）：
   - page/pageSize 钳制 >=1（0/负数 → 1）
   - filters 数组原样透传（fake 捕获收到的 filters，含嵌套 params）
   - 全缺省（object_codes/kb_resource_ids 均空，filters 有值）→ 空信封不报错
   - 信封形状 {items, total, page, pageSize}；items 元素为 ObjectInstanceListItem
   - REGISTRY["enumerateObjectInstances"] 存在且为 async handler
2. 非法 filter type → ValueError → RPC 层 _EXCEPTION_MAP → 400 invalid_params
   （TestClient 全链路，monkeypatch platform 抛 ValueError）
3. 链路层（sync）：TermBackendMixin（data_adapter/_term.py）→ knowledge
   provider（monkeypatch fake 注入，不依赖真实 SQL）：filters 透传 + 9 字段映射
4. TermMixin → TermBackend 委托链路（conftest platform fixture + FakeTermBackend）
5. none_adapters _NoopTermBackend stub（sync，返回空列表）

async 纪律：仅 handler 为 async；TermMixin/Backend/adapter/stub 全 sync。
"""

from __future__ import annotations

import inspect
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from datacloud_knowledge.contracts.term_provider_types import (
    EnumeratedObjectInstances,
    ObjectInstanceItem,
)

from datacloud_platform.adapters.data_adapter._term import TermBackendMixin
from datacloud_platform.adapters.none_adapters import _NoopTermBackend
from datacloud_platform.api.routers.rpc.handlers.search import (
    REGISTRY,
    _enumerate_object_instances,
)
from datacloud_platform.api.server import create_app
from datacloud_platform.constants import DEFAULT_BASE_ID
from datacloud_platform.models.shared import (
    ObjectInstanceListItem,
    ObjectInstanceListPage,
)

DEGREE_FILTER = {
    "type": "degree",
    "params": {"metric": "out_minus_in", "op": "gte", "value": 0},
}


class FakeRequest:
    """测试用伪 Request 对象。"""


class RecordingFakePlatform:
    """可记录调用参数的 duck-typed fake platform。

    只实现 handler 依赖的 ``enumerate_object_instances``；返回可配置信封。
    """

    def __init__(self, page: ObjectInstanceListPage | None = None) -> None:
        self._page = page
        self.calls: list[dict[str, Any]] = []

    def enumerate_object_instances(
        self,
        *,
        base_id: str = "",
        object_codes: list[str] | None = None,
        kb_resource_ids: list[str] | None = None,
        filters: list[dict[str, Any]] | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> ObjectInstanceListPage:
        """记录调用参数；返回可配置信封（默认空页）。"""
        self.calls.append(
            {
                "base_id": base_id,
                "object_codes": object_codes,
                "kb_resource_ids": kb_resource_ids,
                "filters": filters,
                "page": page,
                "page_size": page_size,
            }
        )
        if self._page is not None:
            return self._page
        return ObjectInstanceListPage(items=[], total=0, page=page, page_size=page_size)


def _make_item(i: int) -> ObjectInstanceListItem:
    """构造第 i 条枚举结果项（9 字段）。"""
    return ObjectInstanceListItem(
        instance_id=f"t{i}",
        instance_code=f"code_{i}",
        instance_name=f"实例{i}",
        object_code="Event",
        file_name=None,
        kb_resource_id=None,
        kb_id=None,
        out_degree=i,
        in_degree=1,
    )


def _call_handler(platform: RecordingFakePlatform, params: dict[str, Any]) -> Any:
    """直接调用 async handler（同 RPC dispatch 的调用方式）。"""
    return _enumerate_object_instances(
        platform,
        params,
        FakeRequest(),  # type: ignore[arg-type]
    )


# ============================================================================
# handler 层：参数钳制 + filters 透传 + 信封形状 + REGISTRY
# ============================================================================


class TestHandler:
    """enumerateObjectInstances handler 行为测试（fake 注入）。"""

    @pytest.mark.asyncio
    async def test_default_page_and_page_size(self) -> None:
        """缺省 page=1 / pageSize=20；fake 收到 1/20；信封回显 1/20。"""
        fake = RecordingFakePlatform()
        resp = await _call_handler(
            fake,
            {"object_codes": ["Event"], "kb_resource_ids": ["10000383"]},
        )

        call = fake.calls[-1]
        assert call["page"] == 1
        assert call["page_size"] == 20
        assert call["object_codes"] == ["Event"]
        assert call["kb_resource_ids"] == ["10000383"]

        data = resp.data
        assert data is not None
        assert data == {"items": [], "total": 0, "page": 1, "pageSize": 20}

    @pytest.mark.asyncio
    async def test_page_params_clamped_to_at_least_one(self) -> None:
        """钳制：page=0/pageSize=-3 → 1/1（fake 收到钳制后值，信封回显钳制值）。"""
        fake = RecordingFakePlatform()
        resp = await _call_handler(
            fake,
            {"object_codes": ["Event"], "page": 0, "pageSize": -3},
        )

        call = fake.calls[-1]
        assert call["page"] == 1
        assert call["page_size"] == 1

        data = resp.data
        assert data is not None
        assert data["page"] == 1
        assert data["pageSize"] == 1

    @pytest.mark.asyncio
    async def test_filters_passed_through_unchanged(self) -> None:
        """锚点：filters 数组原样透传（含嵌套 params），handler 不解析。"""
        filters = [
            DEGREE_FILTER,
            {"type": "degree", "params": {"metric": "out", "op": "gte", "value": 5}},
        ]
        fake = RecordingFakePlatform()
        await _call_handler(
            fake,
            {
                "object_codes": ["Event", "Document"],
                "kb_resource_ids": ["10000383"],
                "filters": filters,
                "page": 2,
                "pageSize": 10,
            },
        )

        call = fake.calls[-1]
        assert call["filters"] == filters
        assert call["filters"][0] == DEGREE_FILTER  # 深层相等（含 params）
        assert call["object_codes"] == ["Event", "Document"]
        assert call["kb_resource_ids"] == ["10000383"]
        assert call["page"] == 2
        assert call["page_size"] == 10

    @pytest.mark.asyncio
    async def test_filters_none_passed_as_none(self) -> None:
        """filters 缺省 → None 透传（不默认空数组）。"""
        fake = RecordingFakePlatform()
        await _call_handler(fake, {"object_codes": ["Event"]})

        assert fake.calls[-1]["filters"] is None

    @pytest.mark.asyncio
    async def test_absent_scope_with_filters_returns_empty_envelope(self) -> None:
        """范围全缺省（filters 有值）→ 不报错；fake 返回空页 → 信封 items=[] total=0。

        空语义本体在 knowledge 层（T-45 已测：全空 → 空结果）；handler 只
        保证参数透传 + 信封组装，此测试验证链路不炸且信封诚实。
        """
        fake = RecordingFakePlatform()
        resp = await _call_handler(
            fake,
            {"filters": [DEGREE_FILTER], "page": 1, "pageSize": 20},
        )

        call = fake.calls[-1]
        assert call["object_codes"] is None
        assert call["kb_resource_ids"] is None
        assert call["filters"] == [DEGREE_FILTER]

        data = resp.data
        assert data is not None
        assert data["items"] == []
        assert data["total"] == 0
        assert data["page"] == 1
        assert data["pageSize"] == 20

    @pytest.mark.asyncio
    async def test_envelope_shape_with_items(self) -> None:
        """信封形状：{items, total, page, pageSize}；items 为 9 字段模型。"""
        page = ObjectInstanceListPage(
            items=[_make_item(0), _make_item(1)],
            total=2,
            page=1,
            page_size=20,
        )
        fake = RecordingFakePlatform(page=page)
        resp = await _call_handler(
            fake,
            {"object_codes": ["Event"], "kb_resource_ids": ["10000383"]},
        )

        data = resp.data
        assert data is not None
        assert set(data.keys()) == {"items", "total", "page", "pageSize"}
        assert data["total"] == 2
        assert data["page"] == 1
        assert data["pageSize"] == 20
        assert len(data["items"]) == 2
        item = data["items"][0]
        assert isinstance(item, ObjectInstanceListItem)
        # 9 字段（含 out_degree/in_degree；无 score）
        assert item.instance_id == "t0"
        assert item.instance_code == "code_0"
        assert item.instance_name == "实例0"
        assert item.object_code == "Event"
        assert item.file_name is None
        assert item.kb_resource_id is None
        assert item.kb_id is None
        assert item.out_degree == 0
        assert item.in_degree == 1
        assert not hasattr(item, "score")  # 不复用检索概念

    @pytest.mark.asyncio
    async def test_base_id_defaults_to_default_base(self) -> None:
        """base_id 缺省 → DEFAULT_BASE_ID；显式传参原样透传。"""
        fake = RecordingFakePlatform()
        await _call_handler(fake, {"object_codes": ["Event"]})
        assert fake.calls[-1]["base_id"] == DEFAULT_BASE_ID

        await _call_handler(fake, {"object_codes": ["Event"], "base_id": "b1"})
        assert fake.calls[-1]["base_id"] == "b1"


class TestHandlerRegistry:
    """REGISTRY 注册测试。"""

    def test_registry_registers_enumerate_method(self) -> None:
        """REGISTRY 中存在 enumerateObjectInstances 且为 async handler。"""
        handler = REGISTRY["enumerateObjectInstances"]
        assert callable(handler)
        assert inspect.iscoroutinefunction(handler)


# ============================================================================
# 非法 filter type → ValueError → 400 invalid_params（TestClient 全链路）
# ============================================================================


class TestInvalidFilterType400:
    """非法 filter type/params 由 knowledge 层 validate 抛 ValueError →
    RPC 层 _EXCEPTION_MAP 自动映射 400 invalid_params（handler 只透传）。"""

    def test_invalid_filter_type_maps_to_400(
        self, platform: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """platform.enumerate_object_instances 抛 ValueError（模拟 knowledge
        validate 拒绝未知 filter type）→ RPC 层 _EXCEPTION_MAP 映射
        body.code=400 invalid_params（RPC 统一信封：HTTP 200 + code 字段）。"""

        def _boom(**_kwargs: Any) -> Any:
            raise ValueError("未知 filter type: 'unknown_filter'")

        monkeypatch.setattr(platform, "enumerate_object_instances", _boom)
        client = TestClient(create_app(platform))

        resp = client.post(
            "/api/v1/rpc/search/enumerateObjectInstances",
            json={
                "params": {
                    "object_codes": ["Event"],
                    "filters": [{"type": "unknown_filter", "params": {}}],
                }
            },
        )

        assert resp.status_code == 200  # RPC 统一信封：HTTP 层 200
        body = resp.json()
        assert body["code"] == 400
        assert body["message"] == "未知 filter type: 'unknown_filter'"
        assert body["data"] is None

    def test_route_is_registered_and_reachable(
        self, platform: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """路由存在且可调用（正常返回 200 信封，而非 404）。"""

        def _ok(**_kwargs: Any) -> ObjectInstanceListPage:
            return ObjectInstanceListPage(items=[], total=0, page=1, page_size=20)

        monkeypatch.setattr(platform, "enumerate_object_instances", _ok)
        client = TestClient(create_app(platform))

        resp = client.post(
            "/api/v1/rpc/search/enumerateObjectInstances",
            json={"params": {"object_codes": ["Event"]}},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["data"] == {
            "items": [],
            "total": 0,
            "page": 1,
            "pageSize": 20,
        }


# ============================================================================
# 链路层（sync）：data_adapter/_term.py → knowledge provider（fake 注入）
# ============================================================================


class TestDataAdapterLink:
    """TermBackendMixin.enumerate_object_instances 链路测试。

    monkeypatch knowledge provider（不依赖真实 SQL）；验证：
    - filters 数组原样透传（fake 捕获）
    - object_codes/kb_resource_ids None → [] 归一化（provider 签名非 Optional）
    - knowledge ObjectInstanceItem（6 字段）→ platform ObjectInstanceListItem
      （9 字段）映射，out_degree/in_degree 正确
    - page/page_size 回显
    """

    @staticmethod
    def _capture_fake() -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """构造捕获参数的 fake provider。"""
        captured: list[dict[str, Any]] = []

        def fake_provider(
            *,
            object_codes: list[str],
            kb_resource_ids: list[str],
            filters: list[dict[str, Any]] | None = None,
            page: int = 1,
            page_size: int = 20,
        ) -> EnumeratedObjectInstances:
            captured.append(
                {
                    "object_codes": object_codes,
                    "kb_resource_ids": kb_resource_ids,
                    "filters": filters,
                    "page": page,
                    "page_size": page_size,
                }
            )
            return EnumeratedObjectInstances(items=[], total=0)

        return fake_provider, captured

    def test_filters_passthrough_and_nine_field_mapping(self, monkeypatch: Any) -> None:
        """filters 原样透传；6 字段 → 9 字段映射（out_degree/in_degree 正确）。"""
        fake_provider, captured = self._capture_fake()

        def provider_with_items(
            *,
            object_codes: list[str],
            kb_resource_ids: list[str],
            filters: list[dict[str, Any]] | None = None,
            page: int = 1,
            page_size: int = 20,
        ) -> EnumeratedObjectInstances:
            captured.append(
                {
                    "object_codes": object_codes,
                    "kb_resource_ids": kb_resource_ids,
                    "filters": filters,
                    "page": page,
                    "page_size": page_size,
                }
            )
            return EnumeratedObjectInstances(
                items=[
                    ObjectInstanceItem(
                        term_id="t1",
                        term_code="code_1",
                        term_name="实例1",
                        term_type_code="Event",
                        out_degree=3,
                        in_degree=1,
                    ),
                    ObjectInstanceItem(
                        term_id="t2",
                        term_code="code_2",
                        term_name="实例2",
                        term_type_code="Event",
                        out_degree=0,
                        in_degree=5,
                    ),
                ],
                total=2,
            )

        with patch(
            "datacloud_knowledge.provider.enumerate_object_instances",
            provider_with_items,
        ):
            backend = TermBackendMixin()
            result = backend.enumerate_object_instances(
                object_codes=["Event"],
                kb_resource_ids=["10000383"],
                filters=[DEGREE_FILTER],
                page=2,
                page_size=10,
            )

        # filters 原样透传（含嵌套 params，深层相等）
        call = captured[-1]
        assert call["filters"] == [DEGREE_FILTER]
        assert call["object_codes"] == ["Event"]
        assert call["kb_resource_ids"] == ["10000383"]
        assert call["page"] == 2
        assert call["page_size"] == 10

        # 9 字段映射
        assert result.total == 2
        assert result.page == 2
        assert result.page_size == 10
        assert len(result.items) == 2
        first = result.items[0]
        assert isinstance(first, ObjectInstanceListItem)
        assert (
            first.instance_id,
            first.instance_code,
            first.instance_name,
            first.object_code,
        ) == ("t1", "code_1", "实例1", "Event")
        assert first.out_degree == 3
        assert first.in_degree == 1
        # 枚举接口不返回的 ext_attrs 派生字段 → None
        assert first.file_name is None
        assert first.kb_resource_id is None
        assert first.kb_id is None
        assert result.items[1].out_degree == 0
        assert result.items[1].in_degree == 5

    def test_none_scope_normalized_to_empty_lists(self, monkeypatch: Any) -> None:
        """范围全缺省（filters 有值）→ provider 收到 []/[]；信封空。"""
        fake_provider, captured = self._capture_fake()
        with patch(
            "datacloud_knowledge.provider.enumerate_object_instances",
            fake_provider,
        ):
            backend = TermBackendMixin()
            result = backend.enumerate_object_instances(
                object_codes=None,
                kb_resource_ids=None,
                filters=[DEGREE_FILTER],
            )

        call = captured[-1]
        assert call["object_codes"] == []
        assert call["kb_resource_ids"] == []
        # filters 不代替范围：即使有值，knowledge 层全空 → 空结果
        assert call["filters"] == [DEGREE_FILTER]
        assert result.items == []
        assert result.total == 0
        assert result.page == 1
        assert result.page_size == 20

    def test_value_error_propagates_unchanged(self, monkeypatch: Any) -> None:
        """非法 filter type：knowledge validate 抛 ValueError → 链路层不吞异常
        （400 映射由 RPC 层 _EXCEPTION_MAP 负责，data_adapter 只透传）。"""

        def _boom(**_kwargs: Any) -> Any:
            raise ValueError("未知 filter type: 'unknown_filter'")

        with patch(
            "datacloud_knowledge.provider.enumerate_object_instances",
            _boom,
        ):
            backend = TermBackendMixin()
            with pytest.raises(ValueError, match="unknown_filter"):
                backend.enumerate_object_instances(
                    object_codes=["Event"],
                    kb_resource_ids=None,
                    filters=[{"type": "unknown_filter", "params": {}}],
                )


# ============================================================================
# TermMixin → TermBackend 委托链路（conftest platform fixture）
# ============================================================================


class TestMixinLink:
    """platform.enumerate_object_instances → TermMixin → TermBackend（sync）。"""

    def test_mixin_delegates_with_filters_passthrough(self, platform: Any) -> None:
        """platform 委托链路：FakeTermBackend 收到全部参数，filters 原样。"""
        _, _, know, _, _ = platform._fakes  # type: ignore[attr-defined]

        result = platform.enumerate_object_instances(
            base_id="local-base",
            object_codes=["Event"],
            kb_resource_ids=["10000383"],
            filters=[DEGREE_FILTER],
            page=2,
            page_size=10,
        )

        call = know._enumerate_calls[-1]
        assert call["object_codes"] == ["Event"]
        assert call["kb_resource_ids"] == ["10000383"]
        assert call["filters"] == [DEGREE_FILTER]
        assert call["page"] == 2
        assert call["page_size"] == 10

        # 默认空页信封（items=[], total=0）+ 分页回显
        assert result.items == []
        assert result.total == 0
        assert result.page == 2
        assert result.page_size == 10

    def test_mixin_is_sync(self, platform: Any) -> None:
        """async 纪律：platform 层方法保持 sync（仅 RPC handler 为 async）。"""
        assert not inspect.iscoroutinefunction(platform.enumerate_object_instances)


# ============================================================================
# none_adapters stub（sync，返回空列表）
# ============================================================================


class TestNoopStub:
    """_NoopTermBackend stub 返回空页（sync，无知识库时安全降级）。"""

    def test_stub_returns_empty_page(self) -> None:
        """stub 返回 items=[] total=0，分页回显保留。"""
        stub = _NoopTermBackend()
        result = stub.enumerate_object_instances(
            object_codes=["Event"],
            kb_resource_ids=["10000383"],
            filters=[DEGREE_FILTER],
            page=3,
            page_size=50,
        )

        assert result.items == []
        assert result.total == 0
        assert result.page == 3
        assert result.page_size == 50

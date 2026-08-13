"""deleteObjectInstances RPC handler 测试。

覆盖验收点：
1. REGISTRY["deleteObjectInstances"] 注册存在且为 async handler
2. 参数校验（handler 直接调用抛 ValueError + TestClient 全链路 400 invalid_params）：
   - objectCodes 缺失 → ValueError
   - objectCodes 为空 [] → ValueError
   - objectCodes 全为空串/空白（如 ["", " "]）→ ValueError
   - 含任一空串/纯空白串（如 ["Event", ""] 或 ["Event", "  "]）→ ValueError
     （对齐 discover 的 not all 校验，空白条目不静默过滤）
3. 删除语义（duck-typed fake platform 记录调用）：
   - 默认 deleteObjectType=False：仅删实例——remove_term_co_occurrence_partners
     与 delete_term 逐实例调用；delete_object_from_all_scenes **不**调用
   - deleteObjectType=True：实例 + 对象类型都删（delete_object_from_all_scenes 每 code 一次）
   - 不存在的 object code：枚举空 → deleted=0 成功，不调用任何删除方法（幂等）
   - object_code="object" 的对象术语行被排除（不删，归 deleteObjectType 链路）
   - 循环分页：500 条 → 3 页枚举（page_size=200），全部删除
   - 孤儿词候选：主名 + 别名（list_term_names）收集后传给
     delete_orphan_vocabulary_words（sorted）
4. 响应结构：ok(data={"deleted", "deletedObjectTypes",
   "items": [{object_code, term_id, term_name}, ...]})
5. TestClient 全链路：RPC 统一信封（HTTP 200 + body.code）——400 invalid_params
   映射与路由可达；空枚举成功路径 deleted=0（幂等语义全链路验证）

async 纪律：仅 handler 为 async；fake platform 全 sync。
"""

from __future__ import annotations

import inspect
from collections import defaultdict
from typing import Any

import pytest
from fastapi.testclient import TestClient

from datacloud_platform.api.routers.rpc.handlers.search import (
    REGISTRY,
    _delete_object_instances,
)
from datacloud_platform.api.server import create_app
from datacloud_platform.models.shared import (
    ObjectInstanceListItem,
    ObjectInstanceListPage,
)


class FakeRequest:
    """测试用伪 Request 对象。"""


# ============================================================================
# duck-typed fake platform
# ============================================================================


class FakeDeletePlatform:
    """记录调用参数的 duck-typed fake platform（handler 依赖方法全覆盖）。

    枚举结果可配置且支持分页切片；list_term_names 返回可配置别名
    （dict 形式，与 TermBackend 返回约定一致）；每个删除方法记录调用参数。
    """

    def __init__(
        self,
        instances: list[ObjectInstanceListItem] | None = None,
        total: int | None = None,
        term_names: dict[str, list[dict[str, Any]]] | None = None,
    ) -> None:
        self._instances = instances or []
        self._total = total if total is not None else len(self._instances)
        self._term_names = term_names or {}
        self.calls: dict[str, list[Any]] = defaultdict(list)
        self.deleted_terms: list[str] = []
        self.deleted_object_types: list[str] = []

    # -- handler 依赖的方法（全 sync） --

    def enumerate_object_instances(
        self,
        *,
        base_id: str = "",
        object_codes: list[str] | None = None,
        kb_resource_ids: list[str] | None = None,
        page: int = 1,
        page_size: int = 200,
    ) -> ObjectInstanceListPage:
        self.calls["enumerate_object_instances"].append(
            {
                "base_id": base_id,
                "object_codes": object_codes,
                "kb_resource_ids": kb_resource_ids,
                "page": page,
                "page_size": page_size,
            }
        )
        start = (page - 1) * page_size
        items = self._instances[start : start + page_size]
        return ObjectInstanceListPage(
            items=items,
            total=self._total,
            page=page,
            page_size=page_size,
        )

    def remove_term_co_occurrence_partners(
        self, base_id: str, *, term_id: str
    ) -> list[str]:
        self.calls["remove_term_co_occurrence_partners"].append(term_id)
        return []

    def list_term_names(self, base_id: str, *, term_id: str) -> list[dict[str, Any]]:
        self.calls["list_term_names"].append(term_id)
        return list(self._term_names.get(term_id, []))

    def delete_term(self, base_id: str, *, term_id: str) -> None:
        self.calls["delete_term"].append(term_id)
        self.deleted_terms.append(term_id)

    def delete_terms_batch(self, base_id: str, *, term_ids: list[str]) -> list[str]:
        """批量删除模拟：记录调用、收集孤儿词候选（主名 + 别名）。"""
        self.calls["delete_terms_batch"].append(list(term_ids))
        self.deleted_terms.extend(term_ids)
        candidates: list[str] = []
        name_by_id = {item.instance_id: item.instance_name for item in self._instances}
        for tid in term_ids:
            name = name_by_id.get(tid)
            if name:
                candidates.append(name)
            for entry in self._term_names.get(tid, []):
                name_text = (
                    entry.get("name_text") if isinstance(entry, dict) else str(entry)
                )
                if name_text:
                    candidates.append(name_text)
        return list(dict.fromkeys(candidates))

    def delete_orphan_vocabulary_words(self, base_id: str, *, words: list[str]) -> int:
        self.calls["delete_orphan_vocabulary_words"].append(list(words))
        return len(words)

    def delete_object_from_all_scenes(self, base_id: str, object_code: str) -> None:
        self.calls["delete_object_from_all_scenes"].append(object_code)
        self.deleted_object_types.append(object_code)


def _make_item(
    instance_id: str,
    object_code: str = "Event",
    name: str | None = None,
    index: int = 0,
) -> ObjectInstanceListItem:
    """构造枚举结果项（9 字段 ObjectInstanceListItem）。"""
    return ObjectInstanceListItem(
        instance_id=instance_id,
        instance_code=f"code_{index}",
        instance_name=name or f"实例{index}",
        object_code=object_code,
        file_name=None,
        kb_resource_id=None,
        kb_id=None,
        out_degree=0,
        in_degree=0,
    )


def _two_instance_fake() -> FakeDeletePlatform:
    """装配两个实例的 fake（Event 类型 t1/t2，t2 带别名）。"""
    fake = FakeDeletePlatform(
        instances=[
            _make_item("t1", object_code="Event", name="商机A", index=1),
            _make_item("t2", object_code="Event", name="商机B", index=2),
        ],
        term_names={
            "t2": [
                {"name_text": "商机B别名"},
                {"name_text": "别名二号"},
            ]
        },
    )
    return fake


def _call_handler(platform: FakeDeletePlatform, params: dict[str, Any]) -> Any:
    """直接调用 async handler（同 RPC dispatch 的调用方式）。"""
    return _delete_object_instances(
        platform,
        params,
        FakeRequest(),  # type: ignore[arg-type]
    )


# ============================================================================
# 注册 + 参数校验
# ============================================================================


class TestRegistryAndValidation:
    """handler 注册与入参校验。"""

    @pytest.mark.asyncio
    async def test_registered_in_registry(self) -> None:
        """REGISTRY 含 deleteObjectInstances 且为 async handler。"""
        handler = REGISTRY["deleteObjectInstances"]
        assert callable(handler)
        assert inspect.iscoroutinefunction(handler)

    @pytest.mark.asyncio
    async def test_missing_object_codes_raises_value_error(self) -> None:
        """objectCodes 缺失 → ValueError（→ RPC 层 400 invalid_params）。"""
        fake = FakeDeletePlatform()
        with pytest.raises(ValueError):
            await _call_handler(fake, {})

    @pytest.mark.asyncio
    async def test_empty_object_codes_raises_value_error(self) -> None:
        """objectCodes 为空列表 → ValueError。"""
        fake = FakeDeletePlatform()
        with pytest.raises(ValueError):
            await _call_handler(fake, {"objectCodes": []})

    @pytest.mark.asyncio
    async def test_blank_only_object_codes_raises_value_error(self) -> None:
        """objectCodes 全为空串/空白 → strip 后为空 → ValueError。"""
        fake = FakeDeletePlatform()
        with pytest.raises(ValueError):
            await _call_handler(fake, {"objectCodes": ["", " "]})

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "object_codes",
        [
            ["Event", ""],  # 含空串（非全空）
            ["Event", "  "],  # 含纯空白串（非全空）
        ],
    )
    async def test_blank_entry_anywhere_raises_value_error(
        self, object_codes: list[str]
    ) -> None:
        """含任一空串/纯空白串（非全空也拒绝）→ ValueError（→ 400 invalid_params）。

        对齐 discover 的 not all 校验：["Event", ""] 不再被 strip 过滤
        静默忽略——任何空白条目都使整个请求非法，测试钉死该严格行为。
        """
        fake = FakeDeletePlatform(
            instances=[_make_item("t1", object_code="Event", name="商机A", index=1)]
        )
        with pytest.raises(ValueError):
            await _call_handler(fake, {"objectCodes": object_codes})

        # 校验失败 → 不触发任何枚举/删除调用
        assert fake.calls["enumerate_object_instances"] == []

    @pytest.mark.asyncio
    async def test_snake_case_object_codes_alias(self) -> None:
        """object_codes（snake_case）作为 objectCodes 的兼容别名。"""
        fake = FakeDeletePlatform(
            instances=[_make_item("t1", object_code="Event", name="商机A", index=1)]
        )
        resp = await _call_handler(fake, {"object_codes": ["Event"]})

        data = resp.data
        assert data is not None
        assert data["deleted"] == 1


# ============================================================================
# 删除语义
# ============================================================================


class TestDeleteSemantics:
    """默认/显式/幂等/排除对象术语行/分页/孤儿词收集。"""

    @pytest.mark.asyncio
    async def test_default_only_deletes_instances(self) -> None:
        """默认 deleteObjectType=False：仅删实例。

        批量删除（delete_terms_batch 单事务级联，含共现反向引用与词候选收集）；
        delete_object_from_all_scenes **不**被调用（object type 未删）。
        """
        fake = _two_instance_fake()
        resp = await _call_handler(fake, {"objectCodes": ["Event"]})

        # 批量删除：一次调用，term_ids 顺序与枚举一致
        assert fake.calls["delete_terms_batch"] == [["t1", "t2"]]
        # 实例删除顺序与枚举一致
        assert fake.deleted_terms == ["t1", "t2"]
        # object type 未删除
        assert fake.calls["delete_object_from_all_scenes"] == []
        assert fake.deleted_object_types == []

        data = resp.data
        assert data is not None
        assert data["deleted"] == 2
        assert data["deletedObjectTypes"] == 0

    @pytest.mark.asyncio
    async def test_delete_object_type_true_deletes_types(self) -> None:
        """deleteObjectType=True：实例 + 对象类型都删。

        delete_object_from_all_scenes 对每个规范化 object code 各调一次；
        deletedObjectTypes 等于 code 数。
        """
        fake = _two_instance_fake()
        resp = await _call_handler(
            fake,
            {"objectCodes": ["Event", "Document"], "deleteObjectType": True},
        )

        assert fake.calls["delete_object_from_all_scenes"] == ["Event", "Document"]
        assert fake.deleted_object_types == ["Event", "Document"]
        assert fake.calls["delete_terms_batch"] == [["t1", "t2"]]  # 实例仍删

        data = resp.data
        assert data is not None
        assert data["deleted"] == 2
        assert data["deletedObjectTypes"] == 2

    @pytest.mark.asyncio
    async def test_non_existent_object_code_idempotent(self) -> None:
        """不存在的 object code：枚举空 → deleted=0 成功，不报错。

        不调用任何删除方法（幂等语义）。
        """
        fake = FakeDeletePlatform()  # 空枚举
        resp = await _call_handler(fake, {"objectCodes": ["ghost_code"]})

        assert fake.calls["delete_term"] == []
        assert fake.calls["delete_orphan_vocabulary_words"] == []
        assert fake.calls["delete_object_from_all_scenes"] == []

        data = resp.data
        assert data is not None
        assert data["deleted"] == 0
        assert data["deletedObjectTypes"] == 0
        assert data["items"] == []

    @pytest.mark.asyncio
    async def test_object_term_rows_excluded(self) -> None:
        """object_code='object' 的对象术语行被排除（不删实例）。

        其删除归 deleteObjectType=True 的 delete_object_from_all_scenes 链路。
        """
        fake = FakeDeletePlatform(
            instances=[
                _make_item(
                    "obj_term_1", object_code="object", name="对象术语", index=1
                ),
                _make_item("t1", object_code="Event", name="商机A", index=2),
            ]
        )
        resp = await _call_handler(fake, {"objectCodes": ["Event"]})

        # 仅 Event 实例被删除；对象术语行被跳过
        assert fake.calls["delete_terms_batch"] == [["t1"]]
        data = resp.data
        assert data is not None
        assert data["deleted"] == 1
        assert [i["term_id"] for i in data["items"]] == ["t1"]

    @pytest.mark.asyncio
    async def test_pagination_loop_500_instances(self) -> None:
        """循环分页：500 条（page_size=200）→ 3 页枚举，全部删除。"""
        instances = [
            _make_item(f"t{i}", object_code="Event", name=f"实例{i}", index=i)
            for i in range(500)
        ]
        fake = FakeDeletePlatform(instances=instances, total=500)
        resp = await _call_handler(fake, {"objectCodes": ["Event"]})

        pages = [c["page"] for c in fake.calls["enumerate_object_instances"]]
        assert pages == [1, 2, 3]  # 200 + 200 + 100
        assert fake.calls["delete_terms_batch"] == [[f"t{i}" for i in range(500)]]
        data = resp.data
        assert data is not None
        assert data["deleted"] == 500

    @pytest.mark.asyncio
    async def test_orphan_words_collected_main_plus_aliases(self) -> None:
        """孤儿词候选 = 主名 + 别名（list_term_names），sorted 后传给
        delete_orphan_vocabulary_words。"""
        fake = _two_instance_fake()  # t2 带两个别名
        await _call_handler(fake, {"objectCodes": ["Event"]})

        # sorted 按 Unicode 码点：'别'(U+522B) < '商'(U+5546)；
        # 同前缀 '商机' 下 'A' < 'B' < '别'(U+522B)
        assert fake.calls["delete_orphan_vocabulary_words"] == [
            ["别名二号", "商机A", "商机B", "商机B别名"]
        ]

    @pytest.mark.asyncio
    async def test_orphan_words_not_called_when_no_instances(self) -> None:
        """无实例 → 无孤儿词候选 → delete_orphan_vocabulary_words 不调用。"""
        fake = FakeDeletePlatform()
        await _call_handler(fake, {"objectCodes": ["Event"]})
        assert fake.calls["delete_orphan_vocabulary_words"] == []


# ============================================================================
# 响应结构
# ============================================================================


class TestResponseStructure:
    """响应信封 {deleted, deletedObjectTypes, items}。"""

    @pytest.mark.asyncio
    async def test_envelope_keys(self) -> None:
        """信封恰含 deleted / deletedObjectTypes / items 三键。"""
        fake = _two_instance_fake()
        resp = await _call_handler(fake, {"objectCodes": ["Event"]})

        data = resp.data
        assert data is not None
        assert set(data.keys()) == {"deleted", "deletedObjectTypes", "items"}

    @pytest.mark.asyncio
    async def test_item_fields(self) -> None:
        """items 元素恰含 object_code / term_id / term_name，值与枚举一致。"""
        fake = _two_instance_fake()
        resp = await _call_handler(fake, {"objectCodes": ["Event"]})

        data = resp.data
        assert data is not None
        assert data["items"] == [
            {"object_code": "Event", "term_id": "t1", "term_name": "商机A"},
            {"object_code": "Event", "term_id": "t2", "term_name": "商机B"},
        ]

    @pytest.mark.asyncio
    async def test_base_id_passed_through(self) -> None:
        """base_id 透传到枚举与删除调用（默认 DEFAULT_BASE_ID）。"""
        fake = _two_instance_fake()
        await _call_handler(fake, {"base_id": "custom-base", "objectCodes": ["Event"]})

        assert fake.calls["enumerate_object_instances"][0]["base_id"] == "custom-base"


# ============================================================================
# TestClient 全链路：400 映射 + 路由可达
# ============================================================================


class TestRpcIntegration:
    """RPC 统一信封（HTTP 200 + body.code）下的错误映射与路由注册。"""

    def test_missing_object_codes_maps_to_400(
        self, platform: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """缺 objectCodes → handler ValueError → RPC _EXCEPTION_MAP → 400。"""
        client = TestClient(create_app(platform))
        resp = client.post(
            "/api/v1/rpc/search/deleteObjectInstances",
            json={"params": {}},
        )

        assert resp.status_code == 200  # RPC 统一信封
        body = resp.json()
        assert body["code"] == 400
        assert body["message"] == "objectCodes 必须为非空字符串列表，且不允许空串"
        assert body["data"] is None

    def test_empty_object_codes_maps_to_400(
        self, platform: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """objectCodes=[] → 400 invalid_params。"""
        client = TestClient(create_app(platform))
        resp = client.post(
            "/api/v1/rpc/search/deleteObjectInstances",
            json={"params": {"objectCodes": []}},
        )

        body = resp.json()
        assert body["code"] == 400
        assert body["data"] is None

    def test_blank_object_codes_maps_to_400(
        self, platform: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """objectCodes 全为空串/空白 → 400 invalid_params。"""
        client = TestClient(create_app(platform))
        resp = client.post(
            "/api/v1/rpc/search/deleteObjectInstances",
            json={"params": {"objectCodes": ["", " "]}},
        )

        body = resp.json()
        assert body["code"] == 400
        assert body["data"] is None

    def test_route_reachable_idempotent_success(
        self, platform: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """路由可达 + 空枚举幂等成功（HTTP 200 信封，deleted=0）。

        使用 conftest 的 FakeTermBackend 装配——枚举返回空页，不触发
        新增删除方法；deleteObjectType 默认 False 不触碰 ontology。
        """
        client = TestClient(create_app(platform))
        resp = client.post(
            "/api/v1/rpc/search/deleteObjectInstances",
            # conftest 注册的 base 为 "local-base"；显式传入避免
            # DEFAULT_BASE_ID("BYCLAW_DATACLOUD") 未注册 → KeyError 404
            json={"params": {"base_id": "local-base", "objectCodes": ["ghost_code"]}},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 200  # ok 默认 code=200（成功）
        data = body["data"]
        assert data == {"deleted": 0, "deletedObjectTypes": 0, "items": []}

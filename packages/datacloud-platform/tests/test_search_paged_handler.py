"""searchObjectInstancesUnstructuredPaged RPC handler 单元测试。

验证点（对齐 T-39 Acceptance Criteria）：
1. page/pageSize 钳制换算 → offset=(page-1)*pageSize, limit=pageSize
2. 锚点：fake platform 收到 top_k == offset+limit+1（哨兵 +1）
3. 锚点：fake platform 收到 query=用户输入、queries=None、enable_chunk_recall=False
4. 入参屏蔽：客户端传 queries / top_k / enable_chunk_recall 一律忽略
5. 融合后切片 [offset:offset+limit] + has_more 单 bool 哨兵
6. 信封形状 {results: {kw: [...]}, pagination: {page, pageSize, has_more}}
7. REGISTRY 注册 + async handler
8. 边界：offset 越界不报错、空结果、哨兵退化不崩溃、非法输入钳制

注入方式：duck-typed fake platform（可记录调用参数），不拉真平台。
"""

from __future__ import annotations

import inspect
from typing import Any

import pytest

from datacloud_platform.api.routers.rpc.handlers.search import (
    REGISTRY,
    _search_object_instances_unstructured_paged,
)
from datacloud_platform.constants import DEFAULT_BASE_ID
from datacloud_platform.models.shared import (
    ObjectInstanceHit,
    ObjectInstanceSearchResult,
)


class FakeRequest:
    """测试用伪 Request 对象。"""


class RecordingFakePlatform:
    """可记录调用参数的 duck-typed fake platform。

    只实现 handler 依赖的 ``search_object_instances_unstructured``，
    返回可配置的 hits 池（模拟 RRF 融合后的单 keyword 结果列表）。
    """

    def __init__(self, pool: list[ObjectInstanceHit] | None = None) -> None:
        self._pool = list(pool or [])
        self.calls: list[dict[str, Any]] = []

    async def search_object_instances_unstructured(
        self,
        *,
        base_id: str = "",
        object_codes: list[str] | None = None,
        query: str | None = None,
        queries: list[str] | None = None,
        top_k: int = 20,
        enable_chunk_recall: bool = True,
    ) -> ObjectInstanceSearchResult:
        """记录调用参数；query 为空时返回空 results（对齐实现层行为）。"""
        self.calls.append(
            {
                "base_id": base_id,
                "object_codes": object_codes,
                "query": query,
                "queries": queries,
                "top_k": top_k,
                "enable_chunk_recall": enable_chunk_recall,
            }
        )
        if not query or not query.strip():
            return ObjectInstanceSearchResult(results={})
        return ObjectInstanceSearchResult(results={query.strip(): list(self._pool)})


def _make_hit(i: int) -> ObjectInstanceHit:
    """构造第 i 条命中（排名即 i，越小越靠前）。"""
    return ObjectInstanceHit(
        instance_id=f"t{i}",
        instance_code=f"code_{i}",
        instance_name=f"实例{i}",
        object_code="by_opportunity",
        file_name=f"/docs/{i}.md",
        kb_resource_id=None,
        kb_id=None,
        score=float(100 - i),
    )


async def _call_handler(platform: RecordingFakePlatform, params: dict[str, Any]) -> Any:
    """直接调用 async handler（同 RPC dispatch 的调用方式）。"""
    return await _search_object_instances_unstructured_paged(
        platform,
        params,
        FakeRequest(),  # type: ignore[arg-type]
    )


# ============================================================================
# 分页行为测试
# ============================================================================


class TestPagedHandler:
    """searchObjectInstancesUnstructuredPaged handler 行为测试。"""

    @pytest.mark.asyncio
    async def test_page1_returns_first_page_with_has_more(self) -> None:
        """page=1, pageSize=5，池 6 条 → results 5 条 + has_more=True。"""
        fake = RecordingFakePlatform(pool=[_make_hit(i) for i in range(6)])
        resp = await _call_handler(fake, {"query": "机会"})

        data = resp.data
        assert data is not None
        assert list(data["results"].keys()) == ["机会"]
        ids = [h.instance_id for h in data["results"]["机会"]]
        assert ids == ["t0", "t1", "t2", "t3", "t4"]
        assert data["pagination"] == {"page": 1, "pageSize": 5, "has_more": True}

    @pytest.mark.asyncio
    async def test_page2_slices_second_page_no_has_more(self) -> None:
        """page=2, pageSize=5，池 10 条 → 第 2 页正确 + has_more=False。"""
        fake = RecordingFakePlatform(pool=[_make_hit(i) for i in range(10)])
        resp = await _call_handler(fake, {"query": "机会", "page": 2})

        data = resp.data
        assert data is not None
        ids = [h.instance_id for h in data["results"]["机会"]]
        assert ids == ["t5", "t6", "t7", "t8", "t9"]
        assert data["pagination"] == {"page": 2, "pageSize": 5, "has_more": False}

    @pytest.mark.asyncio
    async def test_fetch_top_is_offset_plus_limit_plus_one(self) -> None:
        """锚点：page=2, pageSize=5 → fake 收到 top_k == 11。"""
        fake = RecordingFakePlatform(pool=[_make_hit(i) for i in range(20)])
        await _call_handler(fake, {"query": "机会", "page": 2})

        assert fake.calls[-1]["top_k"] == 11

    @pytest.mark.asyncio
    async def test_internal_call_passes_sentence_mode_params(self) -> None:
        """锚点：fake 收到 query=用户输入、queries=None、enable_chunk_recall=False。"""
        fake = RecordingFakePlatform(pool=[_make_hit(i) for i in range(6)])
        await _call_handler(fake, {"query": "商机", "page": 1, "pageSize": 3})

        call = fake.calls[-1]
        assert call["query"] == "商机"
        assert call["queries"] is None
        assert call["enable_chunk_recall"] is False

    @pytest.mark.asyncio
    async def test_shields_queries_top_k_and_chunk_recall_inputs(self) -> None:
        """入参屏蔽：客户端传 queries/top_k/enable_chunk_recall 被忽略。"""
        fake = RecordingFakePlatform(pool=[_make_hit(i) for i in range(6)])
        resp = await _call_handler(
            fake,
            {
                "query": "商机",
                "queries": ["不应生效"],
                "top_k": 999,
                "enable_chunk_recall": True,
            },
        )

        call = fake.calls[-1]
        assert call["queries"] is None
        assert call["top_k"] == 6  # page=1, pageSize=5 → 0+5+1
        assert call["enable_chunk_recall"] is False
        data = resp.data
        assert data is not None
        assert list(data["results"].keys()) == ["商机"]

    @pytest.mark.asyncio
    async def test_base_id_defaults_and_object_codes_passthrough(self) -> None:
        """base_id 默认 DEFAULT_BASE_ID；object_codes 原样透传。"""
        fake = RecordingFakePlatform(pool=[_make_hit(i) for i in range(6)])
        await _call_handler(
            fake,
            {"query": "商机", "object_codes": ["by_opportunity"], "base_id": "b1"},
        )
        call = fake.calls[-1]
        assert call["base_id"] == "b1"
        assert call["object_codes"] == ["by_opportunity"]

        await _call_handler(fake, {"query": "商机"})
        assert fake.calls[-1]["base_id"] == DEFAULT_BASE_ID


# ============================================================================
# 边界行为测试
# ============================================================================


class TestPagedHandlerBoundaries:
    """边界行为：越界、空结果、哨兵退化、非法输入。"""

    @pytest.mark.asyncio
    async def test_offset_out_of_range_returns_empty_without_error(self) -> None:
        """page=100（offset 越界）→ 空列表 + has_more=False，不报错。"""
        fake = RecordingFakePlatform(pool=[_make_hit(i) for i in range(6)])
        resp = await _call_handler(fake, {"query": "机会", "page": 100})

        data = resp.data
        assert data is not None
        assert data["results"]["机会"] == []
        assert data["pagination"] == {
            "page": 100,
            "pageSize": 5,
            "has_more": False,
        }

    @pytest.mark.asyncio
    async def test_empty_results_returns_empty_envelope(self) -> None:
        """空结果（fake 返回空 results）→ results={} + pagination 正常。"""
        fake = RecordingFakePlatform(pool=[])
        resp = await _call_handler(fake, {"query": ""})

        data = resp.data
        assert data is not None
        assert data["results"] == {}
        assert data["pagination"] == {"page": 1, "pageSize": 5, "has_more": False}

    @pytest.mark.asyncio
    async def test_sentinel_pool_exactly_fetch_top_does_not_crash(self) -> None:
        """哨兵退化：池恰好 fetch_top 条 → has_more=True 但不越界、不崩溃。"""
        # page=1, pageSize=5 → fetch_top=6；池恰好 6 条
        fake = RecordingFakePlatform(pool=[_make_hit(i) for i in range(6)])
        resp = await _call_handler(fake, {"query": "机会"})

        data = resp.data
        assert data is not None
        assert len(data["results"]["机会"]) == 5
        assert data["pagination"]["has_more"] is True

    @pytest.mark.asyncio
    async def test_invalid_page_params_are_clamped(self) -> None:
        """非法输入钳制：page=0 → 当 1，pageSize=0 → 当 1。"""
        fake = RecordingFakePlatform(pool=[_make_hit(i) for i in range(6)])
        resp = await _call_handler(fake, {"query": "机会", "page": 0, "pageSize": 0})

        data = resp.data
        assert data is not None
        assert data["pagination"] == {"page": 1, "pageSize": 1, "has_more": True}
        assert len(data["results"]["机会"]) == 1
        assert fake.calls[-1]["top_k"] == 2  # offset=0, limit=1 → fetch_top=2


# ============================================================================
# REGISTRY 测试
# ============================================================================


class TestPagedHandlerRegistry:
    """REGISTRY 注册测试。"""

    def test_registry_registers_paged_method(self) -> None:
        """REGISTRY 中存在 searchObjectInstancesUnstructuredPaged 且可调用。"""
        handler = REGISTRY["searchObjectInstancesUnstructuredPaged"]
        assert callable(handler)
        assert inspect.iscoroutinefunction(handler)

    def test_legacy_method_still_registered(self) -> None:
        """旧接口 searchObjectInstancesUnstructured 仍在 REGISTRY 中（零改动）。"""
        assert "searchObjectInstancesUnstructured" in REGISTRY
        assert callable(REGISTRY["searchObjectInstancesUnstructured"])

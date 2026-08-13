"""测试 discoverObjectInstancesUnstructured — 非结构化对象实例发现接口。

演进：模型默认值、参数校验、管道异常上抛（不降级）；词典锚定（快路命中 + 反查兜底）
与 LLM 抽取（优先类型枚举 + 允许自动发现）已落地替换占位；RPC 错误码映射全套；
会话 ID 改由全局请求上下文提供（middleware 注入 InvocationContext），不依赖 X-Session-Id 请求头；
501 not_implemented 语义已收口移除（回归断言同步删除）。
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from datacloud_data_sdk.context import InvocationContext
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
        self.vocab_words: list[str] = []
        self.term_search_results: dict[str, Any] = {"data": [], "totalCount": 0}
        self.term_exact_results: dict[str, Any] = {"data": [], "totalCount": 0}
        self.name_rows: list[dict[str, Any]] = []
        self.term_batch_results: dict[str, dict[str, Any]] = {}

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

    def list_vocabulary(self, base_id: str) -> list[str]:
        self.calls.append(("list_vocabulary", {"base_id": base_id}))
        return list(self.vocab_words)

    def search_terms(self, base_id: str, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("search_terms", {"base_id": base_id, **kwargs}))
        return self.term_search_results

    def search_terms_batch(self, base_id: str, **kwargs: Any) -> dict[str, Any]:
        """批量精确检索：显式配置 term_batch_results 时按其分发；
        否则默认每个 keyword 返回 term_search_results（单词场景简化）。"""
        self.calls.append(("search_terms_batch", {"base_id": base_id, **kwargs}))
        if self.term_batch_results:
            return dict(self.term_batch_results)
        keywords = kwargs.get("keywords") or []
        return {kw: dict(self.term_search_results) for kw in keywords}

    def search_terms_exact(self, base_id: str, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("search_terms_exact", {"base_id": base_id, **kwargs}))
        return self.term_exact_results

    def list_term_names(self, base_id: str, **kwargs: Any) -> list[dict[str, Any]]:
        self.calls.append(("list_term_names", {"base_id": base_id, **kwargs}))
        return list(self.name_rows)

    def list_term_relations(self, base_id: str, **kwargs: Any) -> dict[str, Any]:
        """分页感知的假实现：按 page_index/page_size 切片并返回分页元信息。

        对齐真实 reader（opengauss _relation.list_term_relations）的响应结构：
        ``{data, pageIndex, pageSize, totalCount, totalPages}``，page_size 上限 100。
        """
        self.calls.append(("list_term_relations", {"base_id": base_id, **kwargs}))
        page_index = int(kwargs.get("page_index", 1))
        page_size = min(int(kwargs.get("page_size", 20)), 100)
        total = len(self.relations)
        start = (page_index - 1) * page_size
        batch = list(self.relations[start : start + page_size])
        total_pages = (total + page_size - 1) // page_size if total else 0
        return {
            "data": batch,
            "pageIndex": page_index,
            "pageSize": page_size,
            "totalCount": total,
            "totalPages": total_pages,
        }

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

    def get_object_detail(
        self, _base_id: str, object_code: str
    ) -> dict[str, Any] | None:
        return {
            "objectCode": object_code,
            "objectName": "商机",
            "extProperty": {
                "kb_resource_id": "10001",
                "kb_id": "201",
                "kb_directory": "/商机目录",
            },
        }

    # ── 抽取/直写/裁决/共现协议能力（默认实现；测试用 monkeypatch 覆盖具体行为）──

    def get_term_type(
        self, base_id: str, *, library_id: str, type_code: str
    ) -> dict[str, Any] | None:
        self.calls.append(
            (
                "get_term_type",
                {"base_id": base_id, "library_id": library_id, "type_code": type_code},
            )
        )
        return None

    def batch_create_vocabulary(self, base_id: str, *, words: list[str]) -> None:
        self.calls.append(
            ("batch_create_vocabulary", {"base_id": base_id, "words": words})
        )
        self.vocab_words.extend(words)

    def create_term_name(self, base_id: str, *, name: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(("create_term_name", {"base_id": base_id, "name": name}))
        return {"nameId": "name-x"}

    def ensure_term_type(self, *, base_id: str, type_code: str, type_name: str) -> None:
        self.calls.append(
            (
                "ensure_term_type",
                {"base_id": base_id, "type_code": type_code, "type_name": type_name},
            )
        )

    def create_term(self, base_id: str, *, term: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(("create_term", {"base_id": base_id, "term": term}))
        return {"created": 1, "updated": 0, "skipped": 0, "term_ids": ["term-ad-1"]}

    def import_terms(
        self,
        base_id: str,
        *,
        library_id: str,
        terms: list[dict[str, Any]],
        backfill: bool = False,
    ) -> dict[str, Any]:
        self.calls.append(
            (
                "import_terms",
                {
                    "base_id": base_id,
                    "library_id": library_id,
                    "terms": terms,
                    "backfill": backfill,
                },
            )
        )
        return {
            "created": len(terms),
            "updated": 0,
            "skipped": 0,
            "term_ids": [f"term-ad-{i}" for i in range(len(terms))],
            "errors": [],
        }

    def create_term_knowledge(
        self, base_id: str, *, knowledge: dict[str, Any]
    ) -> dict[str, Any]:
        self.calls.append(
            ("create_term_knowledge", {"base_id": base_id, "knowledge": knowledge})
        )
        return {"knowledgeId": "know-x"}

    def update_term_co_occurrence(
        self, base_id: str, *, term_id: str, patch: dict[str, int]
    ) -> None:
        self.calls.append(
            (
                "update_term_co_occurrence",
                {"base_id": base_id, "term_id": term_id, "patch": patch},
            )
        )

    def get_term_detail(
        self, base_id: str, *, library_id: str, term_id: str
    ) -> dict[str, Any] | None:
        self.calls.append(
            (
                "get_term_detail",
                {"base_id": base_id, "library_id": library_id, "term_id": term_id},
            )
        )
        return {"term_id": term_id, "term_tags": {}}


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
# 参数校验
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
            )

    @pytest.mark.asyncio
    async def test_missing_object_codes_raises_value_error(self) -> None:
        platform = _FakePlatform()
        with pytest.raises(ValueError, match="object_codes"):
            await platform.discover_object_instances_unstructured(
                BASE_ID,
                instance_id="term-input",
                object_codes=[],
            )


# ============================================================================
# 管道异常上抛（无降级）
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
            )


# ============================================================================
# 词典锚定：快路命中 + 反查兜底 + 结果分发
# ============================================================================


def _mention(name: str, object_code: str = "by_opportunity") -> dict[str, Any]:
    return {"term_name": name, "object_code": object_code, "evidence": None}


def _term_row(
    term_id: str, term_name: str, term_type: str = "by_opportunity"
) -> dict[str, Any]:
    return {
        "term_id": term_id,
        "term_code": f"code-{term_id}",
        "term_name": term_name,
        "term_type": term_type,
        "library_id": BASE_ID,
    }


class TestAnchorExistingDiscovery:
    @pytest.fixture(autouse=True)
    def _reset_cache(self) -> Any:
        discovery_module.invalidate_vocabulary_cache()
        yield
        discovery_module.invalidate_vocabulary_cache()

    def test_unique_surface_hit_builds_existing(self) -> None:
        """唯一词面相等命中 → existing hit（is_new=False，evidence=mention）。"""
        platform = _FakePlatform()
        platform.vocab_words = ["张三"]
        platform.term_search_results = {
            "total": 1,
            "items": [_term_row("t1", "张三")],
        }
        result = platform._discover_existing_object_instances(
            BASE_ID, mentions=[_mention("张三")], object_codes=["by_opportunity"]
        )
        assert len(result.existing) == 1
        row = result.existing[0]
        assert row["term_id"] == "t1"
        assert row["term_name"] == "张三"
        assert row["evidence"] == "张三"
        hit = discovery_module._build_existing_hit(row)
        assert hit.instance_id == "t1"
        assert hit.is_new is False
        assert hit.evidence == "张三"

    def test_duplicate_same_name_produces_ambiguity_candidates(self) -> None:
        """词面相等命中 ≥2 term → 歧义候选队列，不直接建 hit。"""
        platform = _FakePlatform()
        platform.vocab_words = ["张三"]
        platform.term_search_results = {
            "total": 2,
            "items": [_term_row("t1", "张三"), _term_row("t2", "张三")],
        }
        result = platform._discover_existing_object_instances(
            BASE_ID, mentions=[_mention("张三")], object_codes=["by_opportunity"]
        )
        assert result.existing == []
        assert len(result.ambiguity) == 1
        assert result.ambiguity[0]["mention"] == "张三"
        assert [t["term_id"] for t in result.ambiguity[0]["terms"]] == ["t1", "t2"]
        assert result.unanchored == []

    def test_exact_miss_with_substring_overlap_is_unanchored(self) -> None:
        """精确反查落空（即使与已有 term 子串重叠）→ 未锚定走新实例创建。

        v3 语义（用户拍板）：命中词表后必须精确找到 term 才算命中；
        精确找不到 → 当未命中，**不做 BM25/ilike 混合检索兜底**（synonym 桶恒空）。
        """
        platform = _FakePlatform()
        platform.vocab_words = ["苹果公司", "苹果"]
        platform.term_search_results = {"total": 0, "items": []}
        result = platform._discover_existing_object_instances(
            BASE_ID, mentions=[_mention("苹果公司")], object_codes=["by_opportunity"]
        )
        assert result.existing == []
        assert result.synonym == []
        assert result.unanchored == [_mention("苹果公司")]

    def test_no_hit_produces_unanchored(self) -> None:
        """mention 不在词典 → 未锚定（走新实例创建），不产出已有 hit。"""
        platform = _FakePlatform()
        platform.vocab_words = ["苹果"]
        result = platform._discover_existing_object_instances(
            BASE_ID, mentions=[_mention("华为")], object_codes=["by_opportunity"]
        )
        assert result.existing == []
        assert result.ambiguity == []
        assert result.synonym == []
        assert result.unanchored == [_mention("华为")]

    def test_cache_hit_but_reverse_lookup_miss_falls_back_to_unanchored(self) -> None:
        """缓存命中但反查落空（词已删/改名/孤儿词）→ 未锚定，不报错、不建实例。"""
        platform = _FakePlatform()
        platform.vocab_words = ["孤儿词"]
        platform.term_search_results = {"total": 0, "items": []}
        platform.name_rows = []
        result = platform._discover_existing_object_instances(
            BASE_ID, mentions=[_mention("孤儿词")], object_codes=["by_opportunity"]
        )
        assert result.existing == []
        assert result.unanchored == [_mention("孤儿词")]

    def test_exact_miss_with_alias_only_is_unanchored(self) -> None:
        """仅别名（TermName）存在而 term_name 精确查不到 → 未锚定走新实例创建。

        v3 语义：删除 ilike 别名反查兜底（list_term_names 不再参与锚定），
        精确找不到即未命中。
        """
        platform = _FakePlatform()
        platform.vocab_words = ["苹果公司"]
        platform.term_search_results = {"total": 0, "items": []}
        platform.name_rows = [
            {"name_id": "n1", "term_id": "t9", "name_text": "苹果公司"}
        ]
        result = platform._discover_existing_object_instances(
            BASE_ID, mentions=[_mention("苹果公司")], object_codes=["by_opportunity"]
        )
        assert result.existing == []
        assert result.unanchored == [_mention("苹果公司")]
        # 锚定只走一次批量精确查询，不再触发 list_term_names / 逐词 search_terms
        assert not any(c[0] == "list_term_names" for c in platform.calls)
        assert not any(c[0] == "search_terms" for c in platform.calls)

    def test_batch_exact_single_query_all_mentions(self) -> None:
        """全部 mentions 一次性 search_terms_batch(exact)，不逐词串行反查。

        命中词表去重保序进 keywords；未命中词表的不参与查询；不再调用
        search_terms / list_term_names 模糊兜底路径。
        """
        platform = _FakePlatform()
        platform.vocab_words = ["张三", "李四"]
        platform.term_search_results = {"total": 0, "items": []}
        platform.term_batch_results = {
            "张三": {"total": 1, "items": [_term_row("t1", "张三")]},
            "李四": {"total": 1, "items": [_term_row("t2", "李四")]},
        }
        result = platform._discover_existing_object_instances(
            BASE_ID,
            mentions=[
                _mention("张三"),
                _mention("张三"),
                _mention("李四"),
                _mention("王五"),
            ],
            object_codes=["by_opportunity"],
        )
        # 重复 mention 各自产出已有实例候选（与逐词语义一致）
        assert [r["term_id"] for r in result.existing] == ["t1", "t1", "t2"]
        assert result.unanchored == [_mention("王五")]

        batch_calls = [c for c in platform.calls if c[0] == "search_terms_batch"]
        assert len(batch_calls) == 1
        kwargs = batch_calls[0][1]
        assert kwargs["keywords"] == ["张三", "李四"]  # 去重保序，未命中词不查询
        assert kwargs["query_type"] == "exact"
        # 模糊兜底路径（逐词 search_terms / ilike list_term_names）不再触发
        assert not any(c[0] == "search_terms" for c in platform.calls)
        assert not any(c[0] == "list_term_names" for c in platform.calls)

    def test_blank_mention_is_skipped(self) -> None:
        platform = _FakePlatform()
        platform.vocab_words = ["苹果"]
        platform.term_search_results = {
            "total": 1,
            "items": [_term_row("t1", "苹果")],
        }
        result = platform._discover_existing_object_instances(
            BASE_ID,
            mentions=[_mention("  "), _mention("苹果")],
            object_codes=["by_opportunity"],
        )
        assert len(result.existing) == 1
        assert result.existing[0]["term_name"] == "苹果"
        assert len(result.unanchored) == 0


# ============================================================================
# 新实例创建 + term_id 强校验
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
        )
        assert term_id == "term-strict"


# ============================================================================
# 文件登记
# ============================================================================


class TestRegisterObjectFile:
    @pytest.mark.asyncio
    async def test_registers_file_with_session_and_strict_term_id(self) -> None:
        platform = _FakePlatform()
        # 会话 ID 由全局请求上下文提供（middleware 注入 InvocationContext）
        with InvocationContext(session_id="session-1"):
            await platform._register_object_file(
                base_id=BASE_ID,
                object_code="by_opportunity",
                term_name="张三",
                term_id="term-new-1",
                action_result={
                    "records": [
                        {
                            "termId": "term-new-1",
                            "fileName": "张三.md",
                            "filePath": "/实际目录/张三.md",
                        }
                    ]
                },
            )
        assert len(platform.object_files) == 1
        entry = platform.object_files[0][0]
        assert entry["sessionId"] == "session-1"
        assert entry["objectName"] == "商机"
        assert entry["objectCode"] == "by_opportunity"
        assert entry["fileName"] == "张三.md"
        assert entry["filePath"] == "/实际目录/张三.md"
        assert entry["statusCd"] == "待整理"
        ext = json.loads(entry["extContent"])
        assert ext["kb_resource_id"] == "10001"
        assert ext["kb_id"] == "201"
        assert ext["kb_directory"] == "/商机目录"
        assert ext["term_id"] == "term-new-1"

    @pytest.mark.asyncio
    async def test_registers_file_falls_back_to_strict_term_id(self) -> None:
        platform = _FakePlatform()
        await platform._register_object_file(
            base_id=BASE_ID,
            object_code="by_opportunity",
            term_name="张三",
            term_id="term-new-1",
            action_result={"records": [{"fileName": "张三.md"}]},
        )
        entry = platform.object_files[0][0]
        ext = json.loads(entry["extContent"])
        assert ext["term_id"] == "term-new-1"


# ============================================================================
# 「提及」关系（源→目标，单向幂等）
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
                "relationCategory": "BUSINESS",
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
                "relationCategory": "BUSINESS",
            }
        ]
        relation_calls = [c for c in platform.calls if c[0] == "create_term_relation"]
        assert len(relation_calls) == 1

    # ── 分页拉全：list_term_relations 默认 page_size=20 只查首页 ──────────────

    @staticmethod
    def _mention_rows(count: int, target: str = "") -> list[dict[str, Any]]:
        """构造 count 条源=term-input 的「提及」关系行（目标可自定义末条）。"""
        rows = [
            {
                "relation_name": "提及",
                "source_term_id": "term-input",
                "target_term_id": f"term-other-{i}",
            }
            for i in range(count)
        ]
        if target:
            rows[-1] = {
                "relation_name": "提及",
                "source_term_id": "term-input",
                "target_term_id": target,
            }
        return rows

    def test_target_beyond_first_page_skips_create(self) -> None:
        """>20 条提及关系、目标落在第 2 页：分页拉全后命中，不重复创建。"""
        platform = _FakePlatform()
        platform.relations = self._mention_rows(25, target="term-new-1")
        created = platform._establish_mention_relation(
            base_id=BASE_ID,
            source_term_id="term-input",
            target_term_id="term-new-1",
        )
        assert created is False
        assert platform.created_relations == []

    def test_pagination_pulls_all_pages(self) -> None:
        """断言分页拉全：page_size=100 拉满、page_index 递增直到末尾。"""
        platform = _FakePlatform()
        platform.relations = self._mention_rows(125)
        platform._establish_mention_relation(
            base_id=BASE_ID,
            source_term_id="term-input",
            target_term_id="term-missing",
        )
        list_calls = [c for c in platform.calls if c[0] == "list_term_relations"]
        assert [c[1].get("page_index") for c in list_calls] == [1, 2]
        assert all(c[1].get("page_size") == 100 for c in list_calls)

    def test_different_target_across_pages_still_creates(self) -> None:
        """120 条提及均指向其他目标：新目标照建且仅一次。"""
        platform = _FakePlatform()
        platform.relations = self._mention_rows(120)
        created = platform._establish_mention_relation(
            base_id=BASE_ID,
            source_term_id="term-input",
            target_term_id="term-new-1",
        )
        assert created is True
        create_calls = [c for c in platform.calls if c[0] == "create_term_relation"]
        assert len(create_calls) == 1
        assert create_calls[0][1]["relation"]["targetTermId"] == "term-new-1"

    def test_empty_relations_single_page(self) -> None:
        """空关系集只查一页即停（无多余分页请求）。"""
        platform = _FakePlatform()
        created = platform._establish_mention_relation(
            base_id=BASE_ID,
            source_term_id="term-input",
            target_term_id="term-new-1",
        )
        assert created is True
        list_calls = [c for c in platform.calls if c[0] == "list_term_relations"]
        assert [c[1].get("page_index") for c in list_calls] == [1]


# ============================================================================
# 平台接线
# ============================================================================


class TestPlatformWiring:
    def test_mixin_is_exported(self) -> None:
        assert ObjectInstanceDiscoveryMixin is not None

    def test_assembled_platform_has_discover_method(self, platform: Any) -> None:
        assert hasattr(platform, "discover_object_instances_unstructured")


# ============================================================================
# RPC handler（会话 ID 由全局请求上下文提供；错误码映射；501 语义已移除）
# ============================================================================


class _RpcFakePlatform:
    """RPC 级假平台：按 behavior 抛出对应异常。"""

    def __init__(self, behavior: str = "ok") -> None:
        self.behavior = behavior

    async def discover_object_instances_unstructured(
        self,
        base_id: str,
        *,
        instance_id: str,
        object_codes: list[str],
    ) -> ObjectInstanceDiscoveryResult:
        if self.behavior == "ok":
            return ObjectInstanceDiscoveryResult(items=[])
        if self.behavior == "not_found":
            raise KeyError(f"term not found: {instance_id}")
        if self.behavior == "invalid_params":
            raise ValueError("term knowledge location is incomplete")
        if self.behavior == "permission_denied":
            raise PermissionError("no permission")
        raise RuntimeError("boom")


class _RpcComboPlatform(ObjectInstanceDiscoveryMixin):
    """组合平台：走真实 mixin 主流程（参数校验），供 RPC 层测试。"""

    def __init__(self, behavior: str = "ok") -> None:
        self.behavior = behavior

    async def get_document_content_by_term_id(
        self, base_id: str, *, term_id: str
    ) -> DocumentContentResult:
        if self.behavior == "not_found":
            raise KeyError(f"term not found: {term_id}")
        return _make_document(term_id)

    def list_term_relations(self, base_id: str, **kwargs: Any) -> dict[str, Any]:
        return {"data": []}

    def create_term_relation(
        self, base_id: str, *, relation: dict[str, Any]
    ) -> dict[str, Any]:
        return {"relationId": "rel-x"}

    async def save_or_update_object_files(
        self, base_id: str, *, object_files: list[dict[str, Any]]
    ) -> None:
        return None

    def get_object_detail(
        self, _base_id: str, object_code: str
    ) -> dict[str, Any] | None:
        return {
            "objectCode": object_code,
            "objectName": "商机",
            "extProperty": {
                "kb_resource_id": "10001",
                "kb_id": "201",
                "kb_directory": "/商机目录",
            },
        }

    def update_term_co_occurrence(
        self, base_id: str, *, term_id: str, patch: dict[str, int]
    ) -> None:
        return None


def _rpc_client(platform: Any) -> TestClient:
    app = FastAPI()
    app.include_router(create_rpc_router(platform=platform))
    return TestClient(app)


class TestDiscoverRpc:
    def test_normal_input_returns_200(self) -> None:
        """501 语义已移除，正常输入不再短路（走 platform 返回结果）。"""
        client = _rpc_client(_RpcFakePlatform("ok"))
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
        assert body["code"] == 200
        assert body["success"] is True
        assert body["data"]["items"] == []

    def test_without_session_header_succeeds(self) -> None:
        """无 X-Session-Id 请求头也返回 200：handler 不再校验，全局上下文为空串。"""
        client = _rpc_client(_RpcFakePlatform("ok"))
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
        assert body["code"] == 200
        assert body["success"] is True
        assert body["data"]["items"] == []


# ============================================================================
# RPC 级错误码映射（404/400/403/500）
# ============================================================================


def _discover_rpc_post(client: TestClient, **headers: str) -> Any:
    return client.post(
        "/api/v1/rpc/search/discoverObjectInstancesUnstructured",
        json={
            "params": {
                "base_id": BASE_ID,
                "instance_id": "term-input",
                "object_codes": ["by_opportunity"],
            }
        },
        headers=headers,
    )


class TestDiscoverRpcErrorMapping:
    def test_missing_term_returns_404(self) -> None:
        client = _rpc_client(_RpcFakePlatform("not_found"))
        body = _discover_rpc_post(client, **{"X-Session-Id": "s1"}).json()
        assert body["code"] == 404
        assert "term not found" in body["message"]

    def test_incomplete_kb_location_returns_400(self) -> None:
        client = _rpc_client(_RpcFakePlatform("invalid_params"))
        body = _discover_rpc_post(client, **{"X-Session-Id": "s1"}).json()
        assert body["code"] == 400
        assert "incomplete" in body["message"]

    def test_permission_denied_returns_403(self) -> None:
        client = _rpc_client(_RpcFakePlatform("permission_denied"))
        body = _discover_rpc_post(client, **{"X-Session-Id": "s1"}).json()
        assert body["code"] == 403

    def test_unexpected_error_returns_500(self) -> None:
        client = _rpc_client(_RpcFakePlatform("internal_error"))
        body = _discover_rpc_post(client, **{"X-Session-Id": "s1"}).json()
        assert body["code"] == 500

    def test_missing_object_codes_returns_400(self) -> None:
        """RPC 路径走真实 mixin 参数校验：空 object_codes → ValueError → 400。"""
        platform = _RpcComboPlatform()
        client = _rpc_client(platform)
        resp = client.post(
            "/api/v1/rpc/search/discoverObjectInstancesUnstructured",
            json={
                "params": {
                    "base_id": BASE_ID,
                    "instance_id": "term-input",
                    "object_codes": [],
                }
            },
            headers={"X-Session-Id": "s1"},
        )
        body = resp.json()
        assert body["code"] == 400
        assert "object_codes" in body["message"]


# ============================================================================
# 锚定 RPC 级：输入实例含已有实例 mention → items 已有在前（is_new=False）
# ============================================================================


class _RpcAnchorPlatform(ObjectInstanceDiscoveryMixin):
    """RPC 级锚定平台：真实 mixin 主流程 + 可控词典/反查。"""

    def __init__(self) -> None:
        self.vocab_words: list[str] = []
        self.term_search_results: dict[str, Any] = {"total": 0, "items": []}
        self.name_rows: list[dict[str, Any]] = []
        self.mentions: list[dict[str, Any]] = []

    async def get_document_content_by_term_id(
        self, base_id: str, *, term_id: str
    ) -> DocumentContentResult:
        return _make_document(term_id)

    def list_vocabulary(self, base_id: str) -> list[str]:
        return list(self.vocab_words)

    def search_terms(self, base_id: str, **kwargs: Any) -> dict[str, Any]:
        return self.term_search_results

    def search_terms_batch(self, base_id: str, **kwargs: Any) -> dict[str, Any]:
        keywords = kwargs.get("keywords") or []
        return {kw: dict(self.term_search_results) for kw in keywords}

    def list_term_names(self, base_id: str, **kwargs: Any) -> list[dict[str, Any]]:
        return list(self.name_rows)

    def list_term_relations(self, base_id: str, **kwargs: Any) -> dict[str, Any]:
        return {"data": []}

    def create_term_relation(
        self, base_id: str, *, relation: dict[str, Any]
    ) -> dict[str, Any]:
        return {"relationId": "rel-x"}

    async def save_or_update_object_files(
        self, base_id: str, *, object_files: list[dict[str, Any]]
    ) -> None:
        return None

    def get_object_detail(
        self, _base_id: str, object_code: str
    ) -> dict[str, Any] | None:
        return {
            "objectCode": object_code,
            "objectName": "商机",
            "extProperty": {
                "kb_resource_id": "10001",
                "kb_id": "201",
                "kb_directory": "/商机目录",
            },
        }

    def update_term_co_occurrence(
        self, base_id: str, *, term_id: str, patch: dict[str, int]
    ) -> None:
        return None

    async def _discover_new_object_instances(
        self, base_id: str, *, content: str, object_codes: list[str]
    ) -> list[dict[str, Any]]:
        return list(self.mentions)


class TestDiscoverRpcAnchor:
    def test_existing_instance_mention_comes_first(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        platform = _RpcAnchorPlatform()
        platform.vocab_words = ["张三"]
        platform.term_search_results = {
            "total": 1,
            "items": [_term_row("term-existing-1", "张三")],
        }
        platform.mentions = [
            {"term_name": "张三", "object_code": "by_opportunity", "evidence": "张三"},
            {
                "term_name": "新客户A",
                "object_code": "by_opportunity",
                "evidence": "新客户A",
            },
        ]

        async def fake_write_action(**kwargs: Any) -> dict[str, Any]:
            return {
                "records": [
                    {
                        "termId": "term-new-1",
                        "fileName": "张三-实际.md",
                        "filePath": "/实际目录/张三-实际.md",
                    }
                ]
            }

        monkeypatch.setattr(
            discovery_module, "invoke_object_write_action", fake_write_action
        )
        client = _rpc_client(platform)
        resp = client.post(
            "/api/v1/rpc/search/discoverObjectInstancesUnstructured",
            json={
                "params": {
                    "base_id": BASE_ID,
                    "instance_id": "term-input",
                    "object_codes": ["by_opportunity"],
                }
            },
            headers={"X-Session-Id": "s1"},
        )
        body = resp.json()
        assert body["code"] == 200, body
        items = body["data"]["items"]
        # 已有在前、新在后（RPC 序列化为 snake_case dataclass 字段名）
        assert [item["instance_id"] for item in items] == [
            "term-existing-1",
            "term-new-1",
        ]
        assert items[0]["is_new"] is False
        assert items[0]["evidence"] == "张三"
        assert items[1]["is_new"] is True


# ============================================================================
# 串联：mock 锚定/抽取占位方法后验证 创建→强校验→登记→提及 全链路
# ============================================================================


class TestDiscoverOrchestration:
    @pytest.mark.asyncio
    async def test_full_flow_orchestrates_create_register_relation(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        platform = _FakePlatform()
        platform.document = _make_document()

        async def fake_new_instances(*a: Any, **k: Any) -> list[dict[str, Any]]:
            return [
                {
                    "term_name": "新实例",
                    "object_code": "by_opportunity",
                    "evidence": "证据片段",
                }
            ]

        monkeypatch.setattr(
            platform, "_discover_new_object_instances", fake_new_instances
        )
        monkeypatch.setattr(
            platform,
            "_discover_existing_object_instances",
            lambda *a, **k: discovery_module._AnchorResult(
                existing=[
                    {
                        "term_id": "term-existing-1",
                        "term_name": "已有实例",
                        "term_code": "existing-1",
                        "term_type_code": "by_opportunity",
                        "file_name": "/by_opportunity/已有实例.md",
                        "kb_resource_id": "kr1",
                        "kb_id": "kb1",
                        "evidence": "已有实例",
                    }
                ],
                ambiguity=[],
                synonym=[],
                unanchored=[
                    {
                        "term_name": "新实例",
                        "object_code": "by_opportunity",
                        "evidence": "证据片段",
                    }
                ],
            ),
        )

        async def fake_write_action(**kwargs: Any) -> dict[str, Any]:
            return {"records": [{"termId": "term-new-1"}]}

        monkeypatch.setattr(
            discovery_module, "invoke_object_write_action", fake_write_action
        )
        result = await platform.discover_object_instances_unstructured(
            BASE_ID,
            instance_id="term-input",
            object_codes=["by_opportunity"],
        )
        # 已有在前、新在后
        assert [h.instance_id for h in result.items] == [
            "term-existing-1",
            "term-new-1",
        ]
        existing, new = result.items
        assert existing.is_new is False
        assert existing.instance_name == "已有实例"
        assert existing.evidence == "已有实例"
        assert new.is_new is True
        assert new.instance_name == "新实例"
        assert new.relation_name == "提及"
        assert new.evidence == "证据片段"
        # 关系时序：已有实例的关系创建于登记之前（existing 分支无登记动作）
        call_names = [c[0] for c in platform.calls]
        assert call_names.index("create_term_relation") < call_names.index(
            "save_or_update_object_files"
        )
        # 新实例登记先于其建关系
        new_relation_index = next(
            i
            for i, c in enumerate(platform.calls)
            if c[0] == "create_term_relation"
            and c[1]["relation"]["targetTermId"] == "term-new-1"
        )
        assert call_names.index("save_or_update_object_files") < new_relation_index
        # 关系：源=输入实例；已有实例在前、新实例在后（仅一次，无反向）
        assert platform.created_relations == [
            {
                "sourceTermId": "term-input",
                "targetTermId": "term-existing-1",
                "relationName": "提及",
                "relationCategory": "BUSINESS",
            },
            {
                "sourceTermId": "term-input",
                "targetTermId": "term-new-1",
                "relationName": "提及",
                "relationCategory": "BUSINESS",
            },
        ]

    @pytest.mark.asyncio
    async def test_full_flow_without_existing_only_creates_new(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        platform = _FakePlatform()
        platform.document = _make_document()

        async def fake_new_instances(*a: Any, **k: Any) -> list[dict[str, Any]]:
            return [{"term_name": "新实例A", "object_code": "by_opportunity"}]

        monkeypatch.setattr(
            platform, "_discover_new_object_instances", fake_new_instances
        )
        monkeypatch.setattr(
            platform,
            "_discover_existing_object_instances",
            lambda *a, **k: discovery_module._AnchorResult(
                existing=[],
                ambiguity=[],
                synonym=[],
                unanchored=[{"term_name": "新实例A", "object_code": "by_opportunity"}],
            ),
        )

        async def fake_write_action(**kwargs: Any) -> dict[str, Any]:
            return {"records": [{"termId": "term-new-1"}]}

        monkeypatch.setattr(
            discovery_module, "invoke_object_write_action", fake_write_action
        )
        result = await platform.discover_object_instances_unstructured(
            BASE_ID,
            instance_id="term-input",
            object_codes=["by_opportunity"],
        )
        assert [h.instance_id for h in result.items] == ["term-new-1"]
        assert result.items[0].is_new is True

    @pytest.mark.asyncio
    async def test_repeat_discovery_existing_relation_is_idempotent(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """重复发现：已有实例的提及关系已存在（第一遍已建）→ 不重复创建（幂等）。"""
        platform = _FakePlatform()
        platform.document = _make_document()
        # 模拟第一遍发现已建立的 源=输入实例 → 目标=已有实例 提及关系
        platform.relations = [
            {
                "relation_name": "提及",
                "source_term_id": "term-input",
                "target_term_id": "term-existing-1",
            }
        ]

        async def fake_new_instances(*a: Any, **k: Any) -> list[dict[str, Any]]:
            return []

        monkeypatch.setattr(
            platform, "_discover_new_object_instances", fake_new_instances
        )
        monkeypatch.setattr(
            platform,
            "_discover_existing_object_instances",
            lambda *a, **k: discovery_module._AnchorResult(
                existing=[_term_row("term-existing-1", "已有实例")],
                ambiguity=[],
                synonym=[],
                unanchored=[],
            ),
        )
        result = await platform.discover_object_instances_unstructured(
            BASE_ID,
            instance_id="term-input",
            object_codes=["by_opportunity"],
        )
        assert [h.instance_id for h in result.items] == ["term-existing-1"]
        assert result.items[0].is_new is False
        # 幂等：重复发现不产生重复提及关系
        assert platform.created_relations == []

    @pytest.mark.asyncio
    async def test_ambiguity_same_entity_merges_alias_not_created(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """歧义候选裁决 same_entity=true → 归并别名到主 term，不建新实例、不产已有 hit。"""
        platform = _FakePlatform()
        platform.document = _make_document()

        async def fake_new_instances(*a: Any, **k: Any) -> list[dict[str, Any]]:
            return [
                {
                    "term_name": "张三",
                    "object_code": "by_opportunity",
                    "evidence": None,
                }
            ]

        monkeypatch.setattr(
            platform, "_discover_new_object_instances", fake_new_instances
        )
        monkeypatch.setattr(
            platform,
            "_discover_existing_object_instances",
            lambda *a, **k: discovery_module._AnchorResult(
                existing=[],
                ambiguity=[
                    {
                        "mention": "张三",
                        "terms": [
                            _term_row("t1", "张三"),
                            _term_row("t2", "张三"),
                        ],
                    }
                ],
                synonym=[],
                unanchored=[],
            ),
        )

        async def fake_judge(messages: list[dict[str, str]]) -> Any:
            return _AiMessage('{"same_entity": true, "entity_names": ["张三"]}')

        monkeypatch.setattr(platform, "_invoke_judge_llm", fake_judge)
        result = await platform.discover_object_instances_unstructured(
            BASE_ID,
            instance_id="term-input",
            object_codes=["by_opportunity"],
        )
        assert result.items == []
        # 归并：别名写回主 term（termId=canonical、nameText=mention）
        alias_call = next(c for c in platform.calls if c[0] == "create_term_name")
        assert alias_call[1]["name"]["termId"] == "t1"
        assert alias_call[1]["name"]["nameText"] == "张三"
        # 不建新实例（无 create_term）；归并仍为 canonical 建立提及关系（源=输入实例）
        assert all(c[0] != "create_term" for c in platform.calls)
        assert platform.created_relations == [
            {
                "sourceTermId": "term-input",
                "targetTermId": "t1",
                "relationName": "提及",
                "relationCategory": "BUSINESS",
            }
        ]

    @pytest.mark.asyncio
    async def test_synonym_same_writes_alias_not_created(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """同义候选裁决 same=true → 写 TermName 别名（term_id=canonical），不建新实例。"""
        platform = _FakePlatform()
        platform.document = _make_document()

        async def fake_new_instances(*a: Any, **k: Any) -> list[dict[str, Any]]:
            return [
                {
                    "term_name": "苹果公司",
                    "object_code": "by_opportunity",
                    "evidence": None,
                }
            ]

        monkeypatch.setattr(
            platform, "_discover_new_object_instances", fake_new_instances
        )
        monkeypatch.setattr(
            platform,
            "_discover_existing_object_instances",
            lambda *a, **k: discovery_module._AnchorResult(
                existing=[],
                ambiguity=[],
                synonym=[{"mention": "苹果公司", "term": _term_row("t1", "苹果")}],
                unanchored=[],
            ),
        )

        async def fake_judge(messages: list[dict[str, str]]) -> Any:
            return _AiMessage('{"same": true, "canonical": "t1"}')

        monkeypatch.setattr(platform, "_invoke_judge_llm", fake_judge)
        result = await platform.discover_object_instances_unstructured(
            BASE_ID,
            instance_id="term-input",
            object_codes=["by_opportunity"],
        )
        assert result.items == []
        alias_call = next(c for c in platform.calls if c[0] == "create_term_name")
        assert alias_call[1]["name"]["termId"] == "t1"
        assert alias_call[1]["name"]["nameText"] == "苹果公司"
        # 不建新实例（无 create_term）；归并仍为 canonical 建立提及关系（源=输入实例）
        assert all(c[0] != "create_term" for c in platform.calls)
        assert platform.created_relations == [
            {
                "sourceTermId": "term-input",
                "targetTermId": "t1",
                "relationName": "提及",
                "relationCategory": "BUSINESS",
            }
        ]


# ============================================================================
# 词典缓存单例：惰性加载一次 / invalidate 后重载 / 新词生效
# ============================================================================


class TestVocabularyCache:
    @pytest.fixture(autouse=True)
    def _reset_cache(self) -> Any:
        """模块级缓存为单例，测试前后显式失效，避免跨用例污染。"""
        discovery_module.invalidate_vocabulary_cache()
        yield
        discovery_module.invalidate_vocabulary_cache()

    def test_lazy_loads_once(self) -> None:
        platform = _FakePlatform()
        platform.vocab_words = ["苹果", "华为"]
        words = platform._vocabulary_words(BASE_ID)
        assert words == frozenset({"苹果", "华为"})
        assert isinstance(words, frozenset)
        # 再次访问不触发第二次 list_vocabulary
        platform._vocabulary_words(BASE_ID)
        list_calls = [c for c in platform.calls if c[0] == "list_vocabulary"]
        assert len(list_calls) == 1

    def test_invalidate_reloads(self) -> None:
        platform = _FakePlatform()
        platform.vocab_words = ["苹果"]
        assert platform._vocabulary_words(BASE_ID) == frozenset({"苹果"})
        discovery_module.invalidate_vocabulary_cache()
        assert platform._vocabulary_words(BASE_ID) == frozenset({"苹果"})
        list_calls = [c for c in platform.calls if c[0] == "list_vocabulary"]
        assert len(list_calls) == 2

    def test_reload_after_invalidate_includes_new_words(self) -> None:
        platform = _FakePlatform()
        platform.vocab_words = ["苹果"]
        assert platform._vocabulary_words(BASE_ID) == frozenset({"苹果"})
        # 词典新增词（模拟词表回填 / 创建后触发器投影）
        platform.vocab_words = ["苹果", "华为"]
        discovery_module.invalidate_vocabulary_cache()
        assert platform._vocabulary_words(BASE_ID) == frozenset({"苹果", "华为"})


# ============================================================================
# 适配器同步：remote / none 不抛 NotImplementedError，data_adapter 代理转发
# ============================================================================


class TestVocabularyAdapterSync:
    def test_none_adapter_returns_empty_list(self) -> None:
        from datacloud_platform.adapters.none_adapters import _NoopTermBackend

        backend = _NoopTermBackend()
        assert backend.list_vocabulary() == []

    def test_none_adapter_batch_create_is_noop(self) -> None:
        from datacloud_platform.adapters.none_adapters import _NoopTermBackend

        backend = _NoopTermBackend()
        backend.batch_create_vocabulary(words=["苹果"])  # 不应抛异常
        assert backend.list_vocabulary() == []

    def test_remote_adapter_returns_empty_list(self) -> None:
        from datacloud_platform.adapters.remote_adapter import RemoteTermBackend

        backend = RemoteTermBackend(source_url="http://localhost:9999")
        assert backend.list_vocabulary() == []

    def test_data_adapter_proxies_list_vocabulary_to_reader(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from datacloud_platform.adapters.data_adapter import _term as term_adapter
        from datacloud_platform.adapters.data_adapter._term import TermBackendMixin

        class _StubReader:
            def list_vocabulary(self) -> list[str]:
                return ["苹果", "华为"]

        monkeypatch.setattr(
            term_adapter, "create_reader", lambda *a, **k: _StubReader()
        )
        backend = TermBackendMixin()
        assert backend.list_vocabulary() == ["苹果", "华为"]

    def test_data_adapter_proxies_batch_create_to_writer(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from datacloud_platform.adapters.data_adapter import _term as term_adapter
        from datacloud_platform.adapters.data_adapter._term import TermBackendMixin

        captured: dict[str, Any] = {}

        class _StubWriter:
            def __enter__(self) -> "_StubWriter":
                return self

            def __exit__(self, *args: Any) -> None:
                return None

            def batch_create_vocabulary(self, *, words: list[str]) -> None:
                captured["words"] = words

        monkeypatch.setattr(
            term_adapter, "create_writer", lambda *a, **k: _StubWriter()
        )
        backend = TermBackendMixin()
        backend.batch_create_vocabulary(words=["苹果", "华为"])
        assert captured["words"] == ["苹果", "华为"]


# ============================================================================
# LLM 抽取：类型枚举 / 16K 截断 / JSON 重试 / AUTO_DISCOVERED / 词表回填
# ============================================================================


class _AiMessage:
    """模拟 langchain AIMessage：仅保留 content。"""

    def __init__(self, content: str) -> None:
        self.content = content


class TestDiscoverNewObjectInstances:
    @pytest.fixture(autouse=True)
    def _reset_cache(self) -> Any:
        discovery_module.invalidate_vocabulary_cache()
        yield
        discovery_module.invalidate_vocabulary_cache()

    @pytest.mark.asyncio
    async def test_builds_prompt_with_type_enumeration(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """prompt 类型枚举 = object_codes 的 TermType 中文名（library 域限定）。"""
        platform = _FakePlatform()
        captured: dict[str, Any] = {}

        async def fake_invoke(messages: list[dict[str, str]]) -> Any:
            captured["messages"] = messages
            return _AiMessage("[]")

        monkeypatch.setattr(platform, "_invoke_extract_llm", fake_invoke)
        monkeypatch.setattr(
            platform,
            "get_term_type",
            lambda base_id, *, library_id, type_code: (
                {"type_name": "商机"}
                if type_code == "by_opportunity"
                else {"type_name": "客户"}
            ),
        )
        monkeypatch.setattr(
            platform, "batch_create_vocabulary", lambda base_id, *, words: None
        )
        mentions = await platform._discover_new_object_instances(
            BASE_ID, content="正文", object_codes=["by_opportunity", "by_customer"]
        )
        assert mentions == []
        system = next(m for m in captured["messages"] if m["role"] == "system")
        user = next(m for m in captured["messages"] if m["role"] == "user")
        assert "by_opportunity=商机" in system["content"]
        assert "by_customer=客户" in system["content"]
        assert "AUTO_DISCOVERED" in system["content"]
        assert "正文" in user["content"]

    @pytest.mark.asyncio
    async def test_type_enumeration_falls_back_to_raw_code(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """缺行（get_term_type 返回 None）→ 回退原始 code。"""
        platform = _FakePlatform()
        captured: dict[str, Any] = {}

        async def fake_invoke(messages: list[dict[str, str]]) -> Any:
            captured["messages"] = messages
            return _AiMessage("[]")

        monkeypatch.setattr(platform, "_invoke_extract_llm", fake_invoke)
        monkeypatch.setattr(
            platform, "get_term_type", lambda base_id, *, library_id, type_code: None
        )
        monkeypatch.setattr(
            platform, "batch_create_vocabulary", lambda base_id, *, words: None
        )
        await platform._discover_new_object_instances(
            BASE_ID, content="正文", object_codes=["by_opportunity"]
        )
        system = next(m for m in captured["messages"] if m["role"] == "system")
        assert "by_opportunity=by_opportunity" in system["content"]

    @pytest.mark.asyncio
    async def test_type_enumeration_falls_back_to_object_term_name(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """get_term_type 缺行 → 按 term_code 查对象术语行（term_type_code='object'）取中文名。"""
        platform = _FakePlatform()
        captured: dict[str, Any] = {}
        exact_calls: list[dict[str, Any]] = []

        async def fake_invoke(messages: list[dict[str, str]]) -> Any:
            captured["messages"] = messages
            return _AiMessage("[]")

        def fake_search_terms_exact(base_id: str, **kwargs: Any) -> dict[str, Any]:
            exact_calls.append({"base_id": base_id, **kwargs})
            return {
                "data": [
                    {
                        "term_code": "p_MedicalRecord_e2e_2ded9c",
                        "term_name": "医疗文书",
                        "term_type_code": "object",
                    }
                ],
                "totalCount": 1,
            }

        monkeypatch.setattr(platform, "_invoke_extract_llm", fake_invoke)
        monkeypatch.setattr(
            platform, "get_term_type", lambda base_id, *, library_id, type_code: None
        )
        monkeypatch.setattr(platform, "search_terms_exact", fake_search_terms_exact)
        monkeypatch.setattr(
            platform, "batch_create_vocabulary", lambda base_id, *, words: None
        )
        await platform._discover_new_object_instances(
            BASE_ID, content="正文", object_codes=["p_MedicalRecord_e2e_2ded9c"]
        )
        system = next(m for m in captured["messages"] if m["role"] == "system")
        assert "p_MedicalRecord_e2e_2ded9c=医疗文书" in system["content"]
        assert exact_calls == [
            {
                "base_id": BASE_ID,
                "term_type_code": "object",
                "keyword": "p_MedicalRecord_e2e_2ded9c",
                "limit": 1,
            }
        ]

    @pytest.mark.asyncio
    async def test_type_enumeration_object_row_preferred_over_placeholder_name(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """get_term_type 命中但 type_name 是英文 code 占位（import 自动建行）
        → 视为失真，回退对象术语行中文名（对象行比 term_type 占位更准）。"""
        platform = _FakePlatform()
        captured: dict[str, Any] = {}
        exact_calls: list[dict[str, Any]] = []

        async def fake_invoke(messages: list[dict[str, str]]) -> Any:
            captured["messages"] = messages
            return _AiMessage("[]")

        def fake_search_terms_exact(base_id: str, **kwargs: Any) -> dict[str, Any]:
            exact_calls.append({"base_id": base_id, **kwargs})
            return {
                "data": [
                    {
                        "term_code": "Concept",
                        "term_name": "概念",
                        "term_type_code": "object",
                    }
                ],
                "totalCount": 1,
            }

        monkeypatch.setattr(platform, "_invoke_extract_llm", fake_invoke)
        monkeypatch.setattr(
            platform,
            "get_term_type",
            lambda base_id, *, library_id, type_code: {"type_name": "Concept"},
        )
        monkeypatch.setattr(platform, "search_terms_exact", fake_search_terms_exact)
        monkeypatch.setattr(
            platform, "batch_create_vocabulary", lambda base_id, *, words: None
        )
        await platform._discover_new_object_instances(
            BASE_ID, content="正文", object_codes=["Concept"]
        )
        system = next(m for m in captured["messages"] if m["role"] == "system")
        assert "Concept=概念" in system["content"]
        assert exact_calls == [
            {
                "base_id": BASE_ID,
                "term_type_code": "object",
                "keyword": "Concept",
                "limit": 1,
            }
        ]

    @pytest.mark.asyncio
    async def test_truncates_long_content_to_16k(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        platform = _FakePlatform()
        captured: dict[str, Any] = {}

        async def fake_invoke(messages: list[dict[str, str]]) -> Any:
            captured["messages"] = messages
            return _AiMessage("[]")

        monkeypatch.setattr(platform, "_invoke_extract_llm", fake_invoke)
        monkeypatch.setattr(
            platform, "get_term_type", lambda base_id, *, library_id, type_code: None
        )
        monkeypatch.setattr(
            platform, "batch_create_vocabulary", lambda base_id, *, words: None
        )
        long_content = "字" * 20_000
        await platform._discover_new_object_instances(
            BASE_ID, content=long_content, object_codes=["by_opportunity"]
        )
        user = next(m for m in captured["messages"] if m["role"] == "user")
        assert len(user["content"]) <= discovery_module._MAX_EXTRACT_CHARS
        assert user["content"].endswith("…")

    @pytest.mark.asyncio
    async def test_think_block_is_stripped(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        platform = _FakePlatform()
        raw = (
            "<think>我需要分析这段文档……</think>\n"
            '[{"term_name": "张三", "object_code": "by_opportunity",'
            ' "evidence": "张三", "raw_type": "商机"}]'
        )

        async def fake_invoke(messages: list[dict[str, str]]) -> Any:
            return _AiMessage(raw)

        monkeypatch.setattr(platform, "_invoke_extract_llm", fake_invoke)
        monkeypatch.setattr(
            platform, "get_term_type", lambda base_id, *, library_id, type_code: None
        )
        monkeypatch.setattr(
            platform, "batch_create_vocabulary", lambda base_id, *, words: None
        )
        mentions = await platform._discover_new_object_instances(
            BASE_ID, content="正文", object_codes=["by_opportunity"]
        )
        assert mentions == [
            {
                "term_name": "张三",
                "object_code": "by_opportunity",
                "evidence": "张三",
                "raw_type": "商机",
            }
        ]

    @pytest.mark.asyncio
    async def test_invalid_json_retries_up_to_limit(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """非法 JSON → 重试 prompt 再解析（≤3 次退避）；第二次成功即返回。"""
        platform = _FakePlatform()
        calls: list[list[dict[str, str]]] = []
        raw_outputs = [
            "不是JSON{{",
            '[{"term_name": "张三", "object_code": "by_opportunity"}]',
        ]

        async def fake_invoke(messages: list[dict[str, str]]) -> Any:
            calls.append(messages)
            return _AiMessage(raw_outputs[min(len(calls) - 1, 1)])

        monkeypatch.setattr(platform, "_invoke_extract_llm", fake_invoke)
        monkeypatch.setattr(
            platform, "get_term_type", lambda base_id, *, library_id, type_code: None
        )
        monkeypatch.setattr(
            platform, "batch_create_vocabulary", lambda base_id, *, words: None
        )
        monkeypatch.setattr(discovery_module, "_JSON_RETRY_BACKOFF_SECONDS", 0)
        mentions = await platform._discover_new_object_instances(
            BASE_ID, content="正文", object_codes=["by_opportunity"]
        )
        assert mentions == [{"term_name": "张三", "object_code": "by_opportunity"}]
        assert len(calls) == 2
        # 第二次调用带重试提示
        assert "不是合法 JSON" in calls[1][-1]["content"]

    @pytest.mark.asyncio
    async def test_retries_exhausted_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        platform = _FakePlatform()
        calls: list[Any] = []

        async def fake_invoke(messages: list[dict[str, str]]) -> Any:
            calls.append(messages)
            return _AiMessage("仍旧不是JSON")

        monkeypatch.setattr(platform, "_invoke_extract_llm", fake_invoke)
        monkeypatch.setattr(
            platform, "get_term_type", lambda base_id, *, library_id, type_code: None
        )
        monkeypatch.setattr(discovery_module, "_JSON_RETRY_BACKOFF_SECONDS", 0)
        with pytest.raises(RuntimeError, match="JSON"):
            await platform._discover_new_object_instances(
                BASE_ID, content="正文", object_codes=["by_opportunity"]
            )
        assert len(calls) == discovery_module._MAX_JSON_RETRIES

    @pytest.mark.asyncio
    async def test_out_of_enum_type_maps_to_auto_discovered(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """object_code ∉ object_codes → AUTO_DISCOVERED，raw_type 保留原始类型名。"""
        platform = _FakePlatform()
        raw = (
            '[{"term_name": "新品类X", "object_code": "by_unknown_type",'
            ' "evidence": "X", "raw_type": "未知业务对象"}]'
        )

        async def fake_invoke(messages: list[dict[str, str]]) -> Any:
            return _AiMessage(raw)

        monkeypatch.setattr(platform, "_invoke_extract_llm", fake_invoke)
        monkeypatch.setattr(
            platform, "get_term_type", lambda base_id, *, library_id, type_code: None
        )
        monkeypatch.setattr(
            platform, "batch_create_vocabulary", lambda base_id, *, words: None
        )
        mentions = await platform._discover_new_object_instances(
            BASE_ID, content="正文", object_codes=["by_opportunity"]
        )
        assert mentions == [
            {
                "term_name": "新品类X",
                "object_code": "AUTO_DISCOVERED",
                "evidence": "X",
                "raw_type": "未知业务对象",
            }
        ]

    @pytest.mark.asyncio
    async def test_backfills_vocabulary_idempotently(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """抽到就填：batch_create_vocabulary 被调（无门槛）；mock 记录 words。"""
        platform = _FakePlatform()
        raw = (
            '[{"term_name": "张三", "object_code": "by_opportunity"},'
            ' {"term_name": "李四", "object_code": "by_opportunity"}]'
        )

        async def fake_invoke(messages: list[dict[str, str]]) -> Any:
            return _AiMessage(raw)

        monkeypatch.setattr(platform, "_invoke_extract_llm", fake_invoke)
        monkeypatch.setattr(
            platform, "get_term_type", lambda base_id, *, library_id, type_code: None
        )
        backfilled: list[str] = []
        monkeypatch.setattr(
            platform,
            "batch_create_vocabulary",
            lambda base_id, *, words: backfilled.extend(words),
        )
        mentions = await platform._discover_new_object_instances(
            BASE_ID, content="正文", object_codes=["by_opportunity"]
        )
        assert [m["term_name"] for m in mentions] == ["张三", "李四"]
        assert backfilled == ["张三", "李四"]

    @pytest.mark.asyncio
    async def test_blank_term_name_rows_are_dropped(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        platform = _FakePlatform()
        raw = '[{"term_name": "  ", "object_code": "by_opportunity"}]'

        async def fake_invoke(messages: list[dict[str, str]]) -> Any:
            return _AiMessage(raw)

        monkeypatch.setattr(platform, "_invoke_extract_llm", fake_invoke)
        monkeypatch.setattr(
            platform, "get_term_type", lambda base_id, *, library_id, type_code: None
        )
        backfilled: list[str] = []
        monkeypatch.setattr(
            platform,
            "batch_create_vocabulary",
            lambda base_id, *, words: backfilled.extend(words),
        )
        mentions = await platform._discover_new_object_instances(
            BASE_ID, content="正文", object_codes=["by_opportunity"]
        )
        assert mentions == []
        assert backfilled == []

    @pytest.mark.asyncio
    async def test_uses_build_llm_singleton_pattern(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """LLM 经 build_llm(thinking=False, temperature=0.0) + stream_invoke_with_thinking。

        发现链路显式禁用思考链并固定零温度（抽取/裁决均为结构化 JSON 输出，
        无需思考链；temp=0 对齐 spec D-1 确定性要求）。
        """
        platform = _FakePlatform()
        built: list[Any] = []
        invoked: list[Any] = []

        class _FakeLlm:
            pass

        async def fake_run_sync(func: Any) -> Any:
            return func()

        monkeypatch.setattr(discovery_module.to_thread, "run_sync", fake_run_sync)
        monkeypatch.setattr(
            discovery_module,
            "build_llm",
            lambda **kwargs: (built.append((_FakeLlm(), kwargs)), _FakeLlm())[1],
        )
        monkeypatch.setattr(
            discovery_module,
            "stream_invoke_with_thinking",
            lambda llm, messages, on_event=None: (
                invoked.append((llm, messages, on_event)),
                _AiMessage("[]"),
            )[1],
        )
        monkeypatch.setattr(
            platform, "get_term_type", lambda base_id, *, library_id, type_code: None
        )
        monkeypatch.setattr(
            platform, "batch_create_vocabulary", lambda base_id, *, words: None
        )
        mentions = await platform._discover_new_object_instances(
            BASE_ID, content="正文", object_codes=["by_opportunity"]
        )
        assert mentions == []
        assert len(built) == 1
        assert built[0][1] == {"thinking": False, "temperature": 0.0}
        assert len(invoked) == 1
        assert invoked[0][2] is None  # on_event=None（无流式回调）


# ============================================================================
# 集成：真实抽取 + 锚定 + 创建 全链路
# ============================================================================


class TestDiscoverFullFlowWithExtraction:
    @pytest.fixture(autouse=True)
    def _reset_cache(self) -> Any:
        discovery_module.invalidate_vocabulary_cache()
        yield
        discovery_module.invalidate_vocabulary_cache()

    @pytest.mark.asyncio
    async def test_full_flow_with_real_extraction_and_anchor(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        platform = _FakePlatform()
        platform.document = _make_document()
        platform.vocab_words = ["张三"]  # 张三已在词典（库中已有）
        platform.term_search_results = {
            "total": 1,
            "items": [_term_row("t-existing", "张三")],
        }
        raw = (
            '[{"term_name": "张三", "object_code": "by_opportunity", "evidence": "张三"},'
            ' {"term_name": "新客户A", "object_code": "by_opportunity", "evidence": "新客户A"}]'
        )

        async def fake_invoke(messages: list[dict[str, str]]) -> Any:
            return _AiMessage(raw)

        monkeypatch.setattr(platform, "_invoke_extract_llm", fake_invoke)
        monkeypatch.setattr(
            platform,
            "get_term_type",
            lambda base_id, *, library_id, type_code: {"type_name": "商机"},
        )
        backfilled: list[str] = []
        monkeypatch.setattr(
            platform,
            "batch_create_vocabulary",
            lambda base_id, *, words: backfilled.extend(words),
        )

        async def fake_write_action(**kwargs: Any) -> dict[str, Any]:
            return {"records": [{"termId": "term-new-1"}]}

        monkeypatch.setattr(
            discovery_module, "invoke_object_write_action", fake_write_action
        )
        result = await platform.discover_object_instances_unstructured(
            BASE_ID,
            instance_id="term-input",
            object_codes=["by_opportunity"],
        )
        # 已有在前、新在后
        assert [h.instance_id for h in result.items] == ["t-existing", "term-new-1"]
        assert result.items[0].is_new is False
        assert result.items[0].evidence == "张三"
        assert result.items[1].is_new is True
        assert result.items[1].instance_name == "新客户A"
        # 回填：抽到就填（幂等语义由 knowledge 层 WHERE NOT EXISTS 保证）
        assert set(backfilled) == {"张三", "新客户A"}
        # 主流程完成后词典缓存已失效（下次 discover 重载 → 飞轮实时）
        assert discovery_module._cached_vocabulary is None

    @pytest.mark.asyncio
    async def test_full_flow_no_anchored_mention_creates_all(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        platform = _FakePlatform()
        platform.document = _make_document()
        platform.vocab_words = []
        raw = (
            '[{"term_name": "新客户A", "object_code": "by_opportunity"},'
            ' {"term_name": "新客户B", "object_code": "by_opportunity"}]'
        )

        async def fake_invoke(messages: list[dict[str, str]]) -> Any:
            return _AiMessage(raw)

        monkeypatch.setattr(platform, "_invoke_extract_llm", fake_invoke)
        monkeypatch.setattr(
            platform,
            "get_term_type",
            lambda base_id, *, library_id, type_code: {"type_name": "商机"},
        )
        monkeypatch.setattr(
            platform, "batch_create_vocabulary", lambda base_id, *, words: None
        )
        created: list[str] = []

        async def fake_write_action(**kwargs: Any) -> dict[str, Any]:
            created.append(str(kwargs["source_path"]))
            return {"records": [{"termId": f"term-{len(created)}"}]}

        monkeypatch.setattr(
            discovery_module, "invoke_object_write_action", fake_write_action
        )
        result = await platform.discover_object_instances_unstructured(
            BASE_ID,
            instance_id="term-input",
            object_codes=["by_opportunity"],
        )
        assert [h.instance_name for h in result.items] == ["新客户A", "新客户B"]
        assert all(h.is_new for h in result.items)
        assert created == [
            "/by_opportunity/新客户A.md",
            "/by_opportunity/新客户B.md",
        ]
        assert len(platform.created_relations) == 2


# ============================================================================
# AUTO_DISCOVERED 创建通道：兜底直写 + TermType 预置行
# ============================================================================


class TestAutoDiscoveredCreateChannel:
    @pytest.fixture(autouse=True)
    def _reset_cache(self) -> Any:
        discovery_module.invalidate_vocabulary_cache()
        yield
        discovery_module.invalidate_vocabulary_cache()

    @pytest.mark.asyncio
    async def test_direct_write_channel_with_raw_type_and_labels(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """AUTO_DISCOVERED 项走直写通道：不调 action 管道，
        ext_attrs.raw_type / labels.dc_status 落库，登记条目含 term_id，缓存失效。"""
        platform = _FakePlatform()
        written: list[dict[str, Any]] = []
        monkeypatch.setattr(
            platform,
            "create_term",
            lambda base_id, *, term: (
                written.append({"base_id": base_id, **term}),
                {
                    "created": 1,
                    "updated": 0,
                    "skipped": 0,
                    "term_ids": ["term-ad-1"],
                    "errors": [],
                },
            )[1],
        )
        monkeypatch.setattr(
            platform,
            "create_term_knowledge",
            lambda base_id, *, knowledge: {"knowledgeId": "k1"},
        )
        action_calls: list[dict[str, Any]] = []
        monkeypatch.setattr(
            discovery_module,
            "invoke_object_write_action",
            lambda **kwargs: (
                action_calls.append(kwargs) or {"records": [{"termId": "bad"}]}
            ),
        )
        hit = await platform._create_new_instance_flow(
            base_id=BASE_ID,
            source_term_id="term-input",
            candidate={
                "term_name": "新品类X",
                "object_code": "AUTO_DISCOVERED",
                "evidence": "X",
                "raw_type": "未知业务对象",
            },
        )
        assert not action_calls  # 跳过 action 管道（方案 (a)）
        assert len(written) == 1
        term = written[0]
        assert term["base_id"] == BASE_ID
        assert term["term_name"] == "新品类X"
        assert term["term_type_code"] == "AUTO_DISCOVERED"
        assert term["ext_attrs"]["raw_type"] == "未知业务对象"
        assert term["labels"]["dc_status"] == "待整理"
        assert hit.instance_id == "term-ad-1"
        assert hit.object_code == "AUTO_DISCOVERED"
        assert hit.is_new is True
        # AUTO_DISCOVERED 只参与术语飞轮，不登记对象文件。
        assert platform.object_files == []
        # 直写后缓存失效（飞轮实时）
        assert discovery_module._cached_vocabulary is None

    @pytest.mark.asyncio
    async def test_ensure_term_type_called_and_idempotent(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """TermType 预置行经 ensure_term_type 幂等落地（重复执行不报错）。"""
        platform = _FakePlatform()
        ensured: list[tuple[str, str]] = []
        monkeypatch.setattr(
            platform,
            "ensure_term_type",
            lambda **kwargs: ensured.append((kwargs["type_code"], kwargs["type_name"])),
        )
        monkeypatch.setattr(
            platform,
            "create_term",
            lambda base_id, *, term: {
                "created": 1,
                "updated": 0,
                "skipped": 0,
                "term_ids": ["term-ad-1"],
                "errors": [],
            },
        )
        monkeypatch.setattr(
            platform,
            "create_term_knowledge",
            lambda base_id, *, knowledge: {"knowledgeId": "k1"},
        )
        candidate = {
            "term_name": "新品类X",
            "object_code": "AUTO_DISCOVERED",
            "raw_type": "未知业务对象",
        }
        # 首次 + 重复执行均不抛错（幂等）
        await platform._create_new_instance_flow(
            base_id=BASE_ID,
            source_term_id="term-input",
            candidate=candidate,
        )
        await platform._create_new_instance_flow(
            base_id=BASE_ID,
            source_term_id="term-input",
            candidate={**candidate, "term_name": "新品类Y"},
        )
        assert ensured == [
            ("AUTO_DISCOVERED", "自动发现类型"),
            ("AUTO_DISCOVERED", "自动发现类型"),
        ]

    @pytest.mark.asyncio
    async def test_non_auto_discovered_keeps_action_pipeline(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """非 AUTO_DISCOVERED 项仍走 action 管道（创建回归不破坏）。"""
        platform = _FakePlatform()
        created_terms: list[dict[str, Any]] = []
        monkeypatch.setattr(
            platform,
            "create_term",
            lambda base_id, *, term: (
                created_terms.append(term),
                {"term_ids": ["term-ad-x"]},
            )[1],
        )

        async def fake_write_action(**kwargs: Any) -> dict[str, Any]:
            return {
                "records": [
                    {
                        "termId": "term-new-1",
                        "fileName": "张三-实际.md",
                        "filePath": "/实际目录/张三-实际.md",
                    }
                ]
            }

        monkeypatch.setattr(
            discovery_module, "invoke_object_write_action", fake_write_action
        )
        hit = await platform._create_new_instance_flow(
            base_id=BASE_ID,
            source_term_id="term-input",
            candidate={
                "term_name": "张三",
                "object_code": "by_opportunity",
                "evidence": "e",
            },
        )
        assert hit.instance_id == "term-new-1"
        assert hit.object_code == "by_opportunity"
        assert not created_terms  # 未走直写通道
        assert platform.object_files[0][0]["fileName"] == "张三-实际.md"
        assert platform.object_files[0][0]["filePath"] == "/实际目录/张三-实际.md"
        assert hit.file_name == "/实际目录/张三-实际.md"
        assert hit.kb_resource_id == "10001"
        assert hit.kb_id == "201"

    @pytest.mark.asyncio
    async def test_new_instance_hit_uses_object_kb_directory_when_action_omits_path(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        platform = _FakePlatform()

        async def fake_write_action(**kwargs: Any) -> dict[str, Any]:
            return {"records": [{"termId": "term-new-2"}]}

        monkeypatch.setattr(
            discovery_module, "invoke_object_write_action", fake_write_action
        )
        hit = await platform._create_new_instance_flow(
            base_id=BASE_ID,
            source_term_id="term-input",
            candidate={
                "term_name": "李四",
                "object_code": "by_opportunity",
                "evidence": "e",
            },
        )

        assert hit.file_name == "/商机目录/李四.md"
        assert hit.kb_resource_id == "10001"
        assert hit.kb_id == "201"

    @pytest.mark.asyncio
    async def test_full_flow_creates_auto_discovered_instance(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """主流程：AUTO_DISCOVERED mention → 直写创建 + 登记 + 提及关系。"""
        platform = _FakePlatform()
        platform.document = _make_document()
        platform.vocab_words = []
        raw = (
            '[{"term_name": "新品类X", "object_code": "by_unknown_type",'
            ' "evidence": "X", "raw_type": "未知业务对象"}]'
        )

        async def fake_invoke(messages: list[dict[str, str]]) -> Any:
            return _AiMessage(raw)

        monkeypatch.setattr(platform, "_invoke_extract_llm", fake_invoke)
        monkeypatch.setattr(
            platform,
            "get_term_type",
            lambda base_id, *, library_id, type_code: {"type_name": "商机"},
        )
        monkeypatch.setattr(
            platform, "batch_create_vocabulary", lambda base_id, *, words: None
        )
        created_terms: list[dict[str, Any]] = []
        monkeypatch.setattr(
            platform,
            "create_term",
            lambda base_id, *, term: (
                created_terms.append(term),
                {
                    "created": 1,
                    "updated": 0,
                    "skipped": 0,
                    "term_ids": ["term-ad-1"],
                    "errors": [],
                },
            )[1],
        )
        monkeypatch.setattr(
            platform,
            "create_term_knowledge",
            lambda base_id, *, knowledge: {"knowledgeId": "k1"},
        )
        result = await platform.discover_object_instances_unstructured(
            BASE_ID,
            instance_id="term-input",
            object_codes=["by_opportunity"],
        )
        # AUTO_DISCOVERED 兜底类型实例不入发现结果（仍入库：词表飞轮/共现用）
        assert result.items == []
        assert len(created_terms) == 1
        assert created_terms[0]["ext_attrs"]["raw_type"] == "未知业务对象"
        assert created_terms[0]["labels"]["dc_status"] == "待整理"
        # 提及关系：输入实例 → 新实例
        assert platform.created_relations == [
            {
                "sourceTermId": "term-input",
                "targetTermId": "term-ad-1",
                "relationName": "提及",
                "relationCategory": "BUSINESS",
            }
        ]

    @pytest.mark.asyncio
    async def test_full_flow_filters_auto_discovered_out_of_result(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """主流程：AUTO_DISCOVERED 兜底实例仍入库（词表飞轮/共现用），但不作为发现结果返回。"""
        platform = _FakePlatform()
        platform.document = _make_document()

        async def fake_new_instances(*a: Any, **k: Any) -> list[dict[str, Any]]:
            return []

        monkeypatch.setattr(
            platform, "_discover_new_object_instances", fake_new_instances
        )
        monkeypatch.setattr(
            platform,
            "_discover_existing_object_instances",
            lambda *a, **k: discovery_module._AnchorResult(
                existing=[_term_row("t-existing", "张三")],
                ambiguity=[],
                synonym=[],
                unanchored=[
                    {
                        "term_name": "新品类X",
                        "object_code": "AUTO_DISCOVERED",
                        "raw_type": "未知业务对象",
                        "evidence": None,
                    }
                ],
            ),
        )
        created_terms: list[dict[str, Any]] = []
        monkeypatch.setattr(
            platform,
            "create_term",
            lambda base_id, *, term: (
                created_terms.append(term),
                {
                    "created": 1,
                    "updated": 0,
                    "skipped": 0,
                    "term_ids": ["term-ad-1"],
                    "errors": [],
                },
            )[1],
        )
        monkeypatch.setattr(
            platform,
            "create_term_knowledge",
            lambda base_id, *, knowledge: {"knowledgeId": "k1"},
        )
        result = await platform.discover_object_instances_unstructured(
            BASE_ID,
            instance_id="term-input",
            object_codes=["by_opportunity"],
        )
        # 发现结果不含 AUTO_DISCOVERED 兜底实例（正常实例照常返回）
        assert [h.instance_id for h in result.items] == ["t-existing"]
        # 但仍入库：直写创建（词表飞轮）+ 提及关系（已有实例在前、新实例在后）
        assert len(created_terms) == 1
        assert created_terms[0]["term_type_code"] == "AUTO_DISCOVERED"
        assert created_terms[0]["ext_attrs"]["raw_type"] == "未知业务对象"
        assert platform.created_relations == [
            {
                "sourceTermId": "term-input",
                "targetTermId": "t-existing",
                "relationName": "提及",
                "relationCategory": "BUSINESS",
            },
            {
                "sourceTermId": "term-input",
                "targetTermId": "term-ad-1",
                "relationName": "提及",
                "relationCategory": "BUSINESS",
            },
        ]
        # 共现仍计入 AUTO_DISCOVERED 实例（过滤只影响返回，不影响入库副作用）
        co_ids = {
            c[1]["term_id"]
            for c in platform.calls
            if c[0] == "update_term_co_occurrence"
        }
        assert "term-ad-1" in co_ids
        assert "t-existing" in co_ids

    @pytest.mark.asyncio
    async def test_full_flow_filters_source_instance_itself(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """主流程：锚定回输入实例自身（instance_id == 输入 term）的条目不作为发现结果返回。"""
        platform = _FakePlatform()
        platform.document = _make_document()

        async def fake_new_instances(*a: Any, **k: Any) -> list[dict[str, Any]]:
            return []

        monkeypatch.setattr(
            platform, "_discover_new_object_instances", fake_new_instances
        )
        monkeypatch.setattr(
            platform,
            "_discover_existing_object_instances",
            lambda *a, **k: discovery_module._AnchorResult(
                existing=[
                    # 输入实例自身（如 object_codes 含 Document 时 LLM 抽出文档名锚定回输入）
                    _term_row("term-input", "业务本体", "Document"),
                    _term_row("t-existing", "张三"),
                ],
                ambiguity=[],
                synonym=[],
                unanchored=[],
            ),
        )
        result = await platform.discover_object_instances_unstructured(
            BASE_ID,
            instance_id="term-input",
            object_codes=["by_opportunity", "Document"],
        )
        # 输入实例自身被过滤，其余正常返回
        assert [h.instance_id for h in result.items] == ["t-existing"]
        # 输入实例自身不建立自引用提及关系；其他已有实例正常建立
        assert platform.created_relations == [
            {
                "sourceTermId": "term-input",
                "targetTermId": "t-existing",
                "relationName": "提及",
                "relationCategory": "BUSINESS",
            }
        ]


# ============================================================================
# 同步裁决：同名多候选（歧义）/ 子串重叠（同义），temp=0 带上下文一票
# ============================================================================


class TestAdjudication:
    @pytest.fixture(autouse=True)
    def _reset_cache(self) -> Any:
        discovery_module.invalidate_vocabulary_cache()
        yield
        discovery_module.invalidate_vocabulary_cache()

    @pytest.mark.asyncio
    async def test_no_conflict_skips_adjudication(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """无冲突候选 → 直通不调裁决 LLM。"""
        platform = _FakePlatform()
        called: list[Any] = []
        monkeypatch.setattr(
            platform,
            "_invoke_judge_llm",
            lambda messages: called.append(1) or _AiMessage("{}"),
        )
        hits = await platform._adjudicate_candidates(
            base_id=BASE_ID,
            ambiguity=[],
            synonym=[],
            source_term_id="term-input",
        )
        assert hits == []
        assert not called

    @pytest.mark.asyncio
    async def test_synonym_same_writes_alias(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """同义 same=true → create_term_name（term_id=canonical、name_text=mention）、无新 term、缓存失效。"""
        platform = _FakePlatform()

        async def fake_judge(messages: list[dict[str, str]]) -> Any:
            return _AiMessage('{"same": true, "canonical": "t1"}')

        monkeypatch.setattr(platform, "_invoke_judge_llm", fake_judge)
        hits = await platform._adjudicate_candidates(
            base_id=BASE_ID,
            ambiguity=[],
            synonym=[{"mention": "苹果公司", "term": _term_row("t1", "苹果")}],
            source_term_id="term-input",
        )
        assert hits == []
        alias = next(c for c in platform.calls if c[0] == "create_term_name")
        assert alias[1]["name"]["termId"] == "t1"
        assert alias[1]["name"]["nameText"] == "苹果公司"
        # 无新 term 创建（create_term 未被调）
        assert all(c[0] != "create_term" for c in platform.calls)
        # 别名落库后缓存失效 → 下次 discover 重载
        assert discovery_module._cached_vocabulary is None

    @pytest.mark.asyncio
    async def test_synonym_same_writes_alias_idempotent(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """同义裁决重复归并同一别名（重复发现同一文档）：第二次写前查重命中 → 跳过，不抛错。"""
        platform = _FakePlatform()
        alias_writes: list[dict[str, Any]] = []

        # 模拟真实后端：create_term_name 成功后，查重可读到该行
        def fake_create_term_name(
            base_id: str, *, name: dict[str, Any]
        ) -> dict[str, Any]:
            platform.name_rows.append(
                {
                    "name_id": "n-1",
                    "term_id": name["termId"],
                    "name_text": name["nameText"],
                    "search_scope": {},
                }
            )
            alias_writes.append(name)
            return {"nameId": "n-1"}

        monkeypatch.setattr(platform, "create_term_name", fake_create_term_name)

        async def fake_judge(messages: list[dict[str, str]]) -> Any:
            return _AiMessage('{"same": true, "canonical": "t1"}')

        monkeypatch.setattr(platform, "_invoke_judge_llm", fake_judge)
        candidate = {"mention": "苹果公司", "term": _term_row("t1", "苹果")}
        await platform._adjudicate_candidates(
            base_id=BASE_ID,
            ambiguity=[],
            synonym=[candidate],
            source_term_id="term-input",
        )
        await platform._adjudicate_candidates(
            base_id=BASE_ID,
            ambiguity=[],
            synonym=[candidate],
            source_term_id="term-input",
        )
        # 第二次写前查重命中 → create_term_name 仅写入一次
        assert len(alias_writes) == 1

    def test_write_alias_skips_when_name_already_exists(self) -> None:
        """_write_alias 幂等：库中已有同 (term_id, name_text, 空 scope) 行 → 跳过写入。"""
        platform = _FakePlatform()
        platform.name_rows = [
            {
                "name_id": "n-1",
                "term_id": "t1",
                "name_text": "苹果公司",
                "search_scope": {},
            }
        ]
        platform._write_alias(base_id=BASE_ID, term_id="t1", name_text="苹果公司")
        assert all(c[0] != "create_term_name" for c in platform.calls)

    def test_write_alias_does_not_skip_different_name_or_scope(self) -> None:
        """_write_alias 查重精确：不同 name 或带非空 scope 的已有行不拦截本次写入（约束三元组不一致）。"""
        platform = _FakePlatform()
        platform.name_rows = [
            # 不同 name 不拦截
            {
                "name_id": "n-1",
                "term_id": "t1",
                "name_text": "苹果",
                "search_scope": {},
            },
            # 同 name 但带非空 scope 不拦截（不会撞 uq_term_name_scope）
            {
                "name_id": "n-2",
                "term_id": "t1",
                "name_text": "苹果公司",
                "search_scope": {"scope": "view"},
            },
        ]
        platform._write_alias(base_id=BASE_ID, term_id="t1", name_text="苹果公司")
        alias_calls = [c for c in platform.calls if c[0] == "create_term_name"]
        assert len(alias_calls) == 1

    @pytest.mark.asyncio
    async def test_synonym_not_same_creates_new_instance(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """同义 same=false → 独立新实例（复用 _create_new_instance_flow，能定类型用该类型）。"""
        platform = _FakePlatform()

        async def fake_judge(messages: list[dict[str, str]]) -> Any:
            return _AiMessage('{"same": false, "canonical": ""}')

        monkeypatch.setattr(platform, "_invoke_judge_llm", fake_judge)
        created: list[dict[str, Any]] = []

        async def fake_write_action(**kwargs: Any) -> dict[str, Any]:
            created.append(kwargs)
            return {"records": [{"termId": "term-adj-1"}]}

        monkeypatch.setattr(
            discovery_module, "invoke_object_write_action", fake_write_action
        )
        hits = await platform._adjudicate_candidates(
            base_id=BASE_ID,
            ambiguity=[],
            synonym=[
                {
                    "mention": "苹果公司",
                    "term": _term_row("t1", "苹果"),
                    "object_code": "by_opportunity",
                }
            ],
            source_term_id="term-input",
        )
        assert len(hits) == 1
        assert hits[0].instance_id == "term-adj-1"
        assert hits[0].instance_name == "苹果公司"
        assert hits[0].object_code == "by_opportunity"
        assert hits[0].is_new is True
        assert len(created) == 1
        # 同义裁决 false 不写别名
        assert all(c[0] != "create_term_name" for c in platform.calls)

    @pytest.mark.asyncio
    async def test_ambiguity_distinct_creates_auto_discovered_when_no_type(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """歧义 same_entity=false 且 mention 类型定不了 → AUTO_DISCOVERED 通道。"""
        platform = _FakePlatform()

        async def fake_judge(messages: list[dict[str, str]]) -> Any:
            return _AiMessage('{"same_entity": false, "entity_names": ["张三"]}')

        monkeypatch.setattr(platform, "_invoke_judge_llm", fake_judge)
        created_terms: list[dict[str, Any]] = []
        monkeypatch.setattr(
            platform,
            "create_term",
            lambda base_id, *, term: (
                created_terms.append(term),
                {"term_ids": ["term-adj-2"]},
            )[1],
        )
        monkeypatch.setattr(
            platform,
            "create_term_knowledge",
            lambda base_id, *, knowledge: {"knowledgeId": "k"},
        )
        hits = await platform._adjudicate_candidates(
            base_id=BASE_ID,
            ambiguity=[
                {
                    "mention": "张三",
                    "terms": [_term_row("t1", "张三"), _term_row("t2", "张三")],
                    "object_code": "AUTO_DISCOVERED",
                    "raw_type": "人员",
                }
            ],
            synonym=[],
            source_term_id="term-input",
        )
        assert len(hits) == 1
        assert hits[0].object_code == "AUTO_DISCOVERED"
        assert hits[0].instance_id == "term-adj-2"
        assert created_terms and created_terms[0]["term_type_code"] == "AUTO_DISCOVERED"
        assert created_terms[0]["ext_attrs"]["raw_type"] == "人员"

    @pytest.mark.asyncio
    async def test_co_occurrence_signal_defensive_when_empty(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """term_tags 无 co_occurrence（共现未写入）→ prompt 不带共现段，不阻塞。"""
        platform = _FakePlatform()
        captured: dict[str, Any] = {}

        async def fake_judge(messages: list[dict[str, str]]) -> Any:
            captured["messages"] = messages
            return _AiMessage('{"same": true, "canonical": "t1"}')

        monkeypatch.setattr(platform, "_invoke_judge_llm", fake_judge)
        await platform._adjudicate_candidates(
            base_id=BASE_ID,
            ambiguity=[],
            synonym=[{"mention": "苹果公司", "term": _term_row("t1", "苹果")}],
            source_term_id="term-input",
        )
        user = next(m for m in captured["messages"] if m["role"] == "user")
        assert "共现" not in user["content"]
        assert "co_occurrence" not in user["content"]

    @pytest.mark.asyncio
    async def test_judge_invalid_json_retries(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """裁决 LLM 非法 JSON → 重试（≤3 次退避），第二次成功即返回。"""
        platform = _FakePlatform()
        calls: list[Any] = []
        outputs = ["不是JSON{{", '{"same": true, "canonical": "t1"}']

        async def fake_judge(messages: list[dict[str, str]]) -> Any:
            calls.append(messages)
            return _AiMessage(outputs[min(len(calls) - 1, 1)])

        monkeypatch.setattr(platform, "_invoke_judge_llm", fake_judge)
        monkeypatch.setattr(discovery_module, "_JSON_RETRY_BACKOFF_SECONDS", 0)
        hits = await platform._adjudicate_candidates(
            base_id=BASE_ID,
            ambiguity=[],
            synonym=[{"mention": "苹果公司", "term": _term_row("t1", "苹果")}],
            source_term_id="term-input",
        )
        assert hits == []
        assert len(calls) == 2
        alias = next(c for c in platform.calls if c[0] == "create_term_name")
        assert alias[1]["name"]["nameText"] == "苹果公司"

    @pytest.mark.asyncio
    async def test_judge_think_block_stripped(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """裁决响应 <think> 块剥离后解析。"""
        platform = _FakePlatform()

        async def fake_judge(messages: list[dict[str, str]]) -> Any:
            return _AiMessage('<think>判断中</think>\n{"same": false, "canonical": ""}')

        monkeypatch.setattr(platform, "_invoke_judge_llm", fake_judge)

        async def fake_write_action(**kwargs: Any) -> dict[str, Any]:
            return {"records": [{"termId": "term-adj-3"}]}

        monkeypatch.setattr(
            discovery_module, "invoke_object_write_action", fake_write_action
        )
        hits = await platform._adjudicate_candidates(
            base_id=BASE_ID,
            ambiguity=[],
            synonym=[
                {
                    "mention": "苹果公司",
                    "term": _term_row("t1", "苹果"),
                    "object_code": "by_opportunity",
                }
            ],
            source_term_id="term-input",
        )
        assert len(hits) == 1
        assert hits[0].instance_id == "term-adj-3"

    @pytest.mark.asyncio
    async def test_full_flow_exact_miss_creates_new_instance(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """主流程：精确反查落空（即使子串重叠）→ unanchored → 创建新实例。

        v3 语义：不做 BM25 兜底产生同义候选，词表旧/子串重叠一律走新实例创建，
        不写别名（create_term_name 不再触发）。
        """
        platform = _FakePlatform()
        platform.document = _make_document()
        # 词典含 mention 词（回填后词典即含该词）→ 快路命中 → 精确反查落空
        platform.vocab_words = ["苹果", "苹果公司"]
        platform.term_search_results = {"total": 0, "items": []}
        raw = (
            '[{"term_name": "苹果公司", "object_code": "by_opportunity",'
            ' "evidence": "苹果公司"}]'
        )

        async def fake_invoke(messages: list[dict[str, str]]) -> Any:
            return _AiMessage(raw)

        async def fake_write_action(**kwargs: Any) -> dict[str, Any]:
            return {"records": [{"termId": "term-new-1"}], "total": 1, "meta": {}}

        monkeypatch.setattr(platform, "_invoke_extract_llm", fake_invoke)
        monkeypatch.setattr(
            platform,
            "get_term_type",
            lambda base_id, *, library_id, type_code: {"type_name": "商机"},
        )
        monkeypatch.setattr(
            platform, "batch_create_vocabulary", lambda base_id, *, words: None
        )
        monkeypatch.setattr(
            discovery_module, "invoke_object_write_action", fake_write_action
        )
        result = await platform.discover_object_instances_unstructured(
            BASE_ID,
            instance_id="term-input",
            object_codes=["by_opportunity"],
        )
        assert [h.instance_id for h in result.items] == ["term-new-1"]
        assert result.items[0].is_new is True
        # 无同义候选 → 不写别名、不调同义裁决
        assert not any(c[0] == "create_term_name" for c in platform.calls)
        assert not any(c[0] == "_invoke_judge_llm" for c in platform.calls)
        # 新实例创建 → 提及关系（源→目标）
        assert any(c[0] == "create_term_relation" for c in platform.calls)


# ============================================================================
# 共现存储：term_tags.co_occurrence Top-50 计数，同文档实例两两 +1
# ============================================================================


class TestDocumentCoOccurrence:
    @pytest.fixture(autouse=True)
    def _reset_cache(self) -> Any:
        discovery_module.invalidate_vocabulary_cache()
        yield
        discovery_module.invalidate_vocabulary_cache()

    @staticmethod
    def _co_calls(platform: _FakePlatform) -> list[tuple[str, dict[str, int]]]:
        return [
            (c[1]["term_id"], c[1]["patch"])
            for c in platform.calls
            if c[0] == "update_term_co_occurrence"
        ]

    def test_aggregates_all_document_instances(self) -> None:
        """同文档实例两两 +1：C(n,2) 配对本地聚合后每 term 一次批量写。

        3 term → 3 次调用（而非旧的 6 次逐对双向写）；每 patch 携带全部伙伴。
        """
        platform = _FakePlatform()
        platform._update_document_co_occurrence(BASE_ID, ["t1", "t2", "t3"])
        calls = self._co_calls(platform)
        assert len(calls) == 3
        by_term = dict(calls)
        assert by_term == {
            "t1": {"t2": 1, "t3": 1},
            "t2": {"t1": 1, "t3": 1},
            "t3": {"t1": 1, "t2": 1},
        }

    def test_duplicate_term_ids_count_multiple(self) -> None:
        """重复 term_id 不配对自身、计数按出现次数累加（[t1,t1,t2] → t1-t2 各 +2）。"""
        platform = _FakePlatform()
        platform._update_document_co_occurrence(BASE_ID, ["t1", "t1", "t2"])
        calls = self._co_calls(platform)
        assert len(calls) == 2
        by_term = dict(calls)
        assert by_term == {"t1": {"t2": 2}, "t2": {"t1": 2}}

    def test_single_term_no_writes(self) -> None:
        """单 term（或全相同 term）无有效配对 → 不产生任何写调用。"""
        platform = _FakePlatform()
        platform._update_document_co_occurrence(BASE_ID, ["t1"])
        assert self._co_calls(platform) == []
        platform._update_document_co_occurrence(BASE_ID, ["t1", "t1"])
        assert self._co_calls(platform) == []

    def test_fifteen_terms_one_write_per_term(self) -> None:
        """15 term 两两聚合后只调 15 次（每 term 一次批量 patch），而非 C(15,2)×2=210 次。"""
        terms = [f"t{i}" for i in range(1, 16)]
        platform = _FakePlatform()
        platform._update_document_co_occurrence(BASE_ID, terms)
        calls = self._co_calls(platform)
        assert len(calls) == 15
        by_term = dict(calls)
        assert set(by_term) == set(terms)
        for term_id, patch in by_term.items():
            assert len(patch) == 14  # 每 term 携带全部 14 个伙伴
            assert term_id not in patch  # 不与自身配对
            assert set(patch) == set(terms) - {term_id}
            assert all(count == 1 for count in patch.values())

    def test_patch_multi_key_passthrough_top50_compatible(self) -> None:
        """patch 多 key 一次传递：Top-50 裁剪语义由 update_term_co_occurrence 实现内完成。"""
        platform = _FakePlatform()
        platform._update_document_co_occurrence(BASE_ID, ["t1", "t2", "t3", "t4"])
        calls = self._co_calls(platform)
        by_term = dict(calls)
        assert by_term["t1"] == {"t2": 1, "t3": 1, "t4": 1}
        assert by_term["t4"] == {"t1": 1, "t2": 1, "t3": 1}

    @pytest.mark.asyncio
    async def test_synonym_alias_targets_included(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """同义确认的别名 mention 计入 canonical 伙伴集（alias_targets 收集）。"""
        platform = _FakePlatform()
        alias_targets: list[str] = []

        async def fake_judge(messages: list[dict[str, str]]) -> Any:
            return _AiMessage('{"same": true, "canonical": "t1"}')

        monkeypatch.setattr(platform, "_invoke_judge_llm", fake_judge)
        hits = await platform._adjudicate_candidates(
            base_id=BASE_ID,
            ambiguity=[],
            synonym=[{"mention": "苹果公司", "term": _term_row("t1", "苹果")}],
            source_term_id="term-input",
            alias_targets=alias_targets,
        )
        assert hits == []
        assert alias_targets == ["t1"]

    @pytest.mark.asyncio
    async def test_full_flow_writes_co_occurrence(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """主流程 discover 成功后：已有 + 新建实例两两共现落库，不经过 update_term。"""
        platform = _FakePlatform()
        platform.document = _make_document()
        platform.vocab_words = ["张三"]
        platform.term_search_results = {
            "total": 1,
            "items": [_term_row("t-existing", "张三")],
        }
        raw = (
            '[{"term_name": "张三", "object_code": "by_opportunity"},'
            ' {"term_name": "新客户A", "object_code": "by_opportunity"}]'
        )

        async def fake_invoke(messages: list[dict[str, str]]) -> Any:
            return _AiMessage(raw)

        monkeypatch.setattr(platform, "_invoke_extract_llm", fake_invoke)
        monkeypatch.setattr(
            platform,
            "get_term_type",
            lambda base_id, *, library_id, type_code: {"type_name": "商机"},
        )
        monkeypatch.setattr(
            platform, "batch_create_vocabulary", lambda base_id, *, words: None
        )

        async def fake_write_action(**kwargs: Any) -> dict[str, Any]:
            return {"records": [{"termId": "term-new-1"}]}

        monkeypatch.setattr(
            discovery_module, "invoke_object_write_action", fake_write_action
        )
        result = await platform.discover_object_instances_unstructured(
            BASE_ID,
            instance_id="term-input",
            object_codes=["by_opportunity"],
        )
        assert [h.instance_id for h in result.items] == ["t-existing", "term-new-1"]
        calls = self._co_calls(platform)
        by_term = dict(calls)
        assert by_term == {
            "t-existing": {"term-new-1": 1},
            "term-new-1": {"t-existing": 1},
        }
        # 共现更新不经过 update_term（新写路径断言）
        assert all(c[0] != "update_term" for c in platform.calls)

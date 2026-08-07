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
        self.vocab_words: list[str] = []
        self.term_search_results: dict[str, Any] = {"data": [], "totalCount": 0}
        self.name_rows: list[dict[str, Any]] = []

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

    def list_term_names(self, base_id: str, **kwargs: Any) -> list[dict[str, Any]]:
        self.calls.append(("list_term_names", {"base_id": base_id, **kwargs}))
        return list(self.name_rows)

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

    # ── T8/T9/T10/T11 协议能力（默认实现；测试用 monkeypatch 覆盖具体行为）──

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
# ③④ 占位（T7/T8 已替换，仅保留 RPC 501 映射回归——T12 收口）
# ============================================================================


# ============================================================================
# T7 ③ AC 锚定：词典快路 + 反查兜底 + 结果分发
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

    def test_substring_overlap_produces_synonym_candidates(self) -> None:
        """mention 与已有 term 子串重叠（非相等）→ 同义候选队列。"""
        platform = _FakePlatform()
        platform.vocab_words = ["苹果公司", "苹果"]

        def _search(base_id: str, **kwargs: Any) -> dict[str, Any]:
            if kwargs.get("query_type") == "exact":
                return {"total": 0, "items": []}
            return {"total": 1, "items": [_term_row("t1", "苹果")]}

        platform.search_terms = _search  # type: ignore[method-assign]
        result = platform._discover_existing_object_instances(
            BASE_ID, mentions=[_mention("苹果公司")], object_codes=["by_opportunity"]
        )
        assert result.existing == []
        assert len(result.synonym) == 1
        assert result.synonym[0]["mention"] == "苹果公司"
        assert result.synonym[0]["term"]["term_name"] == "苹果"
        assert result.unanchored == []

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

    def test_alias_reverse_lookup_via_list_term_names(self) -> None:
        """别名反查路径：search 落空 → list_term_names(ilike) → term_ids 反查拿 term 详情。"""
        platform = _FakePlatform()
        platform.vocab_words = ["苹果公司"]
        platform.term_search_results = {"total": 0, "items": []}
        platform.name_rows = [
            {"name_id": "n1", "term_id": "t9", "name_text": "苹果公司"}
        ]
        # 第三次调用 search_terms（term_ids 反查）返回 term 详情
        called: list[dict[str, Any]] = []

        original_search = platform.search_terms

        def _search(base_id: str, **kwargs: Any) -> dict[str, Any]:
            called.append(kwargs)
            if kwargs.get("term_ids"):
                return {"total": 1, "items": [_term_row("t9", "Apple Inc.")]}
            return {"total": 0, "items": []}

        platform.search_terms = _search  # type: ignore[method-assign]
        result = platform._discover_existing_object_instances(
            BASE_ID, mentions=[_mention("苹果公司")], object_codes=["by_opportunity"]
        )
        assert original_search is not None
        assert len(result.existing) == 1
        assert result.existing[0]["term_id"] == "t9"
        assert result.existing[0]["evidence"] == "苹果公司"
        # exact → fulltext → term_ids 反查，共三次
        assert len(called) == 3

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


class _RpcComboPlatform(ObjectInstanceDiscoveryMixin):
    """组合平台：走真实 mixin 主流程（① 校验 + ③④ 占位短路），供 RPC 层测试。"""

    def __init__(self, behavior: str = "not_implemented") -> None:
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

    def update_term_co_occurrence(
        self, base_id: str, *, term_id: str, patch: dict[str, int]
    ) -> None:
        return None


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


# ============================================================================
# RPC 级错误码映射（T4 全套：404/400/403/500）
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
        """RPC 路径走真实 mixin ① 校验：空 object_codes → ValueError → 400。"""
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
# T7 RPC 级：输入实例含已有实例 mention → items 已有在前（is_new=False）
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
            return {"records": [{"termId": "term-new-1"}]}

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
# T4 串联：mock ③④ 占位方法后验证 ⑤⑥⑦⑧ 全链路
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
            session_id="session-1",
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
        # 登记先于建关系
        call_names = [c[0] for c in platform.calls]
        assert call_names.index("save_or_update_object_files") < call_names.index(
            "create_term_relation"
        )
        # 关系：源=输入实例、目标=新实例（仅一次，无反向）
        assert platform.created_relations == [
            {
                "sourceTermId": "term-input",
                "targetTermId": "term-new-1",
                "relationName": "提及",
            }
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
            session_id="session-1",
        )
        assert [h.instance_id for h in result.items] == ["term-new-1"]
        assert result.items[0].is_new is True

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
            session_id="session-1",
        )
        assert result.items == []
        # 归并：别名写回主 term（termId=canonical、nameText=mention）
        alias_call = next(c for c in platform.calls if c[0] == "create_term_name")
        assert alias_call[1]["name"]["termId"] == "t1"
        assert alias_call[1]["name"]["nameText"] == "张三"
        # 无新实例（不建 term、不建关系）
        assert all(c[0] != "create_term_relation" for c in platform.calls)

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
            session_id="session-1",
        )
        assert result.items == []
        alias_call = next(c for c in platform.calls if c[0] == "create_term_name")
        assert alias_call[1]["name"]["termId"] == "t1"
        assert alias_call[1]["name"]["nameText"] == "苹果公司"
        assert all(c[0] != "create_term_relation" for c in platform.calls)


# ============================================================================
# T6 词典缓存单例：惰性加载一次 / invalidate 后重载 / 新词生效
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
        # 词典新增词（模拟 D-2 回填 / ⑤ 创建后触发器投影）
        platform.vocab_words = ["苹果", "华为"]
        discovery_module.invalidate_vocabulary_cache()
        assert platform._vocabulary_words(BASE_ID) == frozenset({"苹果", "华为"})


# ============================================================================
# T6 适配器同步：remote / none 不抛 NotImplementedError，data_adapter 代理转发
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
# T8 ④ B 模式 LLM 抽取：类型枚举 / 16K 截断 / JSON 重试 / AUTO_DISCOVERED / 回填
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
        """LLM 经 build_llm()（temp=0 由环境默认）+ stream_invoke_with_thinking。"""
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
            lambda: (built.append(_FakeLlm()), _FakeLlm())[1],
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
        assert len(invoked) == 1
        assert invoked[0][2] is None  # on_event=None（无流式回调）


# ============================================================================
# T8 集成：真实 ④ 抽取 + ③ 锚定 + ⑤ 创建 全链路
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
            session_id="session-1",
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
            session_id="session-1",
        )
        assert [h.instance_name for h in result.items] == ["新客户A", "新客户B"]
        assert all(h.is_new for h in result.items)
        assert created == [
            "/by_opportunity/新客户A.md",
            "/by_opportunity/新客户B.md",
        ]
        assert len(platform.created_relations) == 2


# ============================================================================
# T9 AUTO_DISCOVERED 创建通道：方案 (a) 兜底直写 + TermType 预置行
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
            session_id="session-1",
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
        # 登记条目含 term_id（强校验值）
        assert len(platform.object_files) == 1
        ext = json.loads(platform.object_files[0][0]["extContent"])
        assert ext["term_id"] == "term-ad-1"
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
            session_id="session-1",
        )
        await platform._create_new_instance_flow(
            base_id=BASE_ID,
            source_term_id="term-input",
            candidate={**candidate, "term_name": "新品类Y"},
            session_id="session-1",
        )
        assert ensured == [
            ("AUTO_DISCOVERED", "自动发现类型"),
            ("AUTO_DISCOVERED", "自动发现类型"),
        ]

    @pytest.mark.asyncio
    async def test_non_auto_discovered_keeps_action_pipeline(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """非 AUTO_DISCOVERED 项仍走 action 管道（⑤ 回归不破坏）。"""
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
            return {"records": [{"termId": "term-new-1"}]}

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
            session_id="session-1",
        )
        assert hit.instance_id == "term-new-1"
        assert hit.object_code == "by_opportunity"
        assert not created_terms  # 未走直写通道

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
            session_id="session-1",
        )
        assert [h.instance_name for h in result.items] == ["新品类X"]
        hit = result.items[0]
        assert hit.instance_id == "term-ad-1"
        assert hit.object_code == "AUTO_DISCOVERED"
        assert hit.is_new is True
        assert len(created_terms) == 1
        assert created_terms[0]["ext_attrs"]["raw_type"] == "未知业务对象"
        assert created_terms[0]["labels"]["dc_status"] == "待整理"
        # 提及关系：输入实例 → 新实例
        assert platform.created_relations == [
            {
                "sourceTermId": "term-input",
                "targetTermId": "term-ad-1",
                "relationName": "提及",
            }
        ]


# ============================================================================
# T10 同步裁决：同名多候选（歧义）/ 子串重叠（同义），temp=0 带上下文一票
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
            session_id="session-1",
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
            session_id="session-1",
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
            session_id="session-1",
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
            session_id="session-1",
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
        """term_tags 无 co_occurrence（T11 未就绪）→ prompt 不带共现段，不阻塞。"""
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
            session_id="session-1",
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
            session_id="session-1",
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
            session_id="session-1",
        )
        assert len(hits) == 1
        assert hits[0].instance_id == "term-adj-3"

    @pytest.mark.asyncio
    async def test_full_flow_adjudicates_synonym_candidate(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """主流程：synonym 候选 → 裁决 same=true → 别名落库，无新实例。"""
        platform = _FakePlatform()
        platform.document = _make_document()
        # 词典含 mention 词（④ 回填后词典即含该词）→ 快路命中 → 反查 → 子串重叠 → synonym 候选
        platform.vocab_words = ["苹果", "苹果公司"]

        def fake_search(base_id: str, **kwargs: Any) -> dict[str, Any]:
            # 精确查询（term_name=苹果公司）无命中；BM25 兜底返回子串相关行"苹果"
            if kwargs.get("query_type") == "fulltext":
                return {"total": 1, "items": [_term_row("t1", "苹果")]}
            return {"total": 0, "items": []}

        monkeypatch.setattr(platform, "search_terms", fake_search)
        raw = (
            '[{"term_name": "苹果公司", "object_code": "by_opportunity",'
            ' "evidence": "苹果公司"}]'
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

        async def fake_judge(messages: list[dict[str, str]]) -> Any:
            return _AiMessage('{"same": true, "canonical": "t1"}')

        monkeypatch.setattr(platform, "_invoke_judge_llm", fake_judge)
        result = await platform.discover_object_instances_unstructured(
            BASE_ID,
            instance_id="term-input",
            object_codes=["by_opportunity"],
            session_id="session-1",
        )
        assert result.items == []
        alias = next(c for c in platform.calls if c[0] == "create_term_name")
        assert alias[1]["name"]["nameText"] == "苹果公司"
        assert all(c[0] != "create_term_relation" for c in platform.calls)


# ============================================================================
# T11 共现存储：term_tags.co_occurrence Top-50 计数，同文档实例两两 +1
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

    def test_pairs_all_document_instances(self) -> None:
        """同文档实例两两 +1：C(n,2) 双向写入。"""
        platform = _FakePlatform()
        platform._update_document_co_occurrence(BASE_ID, ["t1", "t2", "t3"])
        calls = self._co_calls(platform)
        assert len(calls) == 6
        pairs = {(term_id, next(iter(patch))) for term_id, patch in calls}
        assert pairs == {
            ("t1", "t2"),
            ("t1", "t3"),
            ("t2", "t1"),
            ("t2", "t3"),
            ("t3", "t1"),
            ("t3", "t2"),
        }
        assert all(patch == {partner: 1} for _, patch in calls for partner in patch)

    def test_dedupes_term_ids(self) -> None:
        """重复 term_id 去重后再配对。"""
        platform = _FakePlatform()
        platform._update_document_co_occurrence(BASE_ID, ["t1", "t1", "t2"])
        calls = self._co_calls(platform)
        assert len(calls) == 2  # t1-t2 双向
        pairs = {(term_id, next(iter(patch))) for term_id, patch in calls}
        assert pairs == {("t1", "t2"), ("t2", "t1")}

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
            session_id="s1",
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
            session_id="session-1",
        )
        assert [h.instance_id for h in result.items] == ["t-existing", "term-new-1"]
        calls = self._co_calls(platform)
        pairs = {(term_id, next(iter(patch))) for term_id, patch in calls}
        assert pairs == {("t-existing", "term-new-1"), ("term-new-1", "t-existing")}
        # 共现更新不经过 update_term（新写路径断言）
        assert all(c[0] != "update_term" for c in platform.calls)

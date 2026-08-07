"""Tests for bounded document enrichment orchestration."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

import pytest

from datacloud_platform.mixins.document_enrich import (
    DocumentEnrichMixin,
    _remove_leading_thinking,
)
from datacloud_platform.models.document import (
    DocumentContentResult,
    DocumentEnrichObjectScope,
    DocumentEnrichStatus,
    DocumentFragmentItem,
    DocumentFragmentResult,
    Pagination,
    QueryRelatedDocumentObjectsRequest,
    RelatedDocumentRelationItem,
    RelatedDocumentRelationPage,
    RelatedTermInfo,
    SearchDocumentFragmentsRequest,
)

BASE_ID = "base-1"
TARGET_TERM_ID = "term-target"


def test_remove_leading_thinking_keeps_only_final_document() -> None:
    content = (
        "<think>分析 YAML、正文和关系格式。</think>\n\n"
        "<analysis>再次检查属性。</analysis>\n"
        "---\nname: value\n---\n# 正文"
    )

    assert _remove_leading_thinking(content) == "---\nname: value\n---\n# 正文"


def _object_scope() -> list[DocumentEnrichObjectScope]:
    return [
        DocumentEnrichObjectScope(objectCode="customer", objectName="客户"),
        DocumentEnrichObjectScope(objectCode="partner", objectName="合作伙伴"),
        DocumentEnrichObjectScope(objectCode="customer", objectName="客户"),
    ]


def _target_object(
    object_code: str = "customer",
    object_name: str = "客户",
) -> DocumentEnrichObjectScope:
    return DocumentEnrichObjectScope(
        objectCode=object_code,
        objectName=object_name,
    )


def _term(
    term_id: str,
    term_name: str,
    object_code: str,
    file_path: str,
) -> RelatedTermInfo:
    return RelatedTermInfo(
        termId=term_id,
        termName=term_name,
        termCode=f"{object_code}.{term_id}",
        termTypeCode=object_code,
        kbResourceId="kb-1",
        filePath=file_path,
    )


class FakeDocumentEnrichPlatform(DocumentEnrichMixin):
    """Minimal host providing the capabilities consumed by DocumentEnrichMixin."""

    def __init__(
        self,
        *,
        fail_generation: bool = False,
        use_generic_template: bool = False,
        invalid_output: bool = False,
    ) -> None:
        self.fail_generation = fail_generation
        self.use_generic_template = use_generic_template
        self.invalid_output = invalid_output
        self.messages: list[dict[str, str]] = []
        self.loaded_term_ids: list[str] = []
        self.requested_object_codes: list[str] = []
        self.contents = {
            TARGET_TERM_ID: DocumentContentResult(
                termId=TARGET_TERM_ID,
                kbResourceId="kb-1",
                filePath="/customers/acme.md",
                content="# 客户增长计划\n\n客户增长计划聚焦续约和渠道协同。",
            ),
            "term-partner-b": DocumentContentResult(
                termId="term-partner-b",
                kbResourceId="kb-1",
                filePath="/partners/beta.md",
                content=(
                    "# Beta 合作伙伴\n\n"
                    "完全无关的办公地点说明。\n\n"
                    "客户增长计划依赖 Beta 合作伙伴提供渠道覆盖和联合交付。"
                ),
            ),
        }
        target = _term(
            TARGET_TERM_ID,
            "客户增长计划",
            "customer",
            "/customers/acme.md",
        )
        partner_a = _term(
            "term-partner-a",
            "Alpha 合作伙伴",
            "partner",
            "/partners/alpha.md",
        )
        partner_b = _term(
            "term-partner-b",
            "Beta 合作伙伴",
            "partner",
            "/partners/beta.md",
        )
        self.relations = RelatedDocumentRelationPage(
            items=(
                RelatedDocumentRelationItem(
                    relationId="r1",
                    relationName="合作",
                    relationCategory="business",
                    source=partner_a,
                    target=target,
                ),
                RelatedDocumentRelationItem(
                    relationId="r2",
                    relationName="合作",
                    relationCategory="business",
                    source=partner_b,
                    target=target,
                ),
                RelatedDocumentRelationItem(
                    relationId="r3",
                    relationName="协作",
                    relationCategory="business",
                    source=target,
                    target=partner_a,
                ),
            ),
            pagination=Pagination(
                pageIndex=1,
                pageSize=50,
                total=3,
                totalPages=1,
            ),
        )
        self.fragments = DocumentFragmentResult(
            items=(
                DocumentFragmentItem(
                    knCode="kb-1",
                    filePath="/partners/alpha.md",
                    chunkText="Alpha 合作伙伴负责北区渠道和客户联合方案。",
                    score=0.95,
                ),
                DocumentFragmentItem(
                    knCode="kb-1",
                    filePath="/research/renewal.md",
                    chunkText="续约成功率通常受交付响应速度影响。",
                    score=0.88,
                    metadata={
                        "termTypeCode": "customer",
                        "termName": "续约研究",
                    },
                ),
            )
        )

    async def query_related_document_objects(
        self,
        base_id: str,
        *,
        request: QueryRelatedDocumentObjectsRequest,
    ) -> RelatedDocumentRelationPage:
        assert base_id == BASE_ID
        assert request.term_id == TARGET_TERM_ID
        return self.relations

    async def get_document_content_by_term_id(
        self,
        base_id: str,
        *,
        term_id: str,
    ) -> DocumentContentResult:
        assert base_id == BASE_ID
        self.loaded_term_ids.append(term_id)
        return self.contents[term_id]

    async def search_knowledge_fragments(
        self,
        base_id: str,
        *,
        request: SearchDocumentFragmentsRequest,
    ) -> DocumentFragmentResult:
        assert base_id == BASE_ID
        assert request.object_codes == ("customer", "partner")
        assert "客户增长计划" in request.query
        return self.fragments

    def get_object_detail(
        self,
        base_id: str,
        object_code: str,
    ) -> dict[str, Any] | None:
        assert base_id == BASE_ID
        self.requested_object_codes.append(object_code)
        details: dict[str, dict[str, Any]] = {
            "customer": {
                "objectCode": "customer",
                "objectName": "客户",
                "objectDesc": "企业客户及其经营信息",
                "properties": [
                    {
                        "propertyName": "续约日期",
                        "propertyCode": "renewal_date",
                        "dataType": "DATE",
                        "businessDefinition": "当前合同的计划续约日期",
                    }
                ],
                "extProperty": {
                    "template": (
                        "## 5. 实例卡片模板\n\n"
                        "```markdown\n"
                        "---\n"
                        'renewal_date: "{{renewal_date}}"\n'
                        "---\n"
                        "# {{instance_name}}\n\n"
                        "## 增长目标\n\n"
                        "{{growth_goal}}\n\n"
                        "## 执行策略\n\n"
                        "{{execution_strategy}}\n\n"
                        "<!--- relation --->\n"
                        "<!--- relation --->\n"
                        "```\n"
                    )
                },
                "relations": [
                    {
                        "relationName": "协作",
                        "sourceObjectCode": "customer",
                        "targetObjectCode": "partner",
                        "targetObjectName": "合作伙伴",
                    },
                    {
                        "relationName": "合作",
                        "sourceObjectCode": "partner",
                        "targetObjectCode": "customer",
                        "targetObjectName": "客户",
                    },
                ],
            },
            "partner": {
                "objectCode": "partner",
                "objectName": "合作伙伴",
                "objectDesc": "提供联合交付能力的外部伙伴",
            },
        }
        detail = details.get(object_code)
        if detail is not None and self.use_generic_template:
            detail.pop("extProperty", None)
        return detail

    async def _generate_enriched_document(
        self,
        messages: list[dict[str, str]],
        *,
        on_event: Callable[[Any], None] | None,
    ) -> str:
        del on_event
        if self.fail_generation:
            raise RuntimeError("model unavailable")
        self.messages = messages
        if self.invalid_output:
            return "# 缺少 YAML 和关系区块"
        if self.use_generic_template:
            return (
                "---\n"
                'renewal_date: "2027-01-01"\n'
                "---\n"
                "# 客户增长计划\n\n"
                "## 概述\n\n客户增长计划聚焦续约。\n\n"
                "## 核心信息\n\n计划续约日期为 2027-01-01。\n\n"
                "## 详细说明\n\n"
                "通过 [[合作伙伴/Alpha 合作伙伴]] 扩展渠道。\n\n"
                "## 相关信息\n\n相关事实以检索素材为依据。\n\n"
                "<!--- relation --->\n"
                "(协作)[[合作伙伴/Alpha 合作伙伴]]\n"
                "<!--- relation --->"
            )
        return (
            "---\n"
            'renewal_date: "2027-01-01"\n'
            "---\n"
            "# 客户增长计划\n\n"
            "## 增长目标\n\n提升客户续约表现。\n\n"
            "## 执行策略\n\n"
            "客户增长计划通过 [[合作伙伴/Alpha 合作伙伴]] 扩展渠道。\n\n"
            "<!--- relation --->\n"
            "(协作)[[合作伙伴/Alpha 合作伙伴]]\n"
            "<!--- relation --->"
        )


@pytest.mark.asyncio
async def test_enrich_uses_labelled_bounded_evidence_and_relation_fallback(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(
        logging.INFO,
        logger="datacloud_platform.mixins.document_enrich",
    )
    platform = FakeDocumentEnrichPlatform()

    result = await platform.enrich(
        BASE_ID,
        object_scope=_object_scope(),
        target_object=_target_object(),
        term_id=TARGET_TERM_ID,
    )

    assert result.status is DocumentEnrichStatus.SUCCESS
    assert result.exception_info is None
    assert result.enriched_content.startswith("---\nrenewal_date:")
    assert "## 增长目标" in result.enriched_content
    assert "## 执行策略" in result.enriched_content
    assert "[[合作伙伴/Alpha 合作伙伴]]" in result.enriched_content
    assert "<!--- relation --->" not in result.enriched_content
    assert "(协作)" not in result.enriched_content
    assert len(result.relations) == 1
    assert result.relations[0].relation_name == "协作"
    assert result.relations[0].target_object_type == "合作伙伴"
    assert result.relations[0].target_instance_name == "Alpha 合作伙伴"
    prompt = platform.messages[1]["content"]
    assert "renewal_date" in prompt
    assert "## 增长目标" in prompt
    assert "(协作)[[合作伙伴/Alpha 合作伙伴]]" in prompt
    assert "[客户/客户增长计划]" in prompt
    assert "[合作伙伴/Alpha 合作伙伴]" in prompt
    assert "[合作伙伴/Beta 合作伙伴]" in prompt
    assert "[客户/对象定义]" in prompt
    assert "[合作伙伴/对象定义]" not in prompt
    assert "当前合同的计划续约日期" in prompt
    assert "Alpha 合作伙伴负责北区渠道" in prompt
    assert "客户增长计划依赖 Beta 合作伙伴" in prompt
    assert "完全无关的办公地点说明" not in prompt
    assert platform.loaded_term_ids == [TARGET_TERM_ID, "term-partner-b"]
    assert platform.requested_object_codes == ["customer"]
    assert {
        record.name
        for record in caplog.records
        if "document_enrich" in record.getMessage()
    } == {"datacloud_platform.mixins.document_enrich"}
    log_messages = [record.getMessage() for record in caplog.records]
    for stage in (
        "start",
        "load_original_document",
        "load_object_definition",
        "query_document_relations",
        "search_knowledge_fragments",
        "collect_evidence",
        "build_prompt",
        "invoke_llm",
        "validate_output",
        "complete",
    ):
        assert any(f"stage={stage}" in message for message in log_messages)
    assert any("status=success" in message for message in log_messages)
    llm_input_log = next(message for message in log_messages if "llm_input" in message)
    assert "客户增长计划聚焦续约和渠道协同" in llm_input_log
    assert "Alpha 合作伙伴负责北区渠道和客户联合方案" in llm_input_log
    llm_output_log = next(
        message for message in log_messages if "llm_output" in message
    )
    assert 'renewal_date: "2027-01-01"' in llm_output_log
    assert "(协作)[[合作伙伴/Alpha 合作伙伴]]" in llm_output_log


@pytest.mark.asyncio
async def test_enrich_skips_invalid_scope_without_retrieval() -> None:
    platform = FakeDocumentEnrichPlatform()

    result = await platform.enrich(
        BASE_ID,
        object_scope=[],
        target_object=_target_object(),
        term_id=TARGET_TERM_ID,
    )

    assert result.status is DocumentEnrichStatus.SKIPPED
    assert result.exception_info == "object_scope must contain at least one object"
    assert result.enriched_content == ""
    assert platform.loaded_term_ids == []


@pytest.mark.asyncio
async def test_enrich_skips_when_target_object_detail_is_missing() -> None:
    platform = FakeDocumentEnrichPlatform()

    result = await platform.enrich(
        BASE_ID,
        object_scope=_object_scope(),
        target_object=_target_object("missing-object", "缺失对象"),
        term_id=TARGET_TERM_ID,
    )

    assert result.status is DocumentEnrichStatus.SKIPPED
    assert result.exception_info == (
        "object detail not found: base_id=base-1 object_code=missing-object"
    )
    assert platform.requested_object_codes == ["missing-object"]
    assert platform.messages == []


@pytest.mark.asyncio
async def test_enrich_returns_failed_status_and_exception_information() -> None:
    platform = FakeDocumentEnrichPlatform(fail_generation=True)

    result = await platform.enrich(
        BASE_ID,
        object_scope=_object_scope(),
        target_object=_target_object(),
        term_id=TARGET_TERM_ID,
    )

    assert result.status is DocumentEnrichStatus.FAILED
    assert result.exception_info == "RuntimeError: model unavailable"
    assert result.enriched_content == ""


@pytest.mark.asyncio
async def test_enrich_uses_generic_template_when_object_template_is_missing() -> None:
    platform = FakeDocumentEnrichPlatform(use_generic_template=True)

    result = await platform.enrich(
        BASE_ID,
        object_scope=_object_scope(),
        target_object=_target_object(),
        term_id=TARGET_TERM_ID,
    )

    assert result.status is DocumentEnrichStatus.SUCCESS
    assert "## 概述" in result.enriched_content
    assert "## 核心信息" in result.enriched_content
    assert "## 详细说明" in result.enriched_content
    assert "## 相关信息" in result.enriched_content


@pytest.mark.asyncio
async def test_enrich_rejects_output_that_does_not_follow_strict_format() -> None:
    platform = FakeDocumentEnrichPlatform(invalid_output=True)

    result = await platform.enrich(
        BASE_ID,
        object_scope=_object_scope(),
        target_object=_target_object(),
        term_id=TARGET_TERM_ID,
    )

    assert result.status is DocumentEnrichStatus.FAILED
    assert result.exception_info == (
        "ValueError: LLM output must start with YAML front matter"
    )

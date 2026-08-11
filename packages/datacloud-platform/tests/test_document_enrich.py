"""Tests for bounded document enrichment orchestration."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

import pytest

from datacloud_platform.mixins.document_enrich import (
    DocumentEnrichMixin,
    _extract_document_template,
    _object_relation_definitions,
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
ORIGINAL_CONTENT = "# 客户增长计划\n\n客户增长计划聚焦续约和渠道协同。"


def test_remove_leading_thinking_keeps_only_final_document() -> None:
    content = (
        "<think>分析 YAML、正文和关系格式。</think>\n\n"
        "<analysis>再次检查属性。</analysis>\n"
        "---\nname: value\n---\n# 正文"
    )

    assert _remove_leading_thinking(content) == "---\nname: value\n---\n# 正文"


@pytest.mark.parametrize(
    "object_detail",
    [
        {"template": "# {{name}}\n\n## 业务说明\n\n{{description}}"},
        {
            "extProperty": (
                '{"template":"# {{name}}\\n\\n## 业务说明\\n\\n{{description}}"}'
            )
        },
    ],
)
def test_extract_document_template_supports_object_detail_variants(
    object_detail: dict[str, object],
) -> None:
    assert _extract_document_template(object_detail) == (
        "# {{name}}\n\n## 业务说明\n\n{{description}}"
    )


def test_object_relation_definitions_supports_ext_property_rules() -> None:
    object_detail = {
        "objectCode": "Ability",
        "extProperty": {
            "rules": (
                "source_object_type: Ability\n"
                "allowed_relations:\n"
                "- direction: outgoing\n"
                "  relation_code: supports\n"
                "  relation_name: 支撑\n"
                "  target_object_types:\n"
                "  - Feature\n"
                "  - Ability\n"
            )
        },
    }

    assert _object_relation_definitions(object_detail) == (
        {
            "relationName": "支撑",
            "sourceObjectCode": "Ability",
            "targetObjectCode": "Feature",
        },
        {
            "relationName": "支撑",
            "sourceObjectCode": "Ability",
            "targetObjectCode": "Ability",
        },
    )


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
        invalid_yaml_keys: bool = False,
        relation_target_not_in_body: bool = False,
        invalid_relation_lines: bool = False,
        unknown_body_reference: bool = False,
        missing_reference_object_code: bool = False,
        template_constraint_violations: bool = False,
        malformed_yaml: bool = False,
        invalid_original_yaml: bool = False,
        nested_quote_yaml: bool = False,
        unquoted_reference_yaml: bool = False,
        internal_original_yaml_fields: bool = False,
    ) -> None:
        self.fail_generation = fail_generation
        self.use_generic_template = use_generic_template
        self.invalid_output = invalid_output
        self.invalid_yaml_keys = invalid_yaml_keys
        self.relation_target_not_in_body = relation_target_not_in_body
        self.invalid_relation_lines = invalid_relation_lines
        self.unknown_body_reference = unknown_body_reference
        self.missing_reference_object_code = missing_reference_object_code
        self.template_constraint_violations = template_constraint_violations
        self.malformed_yaml = malformed_yaml
        self.nested_quote_yaml = nested_quote_yaml
        self.unquoted_reference_yaml = unquoted_reference_yaml
        self.messages: list[dict[str, str]] = []
        self.loaded_term_ids: list[str] = []
        self.requested_object_codes: list[str] = []
        original_content = ORIGINAL_CONTENT
        if malformed_yaml:
            original_yaml = (
                "renewal_date: [invalid"
                if invalid_original_yaml
                else 'renewal_date: "2026-12-31"\nlegacy_property: remove-me'
            )
            original_content = f"---\n{original_yaml}\n---\n\n{ORIGINAL_CONTENT}"
        if internal_original_yaml_fields:
            original_content = (
                "---\n"
                'renewal_date: "2026-12-31"\n'
                'dc_status: "发现失败-待重试"\n'
                'dc_failure_reason: "模型服务超时"\n'
                "dc_failure_count: 1\n"
                "dc_last_organized_at: null\n"
                "---\n\n"
                f"{ORIGINAL_CONTENT}"
            )
        self.contents = {
            TARGET_TERM_ID: DocumentContentResult(
                termId=TARGET_TERM_ID,
                kbResourceId="kb-1",
                filePath="/customers/acme.md",
                content=original_content,
            ),
            "term-partner-a": DocumentContentResult(
                termId="term-partner-a",
                kbResourceId="kb-1",
                filePath="/partners/alpha.md",
                content=(
                    "---\n"
                    "internal_only: remove-me\n"
                    "---\n"
                    "# Alpha 合作伙伴\n\n"
                    "面向客户的联合方案。\n\n"
                    "Alpha 负责支持客户/客户增长计划的北区渠道建设。\n\n"
                    "后续将扩展联合交付范围。"
                ),
            ),
            "term-partner-b": DocumentContentResult(
                termId="term-partner-b",
                kbResourceId="kb-1",
                filePath="/partners/beta.md",
                content=(
                    "---\n"
                    "internal_only: remove-me\n"
                    "---\n"
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
                    termId="term-partner-a",
                    termName="Alpha 合作伙伴",
                    objectCode="partner",
                    knCode="kb-1",
                    filePath="/partners/alpha.md",
                    chunkText="Alpha 合作伙伴负责北区渠道和客户联合方案。",
                    score=0.95,
                ),
                DocumentFragmentItem(
                    termId="term-research",
                    termName="续约研究",
                    objectCode="customer",
                    knCode="kb-1",
                    filePath="/research/renewal.md",
                    chunkText="续约成功率通常受交付响应速度影响。",
                    score=0.88,
                    metadata={
                        "termTypeCode": "customer",
                        "termName": "续约研究",
                    },
                ),
                DocumentFragmentItem(
                    termId=TARGET_TERM_ID,
                    termName="客户增长计划",
                    objectCode="customer",
                    knCode="kb-1",
                    filePath="/customers/acme.md",
                    chunkText="当前文档的语义命中也暂时保留。",
                    score=0.8,
                ),
                *(
                    (
                        DocumentFragmentItem(
                            termId="term-without-object-code",
                            termName="编码缺失实例",
                            objectCode="",
                            knCode="kb-1",
                            filePath="/research/missing-code.md",
                            chunkText="该片段没有返回对象编码。",
                            score=0.75,
                            metadata={"objectName": "研究对象"},
                        ),
                    )
                    if missing_reference_object_code
                    else ()
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
        assert request.direction == "incoming"
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
                        "## 2. 头部字段填写说明\n\n"
                        "续约日期必须来自可靠素材。\n\n"
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
        if detail is not None and (
            self.nested_quote_yaml or self.unquoted_reference_yaml
        ):
            properties = detail.get("properties")
            assert isinstance(properties, list)
            properties.append(
                {
                    "propertyName": "来源引用",
                    "propertyCode": "source_refs",
                    "dataType": "STRING",
                }
            )
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
        if self.template_constraint_violations:
            return (
                "---\n"
                'renewal_date: "2027-01-01"\n'
                "---\n"
                "# 客户增长计划\n\n"
                "正文不包含对象模板规定的章节。\n\n"
                "{{unreplaced_placeholder}}\n\n"
                "<!--- relation --->\n"
                "\n"
                "<!--- relation --->"
            )
        if self.malformed_yaml:
            return (
                "---\n"
                "renewal_date: [invalid\n"
                "---\n"
                "# 客户增长计划\n\n"
                "客户增长计划聚焦续约。\n\n"
                "<!--- relation --->\n"
                "\n"
                "<!--- relation --->"
            )
        if self.nested_quote_yaml:
            return (
                "---\n"
                'renewal_date: "2027-01-01"\n'
                "source_refs:\n"
                '  - "[事件/台风"白海豚"](term-typhoon)"\n'
                '  - "[事件/第13号强台风"白海豚"](term-strong-typhoon)"\n'
                "---\n"
                "# 客户增长计划\n\n"
                "客户增长计划聚焦续约。\n\n"
                "<!--- relation --->\n"
                "\n"
                "<!--- relation --->"
            )
        if self.unquoted_reference_yaml:
            return (
                "---\n"
                'renewal_date: "2027-01-01"\n'
                "source_refs:\n"
                "  - [事件/7月全国线下消费支付金额同比上涨2.2%]"
                "(term-consumption)\n"
                "---\n"
                "# 客户增长计划\n\n"
                "客户增长计划聚焦续约。\n\n"
                "<!--- relation --->\n"
                "\n"
                "<!--- relation --->"
            )
        if self.use_generic_template:
            return (
                "---\n"
                'renewal_date: "2027-01-01"\n'
                "---\n"
                "# 客户增长计划\n\n"
                "## 概述\n\n客户增长计划聚焦续约。\n\n"
                "## 核心信息\n\n计划续约日期为 2027-01-01。\n\n"
                "## 详细说明\n\n"
                "通过 [合作伙伴/Alpha 合作伙伴]() 扩展渠道。\n\n"
                "## 相关信息\n\n相关事实以检索素材为依据。\n\n"
                "<!--- relation --->\n"
                "(协作)[合作伙伴/Alpha 合作伙伴]\n"
                "<!--- relation --->"
            )
        yaml_content = (
            "relations:\n  supports: []"
            if self.invalid_yaml_keys
            else 'renewal_date: "2027-01-01"'
        )
        body_relation_content = (
            "客户增长计划由 Alpha 合作伙伴扩展渠道。"
            if self.relation_target_not_in_body
            else (
                "客户增长计划通过 "
                "[合作伙伴/Alpha 合作伙伴](错误-id) 扩展渠道，"
                "并由 [合作伙伴/Alpha 合作伙伴](term-partner-a) 联合交付。"
            )
        )
        if self.unknown_body_reference:
            body_relation_content += "\n\n接口说明见 [API/REST](https://example.com)。"
        if self.missing_reference_object_code:
            body_relation_content += (
                "\n\n补充参考 [研究对象/编码缺失实例](term-without-object-code)。"
            )
        relation_content = "(协作)[合作伙伴/Alpha 合作伙伴]"
        if self.invalid_relation_lines:
            relation_content = (
                "(协作)[合作伙伴/Alpha 合作伙伴]\n"
                "(协作)[合作伙伴/Alpha 合作伙伴](错误-id)\n"
                "(未知关系)[合作伙伴/Alpha 合作伙伴](term-partner-a)\n"
                "这不是合法关系"
            )
        return (
            "---\n"
            f"{yaml_content}\n"
            "---\n"
            "# 客户增长计划\n\n"
            "## 增长目标\n\n提升客户续约表现。\n\n"
            "## 执行策略\n\n"
            f"{body_relation_content}\n\n"
            "<!--- relation --->\n"
            f"{relation_content}\n"
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
    assert "[合作伙伴/Alpha 合作伙伴](term-partner-a)" in result.enriched_content
    assert "错误-id" not in result.enriched_content
    assert "<!--- relation --->" not in result.enriched_content
    assert "(协作)" not in result.enriched_content
    assert len(result.relations) == 2
    assert result.relations[0].relation_name == "协作"
    assert result.relations[0].target_object_code == "partner"
    assert result.relations[0].target_object_type == "合作伙伴"
    assert result.relations[0].target_instance_name == "Alpha 合作伙伴"
    assert result.relations[0].target_term_id == "term-partner-a"
    assert result.relations[1].relation_name == "提及"
    assert result.relations[1].target_object_code == "partner"
    assert result.relations[1].target_object_type == "合作伙伴"
    assert result.relations[1].target_instance_name == "Alpha 合作伙伴"
    assert result.relations[1].target_term_id == "term-partner-a"
    prompt = platform.messages[1]["content"]
    assert "renewal_date" in prompt
    assert "## 增长目标" in prompt
    assert "关系名称：协作；目标对象类型：合作伙伴" in prompt
    assert "## 对象定义中的文档格式模板（必须严格使用）" in prompt
    assert "## 对象定义中的完整 template（生成约束）" in prompt
    assert "续约日期必须来自可靠素材" in prompt
    assert "## 增长目标" in prompt
    assert "## 执行策略" in prompt
    assert "[客户/客户增长计划](term-target)" in prompt
    assert "[合作伙伴/Alpha 合作伙伴](term-partner-a)" in prompt
    assert "[合作伙伴/Beta 合作伙伴](term-partner-b)" in prompt
    assert "[客户/续约研究](term-research)" in prompt
    assert "[客户/对象定义]" in prompt
    assert "[合作伙伴/对象定义]" not in prompt
    assert "当前合同的计划续约日期" in prompt
    assert "Alpha 合作伙伴负责北区渠道" in prompt
    assert "当前文档的语义命中也暂时保留" in prompt
    assert "客户增长计划依赖 Beta 合作伙伴" in prompt
    assert "完全无关的办公地点说明" not in prompt
    assert "internal_only: remove-me" not in prompt
    assert "Alpha 负责支持客户/客户增长计划" in prompt
    assert platform.loaded_term_ids == [
        TARGET_TERM_ID,
        "term-partner-a",
        "term-partner-b",
    ]
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
    assert "[合作伙伴/Alpha 合作伙伴](错误-id)" in llm_output_log


@pytest.mark.asyncio
async def test_enrich_loads_original_before_skipping_invalid_scope() -> None:
    platform = FakeDocumentEnrichPlatform()

    result = await platform.enrich(
        BASE_ID,
        object_scope=[],
        target_object=_target_object(),
        term_id=TARGET_TERM_ID,
    )

    assert result.status is DocumentEnrichStatus.SKIPPED
    assert result.exception_info == "object_scope must contain at least one object"
    assert result.enriched_content == ORIGINAL_CONTENT
    assert platform.loaded_term_ids == [TARGET_TERM_ID]


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
    assert result.enriched_content == ORIGINAL_CONTENT
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
    assert result.enriched_content == ORIGINAL_CONTENT


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
    assert (
        "## 通用文档格式模板（对象定义未提供 template）"
        in (platform.messages[1]["content"])
    )


@pytest.mark.asyncio
async def test_enrich_normalizes_missing_and_unexpected_yaml_keys() -> None:
    platform = FakeDocumentEnrichPlatform(invalid_yaml_keys=True)

    result = await platform.enrich(
        BASE_ID,
        object_scope=_object_scope(),
        target_object=_target_object(),
        term_id=TARGET_TERM_ID,
    )

    assert result.status is DocumentEnrichStatus.SUCCESS
    assert result.enriched_content.startswith("---\nrenewal_date: null\n---")
    assert "relations:" not in result.enriched_content


@pytest.mark.asyncio
async def test_enrich_accepts_relation_target_not_referenced_in_body() -> None:
    platform = FakeDocumentEnrichPlatform(relation_target_not_in_body=True)

    result = await platform.enrich(
        BASE_ID,
        object_scope=_object_scope(),
        target_object=_target_object(),
        term_id=TARGET_TERM_ID,
    )

    assert result.status is DocumentEnrichStatus.SUCCESS
    assert len(result.relations) == 1
    assert result.relations[0].relation_name == "协作"
    assert result.relations[0].target_term_id == "term-partner-a"


@pytest.mark.asyncio
async def test_enrich_ignores_invalid_and_duplicate_relation_lines(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(
        logging.WARNING,
        logger="datacloud_platform.mixins.document_enrich",
    )
    platform = FakeDocumentEnrichPlatform(invalid_relation_lines=True)

    result = await platform.enrich(
        BASE_ID,
        object_scope=_object_scope(),
        target_object=_target_object(),
        term_id=TARGET_TERM_ID,
    )

    assert result.status is DocumentEnrichStatus.SUCCESS
    assert [
        (relation.relation_name, relation.target_term_id)
        for relation in result.relations
    ] == [
        ("协作", "term-partner-a"),
        ("提及", "term-partner-a"),
    ]
    assert any(
        "Ignored unknown LLM outgoing relation" in record.getMessage()
        for record in caplog.records
    )
    assert any(
        "Ignored malformed LLM relation line" in record.getMessage()
        for record in caplog.records
    )


@pytest.mark.asyncio
async def test_enrich_preserves_unknown_body_reference_without_extracting_relation(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(
        logging.WARNING,
        logger="datacloud_platform.mixins.document_enrich",
    )
    platform = FakeDocumentEnrichPlatform(unknown_body_reference=True)

    result = await platform.enrich(
        BASE_ID,
        object_scope=_object_scope(),
        target_object=_target_object(),
        term_id=TARGET_TERM_ID,
    )

    assert result.status is DocumentEnrichStatus.SUCCESS
    assert "[API/REST](https://example.com)" in result.enriched_content
    assert all(relation.target_instance_name != "REST" for relation in result.relations)
    assert any(
        "Preserved unknown LLM entity reference" in record.getMessage()
        for record in caplog.records
    )


@pytest.mark.asyncio
async def test_enrich_returns_none_when_reference_object_code_is_unavailable() -> None:
    platform = FakeDocumentEnrichPlatform(missing_reference_object_code=True)

    result = await platform.enrich(
        BASE_ID,
        object_scope=_object_scope(),
        target_object=_target_object(),
        term_id=TARGET_TERM_ID,
    )

    assert result.status is DocumentEnrichStatus.SUCCESS
    relation = next(
        item
        for item in result.relations
        if item.target_term_id == "term-without-object-code"
    )
    assert relation.relation_name == "提及"
    assert relation.target_object_code is None
    assert relation.model_dump(by_alias=True)["targetObjectCode"] is None


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
    assert result.enriched_content == ORIGINAL_CONTENT


@pytest.mark.asyncio
async def test_enrich_treats_document_template_as_prompt_guidance_only() -> None:
    platform = FakeDocumentEnrichPlatform(template_constraint_violations=True)

    result = await platform.enrich(
        BASE_ID,
        object_scope=_object_scope(),
        target_object=_target_object(),
        term_id=TARGET_TERM_ID,
    )

    assert result.status is DocumentEnrichStatus.SUCCESS
    assert "## 增长目标" not in result.enriched_content
    assert "## 执行策略" not in result.enriched_content
    assert "{{unreplaced_placeholder}}" in result.enriched_content
    assert result.relations == ()


@pytest.mark.asyncio
async def test_enrich_falls_back_to_original_yaml_front_matter(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(
        logging.WARNING,
        logger="datacloud_platform.mixins.document_enrich",
    )
    platform = FakeDocumentEnrichPlatform(malformed_yaml=True)

    result = await platform.enrich(
        BASE_ID,
        object_scope=_object_scope(),
        target_object=_target_object(),
        term_id=TARGET_TERM_ID,
    )

    assert result.status is DocumentEnrichStatus.SUCCESS
    assert result.enriched_content.startswith("---\nrenewal_date: '2026-12-31'\n---")
    assert "legacy_property" not in result.enriched_content
    assert any(
        "source=llm target=original reason=invalid_yaml" in record.getMessage()
        for record in caplog.records
    )
    assert any(
        "source=original status=used" in record.getMessage()
        for record in caplog.records
    )


@pytest.mark.asyncio
async def test_enrich_uses_null_yaml_when_original_yaml_is_invalid(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(
        logging.WARNING,
        logger="datacloud_platform.mixins.document_enrich",
    )
    platform = FakeDocumentEnrichPlatform(
        malformed_yaml=True,
        invalid_original_yaml=True,
    )

    result = await platform.enrich(
        BASE_ID,
        object_scope=_object_scope(),
        target_object=_target_object(),
        term_id=TARGET_TERM_ID,
    )

    assert result.status is DocumentEnrichStatus.SUCCESS
    assert result.enriched_content.startswith("---\nrenewal_date: null\n---")
    assert any(
        "source=null status=used reason=invalid_original_yaml" in record.getMessage()
        for record in caplog.records
    )


@pytest.mark.asyncio
async def test_enrich_repairs_nested_double_quotes_in_yaml(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(
        logging.WARNING,
        logger="datacloud_platform.mixins.document_enrich",
    )
    platform = FakeDocumentEnrichPlatform(nested_quote_yaml=True)

    result = await platform.enrich(
        BASE_ID,
        object_scope=_object_scope(),
        target_object=_target_object(),
        term_id=TARGET_TERM_ID,
    )

    assert result.status is DocumentEnrichStatus.SUCCESS
    assert '[事件/台风"白海豚"](term-typhoon)' in result.enriched_content
    assert '[事件/第13号强台风"白海豚"](term-strong-typhoon)' in result.enriched_content
    assert any(
        "status=used strategy=normalize_string_quoting repaired_line_count=2"
        in record.getMessage()
        for record in caplog.records
    )
    assert not any("yaml_fallback" in record.getMessage() for record in caplog.records)


@pytest.mark.asyncio
async def test_enrich_quotes_unquoted_markdown_references_in_yaml(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(
        logging.WARNING,
        logger="datacloud_platform.mixins.document_enrich",
    )
    platform = FakeDocumentEnrichPlatform(unquoted_reference_yaml=True)

    result = await platform.enrich(
        BASE_ID,
        object_scope=_object_scope(),
        target_object=_target_object(),
        term_id=TARGET_TERM_ID,
    )

    assert result.status is DocumentEnrichStatus.SUCCESS
    assert (
        "[事件/7月全国线下消费支付金额同比上涨2.2%](term-consumption)"
        in result.enriched_content
    )
    assert any(
        "status=used strategy=normalize_string_quoting repaired_line_count=1"
        in record.getMessage()
        for record in caplog.records
    )
    assert not any("yaml_fallback" in record.getMessage() for record in caplog.records)


@pytest.mark.asyncio
async def test_enrich_filters_internal_fields_from_original_yaml(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(
        logging.INFO,
        logger="datacloud_platform.mixins.document_enrich",
    )
    platform = FakeDocumentEnrichPlatform(internal_original_yaml_fields=True)

    result = await platform.enrich(
        BASE_ID,
        object_scope=_object_scope(),
        target_object=_target_object(),
        term_id=TARGET_TERM_ID,
    )

    assert result.status is DocumentEnrichStatus.SUCCESS
    prompt = platform.messages[1]["content"]
    for field_name in (
        "dc_status",
        "dc_failure_reason",
        "dc_failure_count",
        "dc_last_organized_at",
    ):
        assert field_name not in prompt
        assert field_name not in result.enriched_content
    assert "renewal_date: '2026-12-31'" in prompt
    assert any(
        "original_yaml_filtered" in record.getMessage()
        and "strategy=parsed" in record.getMessage()
        for record in caplog.records
    )

from __future__ import annotations

import json
import logging
from typing import Any

import pytest
from datacloud_knowledge.object_instance_build import (
    ObjectInstanceBuildRequest,
    ObjectInstanceFragment,
    build_object_instance,
)
from datacloud_knowledge.object_instance_build.parser import (
    ObjectInstanceBuildLabelValidationError,
    parse_object_instance_build_result,
)
from datacloud_knowledge.object_instance_build.prompts import (
    build_enum_prompt_constraints,
    build_object_instance_prompt,
    build_object_instance_retry_prompt,
)


def _label_schema(enum_count: int = 3) -> dict[str, Any]:
    enum_values = [
        {
            "term_id": f"term-{index}",
            "code": f"code-{index}",
            "name": f"枚举值{index}",
            "aliases": [f"别名{index}"],
        }
        for index in range(enum_count)
    ]
    enum_values[1] = {
        "term_id": "term-public",
        "code": "public",
        "name": "通用概念",
        "aliases": ["公共概念"],
    }
    return {
        "name": {
            "field_code": "name",
            "field_name": "名称",
            "data_type": "STRING",
            "required": True,
            "value_kind": "string",
        },
        "owner_type": {
            "field_code": "owner_type",
            "field_name": "概念归属",
            "data_type": "STRING",
            "required": True,
            "value_kind": "enum",
            "terminology": {
                "term_field": "owner_type",
                "term_type_code": "Concept_owner_type",
                "term_master_type": "DICT_TERM",
            },
            "enum_values": enum_values,
        },
    }


def _request(label_schema: dict[str, Any]) -> ObjectInstanceBuildRequest:
    return ObjectInstanceBuildRequest(
        instance_id="term-agent",
        origin_instance_id="origin-agent",
        term_detail={"term_name": "Agent", "term_type": "Concept"},
        object_schema={"objectCode": "Concept"},
        label_schema=label_schema,
        source_content="Agent 是通用概念，包含 Memory、Reasoning、Action。",
        fragments=[
            ObjectInstanceFragment(
                fragment_id="fragment-agent-001",
                content="Agent 是通用概念。",
                origin_file={"file_path": "/Concept/Agent.md"},
            )
        ],
    )


def test_enum_prompt_constraints_limit_large_enum_values_to_50() -> None:
    request = _request(_label_schema(enum_count=120))

    constraints = build_enum_prompt_constraints(request)

    assert "owner_type" in constraints
    assert len(constraints["owner_type"]["enum_prompt_values"]) == 50
    assert constraints["owner_type"]["enum_prompt_values"][0]["code"] == "public"


def test_object_instance_prompt_uses_object_template_as_merge_constraint() -> None:
    request = ObjectInstanceBuildRequest(
        instance_id="term-agent",
        origin_instance_id="origin-agent",
        term_detail={"term_name": "Agent", "term_type": "Concept"},
        object_schema={"objectCode": "Concept"},
        label_schema=_label_schema(),
        object_template=(
            "---\n"
            'name: "{{value}}"\n'
            'owner_type: "{{value}}"\n'
            "---\n\n"
            "# {{name}}\n\n"
            "## 对象说明\n\n"
            "{{object_description}}\n"
        ),
        template_constraints="## 2. 头部字段填写说明\n\n字段必须与 object.schema.yaml 一致。",
        existing_content=(
            "---\n"
            "name: Agent\n"
            "relations:\n"
            "  maps-to:\n"
            "  - Concept: []\n"
            "---\n\n"
            "# Agent\n\n"
            "## 投标标签\n\n"
            "原有投标标签内容。\n"
        ),
        source_content="Agent source content",
        fragments=[
            ObjectInstanceFragment(
                fragment_id="fragment-agent-001",
                content="Agent fragment content",
                origin_file={"file_path": "/Concept/Agent.md"},
            )
        ],
    )

    prompt = build_object_instance_prompt(request)

    assert '"object_template"' in prompt
    assert '"template_constraints"' in prompt
    assert '"existing_content"' in prompt
    assert "# {{name}}" in prompt
    assert "## 投标标签" in prompt
    assert "字段必须与 object.schema.yaml 一致" in prompt
    assert "existing_content 是当前对象实例已有 Markdown" in prompt
    assert "只有 existing_content 为空时，才按照 object_template" in prompt
    assert "第一个非空字符必须是 {" in prompt
    assert "禁止输出 <think>" in prompt
    assert (
        "不得删除 existing_content 中已有的 frontmatter 字段、relations、标题和正文段落" in prompt
    )


def test_retry_prompt_requires_json_only_and_omits_raw_output() -> None:
    prompt = build_object_instance_retry_prompt(
        original_prompt="ORIGINAL_PROMPT_WITH_existing_content",
        raw_output="<think>错误推理</think>\n# 本体论\n\n错误 Markdown 正文",
        parse_error="LLM output must be a JSON object",
        label_schema={"name": {"field_code": "name"}},
    )

    assert "ORIGINAL_PROMPT_WITH_existing_content" in prompt
    assert "忽略上一次输出" in prompt
    assert "第一个非空字符必须是 {" in prompt
    assert "最后一个非空字符必须是 }" in prompt
    assert "禁止输出 <think>" in prompt
    assert "错误推理" not in prompt
    assert "错误 Markdown 正文" not in prompt


@pytest.mark.asyncio
async def test_build_object_instance_retries_when_existing_content_is_deleted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeMessage:
        def __init__(self, content: str) -> None:
            self.content = content

    class FakeLLM:
        def __init__(self) -> None:
            self.calls: list[str] = []

        async def ainvoke(self, prompt: str) -> FakeMessage:
            self.calls.append(prompt)
            if len(self.calls) == 1:
                return FakeMessage(
                    json.dumps(
                        {
                            "content": (
                                "---\nname: Agent\n---\n\n# Agent\n\n## 对象说明\n\n缩水后的内容。"
                            ),
                            "labels": {"name": "Agent", "owner_type": "public"},
                        },
                        ensure_ascii=False,
                    )
                )
            return FakeMessage(
                json.dumps(
                    {
                        "content": (
                            "---\n"
                            "name: Agent\n"
                            "relations:\n"
                            "  maps-to:\n"
                            "  - Concept: []\n"
                            "---\n\n"
                            "# Agent\n\n"
                            "## 投标标签\n\n"
                            "原有投标标签内容。\n\n"
                            "## 对象说明\n\n"
                            "增强后的内容。"
                        ),
                        "labels": {"name": "Agent", "owner_type": "public"},
                    },
                    ensure_ascii=False,
                )
            )

    fake_llm = FakeLLM()
    monkeypatch.setattr(
        "datacloud_knowledge.object_instance_build.service.build_llm",
        lambda: fake_llm,
    )
    request = _request(_label_schema())
    request = ObjectInstanceBuildRequest(
        instance_id=request.instance_id,
        origin_instance_id=request.origin_instance_id,
        term_detail=request.term_detail,
        object_schema=request.object_schema,
        label_schema=request.label_schema,
        existing_content=(
            "---\n"
            "name: Agent\n"
            "relations:\n"
            "  maps-to:\n"
            "  - Concept: []\n"
            "---\n\n"
            "# Agent\n\n"
            "## 投标标签\n\n"
            "原有投标标签内容。"
        ),
        source_content=request.source_content,
        fragments=request.fragments,
    )

    result = await build_object_instance(request)

    assert "## 投标标签" in result.content
    assert "relations:" in result.content
    assert result.diagnostics["retry_count"] == 1
    assert len(fake_llm.calls) == 2


@pytest.mark.asyncio
async def test_build_object_instance_ignores_json_inside_think_block(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeMessage:
        def __init__(self, content: str) -> None:
            self.content = content

    class FakeLLM:
        async def ainvoke(self, prompt: str) -> FakeMessage:
            thought_payload = json.dumps(
                {
                    "content": "错误的思考过程 JSON",
                    "labels": {"name": "Wrong", "owner_type": "public"},
                },
                ensure_ascii=False,
            )
            final_payload = json.dumps(
                {
                    "content": "Agent 是通用概念。",
                    "labels": {"name": "Agent", "owner_type": "public"},
                },
                ensure_ascii=False,
            )
            return FakeMessage(f"<think>{thought_payload}</think>\n{final_payload}")

    monkeypatch.setattr(
        "datacloud_knowledge.object_instance_build.service.build_llm",
        FakeLLM,
    )

    result = await build_object_instance(_request(_label_schema()))

    assert result.content == "Agent 是通用概念。"
    assert result.labels["name"] == "Agent"


@pytest.mark.asyncio
async def test_build_object_instance_rejects_markdown_without_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeMessage:
        def __init__(self, content: str) -> None:
            self.content = content

    class FakeLLM:
        async def ainvoke(self, prompt: str) -> FakeMessage:
            return FakeMessage("# Agent\n\n这是一段 Markdown 正文，不是 JSON。")

    monkeypatch.setattr(
        "datacloud_knowledge.object_instance_build.service.build_llm",
        FakeLLM,
    )

    with pytest.raises(Exception, match="LLM output must be a JSON object"):
        await build_object_instance(_request(_label_schema()))


def test_parse_result_normalizes_enum_name_to_code() -> None:
    payload = {
        "content": "Agent 是通用概念。",
        "labels": {"name": "Agent", "owner_type": "通用概念"},
        "file_description": "Agent 概念对象实例",
        "diagnostics": {"used_fragment_ids": ["fragment-agent-001"]},
    }

    result = parse_object_instance_build_result(
        payload=payload,
        label_schema=_label_schema(),
        retry_count=0,
    )

    assert result.labels["owner_type"] == "public"


def test_parse_result_ignores_labels_outside_schema() -> None:
    payload = {
        "content": "Agent is a common concept.",
        "labels": {"name": "Agent", "kb_id": "97"},
        "diagnostics": {"used_fragment_ids": ["fragment-agent-001"]},
    }

    result = parse_object_instance_build_result(
        payload=payload,
        label_schema=_label_schema(),
        retry_count=0,
    )

    assert result.labels == {"name": "Agent"}
    assert result.diagnostics["ignored_label_fields"] == ["kb_id"]


def test_parse_result_rejects_enum_value_outside_full_enum_values() -> None:
    payload = {
        "content": "Agent 是通用概念。",
        "labels": {"name": "Agent", "owner_type": "enterprise"},
        "file_description": "Agent 概念对象实例",
        "diagnostics": {"used_fragment_ids": ["fragment-agent-001"]},
    }

    with pytest.raises(ObjectInstanceBuildLabelValidationError):
        parse_object_instance_build_result(
            payload=payload,
            label_schema=_label_schema(),
            retry_count=0,
        )


def test_parse_result_rejects_list_for_single_enum_field() -> None:
    payload = {
        "content": "Agent is a common concept.",
        "labels": {"name": "Agent", "owner_type": ["public"]},
        "file_description": "Agent concept object instance",
    }

    with pytest.raises(ObjectInstanceBuildLabelValidationError):
        parse_object_instance_build_result(
            payload=payload,
            label_schema=_label_schema(),
            retry_count=0,
        )


def test_parse_result_accepts_list_for_multi_enum_field() -> None:
    label_schema = _label_schema()
    label_schema["owner_type"]["multiple"] = True
    payload = {
        "content": "Agent is a common concept.",
        "labels": {"name": "Agent", "owner_type": ["public", "public"]},
        "file_description": "Agent concept object instance",
    }

    result = parse_object_instance_build_result(
        payload=payload,
        label_schema=label_schema,
        retry_count=0,
    )

    assert result.labels["owner_type"] == ["public"]


@pytest.mark.asyncio
async def test_build_object_instance_retries_invalid_enum_then_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeMessage:
        def __init__(self, content: str) -> None:
            self.content = content

    class FakeLLM:
        def __init__(self) -> None:
            self.calls: list[str] = []

        async def ainvoke(self, prompt: str) -> FakeMessage:
            self.calls.append(prompt)
            if len(self.calls) == 1:
                return FakeMessage(
                    json.dumps(
                        {
                            "content": "Agent 是通用概念。",
                            "labels": {"name": "Agent", "owner_type": "enterprise"},
                        },
                        ensure_ascii=False,
                    )
                )
            return FakeMessage(
                json.dumps(
                    {
                        "content": "Agent 是通用概念。",
                        "labels": {"name": "Agent", "owner_type": "public"},
                        "diagnostics": {"used_fragment_ids": ["fragment-agent-001"]},
                    },
                    ensure_ascii=False,
                )
            )

    fake_llm = FakeLLM()
    monkeypatch.setattr(
        "datacloud_knowledge.object_instance_build.service.build_llm",
        lambda: fake_llm,
    )

    result = await build_object_instance(_request(_label_schema()))

    assert result.labels["owner_type"] == "public"
    assert result.diagnostics["retry_count"] == 1
    assert len(fake_llm.calls) == 2


@pytest.mark.asyncio
async def test_build_object_instance_extracts_json_from_text_part_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeMessage:
        def __init__(self, content: list[dict[str, str]]) -> None:
            self.content = content

    class FakeLLM:
        async def ainvoke(self, prompt: str) -> FakeMessage:
            payload = json.dumps(
                {
                    "content": "Agent is a common concept.",
                    "labels": {"name": "Agent", "owner_type": "public"},
                    "file_description": "Agent concept object instance",
                },
                ensure_ascii=False,
            )
            return FakeMessage(
                [
                    {
                        "type": "text",
                        "text": f"下面是生成结果：\n{payload}\n请验收。",
                    }
                ]
            )

    monkeypatch.setattr(
        "datacloud_knowledge.object_instance_build.service.build_llm",
        FakeLLM,
    )

    result = await build_object_instance(_request(_label_schema()))

    assert result.content == "Agent is a common concept."
    assert result.labels["owner_type"] == "public"


@pytest.mark.asyncio
async def test_build_object_instance_logs_raw_output_summary_on_parse_failure(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    class FakeMessage:
        def __init__(self, content: str) -> None:
            self.content = content

    class FakeLLM:
        async def ainvoke(self, prompt: str) -> FakeMessage:
            return FakeMessage("这不是 JSON，也没有 content/labels 字段。")

    monkeypatch.setattr(
        "datacloud_knowledge.object_instance_build.service.build_llm",
        FakeLLM,
    )
    caplog.set_level(
        logging.WARNING,
        logger="datacloud_knowledge.object_instance_build.service",
    )

    with pytest.raises(Exception, match="LLM output must be a JSON object"):
        await build_object_instance(_request(_label_schema()))

    messages = "\n".join(record.getMessage() for record in caplog.records)
    assert "object_instance_build llm_parse_failed retry_count=0" in messages
    assert '"raw_output_length"' in messages
    assert "这不是 JSON" in messages

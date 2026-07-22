from __future__ import annotations

import json
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
from datacloud_knowledge.object_instance_build.prompts import build_enum_prompt_constraints


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

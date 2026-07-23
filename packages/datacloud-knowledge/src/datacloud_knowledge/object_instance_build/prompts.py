"""Prompt builders for object instance build SDK."""

from __future__ import annotations

import json
from typing import Any

from datacloud_knowledge.object_instance_build.models import ObjectInstanceBuildRequest

MAX_ENUM_PROMPT_VALUES = 50


def build_enum_prompt_constraints(
    request: ObjectInstanceBuildRequest,
) -> dict[str, dict[str, Any]]:
    """Build compact enum constraints for prompt usage."""
    context = _build_matching_context(request)
    constraints: dict[str, dict[str, Any]] = {}

    for field_code, field_schema in request.label_schema.items():
        if not isinstance(field_schema, dict):
            continue
        enum_values = field_schema.get("enum_values") or []
        if not isinstance(enum_values, list) or not enum_values:
            continue

        prompt_values = _select_enum_prompt_values(enum_values, context)
        constraints[field_code] = {
            "field_code": field_schema.get("field_code") or field_code,
            "field_name": field_schema.get("field_name") or field_code,
            "term_type_code": _term_type_code(field_schema),
            "enum_prompt_values": prompt_values,
        }

    return constraints


def build_object_instance_prompt(request: ObjectInstanceBuildRequest) -> str:
    """Build the initial object instance generation prompt."""
    enum_constraints = build_enum_prompt_constraints(request)
    fragments = [
        {
            "fragment_id": fragment.fragment_id,
            "content": fragment.content,
            "origin_file": fragment.origin_file,
            "sort_key": fragment.sort_key,
        }
        for fragment in request.fragments
    ]
    payload = {
        "term_detail": request.term_detail,
        "object_schema": request.object_schema,
        "label_schema": request.label_schema,
        "enum_prompt_constraints": enum_constraints,
        "existing_content": request.existing_content,
        "object_template": request.object_template,
        "template_constraints": request.template_constraints,
        "source_content": request.source_content,
        "fragments": fragments,
    }
    return (
        "System:\n"
        "你是对象实例构建助手。只能输出一个 JSON object，不要输出解释性文字。\n\n"
        "User:\n"
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}\n\n"
        "输出协议:\n"
        "1. 只能输出一个 JSON object；第一个非空字符必须是 {，最后一个非空字符必须是 }。\n"
        "2. 禁止输出 <think>、解释文字、Markdown 代码块或 JSON 之外的任何文本。\n"
        "3. 禁止直接输出 Markdown 正文；Markdown 只能作为 JSON.content 的字符串值。\n"
        '4. JSON 顶层字段只能包含 "content", "labels", "file_description", '
        '"confidence", "model_name", "diagnostics"。\n'
        '5. 必须包含 "content" 和 "labels"，labels 必须是 JSON object。\n\n'
        "融合要求:\n"
        "1. content 必须是融合后的新 Markdown 文档，不是片段简单拼接。\n"
        "2. existing_content 是当前对象实例已有 Markdown；如果 existing_content 非空，"
        "必须以 existing_content 为基准做增强，保留已有信息并把 source_content/fragments 中的新信息补充进去。\n"
        "3. 不得删除 existing_content 中已有的 frontmatter 字段、relations、标题和正文段落；"
        "除非新片段明确指出原内容错误，否则只能补充、扩写、追加或局部修订。\n"
        "4. existing_content 非空时，以 existing_content 为唯一结构基准；"
        "不得因为 template_constraints 或 object_template 新增模板章节，例如 existing_content 原来没有 ## 对象说明，"
        "最终 content 也不能新增 ## 对象说明。\n"
        "5. object_template 是新建对象实例时的模板；只有 existing_content 为空时，"
        "才按照 object_template 的 Markdown/frontmatter 结构组织输出。\n"
        "6. template_constraints 是填写要求、字段说明、关系说明、常见错误和检查清单，"
        "必须作为生成 content 和 labels 的约束，不要把这些说明文字原样复制到最终 content。\n"
        "7. labels 只能包含 label_schema 中允许的字段。\n"
        "8. 枚举字段输出值必须使用枚举 code。\n"
    )


def build_object_instance_retry_prompt(
    *,
    original_prompt: str,
    raw_output: str,
    parse_error: str,
    label_schema: dict[str, Any],
) -> str:
    """Build retry prompt after invalid LLM output."""
    retry_context = {
        "parse_error": parse_error,
        "label_schema": label_schema,
        "raw_output_length": len(raw_output),
    }
    return (
        f"{original_prompt}\n\n"
        "上一次输出不符合要求。请忽略上一次输出的文本内容，只根据原始任务重新生成结果。\n"
        "必须严格遵守输出协议:\n"
        "1. 只能输出一个 JSON object；第一个非空字符必须是 {，最后一个非空字符必须是 }。\n"
        "2. 禁止输出 <think>、解释文字、Markdown 代码块或 JSON 之外的任何文本。\n"
        "3. 禁止直接输出 Markdown 正文；Markdown 只能作为 JSON.content 的字符串值。\n"
        '4. JSON 顶层字段只能包含 "content", "labels", "file_description", '
        '"confidence", "model_name", "diagnostics"。\n'
        "5. 如果 parse_error 包含 missing headings，必须从 original_prompt 的 existing_content 中恢复这些标题。\n"
        "错误摘要如下:\n"
        f"{json.dumps(retry_context, ensure_ascii=False, indent=2)}"
    )


def _build_matching_context(request: ObjectInstanceBuildRequest) -> str:
    parts = [
        json.dumps(request.term_detail, ensure_ascii=False),
        request.existing_content,
        request.object_template,
        request.template_constraints,
        request.source_content,
        *(fragment.content for fragment in request.fragments),
    ]
    return "\n".join(parts).casefold()


def _select_enum_prompt_values(
    enum_values: list[Any],
    context: str,
) -> list[dict[str, Any]]:
    normalized_options = [_normalize_enum_option(option) for option in enum_values]
    options = [option for option in normalized_options if option is not None]
    matched = [option for option in options if _option_matches_context(option, context)]
    selected = matched + [
        option
        for option in options
        if option.get("code") not in {matched_item.get("code") for matched_item in matched}
    ]
    return selected[:MAX_ENUM_PROMPT_VALUES]


def _normalize_enum_option(option: Any) -> dict[str, Any] | None:
    if not isinstance(option, dict):
        return None
    code = str(option.get("code") or option.get("term_code") or "").strip()
    if not code:
        return None
    aliases = option.get("aliases") or []
    if not isinstance(aliases, list):
        aliases = []
    return {
        "code": code,
        "name": str(option.get("name") or option.get("term_name") or "").strip(),
        "aliases": [str(alias) for alias in aliases if str(alias or "").strip()],
    }


def _option_matches_context(option: dict[str, Any], context: str) -> bool:
    values = [option.get("code"), option.get("name"), *(option.get("aliases") or [])]
    return any(str(value or "").casefold() in context for value in values if value)


def _term_type_code(field_schema: dict[str, Any]) -> str:
    terminology = field_schema.get("terminology") or {}
    if not isinstance(terminology, dict):
        return ""
    return str(terminology.get("term_type_code") or terminology.get("termTypeCode") or "")

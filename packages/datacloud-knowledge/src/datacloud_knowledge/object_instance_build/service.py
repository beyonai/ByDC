"""Service entry point for object instance build SDK."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from datacloud_knowledge.intent.llm_utils import build_llm
from datacloud_knowledge.object_instance_build.models import (
    ObjectInstanceBuildRequest,
    ObjectInstanceBuildResult,
)
from datacloud_knowledge.object_instance_build.parser import (
    ObjectInstanceBuildParseError,
    ObjectInstanceBuildResultError,
    parse_object_instance_build_result,
)
from datacloud_knowledge.object_instance_build.prompts import (
    build_object_instance_prompt,
    build_object_instance_retry_prompt,
)

MAX_JSON_PARSE_RETRIES = 2
RAW_OUTPUT_PREVIEW_CHARS = 500

logger = logging.getLogger(__name__)


async def build_object_instance(
    request: ObjectInstanceBuildRequest,
) -> ObjectInstanceBuildResult:
    """Build a fused object instance document and labels."""
    _validate_request(request)
    base_prompt = build_object_instance_prompt(request)
    prompt = base_prompt
    llm = build_llm()

    last_error: ObjectInstanceBuildResultError | None = None
    for retry_count in range(MAX_JSON_PARSE_RETRIES + 1):
        raw_message = await llm.ainvoke(prompt)
        raw_content = getattr(raw_message, "content", raw_message)
        payload = _extract_json_payload(raw_content)

        try:
            result = parse_object_instance_build_result(
                payload=payload,
                label_schema=request.label_schema,
                retry_count=retry_count,
            )
            _validate_existing_content_preserved(
                existing_content=request.existing_content,
                result_content=result.content,
            )
            return result
        except ObjectInstanceBuildResultError as exc:
            last_error = exc
            logger.warning(
                "object_instance_build llm_parse_failed retry_count=%s error=%s raw_output=%s",
                retry_count,
                str(exc),
                _json_for_log(_raw_output_summary(raw_content)),
            )
            if retry_count >= MAX_JSON_PARSE_RETRIES:
                raise
            prompt = build_object_instance_retry_prompt(
                original_prompt=base_prompt,
                raw_output=str(raw_content),
                parse_error=str(exc),
                label_schema=request.label_schema,
            )

    raise last_error or ObjectInstanceBuildParseError("failed to parse LLM result")


def _validate_request(request: ObjectInstanceBuildRequest) -> None:
    if not request.instance_id.strip():
        raise ValueError("instance_id is required")
    if not request.object_schema:
        raise ValueError("object_schema is required")
    if not request.label_schema:
        raise ValueError("label_schema is required")
    if not request.source_content.strip():
        raise ValueError("source_content is required")
    if not request.fragments:
        raise ValueError("fragments is required")
    for fragment in request.fragments:
        if not fragment.fragment_id.strip() or not fragment.content.strip():
            raise ValueError("fragment_id and content are required")


def _extract_json_payload(raw_content: Any) -> dict[str, Any] | None:
    raw_text = _content_to_text(raw_content)

    payload = _loads_json_object(raw_text)
    if payload is not None:
        return payload

    payload = _extract_fenced_json_object(raw_text)
    if payload is not None:
        return payload

    return _extract_embedded_json_object(raw_text)


def _validate_existing_content_preserved(
    *,
    existing_content: str,
    result_content: str,
) -> None:
    if not existing_content.strip():
        return

    missing_frontmatter_keys = _missing_frontmatter_keys(
        source=existing_content,
        target=result_content,
    )
    missing_headings = _missing_markdown_headings(
        source=existing_content,
        target=result_content,
    )
    if not missing_frontmatter_keys and not missing_headings:
        return

    details: list[str] = []
    if missing_frontmatter_keys:
        details.append(f"missing frontmatter keys: {', '.join(missing_frontmatter_keys[:5])}")
    if missing_headings:
        details.append(f"missing headings: {', '.join(missing_headings[:5])}")
    raise ObjectInstanceBuildParseError(
        f"LLM output removed existing content; {'; '.join(details)}"
    )


def _missing_frontmatter_keys(*, source: str, target: str) -> list[str]:
    source_keys = _frontmatter_keys(source)
    if not source_keys:
        return []
    target_keys = set(_frontmatter_keys(target))
    return [key for key in source_keys if key not in target_keys]


def _frontmatter_keys(markdown: str) -> list[str]:
    lines = markdown.splitlines()
    if not lines or lines[0].strip() != "---":
        return []
    keys: list[str] = []
    for line in lines[1:]:
        if line.strip() == "---":
            break
        match = re.match(r"^([A-Za-z_][A-Za-z0-9_-]*)\s*:", line)
        if match:
            keys.append(match.group(1))
    return keys


def _missing_markdown_headings(*, source: str, target: str) -> list[str]:
    source_headings = _markdown_headings(source)
    if not source_headings:
        return []
    target_headings = {_normalize_heading(heading) for heading in _markdown_headings(target)}
    return [
        heading for heading in source_headings if _normalize_heading(heading) not in target_headings
    ]


def _markdown_headings(markdown: str) -> list[str]:
    headings: list[str] = []
    for line in markdown.splitlines():
        if re.match(r"^#{1,6}\s+\S", line):
            headings.append(line.strip())
    return headings


def _normalize_heading(heading: str) -> str:
    return re.sub(r"\s+", " ", heading.strip()).casefold()


def _content_to_text(raw_content: Any) -> str:
    if isinstance(raw_content, str):
        return raw_content
    if isinstance(raw_content, dict):
        text = raw_content.get("text")
        if isinstance(text, str):
            return text
        content = raw_content.get("content")
        if isinstance(content, str):
            return content
        return json.dumps(raw_content, ensure_ascii=False, default=str)
    if isinstance(raw_content, list):
        return "\n".join(_content_to_text(part) for part in raw_content)
    return str(raw_content)


def _loads_json_object(raw_text: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError:
        return None
    if isinstance(payload, dict):
        return payload
    return None


def _extract_fenced_json_object(raw_text: str) -> dict[str, Any] | None:
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", raw_text, re.DOTALL)
    if match:
        return _loads_json_object(match.group(1).strip())
    return None


def _extract_embedded_json_object(raw_text: str) -> dict[str, Any] | None:
    decoder = json.JSONDecoder()
    for index, char in enumerate(raw_text):
        if char != "{":
            continue
        try:
            payload, _end = decoder.raw_decode(raw_text[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    return None


def _raw_output_summary(raw_content: Any) -> dict[str, Any]:
    raw_text = _content_to_text(raw_content)
    preview = " ".join(raw_text.strip().split())
    if len(preview) > RAW_OUTPUT_PREVIEW_CHARS:
        preview = f"{preview[:RAW_OUTPUT_PREVIEW_CHARS]}..."
    return {
        "raw_output_length": len(raw_text),
        "raw_output_preview": preview,
    }


def _json_for_log(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, default=str)

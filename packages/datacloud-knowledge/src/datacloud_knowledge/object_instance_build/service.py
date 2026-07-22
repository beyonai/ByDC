"""Service entry point for object instance build SDK."""

from __future__ import annotations

import json
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
            return parse_object_instance_build_result(
                payload=payload,
                label_schema=request.label_schema,
                retry_count=retry_count,
            )
        except ObjectInstanceBuildResultError as exc:
            last_error = exc
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
    if isinstance(raw_content, dict):
        return raw_content
    if isinstance(raw_content, list):
        raw_text = "\n".join(str(part) for part in raw_content)
    else:
        raw_text = str(raw_content)

    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError:
        payload = None
    if isinstance(payload, dict):
        return payload

    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", raw_text, re.DOTALL)
    if match:
        try:
            payload = json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            return None
        if isinstance(payload, dict):
            return payload

    return None

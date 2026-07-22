"""Parsing and label validation for object instance build SDK."""

from __future__ import annotations

from typing import Any

from datacloud_knowledge.object_instance_build.models import ObjectInstanceBuildResult


class ObjectInstanceBuildResultError(ValueError):
    """Base error for invalid LLM build results."""


class ObjectInstanceBuildParseError(ObjectInstanceBuildResultError):
    """Raised when the LLM output cannot be parsed as the expected JSON object."""


class ObjectInstanceBuildLabelValidationError(ObjectInstanceBuildResultError):
    """Raised when labels violate the provided label schema."""


def parse_object_instance_build_result(
    *,
    payload: dict[str, Any] | None,
    label_schema: dict[str, Any],
    retry_count: int,
) -> ObjectInstanceBuildResult:
    """Parse and validate the LLM payload."""
    if not isinstance(payload, dict):
        raise ObjectInstanceBuildParseError("LLM output must be a JSON object")

    content = str(payload.get("content") or "").strip()
    if not content:
        raise ObjectInstanceBuildParseError("LLM output content is required")

    raw_labels = payload.get("labels") or {}
    if not isinstance(raw_labels, dict):
        raise ObjectInstanceBuildLabelValidationError("labels must be a JSON object")

    labels = _normalize_labels(raw_labels, label_schema)

    diagnostics = payload.get("diagnostics") or {}
    if not isinstance(diagnostics, dict):
        diagnostics = {}
    diagnostics = dict(diagnostics)
    diagnostics["retry_count"] = retry_count

    confidence = payload.get("confidence")
    return ObjectInstanceBuildResult(
        content=content,
        labels=labels,
        file_description=str(payload.get("file_description") or ""),
        confidence=float(confidence) if isinstance(confidence, int | float) else None,
        model_name=str(payload.get("model_name") or "") or None,
        diagnostics=diagnostics,
    )


def _normalize_labels(
    labels: dict[str, Any],
    label_schema: dict[str, Any],
) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for field_code, value in labels.items():
        if field_code not in label_schema:
            raise ObjectInstanceBuildLabelValidationError(f"unsupported label field: {field_code}")
        field_schema = label_schema[field_code]
        if not isinstance(field_schema, dict):
            normalized[field_code] = value
            continue
        normalized[field_code] = _normalize_label_value(field_code, value, field_schema)
    return normalized


def _normalize_label_value(
    field_code: str,
    value: Any,
    field_schema: dict[str, Any],
) -> Any:
    if _is_enum_field(field_schema):
        return _normalize_enum_value(field_code, value, field_schema)
    return value


def _is_enum_field(field_schema: dict[str, Any]) -> bool:
    return field_schema.get("value_kind") == "enum" or bool(field_schema.get("enum_values"))


def _normalize_enum_value(
    field_code: str,
    value: Any,
    field_schema: dict[str, Any],
) -> str | list[str]:
    enum_values = field_schema.get("enum_values") or []
    if not isinstance(enum_values, list) or not enum_values:
        raise ObjectInstanceBuildLabelValidationError(
            f"enum field has no enum_values: {field_code}"
        )

    is_multiple = _is_multiple_enum_field(field_schema)
    if isinstance(value, list):
        if not is_multiple:
            raise ObjectInstanceBuildLabelValidationError(
                f"single enum label must be a string: {field_code}"
            )
        result: list[str] = []
        seen: set[str] = set()
        for item in value:
            code = _normalize_single_enum_value(field_code, item, enum_values)
            if code not in seen:
                result.append(code)
                seen.add(code)
        return result

    if is_multiple:
        raise ObjectInstanceBuildLabelValidationError(
            f"multiple enum label must be a string list: {field_code}"
        )
    if not isinstance(value, str):
        raise ObjectInstanceBuildLabelValidationError(
            f"enum label must be string or string list: {field_code}"
        )
    return _normalize_single_enum_value(field_code, value, enum_values)


def _is_multiple_enum_field(field_schema: dict[str, Any]) -> bool:
    if bool(
        field_schema.get("multiple")
        or field_schema.get("is_multiple")
        or field_schema.get("isMultiple")
    ):
        return True
    data_type = str(
        field_schema.get("data_type")
        or field_schema.get("dataType")
        or field_schema.get("field_type")
        or ""
    ).upper()
    return data_type in {"ARRAY", "LIST", "MULTI_ENUM"}


def _normalize_single_enum_value(
    field_code: str,
    value: Any,
    enum_values: list[Any],
) -> str:
    if not isinstance(value, str):
        raise ObjectInstanceBuildLabelValidationError(
            f"enum label item must be string: {field_code}"
        )

    raw = value.strip()
    code_map: dict[str, str] = {}
    alias_matches: list[str] = []
    for option in enum_values:
        if not isinstance(option, dict):
            continue
        code = str(option.get("code") or option.get("term_code") or "").strip()
        if not code:
            continue
        code_map[code] = code
        if raw == str(option.get("name") or option.get("term_name") or "").strip():
            alias_matches.append(code)
        aliases = option.get("aliases") or []
        if isinstance(aliases, list):
            alias_matches.extend(code for alias in aliases if raw == str(alias or "").strip())

    if raw in code_map:
        return code_map[raw]

    unique_matches = sorted(set(alias_matches))
    if len(unique_matches) == 1:
        return unique_matches[0]

    raise ObjectInstanceBuildLabelValidationError(
        f"enum label value is not allowed: {field_code}={raw}"
    )

"""查询/动作返回结果术语值转换。"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from datacloud_data_sdk.exceptions import TermResolutionError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TermResultField:
    """需要从术语 code 转换为 name 的结果字段。"""

    row_key: str
    term_set: str
    dataset_id: int | None = None

    @property
    def term_type_code(self) -> str | None:
        """从 term_set 推导术语类型编码。"""
        if "." not in self.term_set:
            return None
        return self.term_set.split(".", 1)[0]


class ResultTermConverter:
    """将返回记录中 codeorname/codeandname=code 的术语字段转换为 name。"""

    def __init__(self, term_loader: Any | None) -> None:
        self._term_loader = term_loader

    def convert_by_payload(
        self, records: list[dict[str, Any]], payload: Any | None
    ) -> list[dict[str, Any]]:
        """按查询 payload 中所有字段配置转换返回记录。"""
        if payload is None:
            return records
        fields = [
            field for obj in getattr(payload, "objects", []) for field in getattr(obj, "fields", [])
        ]
        return self.convert_by_fields(records, fields)

    def convert_by_datasource_payload(
        self,
        records: list[dict[str, Any]],
        payload: Any | None,
        datasource_alias: str,
    ) -> list[dict[str, Any]]:
        """按指定数据源 payload 字段配置转换返回记录。"""
        if payload is None:
            return records
        source_ids = {
            source.source_id
            for source in getattr(payload, "sources", [])
            if source.datasource_alias == datasource_alias
        }
        if not source_ids:
            return records
        fields = [
            field
            for obj in getattr(payload, "objects", [])
            if getattr(obj, "source_id", None) in source_ids
            for field in getattr(obj, "fields", [])
        ]
        return self.convert_by_fields(records, fields)

    def convert_by_action(
        self,
        records: list[dict[str, Any]],
        action: Any,
        extra_fields: list[Any] | None = None,
    ) -> list[dict[str, Any]]:
        """按动作输出参数和关联对象字段配置转换返回记录。"""
        fields = [
            param
            for param in getattr(action, "params", [])
            if getattr(param, "direction", "").upper() in {"OUT", "INOUT"}
        ]
        if extra_fields:
            fields.extend(extra_fields)
        return self.convert_by_fields(records, fields)

    def convert_by_fields(
        self,
        records: list[dict[str, Any]],
        fields: list[Any],
    ) -> list[dict[str, Any]]:
        """按字段/参数元数据转换返回记录。"""
        if not records or self._term_loader is None or not fields:
            return records

        term_fields = self._build_term_fields(records[0], fields)
        if not term_fields:
            return records

        converted_records: list[dict[str, Any]] = []
        for row in records:
            converted_records.append(self._convert_row(row, term_fields))
        return converted_records

    def _build_term_fields(
        self,
        sample_row: dict[str, Any],
        fields: list[Any],
    ) -> list[TermResultField]:
        row_key_by_lower = {key.lower(): key for key in sample_row}
        term_fields: list[TermResultField] = []
        seen_keys: set[str] = set()
        for field in fields:
            term_field = self._match_term_field(field, row_key_by_lower)
            if term_field is None or term_field.row_key in seen_keys:
                continue
            seen_keys.add(term_field.row_key)
            term_fields.append(term_field)
        return term_fields

    def _match_term_field(
        self,
        field: Any,
        row_key_by_lower: dict[str, str],
    ) -> TermResultField | None:
        term_set = getattr(field, "term_set", None)
        if not term_set or not _should_convert_code_result(field):
            return None

        for candidate in _field_key_candidates(field):
            row_key = row_key_by_lower.get(candidate.lower())
            if row_key:
                return TermResultField(
                    row_key=row_key,
                    term_set=str(term_set),
                    dataset_id=getattr(field, "dataset_id", None),
                )
        return None

    def _convert_row(
        self,
        row: dict[str, Any],
        fields: list[TermResultField],
    ) -> dict[str, Any]:
        converted_row = dict(row)
        for field in fields:
            raw_value = converted_row.get(field.row_key)
            if raw_value is None or raw_value == "":
                continue
            converted_row[field.row_key] = self._resolve_label(field, raw_value)
        return converted_row

    def _resolve_label(self, field: TermResultField, value: Any) -> Any:
        if not isinstance(value, str) or self._term_loader is None:
            return value
        try:
            return self._term_loader.resolve_value(
                field.term_set,
                value,
                term_field="name",
                dataset_id=field.dataset_id,
                term_type_code=field.term_type_code,
                keyword=value,
                param_name=field.row_key,
            )
        except TermResolutionError:
            logger.warning(
                "Failed to convert term code to name: field=%s term_set=%s value=%s",
                field.row_key,
                field.term_set,
                value,
                exc_info=True,
            )
            return value


def _field_key_candidates(field: Any) -> list[str]:
    candidates = [
        getattr(field, "name", None),
        getattr(field, "field_code", None),
        getattr(field, "param_code", None),
        getattr(field, "source_column", None),
    ]
    return [str(candidate) for candidate in candidates if candidate]


def _should_convert_code_result(field: Any) -> bool:
    term_field = (
        getattr(field, "codeandname", None)
        or getattr(field, "code_and_name", None)
        or getattr(field, "codeorname", None)
        or getattr(field, "code_or_name", None)
        or getattr(field, "rel_term_codeorname", None)
        or getattr(field, "term_field", None)
    )
    return _normalize_term_field(term_field) == "code"


def _normalize_term_field(term_field: str | None) -> str | None:
    if term_field is None:
        return None
    normalized = term_field.strip().lower()
    if normalized in {"name", "label"}:
        return "name"
    if normalized == "code":
        return "code"
    return normalized

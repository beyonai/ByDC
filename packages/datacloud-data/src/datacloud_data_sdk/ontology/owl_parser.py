"""
OWL 本体解析器模块

本模块提供从 OWL/RDF 文件解析本体定义的能力，支持解析：
- 对象定义
- 字段定义
- 动作定义
- 关系定义
- 数据源定义
- 视图定义
"""

from __future__ import annotations

import json
import logging
import re
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

logger = logging.getLogger(__name__)


def _predicate_local_name(predicate: Any) -> str:
    """提取谓词的本地名称。"""
    predicate_str = str(predicate)
    if "#" in predicate_str:
        return predicate_str.rsplit("#", 1)[-1]
    if "/" in predicate_str:
        return predicate_str.rsplit("/", 1)[-1]
    return predicate_str


def _is_rdf_type_predicate(predicate: Any) -> bool:
    """判断是否为 RDF 的内置 type 谓词。"""
    predicate_str = str(predicate)
    return predicate_str == "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"


def _normalize_owl_xml(content: str) -> str:
    """Normalize malformed OWL XML by deduplicating root tag attributes."""

    def replace_root(match: re.Match[str]) -> str:
        attrs = match.group(1)
        parts = re.findall(r'([^\s=]+)\s*=\s*(".*?"|\'.*?\')', attrs, flags=re.DOTALL)
        deduped: list[str] = []
        seen: set[str] = set()
        for name, value in parts:
            if name in seen:
                continue
            seen.add(name)
            deduped.append(f"{name}={value}")
        if not deduped:
            return "<rdf:RDF>"
        return "<rdf:RDF " + " ".join(deduped) + ">"

    return re.sub(r"<rdf:RDF\b([^>]*)>", replace_root, content, count=1, flags=re.DOTALL)


def _normalize_code_filter(codes: Iterable[str] | None) -> set[str] | None:
    if codes is None:
        return None
    normalized = {str(code).strip() for code in codes if str(code).strip()}
    return normalized or None


def _parse_json_object(value: str | None) -> dict[str, Any]:
    """Parse an optional JSON object string, returning an empty dict on invalid input."""

    if value is None:
        return {}
    raw = value.strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("Invalid ext_property JSON ignored: %s", raw)
        return {}
    if not isinstance(parsed, dict):
        logger.warning("ext_property is not a JSON object, ignored: %s", raw)
        return {}
    return parsed


@dataclass
class ParsedObject:
    object_code: str
    object_name: str
    description: str = ""
    source_type: str = "DB"
    datasource_alias: str | None = None
    datasource_id: int | None = None
    table_name: str | None = None
    source_config: dict[str, Any] | None = None
    ext_property: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    field_refs: list[str] = field(default_factory=list)  # URIs from <fields rdf:resource="..."/>
    fields: list[dict[str, Any]] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)
    relation_refs: list[str] = field(default_factory=list)  # relation codes from <relations> attr


@dataclass
class ParsedField:
    field_code: str
    field_name: str
    field_type: str = "STRING"
    data_format: str | None = None
    description: str = ""
    source_column: str | None = None
    is_primary_key: bool = False
    required: bool = False
    term_type_code_path: str | None = None
    library_code: str | None = None
    rel_term_codeorname: str | None = None
    term_data_type: str | None = None
    ext_property: str | None = None  # OWL ext_property JSON 字符串（含 property_role_rule）
    mapping_path: str = ""
    object_property: str | None = None


@dataclass
class ParsedAction:
    action_code: str
    action_name: str
    description: str = ""
    action_type: str = "QUERY"
    belong_class: str | None = None
    function_refs: list[str] = field(default_factory=list)
    params: list[dict[str, Any]] = field(default_factory=list)
    request_param_refs: list[str] = field(default_factory=list)
    response_param_refs: list[str] = field(default_factory=list)
    request_url: str = ""
    request_method: str = ""
    script: str | None = None


@dataclass
class ParsedRelation:
    relation_code: str
    source_class: str
    target_class: str
    relation_type: str = "ONE_TO_MANY"
    relation_name: str = ""
    join_keys: list[dict[str, str]] = field(default_factory=list)
    description: str = ""


@dataclass
class ParsedDatasource:
    alias: str
    db_type: str
    datasource_id: int | None = None
    config: dict[str, Any] = field(default_factory=dict)


@dataclass
class ParsedView:
    view_id: str
    view_name: str
    description: str = ""
    object_codes: list[str] = field(default_factory=list)
    relations: list[str] = field(default_factory=list)


class OwlParser:
    """
    OWL 本体解析器

    解析 OWL/RDF 格式的本体定义文件，转换为内部数据结构。
    """

    def __init__(self) -> None:
        self._objects: dict[str, ParsedObject] = {}
        self._fields: dict[str, ParsedField] = {}
        self._object_fields: dict[str, dict[str, ParsedField]] = defaultdict(dict)
        self._actions: dict[str, ParsedAction] = {}
        self._relations: dict[str, ParsedRelation] = {}
        self._datasources: dict[str, ParsedDatasource] = {}
        self._views: dict[str, ParsedView] = {}
        self._mappings: dict[str, dict[str, Any]] = {}
        self._current_entity_code: str | None = None
        self._mapping_datasource: dict[str, str] = {}
        self._mapping_table: dict[str, str] = {}
        self._field_uri_to_code: dict[tuple[str, str], str] = {}
        self._request_params_by_uri: dict[str, ParsedField] = {}
        self._response_params_by_uri: dict[str, ParsedField] = {}
        self._view_field_mappings: dict[str, list[dict]] = {}  # view_id → 字段映射列表

    def parse_file(self, path: Path) -> None:
        if path.suffix.lower() != ".owl":
            return

        content = _normalize_owl_xml(path.read_text(encoding="utf-8"))
        object_scope = _infer_object_scope(path)
        mapping_scope = _infer_mapping_scope(path)
        view_scope = _infer_view_scope(path)
        try:
            self._parse_owl_content(
                content,
                path,
                object_scope=object_scope,
                mapping_scope=mapping_scope,
                view_scope=view_scope,
            )
        except Exception as e:
            logger.warning(f"Failed to parse OWL file {path}: {e}")

    def _parse_owl_content(
        self,
        content: str,
        path: Path,
        *,
        object_scope: str | None,
        mapping_scope: str | None,
        view_scope: str | None,
    ) -> None:
        try:
            from rdflib import Graph
            from rdflib.namespace import RDF
        except ImportError:
            logger.error("rdflib is required for OWL parsing. Install with: pip install rdflib")
            raise

        g = Graph()
        g.parse(data=content, format="xml")

        for s, _p, o in g.triples((None, RDF.type, None)):
            type_uri = str(o)
            if type_uri.endswith("EntityDefinition"):
                self._parse_entity_definition(g, s)
            elif type_uri.endswith("EntityField"):
                self._parse_entity_field(g, s, object_scope)
            elif type_uri.endswith("ActionDefinition"):
                self._parse_action_definition(g, s)
            elif type_uri.endswith("RequestParameter"):
                self._parse_request_parameter(g, s)
            elif type_uri.endswith("ResponseParameter"):
                self._parse_response_parameter(g, s)
            elif type_uri.endswith("TermRelation"):
                self._parse_term_relation(g, s)
            elif type_uri.endswith("DatabaseDefinition"):
                self._parse_database_definition(g, s)
            elif type_uri.endswith("SceneDefinition"):
                self._parse_scene_definition(g, s)
            elif type_uri.endswith("SceneField"):
                self._parse_scene_field(g, s, view_scope)
            elif type_uri.endswith("EntityMapping"):
                self._parse_entity_mapping(g, s)
            elif type_uri.endswith("Mapping"):
                self._parse_mapping(g, s, mapping_scope)

    def _get_predicate_value(self, g: Any, subject: Any, predicate_suffix: str) -> str | None:
        matches: list[tuple[Any, Any]] = []
        fallback_matches: list[tuple[Any, Any]] = []
        for p, o in g.predicate_objects(subject):
            local_name = _predicate_local_name(p)
            if local_name == predicate_suffix:
                matches.append((p, o))
            elif str(p).endswith(predicate_suffix):
                fallback_matches.append((p, o))

        for p, o in matches:
            if not _is_rdf_type_predicate(p):
                return str(o)
        if matches:
            return str(matches[0][1])
        if fallback_matches:
            return str(fallback_matches[0][1])
        return None

    def _get_predicate_values(self, g: Any, subject: Any, predicate_suffix: str) -> list[str]:
        exact_matches: list[str] = []
        fallback_matches: list[str] = []
        for p, o in g.predicate_objects(subject):
            local_name = _predicate_local_name(p)
            if local_name == predicate_suffix:
                exact_matches.append(str(o))
            elif str(p).endswith(predicate_suffix):
                fallback_matches.append(str(o))
        result = exact_matches or fallback_matches
        return result

    def _parse_loose_json_list(self, s: str) -> list:
        """Parse non-standard JSON arrays used in OWL files.

        Handles:
          - Standard JSON:          ["a", "b"]
          - Unquoted string list:   [a, b, c]
          - Unquoted object list:   [{key:val, key2:val2}]
        """
        s = s.strip()
        if not s or s == "[]":
            return []
        try:
            return json.loads(s)
        except json.JSONDecodeError:
            pass
        if not (s.startswith("[") and s.endswith("]")):
            return []
        inner = s[1:-1].strip()
        if not inner:
            return []
        if "{" in inner:

            def fix_obj(m: re.Match) -> str:
                pairs = []
                for pair in m.group(1).split(","):
                    if ":" in pair:
                        k, v = pair.split(":", 1)
                        pairs.append(f'"{k.strip()}": "{v.strip()}"')
                return "{" + ", ".join(pairs) + "}"

            fixed = "[" + re.sub(r"\{([^}]+)\}", fix_obj, inner) + "]"
            try:
                return json.loads(fixed)
            except json.JSONDecodeError:
                return []
        else:
            return [item.strip() for item in inner.split(",") if item.strip()]

    def _parse_entity_definition(self, g: Any, subject: Any) -> None:
        entity_code = self._get_predicate_value(g, subject, "entity_code")
        if not entity_code:
            return

        entity_name = self._get_predicate_value(g, subject, "entity_name") or entity_code
        entity_desc = self._get_predicate_value(g, subject, "entity_desc") or ""
        entity_source = self._get_predicate_value(g, subject, "entity_source") or "DB"
        ext_property = _parse_json_object(self._get_predicate_value(g, subject, "ext_property"))

        source_upper = entity_source.upper()
        if "KNOWLEDGE_BASE" in source_upper:
            source_type = "KNOWLEDGE_BASE"
        elif "DB" in source_upper:
            source_type = "DB"
        else:
            source_type = "API"

        action_refs_str = self._get_predicate_value(g, subject, "action_refs") or "[]"
        action_refs = self._parse_loose_json_list(action_refs_str)

        # Read <fields rdf:resource="..."/> — returns full URIs of field individuals
        field_refs = self._get_predicate_values(g, subject, "fields")

        # Read <relations> attribute — list of relation codes referencing relation OWL
        relations_str = self._get_predicate_value(g, subject, "relations") or "[]"
        relation_refs = self._parse_loose_json_list(relations_str)

        obj = ParsedObject(
            object_code=entity_code,
            object_name=entity_name,
            description=entity_desc,
            source_type=source_type,
            ext_property=ext_property,
            field_refs=field_refs,
            actions=action_refs,
            relation_refs=relation_refs,
        )
        self._objects[entity_code] = obj

    def _register_field(
        self,
        *,
        scope: str | None,
        subject: Any,
        field: ParsedField,
    ) -> None:
        subject_uri = str(subject)
        if scope:
            existing = self._object_fields[scope].get(field.field_code)
            if existing is not None and field.source_column is None:
                field.source_column = existing.source_column
            self._object_fields[scope][field.field_code] = field
            self._field_uri_to_code[(scope, subject_uri)] = field.field_code
            return

        existing = self._fields.get(field.field_code)
        if existing is not None and field.source_column is None:
            field.source_column = existing.source_column
        self._fields[field.field_code] = field
        self._field_uri_to_code[("", subject_uri)] = field.field_code

    def _parse_entity_field(self, g: Any, subject: Any, object_scope: str | None) -> None:
        property_code = self._get_predicate_value(g, subject, "property_code")
        if not property_code:
            return

        property_name = self._get_predicate_value(g, subject, "property_name") or property_code
        data_type = self._get_predicate_value(g, subject, "data_type") or "STRING"
        data_format = self._get_predicate_value(g, subject, "data_format")
        source_column = self._get_predicate_value(g, subject, "source_column")
        is_required = self._get_predicate_value(g, subject, "is_required")
        term_type_code_path = self._get_predicate_value(g, subject, "term_type_code_path")
        library_code = self._get_predicate_value(g, subject, "library_code")
        rel_term_codeorname = self._get_predicate_value(g, subject, "rel_term_codeorname")
        term_data_type = self._get_predicate_value(g, subject, "term_data_type")
        # 新增：读取 ext_property 用于后续 analytic_role 解析
        ext_property = self._get_predicate_value(g, subject, "ext_property")

        fld = ParsedField(
            field_code=property_code,
            field_name=property_name,
            field_type=data_type,
            data_format=data_format if data_format else None,
            source_column=source_column,
            required=is_required.lower() == "true" if is_required else False,
            term_type_code_path=term_type_code_path if term_type_code_path else None,
            library_code=library_code if library_code else None,
            rel_term_codeorname=rel_term_codeorname if rel_term_codeorname else None,
            term_data_type=term_data_type if term_data_type else None,
            ext_property=ext_property if ext_property else None,
        )
        self._register_field(scope=object_scope, subject=subject, field=fld)

    def _parse_action_definition(self, g: Any, subject: Any) -> None:
        action_code = self._get_predicate_value(g, subject, "action_code")
        if not action_code:
            return

        action_name = self._get_predicate_value(g, subject, "action_name") or action_code
        action_desc = self._get_predicate_value(g, subject, "action_desc") or ""
        action_type_str = self._get_predicate_value(g, subject, "action_type") or "QUERY"

        action_type_upper = action_type_str.upper()
        action_type = "query"
        if "OPERATION" in action_type_upper or "UPDATE" in action_type_upper:
            action_type = "operation"
        elif "QUERY" in action_type_upper:
            action_type = "query"
        elif action_type_str.strip():
            action_type = action_type_str.strip().lower()

        function_refs_str = self._get_predicate_value(g, subject, "function_refs") or "[]"
        function_refs = self._parse_loose_json_list(function_refs_str)

        belong_entity_str = self._get_predicate_value(g, subject, "belong_entity") or "[]"
        belong_entities = self._parse_loose_json_list(belong_entity_str)
        request_url = self._get_predicate_value(g, subject, "request_url") or ""
        request_method = self._get_predicate_value(g, subject, "request_method") or ""
        script = self._get_predicate_value(g, subject, "script")

        request_params = self._get_predicate_values(g, subject, "request_params")
        response_params = self._get_predicate_values(g, subject, "response_params")

        action = ParsedAction(
            action_code=action_code,
            action_name=action_name,
            description=action_desc,
            action_type=action_type,
            function_refs=function_refs,
            request_param_refs=request_params,
            response_param_refs=response_params,
            request_url=request_url,
            request_method=request_method,
            script=script or None,
        )
        self._actions[action_code] = action

        for entity_code in belong_entities:
            if (
                entity_code in self._objects
                and action_code not in self._objects[entity_code].actions
            ):
                self._objects[entity_code].actions.append(action_code)

    def _parse_request_parameter(self, g: Any, subject: Any) -> None:
        param_code = self._get_predicate_value(g, subject, "paramCode")
        if not param_code:
            return

        param_type = self._get_predicate_value(g, subject, "type") or "string"
        description = self._get_predicate_value(g, subject, "description") or ""
        is_required = self._get_predicate_value(g, subject, "isRequired")
        term_type_code_path = self._get_predicate_value(g, subject, "term_type_code_path")
        library_code = self._get_predicate_value(g, subject, "library_code")
        rel_term_codeorname = self._get_predicate_value(g, subject, "rel_term_codeorname")
        term_data_type = self._get_predicate_value(g, subject, "term_data_type")
        mapping_path = (
            self._get_predicate_value(g, subject, "mapping_path")
            or self._get_predicate_value(g, subject, "json_path")
            or ""
        )

        fld = ParsedField(
            field_code=param_code,
            field_name=description or param_code,
            field_type=param_type.upper(),
            required=is_required.lower() == "true" if is_required else False,
            term_type_code_path=term_type_code_path if term_type_code_path else None,
            library_code=library_code if library_code else None,
            rel_term_codeorname=rel_term_codeorname if rel_term_codeorname else None,
            term_data_type=term_data_type if term_data_type else None,
            mapping_path=mapping_path,
        )
        self._request_params_by_uri[str(subject)] = fld

    def _parse_response_parameter(self, g: Any, subject: Any) -> None:
        field_code = self._get_predicate_value(g, subject, "fieldCode")
        if not field_code:
            return

        field_type = self._get_predicate_value(g, subject, "fieldType") or "string"
        description = self._get_predicate_value(g, subject, "description") or ""
        term_type_code_path = self._get_predicate_value(g, subject, "term_type_code_path")
        library_code = self._get_predicate_value(g, subject, "library_code")
        rel_term_codeorname = self._get_predicate_value(g, subject, "rel_term_codeorname")
        term_data_type = self._get_predicate_value(g, subject, "term_data_type")
        mapping_path = (
            self._get_predicate_value(g, subject, "json_path")
            or self._get_predicate_value(g, subject, "mapping_path")
            or ""
        )
        object_property = self._get_predicate_value(g, subject, "object_property")

        fld = ParsedField(
            field_code=field_code,
            field_name=description or field_code,
            field_type=field_type.upper(),
            description=description,
            term_type_code_path=term_type_code_path if term_type_code_path else None,
            library_code=library_code if library_code else None,
            rel_term_codeorname=rel_term_codeorname if rel_term_codeorname else None,
            term_data_type=term_data_type if term_data_type else None,
            mapping_path=mapping_path,
            object_property=object_property if object_property else None,
        )
        self._response_params_by_uri[str(subject)] = fld

    def _parse_term_relation(self, g: Any, subject: Any) -> None:
        source_code = self._get_predicate_value(g, subject, "source_code")
        target_code = self._get_predicate_value(g, subject, "target_code")
        if not source_code or not target_code:
            return

        # Derive relation_code from the individual's URI fragment (e.g. "#rel_enterprise_grid")
        relation_code = str(subject).split("#")[-1]

        relation_name = self._get_predicate_value(g, subject, "relation_name") or ""
        relation_type = self._get_predicate_value(g, subject, "relation_type") or "ONE_TO_MANY"
        joinkeys_str = self._get_predicate_value(g, subject, "joinkeys") or "[]"
        join_keys = self._parse_loose_json_list(joinkeys_str)

        relation = ParsedRelation(
            relation_code=relation_code,
            source_class=source_code,
            target_class=target_code,
            relation_type=relation_type,
            relation_name=relation_name,
            join_keys=join_keys,
        )
        self._relations[relation_code] = relation

    def _parse_database_definition(self, g: Any, subject: Any) -> None:
        db_code = self._get_predicate_value(g, subject, "dbCode")
        if not db_code:
            return

        db_type = self._get_predicate_value(g, subject, "dbType") or "mysql"
        db_params_str = self._get_predicate_value(g, subject, "dbParams") or "{}"
        datasource_id_str = self._get_predicate_value(g, subject, "dbId")

        try:
            db_params = json.loads(db_params_str)
        except json.JSONDecodeError:
            db_params = {}

        try:
            datasource_id = int(datasource_id_str) if datasource_id_str else None
        except (TypeError, ValueError):
            datasource_id = None

        datasource = ParsedDatasource(
            alias=db_code,
            db_type=db_type,
            datasource_id=datasource_id,
            config=db_params,
        )
        self._datasources[db_code] = datasource

    def _parse_scene_definition(self, g: Any, subject: Any) -> None:
        view_code = self._get_predicate_value(g, subject, "view_code")
        if not view_code:
            return

        view_name = self._get_predicate_value(g, subject, "view_name") or view_code
        description = self._get_predicate_value(g, subject, "description") or ""
        object_codes_str = self._get_predicate_value(g, subject, "object_codes") or "[]"
        relations_str = self._get_predicate_value(g, subject, "relations") or "[]"

        object_codes = self._parse_loose_json_list(object_codes_str)
        relations = self._parse_loose_json_list(relations_str)

        view = ParsedView(
            view_id=view_code,
            view_name=view_name,
            description=description,
            object_codes=object_codes,
            relations=relations,
        )
        self._views[view_code] = view

    def _parse_scene_field(self, g: Any, subject: Any, view_scope: str | None) -> None:
        if not view_scope:
            return

        property_code = self._get_predicate_value(g, subject, "property_code")
        source_object_code = self._get_predicate_value(g, subject, "source_object_code")
        source_object_column_code = self._get_predicate_value(
            g, subject, "source_object_column_code"
        )
        if not property_code or not source_object_code or not source_object_column_code:
            return

        property_name = self._get_predicate_value(g, subject, "property_name") or property_code
        ext_property = self._get_predicate_value(g, subject, "ext_property")
        self._view_field_mappings.setdefault(view_scope, []).append(
            {
                "property_code": property_code,
                "property_name": property_name,
                "source_object_code": source_object_code,
                "source_object_column_code": source_object_column_code,
                "ext_property": ext_property,
            }
        )

    def _parse_entity_mapping(self, g: Any, subject: Any) -> None:
        entity_code = self._get_predicate_value(g, subject, "entity_code")
        if not entity_code:
            return

        self._current_entity_code = entity_code
        mapping_refs = self._get_predicate_values(g, subject, "mapping")
        self._mappings[entity_code] = {
            "mappings": mapping_refs,
        }

    def _parse_mapping(self, g: Any, subject: Any, mapping_scope: str | None) -> None:
        property_code = self._get_predicate_value(g, subject, "property_code")
        source_column = self._get_predicate_value(g, subject, "source_column_code")
        datasource_code = self._get_predicate_value(g, subject, "source_datasource_code")
        source_table = self._get_predicate_value(g, subject, "source_table_code")

        # 视图字段映射（来自 *_mapping.owl 中的 Mapping 个体）
        source_object_code = self._get_predicate_value(g, subject, "source_object_code")
        source_object_column_code = self._get_predicate_value(
            g, subject, "source_object_column_code"
        )
        property_name = self._get_predicate_value(g, subject, "property_name")
        ext_property = self._get_predicate_value(g, subject, "ext_property")

        if property_code:
            if mapping_scope:
                scoped_fields = self._object_fields[mapping_scope]
                if property_code in scoped_fields:
                    scoped_fields[property_code].source_column = source_column
                else:
                    scoped_fields[property_code] = ParsedField(
                        field_code=property_code,
                        field_name=property_code,
                        source_column=source_column,
                    )
            elif property_code in self._fields:
                self._fields[property_code].source_column = source_column
            else:
                fld = ParsedField(
                    field_code=property_code,
                    field_name=property_code,
                    source_column=source_column,
                )
                self._fields[property_code] = fld

            entity_code = mapping_scope or self._current_entity_code
            if entity_code:
                if datasource_code:
                    self._mapping_datasource[entity_code] = datasource_code
                if source_table:
                    self._mapping_table[entity_code] = source_table

                # 存储视图字段映射信息（source_object_code + source_object_column_code + ext_property）
                if source_object_code and source_object_column_code:
                    self._view_field_mappings.setdefault(entity_code, []).append(
                        {
                            "property_code": property_code,
                            "property_name": property_name or property_code,
                            "source_object_code": source_object_code,
                            "source_object_column_code": source_object_column_code,
                            "ext_property": ext_property,
                        }
                    )

    def _apply_mappings_to_objects(self) -> None:
        for entity_code, datasource_code in self._mapping_datasource.items():
            if entity_code in self._objects:
                self._objects[entity_code].datasource_alias = datasource_code
                # 从已解析的数据源中获取 datasource_id
                if datasource_code in self._datasources:
                    self._objects[entity_code].datasource_id = self._datasources[
                        datasource_code
                    ].datasource_id

        for entity_code, table_name in self._mapping_table.items():
            if entity_code in self._objects:
                self._objects[entity_code].table_name = table_name

    def _build_term_meta(self, fld: ParsedField) -> dict[str, Any] | None:
        if not fld.term_type_code_path:
            return None

        term_meta: dict[str, Any] = {}

        if fld.term_data_type == "ONTOLOGY_TERM":
            parts = fld.term_type_code_path.split("#")
            if len(parts) == 2:
                term_meta["termMasterType"] = "ontology"
                term_meta["objectCode"] = parts[1]
        elif fld.term_data_type == "LIST_TERM":
            parts = fld.term_type_code_path.split("#")
            if len(parts) == 2:
                term_meta["termMasterType"] = "list"
                term_meta["termTypeCode"] = parts[1]
                if fld.library_code:
                    term_meta["libraryCode"] = fld.library_code
        elif fld.term_data_type == "DICT_TERM":
            parts = fld.term_type_code_path.split("#")
            if len(parts) == 2:
                term_meta["termMasterType"] = "dict"
                term_meta["termTypeCode"] = parts[1]
        else:
            parts = fld.term_type_code_path.split("#")
            if len(parts) == 2:
                term_meta["termMasterType"] = "dict"
                term_meta["termTypeCode"] = parts[1]
        if fld.rel_term_codeorname:
            term_meta["termField"] = fld.rel_term_codeorname

        return term_meta if term_meta else None

    def _resolve_object_field(self, object_code: str, field_code: str) -> ParsedField | None:
        scoped_field = self._object_fields.get(object_code, {}).get(field_code)
        if scoped_field is not None:
            return scoped_field
        return self._fields.get(field_code)

    def _resolve_object_field_from_ref(
        self, object_code: str, field_uri: str
    ) -> ParsedField | None:
        field_code = self._field_uri_to_code.get((object_code, field_uri))
        if field_code is None:
            field_code = self._field_uri_to_code.get(("", field_uri))
        if field_code is None:
            return None
        return self._resolve_object_field(object_code, field_code)

    def _resolve_action_param_field(
        self,
        *,
        object_code: str,
        param_ref: str,
        direction: str,
    ) -> ParsedField | None:
        if direction == "IN":
            param_field = self._request_params_by_uri.get(param_ref)
        else:
            param_field = self._response_params_by_uri.get(param_ref)

        if param_field is None:
            return None

        object_field = self._resolve_object_field(object_code, param_field.field_code)
        if object_field is None and param_field.object_property:
            object_field = self._resolve_object_field(object_code, param_field.object_property)
        if object_field is None:
            return param_field

        # 参数定义里的 required / type / 术语元信息优先，显示名称回退到对象字段名。
        if param_field.field_name and param_field.field_name != param_field.field_code:
            field_name = param_field.field_name
        else:
            field_name = object_field.field_name

        return ParsedField(
            field_code=param_field.field_code,
            field_name=field_name,
            field_type=param_field.field_type or object_field.field_type,
            description=param_field.description or object_field.description,
            source_column=object_field.source_column,
            is_primary_key=object_field.is_primary_key,
            required=param_field.required,
            term_type_code_path=param_field.term_type_code_path or object_field.term_type_code_path,
            library_code=param_field.library_code or object_field.library_code,
            rel_term_codeorname=param_field.rel_term_codeorname or object_field.rel_term_codeorname,
            term_data_type=param_field.term_data_type or object_field.term_data_type,
            mapping_path=param_field.mapping_path,
            object_property=param_field.object_property,
        )

    def parse_directory(
        self, ontology_dir: Path, relations_dir: Path | None = None
    ) -> dict[str, Any]:
        if ontology_dir.is_dir():
            for owl_file in ontology_dir.rglob("*.owl"):
                self.parse_file(owl_file)

        if relations_dir and relations_dir.is_dir():
            for owl_file in relations_dir.glob("*.owl"):
                self.parse_file(owl_file)

        self._apply_mappings_to_objects()
        return self._build_content()

    def parse_resource_directory(
        self,
        base_dir: Path,
        *,
        object_codes: Iterable[str] | None = None,
        view_codes: Iterable[str] | None = None,
    ) -> dict[str, Any]:
        """解析新的 resource/object + resource/view 目录结构。"""
        selected_object_codes = _normalize_code_filter(object_codes)
        selected_view_codes = _normalize_code_filter(view_codes)
        object_filter_enabled = selected_object_codes is not None
        view_filter_enabled = selected_view_codes is not None
        self._parse_new_layout_directory(
            base_dir,
            object_codes=selected_object_codes,
            view_codes=selected_view_codes,
            object_filter_enabled=object_filter_enabled,
            view_filter_enabled=view_filter_enabled,
        )
        self._apply_mappings_to_objects()
        return self._build_content()

    def _build_content(self) -> dict[str, Any]:
        functions: dict[str, dict[str, Any]] = {}
        objects = []
        for obj in self._objects.values():
            # Resolve field URIs (from <fields rdf:resource="..."/>) to ParsedField instances
            fields = []
            for field_uri in obj.field_refs:
                fld = self._resolve_object_field_from_ref(obj.object_code, field_uri)
                if not fld:
                    continue
                field_dict = {
                    "field_code": fld.field_code,
                    "field_name": fld.field_name,
                    "field_type": fld.field_type,
                    "data_format": fld.data_format,
                    "source_column": fld.source_column,
                    "is_primary_key": fld.is_primary_key,
                    "required": fld.required,
                }
                # 传递 ext_property 供 loader 解析 analytic_role
                if fld.ext_property:
                    field_dict["ext_property"] = fld.ext_property

                if fld.term_type_code_path:
                    term_meta = self._build_term_meta(fld)
                    if term_meta:
                        field_dict["termMeta"] = term_meta

                fields.append(field_dict)

            actions = []
            for action_code in obj.actions:
                if action_code in self._actions:
                    action = self._actions[action_code]
                    params = []

                    for param_ref in action.request_param_refs:
                        f = self._resolve_action_param_field(
                            object_code=obj.object_code,
                            param_ref=param_ref,
                            direction="IN",
                        )
                        if f is None:
                            continue

                        param_dict = {
                            "param_code": f.field_code,
                            "param_name": f.field_name,
                            "param_type": f.field_type,
                            "required": f.required,
                            "direction": "IN",
                        }
                        if f.mapping_path:
                            param_dict["mapping_path"] = f.mapping_path
                        if f.term_type_code_path:
                            term_meta = self._build_term_meta(f)
                            if term_meta:
                                param_dict["termMeta"] = term_meta
                        params.append(param_dict)

                    for param_ref in action.response_param_refs:
                        f = self._resolve_action_param_field(
                            object_code=obj.object_code,
                            param_ref=param_ref,
                            direction="OUT",
                        )
                        if f is None:
                            continue

                        param_dict = {
                            "param_code": f.field_code,
                            "param_name": f.field_name,
                            "param_type": f.field_type,
                            "required": f.required,
                            "direction": "OUT",
                        }
                        if f.mapping_path:
                            param_dict["mapping_path"] = f.mapping_path
                        if f.term_type_code_path:
                            term_meta = self._build_term_meta(f)
                            if term_meta:
                                param_dict["termMeta"] = term_meta
                        params.append(param_dict)

                    self._merge_function_configs(
                        functions=functions,
                        action=action,
                        params=params,
                    )

                    actions.append(
                        {
                            "action_code": action.action_code,
                            "action_name": action.action_name,
                            "description": action.description,
                            "action_type": action.action_type,
                            "function_refs": list(action.function_refs),
                            "params": params,
                            "script": action.script,
                        }
                    )

            source_config = None
            if obj.datasource_alias and obj.datasource_alias in self._datasources:
                ds = self._datasources[obj.datasource_alias]
                source_config = {
                    "alias": ds.alias,
                    "db_type": ds.db_type.upper(),
                    "datasource_id": ds.datasource_id,
                    **ds.config,
                }

            object_dict = {
                "object_code": obj.object_code,
                "object_name": obj.object_name,
                "description": obj.description,
                "source_type": obj.source_type,
                "datasource_alias": obj.datasource_alias,
                "table_name": obj.table_name,
                "source_config": source_config,
                "ext_property": dict(obj.ext_property),
                "fields": fields,
                "actions": actions,
            }
            objects.append(object_dict)

        relations = []
        for rel_code, rel in self._relations.items():
            relations.append(
                {
                    "relation_code": rel_code,
                    "relation_name": rel.relation_name,
                    "source_class": rel.source_class,
                    "target_class": rel.target_class,
                    "relation_type": rel.relation_type,
                    "join_keys": rel.join_keys,
                    "description": rel.description,
                }
            )

        datasource_configs = {}
        for ds_code, ds in self._datasources.items():
            datasource_configs[ds_code] = {
                "alias": ds.alias,
                "db_type": ds.db_type.upper(),
                "datasource_id": ds.datasource_id,
                **ds.config,
            }

        views = []
        for view in self._views.values():
            view_objects = [{"object_code": code} for code in view.object_codes]
            view_relations = []
            for rel_code in view.relations:
                if rel_code in self._relations:
                    rel = self._relations[rel_code]
                    view_relations.append(
                        {
                            "relation_code": rel_code,
                            "relation_name": rel.relation_name,
                            "source_class": rel.source_class,
                            "target_class": rel.target_class,
                            "relation_type": rel.relation_type,
                            "join_keys": rel.join_keys,
                            "description": rel.description,
                        }
                    )
            view_field_mappings = getattr(self, "_view_field_mappings", {}).get(view.view_id, [])
            views.append(
                {
                    "view_id": view.view_id,
                    "view_name": view.view_name,
                    "description": view.description,
                    "objects": view_objects,
                    "relations": view_relations,
                    "mappings": view_field_mappings,  # 视图字段映射（含 ext_property）
                }
            )

        return {
            "functions": functions,
            "objects": objects,
            "relations": relations,
            "datasource_configs": datasource_configs,
            "views": views,
        }

    def _parse_new_layout_directory(
        self,
        base_dir: Path,
        *,
        object_codes: set[str] | None = None,
        view_codes: set[str] | None = None,
        object_filter_enabled: bool = False,
        view_filter_enabled: bool = False,
    ) -> None:
        object_dir = base_dir / "object"
        view_dir = base_dir / "view"

        selected_object_codes = set(object_codes or set())
        selected_view_codes = set(view_codes or set())
        effective_object_filter_enabled = object_filter_enabled or view_filter_enabled
        effective_view_filter_enabled = view_filter_enabled or object_filter_enabled

        if view_dir.is_dir() and selected_view_codes:
            selected_object_codes.update(
                self._discover_view_object_codes(view_dir, selected_view_codes)
            )

        if object_dir.is_dir():
            for object_path in sorted(object_dir.iterdir()):
                if not object_path.is_dir():
                    continue
                if (
                    effective_object_filter_enabled
                    and object_path.name not in selected_object_codes
                ):
                    continue
                self._parse_new_layout_object_directory(object_path)

        if view_dir.is_dir():
            for view_path in sorted(view_dir.iterdir()):
                if not view_path.is_dir():
                    continue
                if effective_view_filter_enabled and view_path.name not in selected_view_codes:
                    continue
                self._parse_new_layout_view_directory(view_path)

    def _discover_view_object_codes(self, view_dir: Path, view_codes: set[str]) -> set[str]:
        object_codes: set[str] = set()
        for view_code in sorted(view_codes):
            view_path = view_dir / view_code
            if not view_path.is_dir():
                logger.warning("Selected view directory not found: %s", view_path)
                continue

            parser = OwlParser()
            parser._parse_new_layout_view_directory(view_path)
            for view in parser._views.values():
                object_codes.update(code for code in view.object_codes if code)
            object_codes.update(parser._discover_view_object_codes_from_mappings(view_code))
            object_codes.update(parser._discover_view_object_codes_from_relations(view_code))
        return object_codes

    def _discover_view_object_codes_from_mappings(self, view_code: str) -> set[str]:
        mappings = self._view_field_mappings.get(view_code, [])
        return {
            str(mapping["source_object_code"])
            for mapping in mappings
            if mapping.get("source_object_code")
        }

    def _discover_view_object_codes_from_relations(self, view_code: str) -> set[str]:
        object_codes: set[str] = set()
        for relation in self._relations.values():
            if relation.source_class == view_code and relation.target_class:
                object_codes.add(relation.target_class)
            if relation.target_class == view_code and relation.source_class:
                object_codes.add(relation.source_class)
        return object_codes

    def _parse_new_layout_object_directory(self, object_dir: Path) -> None:
        definition_files = sorted(object_dir.glob("*_definition.owl"))
        for owl_file in definition_files:
            self.parse_file(owl_file)

        for pattern in (
            "*_mapping.owl",
            "*_dbsource.owl",
            "*_object_relations.owl",
        ):
            for owl_file in sorted(object_dir.glob(pattern)):
                self.parse_file(owl_file)

        actions_dir = object_dir / "actions"
        if actions_dir.is_dir():
            for owl_file in sorted(actions_dir.rglob("*.owl")):
                self.parse_file(owl_file)

    def _parse_new_layout_view_directory(self, view_dir: Path) -> None:
        for pattern in (
            "*_definition.owl",
            "*_relations.owl",
        ):
            for owl_file in sorted(view_dir.glob(pattern)):
                self.parse_file(owl_file)

    def _merge_function_configs(
        self,
        *,
        functions: dict[str, dict[str, Any]],
        action: ParsedAction,
        params: list[dict[str, Any]],
    ) -> None:
        """从动作定义中回填最小 function 配置，供 API 动作执行。"""
        if action.script or not action.request_url:
            return

        if not action.function_refs:
            action.function_refs = [self._build_generated_function_code(action.action_code)]

        server_url, path = self._split_request_url(action.request_url)
        if not path:
            return

        method = (action.request_method or "POST").lower()
        operation: dict[str, Any] = {
            "summary": action.description or action.action_name or action.action_code,
        }
        request_body_params = self._filter_request_params_by_location(
            params, method=method, location="body"
        )
        request_schema = self._build_request_body_schema(request_body_params)
        if request_schema:
            operation["requestBody"] = {
                "required": True,
                "content": {
                    "application/json": {
                        "schema": request_schema,
                    }
                },
            }
        operation_parameters = self._build_operation_parameters(params, method=method)
        if operation_parameters:
            operation["parameters"] = operation_parameters
        response_schema = self._build_response_schema(params)
        if response_schema:
            operation["responses"] = {
                "200": {
                    "description": f"{action.action_name or action.action_code}结果",
                    "content": {
                        "application/json": {
                            "schema": response_schema,
                        }
                    },
                }
            }
        else:
            operation["responses"] = {
                "200": {"description": f"{action.action_name or action.action_code}结果"}
            }

        config: dict[str, Any] = {
            "openapi": "3.0.3",
            "info": {
                "title": action.action_name or action.action_code,
                "version": "1.0.0",
            },
            "paths": {path: {method: operation}},
        }
        if server_url:
            config["servers"] = [{"url": server_url}]

        for function_code in action.function_refs:
            functions.setdefault(function_code, config)

    @staticmethod
    def _build_generated_function_code(action_code: str) -> str:
        """为仅配置 request_url 的动作生成稳定的函数编码。"""
        fragment = re.sub(r"[^0-9A-Za-z_]+", "_", action_code).strip("_")
        if not fragment:
            fragment = "action"
        if fragment[0].isdigit():
            fragment = f"n_{fragment}"
        return f"fn_{fragment}"

    def _build_request_body_schema(self, params: list[dict[str, Any]]) -> dict[str, Any] | None:
        """基于动作入参生成 requestBody schema。"""
        schema = self._build_schema_from_params(
            params,
        )
        return schema if self._schema_has_content(schema) else None

    def _build_response_schema(self, params: list[dict[str, Any]]) -> dict[str, Any] | None:
        """基于动作出参生成响应 schema。"""
        schema = self._build_schema_from_params(
            [param for param in params if param.get("direction") in ("OUT", "INOUT")]
        )
        return schema if self._schema_has_content(schema) else None

    @staticmethod
    def _schema_has_content(schema: dict[str, Any]) -> bool:
        """判断 schema 是否包含有效结构。"""
        schema_type = schema.get("type")
        if schema_type == "object":
            properties = schema.get("properties")
            return isinstance(properties, dict) and bool(properties)
        if schema_type == "array":
            return "items" in schema
        return False

    def _build_schema_from_params(
        self,
        params: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """根据 mapping_path 构造嵌套 JSON Schema。"""
        root: dict[str, Any] = {"type": "object", "properties": {}}
        for param in params:
            mapping_path = str(param.get("mapping_path") or "")
            location, path_parts = self._parse_request_mapping_path(
                mapping_path,
                default_location="body",
            )
            if location != "body":
                path_parts = []
            if not path_parts:
                path_parts = [str(param.get("param_code", "")).strip()]
            path_parts = [part for part in path_parts if part]
            if not path_parts:
                continue

            leaf_schema = self._param_to_json_schema(param)
            self._assign_schema_path(
                root,
                path_parts,
                leaf_schema,
                required=bool(param.get("required", False)),
            )
        return root

    @staticmethod
    def _parse_request_mapping_path(
        mapping_path: str,
        *,
        default_location: str,
    ) -> tuple[str, list[str]]:
        """解析请求 mapping_path，返回 (location, path_parts)。"""
        if not mapping_path.startswith("$."):
            return default_location, []

        parts = [part for part in mapping_path[2:].split(".") if part]
        if not parts:
            return default_location, []

        location_map = {
            "requestBody": "body",
            "body": "body",
            "parameters": "body",
            "query": "query",
            "queryParams": "query",
            "path": "path",
            "pathParams": "path",
            "headers": "header",
            "header": "header",
        }
        location = location_map.get(parts[0], default_location)
        path_parts = parts[1:] if parts[0] in location_map else parts
        return location, path_parts

    def _filter_request_params_by_location(
        self,
        params: list[dict[str, Any]],
        *,
        method: str,
        location: str,
    ) -> list[dict[str, Any]]:
        """筛选指定位置的请求参数。"""
        result: list[dict[str, Any]] = []
        default_location = "query" if method in {"get", "delete", "head"} else "body"
        for param in params:
            if param.get("direction") not in ("IN", "INOUT"):
                continue
            param_location, _ = self._parse_request_mapping_path(
                str(param.get("mapping_path") or ""),
                default_location=default_location,
            )
            if param_location == location:
                result.append(param)
        return result

    def _build_operation_parameters(
        self,
        params: list[dict[str, Any]],
        *,
        method: str,
    ) -> list[dict[str, Any]]:
        """根据动作入参构造 OpenAPI parameters。"""
        default_location = "query" if method in {"get", "delete", "head"} else "body"
        result: list[dict[str, Any]] = []
        for param in params:
            if param.get("direction") not in ("IN", "INOUT"):
                continue
            location, path_parts = self._parse_request_mapping_path(
                str(param.get("mapping_path") or ""),
                default_location=default_location,
            )
            if location == "body":
                continue
            name = (
                path_parts[-1].removesuffix("[]")
                if path_parts
                else str(param.get("param_code", ""))
            )
            param_schema = self._param_to_json_schema(param)
            description = param_schema.pop("description", "")
            required = True if location == "path" else bool(param.get("required", False))
            parameter: dict[str, Any] = {
                "name": name,
                "in": location,
                "required": required,
                "schema": param_schema,
            }
            if description:
                parameter["description"] = description
            result.append(parameter)
        return result

    @staticmethod
    def _param_to_json_schema(param: dict[str, Any]) -> dict[str, Any]:
        """将参数定义转换为 JSON Schema 叶子节点。"""
        param_type = str(param.get("param_type", "STRING")).upper()
        type_mapping = {
            "STRING": "string",
            "NUMBER": "number",
            "DECIMAL": "number",
            "INTEGER": "integer",
            "BIGINT": "integer",
            "BOOLEAN": "boolean",
            "DATE": "string",
            "DATETIME": "string",
            "ARRAY": "array",
            "LIST": "array",
            "OBJECT": "object",
        }
        json_type = type_mapping.get(param_type, "string")
        schema: dict[str, Any] = {"type": json_type}
        if json_type == "array":
            schema["items"] = {"type": "string"}
        description = str(param.get("param_name") or "").strip()
        if description:
            schema["description"] = description
        return schema

    def _assign_schema_path(
        self,
        root: dict[str, Any],
        path_parts: list[str],
        leaf_schema: dict[str, Any],
        *,
        required: bool,
    ) -> None:
        """将叶子 schema 合并到指定路径。"""
        current = root
        start_index = 0
        if path_parts and path_parts[0] == "[]":
            if len(path_parts) == 1:
                if root.get("type") != "array":
                    root.clear()
                    root.update({"type": "array", "items": leaf_schema})
                return
            if root.get("type") != "array":
                root.clear()
                root.update({"type": "array", "items": {"type": "object", "properties": {}}})
            items = root.setdefault("items", {"type": "object", "properties": {}})
            items.setdefault("type", "object")
            items.setdefault("properties", {})
            current = items
            start_index = 1

        for index, raw_part in enumerate(path_parts[start_index:], start=start_index):
            is_last = index == len(path_parts) - 1
            is_array = raw_part.endswith("[]")
            part = raw_part[:-2] if is_array else raw_part
            properties = current.setdefault("properties", {})

            if is_last:
                existing = properties.get(part)
                if existing is None:
                    properties[part] = (
                        leaf_schema
                        if not is_array
                        else {
                            "type": "array",
                            "items": leaf_schema,
                        }
                    )
                elif is_array and existing.get("type") == "array":
                    existing.setdefault("items", leaf_schema)
                else:
                    existing.update({k: v for k, v in leaf_schema.items() if k not in existing})
                if required:
                    required_list = current.setdefault("required", [])
                    if part not in required_list:
                        required_list.append(part)
                return

            if required:
                required_list = current.setdefault("required", [])
                if part not in required_list:
                    required_list.append(part)
            if is_array:
                node = properties.setdefault(
                    part,
                    {"type": "array", "items": {"type": "object", "properties": {}}},
                )
                items = node.setdefault("items", {"type": "object", "properties": {}})
                items.setdefault("type", "object")
                items.setdefault("properties", {})
                current = items
            else:
                node = properties.setdefault(part, {"type": "object", "properties": {}})
                node.setdefault("type", "object")
                node.setdefault("properties", {})
                current = node

    @staticmethod
    def _split_request_url(request_url: str) -> tuple[str, str]:
        """将请求 URL 拆分为 server_url 与 path。"""
        if not request_url:
            return "", ""

        parsed = urlsplit(request_url)
        if parsed.scheme and parsed.netloc:
            base = f"{parsed.scheme}://{parsed.netloc}"
            path = parsed.path or "/"
            return base, path

        return "", request_url


def _infer_scoped_entity_code(path: Path, suffix: str) -> str | None:
    if not path.name.endswith(suffix):
        return None
    return path.name.removesuffix(suffix)


def _infer_object_scope(path: Path) -> str | None:
    scoped_code = _infer_scoped_entity_code(path, "_object.owl")
    if scoped_code is not None:
        return scoped_code

    if (
        path.name.endswith("_definition.owl")
        and path.parent.name
        and path.parent.parent.name == "object"
    ):
        return path.parent.name
    return None


def _infer_mapping_scope(path: Path) -> str | None:
    return _infer_scoped_entity_code(path, "_mapping.owl")


def _infer_view_scope(path: Path) -> str | None:
    if path.parent.name and path.parent.parent.name == "view":
        return path.parent.name
    return None

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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ParsedObject:
    object_code: str
    object_name: str
    description: str = ""
    source_type: str = "DB"
    datasource_alias: str | None = None
    table_name: str | None = None
    source_config: dict[str, Any] | None = None
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
    description: str = ""
    source_column: str | None = None
    is_primary_key: bool = False
    required: bool = False
    term_type_code_path: str | None = None
    library_code: str | None = None
    rel_term_codeorname: str | None = None
    term_data_type: str | None = None


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
        self._actions: dict[str, ParsedAction] = {}
        self._relations: dict[str, ParsedRelation] = {}
        self._datasources: dict[str, ParsedDatasource] = {}
        self._views: dict[str, ParsedView] = {}
        self._mappings: dict[str, dict[str, Any]] = {}
        self._current_entity_code: str | None = None
        self._mapping_datasource: dict[str, str] = {}
        self._mapping_table: dict[str, str] = {}
        self._field_uri_to_code: dict[str, str] = {}  # URI -> property_code

    def parse_file(self, path: Path) -> None:
        if path.suffix.lower() != ".owl":
            return

        content = path.read_text(encoding="utf-8")
        try:
            self._parse_owl_content(content, path)
        except Exception as e:
            logger.warning(f"Failed to parse OWL file {path}: {e}")

    def _parse_owl_content(self, content: str, path: Path) -> None:
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
                self._parse_entity_field(g, s)
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
            elif type_uri.endswith("EntityMapping"):
                self._parse_entity_mapping(g, s)
            elif type_uri.endswith("Mapping"):
                self._parse_mapping(g, s)

    def _get_predicate_value(self, g: Any, subject: Any, predicate_suffix: str) -> str | None:
        for p, o in g.predicate_objects(subject):
            p_str = str(p)
            if p_str.endswith(predicate_suffix):
                return str(o)
        return None

    def _get_predicate_values(self, g: Any, subject: Any, predicate_suffix: str) -> list[str]:
        result = []
        for p, o in g.predicate_objects(subject):
            p_str = str(p)
            if p_str.endswith(predicate_suffix):
                result.append(str(o))
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
            fixed = "[" + re.sub(r'\{([^}]+)\}', fix_obj, inner) + "]"
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

        source_type = "DB" if "DB" in entity_source else "API"

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
            field_refs=field_refs,
            actions=action_refs,
            relation_refs=relation_refs,
        )
        self._objects[entity_code] = obj

    def _parse_entity_field(self, g: Any, subject: Any) -> None:
        property_code = self._get_predicate_value(g, subject, "property_code")
        if not property_code:
            return

        # Track URI -> property_code so EntityDefinition field_refs can resolve to fields
        self._field_uri_to_code[str(subject)] = property_code

        property_name = self._get_predicate_value(g, subject, "property_name") or property_code
        data_type = self._get_predicate_value(g, subject, "data_type") or "STRING"
        source_column = self._get_predicate_value(g, subject, "source_column")
        is_required = self._get_predicate_value(g, subject, "is_required")
        term_type_code_path = self._get_predicate_value(g, subject, "term_type_code_path")
        library_code = self._get_predicate_value(g, subject, "library_code")
        rel_term_codeorname = self._get_predicate_value(g, subject, "rel_term_codeorname")
        term_data_type = self._get_predicate_value(g, subject, "term_data_type")

        fld = ParsedField(
            field_code=property_code,
            field_name=property_name,
            field_type=data_type,
            source_column=source_column,
            required=is_required.lower() == "true" if is_required else False,
            term_type_code_path=term_type_code_path if term_type_code_path else None,
            library_code=library_code if library_code else None,
            rel_term_codeorname=rel_term_codeorname if rel_term_codeorname else None,
            term_data_type=term_data_type if term_data_type else None,
        )
        self._fields[property_code] = fld

    def _parse_action_definition(self, g: Any, subject: Any) -> None:
        action_code = self._get_predicate_value(g, subject, "action_code")
        if not action_code:
            return

        action_name = self._get_predicate_value(g, subject, "action_name") or action_code
        action_desc = self._get_predicate_value(g, subject, "action_desc") or ""
        action_type_str = self._get_predicate_value(g, subject, "action_type") or "QUERY"

        action_type = "query"
        if "UPDATE" in action_type_str:
            action_type = "update"
        elif "QUERY" in action_type_str:
            action_type = "query"

        function_refs_str = self._get_predicate_value(g, subject, "function_refs") or "[]"
        function_refs = self._parse_loose_json_list(function_refs_str)

        belong_entity_str = self._get_predicate_value(g, subject, "belong_entity") or "[]"
        belong_entities = self._parse_loose_json_list(belong_entity_str)

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
        )
        self._actions[action_code] = action

        for entity_code in belong_entities:
            if entity_code in self._objects and action_code not in self._objects[entity_code].actions:
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

        fld = ParsedField(
            field_code=param_code,
            field_name=description or param_code,
            field_type=param_type.upper(),
            required=is_required.lower() == "true" if is_required else False,
            term_type_code_path=term_type_code_path if term_type_code_path else None,
            library_code=library_code if library_code else None,
            rel_term_codeorname=rel_term_codeorname if rel_term_codeorname else None,
            term_data_type=term_data_type if term_data_type else None,
        )
        self._fields[param_code] = fld

    def _parse_response_parameter(self, g: Any, subject: Any) -> None:
        field_code = self._get_predicate_value(g, subject, "fieldCode")
        if not field_code:
            return

        field_type = self._get_predicate_value(g, subject, "fieldType") or "string"
        term_type_code_path = self._get_predicate_value(g, subject, "term_type_code_path")
        library_code = self._get_predicate_value(g, subject, "library_code")
        rel_term_codeorname = self._get_predicate_value(g, subject, "rel_term_codeorname")
        term_data_type = self._get_predicate_value(g, subject, "term_data_type")

        fld = ParsedField(
            field_code=field_code,
            field_name=field_code,
            field_type=field_type.upper(),
            term_type_code_path=term_type_code_path if term_type_code_path else None,
            library_code=library_code if library_code else None,
            rel_term_codeorname=rel_term_codeorname if rel_term_codeorname else None,
            term_data_type=term_data_type if term_data_type else None,
        )
        if field_code not in self._fields:
            self._fields[field_code] = fld

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

        try:
            db_params = json.loads(db_params_str)
        except json.JSONDecodeError:
            db_params = {}

        datasource = ParsedDatasource(
            alias=db_code,
            db_type=db_type,
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

    def _parse_entity_mapping(self, g: Any, subject: Any) -> None:
        entity_code = self._get_predicate_value(g, subject, "entity_code")
        if not entity_code:
            return

        self._current_entity_code = entity_code
        mapping_refs = self._get_predicate_values(g, subject, "mapping")
        self._mappings[entity_code] = {
            "mappings": mapping_refs,
        }

    def _parse_mapping(self, g: Any, subject: Any) -> None:
        property_code = self._get_predicate_value(g, subject, "property_code")
        source_column = self._get_predicate_value(g, subject, "source_column_code")
        datasource_code = self._get_predicate_value(g, subject, "source_datasource_code")
        source_table = self._get_predicate_value(g, subject, "source_table_code")

        if property_code:
            if property_code in self._fields:
                self._fields[property_code].source_column = source_column
            else:
                fld = ParsedField(
                    field_code=property_code,
                    field_name=property_code,
                    source_column=source_column,
                )
                self._fields[property_code] = fld

            if self._current_entity_code:
                if datasource_code:
                    self._mapping_datasource[self._current_entity_code] = datasource_code
                if source_table:
                    self._mapping_table[self._current_entity_code] = source_table

    def _apply_mappings_to_objects(self) -> None:
        for entity_code, datasource_code in self._mapping_datasource.items():
            if entity_code in self._objects:
                self._objects[entity_code].datasource_alias = datasource_code

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

    def parse_directory(self, ontology_dir: Path, relations_dir: Path | None = None) -> dict[str, Any]:
        if ontology_dir.is_dir():
            for owl_file in ontology_dir.rglob("*.owl"):
                self.parse_file(owl_file)

        if relations_dir and relations_dir.is_dir():
            for owl_file in relations_dir.glob("*.owl"):
                self.parse_file(owl_file)

        self._apply_mappings_to_objects()

        objects = []
        for obj in self._objects.values():
            # Resolve field URIs (from <fields rdf:resource="..."/>) to ParsedField instances
            fields = []
            for field_uri in obj.field_refs:
                field_code = self._field_uri_to_code.get(field_uri)
                if not field_code:
                    continue
                fld = self._fields.get(field_code)
                if not fld:
                    continue
                field_dict = {
                    "field_code": fld.field_code,
                    "field_name": fld.field_name,
                    "field_type": fld.field_type,
                    "source_column": fld.source_column,
                    "is_primary_key": fld.is_primary_key,
                    "required": fld.required,
                }

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
                        for f in self._fields.values():
                            if param_ref.endswith(f.field_code) or f.field_code in param_ref:
                                param_dict = {
                                    "param_code": f.field_code,
                                    "param_name": f.field_name,
                                    "param_type": f.field_type,
                                    "required": f.required,
                                    "direction": "IN",
                                }
                                if f.term_type_code_path:
                                    term_meta = self._build_term_meta(f)
                                    if term_meta:
                                        param_dict["termMeta"] = term_meta
                                params.append(param_dict)
                                break

                    for param_ref in action.response_param_refs:
                        for f in self._fields.values():
                            if param_ref.endswith(f.field_code) or f.field_code in param_ref:
                                param_dict = {
                                    "param_code": f.field_code,
                                    "param_name": f.field_name,
                                    "param_type": f.field_type,
                                    "required": f.required,
                                    "direction": "OUT",
                                }
                                if f.term_type_code_path:
                                    term_meta = self._build_term_meta(f)
                                    if term_meta:
                                        param_dict["termMeta"] = term_meta
                                params.append(param_dict)
                                break

                    actions.append({
                        "action_code": action.action_code,
                        "action_name": action.action_name,
                        "description": action.description,
                        "action_type": action.action_type,
                        "function_refs": action.function_refs,
                        "params": params,
                    })

            source_config = None
            if obj.datasource_alias and obj.datasource_alias in self._datasources:
                ds = self._datasources[obj.datasource_alias]
                source_config = {
                    "alias": ds.alias,
                    "db_type": ds.db_type.upper(),
                    **ds.config,
                }

            objects.append({
                "object_code": obj.object_code,
                "object_name": obj.object_name,
                "description": obj.description,
                "source_type": obj.source_type,
                "datasource_alias": obj.datasource_alias,
                "table_name": obj.table_name,
                "source_config": source_config,
                "fields": fields,
                "actions": actions,
            })

        relations = []
        for rel_code, rel in self._relations.items():
            relations.append({
                "relation_code": rel_code,
                "relation_name": rel.relation_name,
                "source_class": rel.source_class,
                "target_class": rel.target_class,
                "relation_type": rel.relation_type,
                "join_keys": rel.join_keys,
                "description": rel.description,
            })

        datasource_configs = {}
        for ds_code, ds in self._datasources.items():
            datasource_configs[ds_code] = {
                "alias": ds.alias,
                "db_type": ds.db_type.upper(),
                **ds.config,
            }

        views = []
        for view in self._views.values():
            views.append({
                "view_id": view.view_id,
                "view_name": view.view_name,
                "description": view.description,
                "object_ids": view.object_codes,
                "relation_ids": view.relations,
            })

        return {
            "objects": objects,
            "relations": relations,
            "datasource_configs": datasource_configs,
            "views": views,
        }

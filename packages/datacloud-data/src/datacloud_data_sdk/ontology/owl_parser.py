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
    fields: list[dict[str, Any]] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)


@dataclass
class ParsedField:
    field_code: str
    field_name: str
    field_type: str = "STRING"
    description: str = ""
    source_column: str | None = None
    is_primary_key: bool = False
    required: bool = False
    term_set: str | None = None


@dataclass
class ParsedAction:
    action_code: str
    action_name: str
    description: str = ""
    action_type: str = "QUERY"
    belong_class: str | None = None
    function_refs: list[str] = field(default_factory=list)
    params: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ParsedRelation:
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
        self._relations: list[ParsedRelation] = []
        self._datasources: dict[str, ParsedDatasource] = {}
        self._views: dict[str, ParsedView] = {}
        self._mappings: dict[str, dict[str, Any]] = {}
        self._current_entity_code: str | None = None
        self._mapping_datasource: dict[str, str] = {}
        self._mapping_table: dict[str, str] = {}

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

    def _parse_entity_definition(self, g: Any, subject: Any) -> None:
        entity_code = self._get_predicate_value(g, subject, "entity_code")
        if not entity_code:
            return

        entity_name = self._get_predicate_value(g, subject, "entity_name") or entity_code
        entity_desc = self._get_predicate_value(g, subject, "entity_desc") or ""
        entity_source = self._get_predicate_value(g, subject, "entity_source") or "DB"

        source_type = "DB" if "DB" in entity_source else "API"

        action_refs_str = self._get_predicate_value(g, subject, "action_refs") or "[]"
        try:
            action_refs = json.loads(action_refs_str)
        except json.JSONDecodeError:
            action_refs = []

        obj = ParsedObject(
            object_code=entity_code,
            object_name=entity_name,
            description=entity_desc,
            source_type=source_type,
            actions=action_refs,
        )
        self._objects[entity_code] = obj

    def _parse_entity_field(self, g: Any, subject: Any) -> None:
        property_code = self._get_predicate_value(g, subject, "property_code")
        if not property_code:
            return

        property_name = self._get_predicate_value(g, subject, "property_name") or property_code
        data_type = self._get_predicate_value(g, subject, "data_type") or "STRING"
        source_column = self._get_predicate_value(g, subject, "source_column")
        is_required = self._get_predicate_value(g, subject, "is_required")
        term_type_code_path = self._get_predicate_value(g, subject, "term_type_code_path")

        fld = ParsedField(
            field_code=property_code,
            field_name=property_name,
            field_type=data_type,
            source_column=source_column,
            required=is_required.lower() == "true" if is_required else False,
            term_set=term_type_code_path if term_type_code_path else None,
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
        try:
            function_refs = json.loads(function_refs_str)
        except json.JSONDecodeError:
            function_refs = []

        belong_entity_str = self._get_predicate_value(g, subject, "belong_entity") or "[]"
        try:
            belong_entities = json.loads(belong_entity_str)
        except json.JSONDecodeError:
            belong_entities = []

        request_params = self._get_predicate_values(g, subject, "request_params")

        params = []
        for param_ref in request_params:
            param_ref_name = param_ref.split("#")[-1] if "#" in param_ref else param_ref
            if param_ref_name in self._fields:
                f = self._fields[param_ref_name]
                params.append({
                    "param_code": f.field_code,
                    "param_name": f.field_name,
                    "param_type": f.field_type,
                    "required": f.required,
                    "direction": "IN",
                    "term_set": f.term_set,
                })

        action = ParsedAction(
            action_code=action_code,
            action_name=action_name,
            description=action_desc,
            action_type=action_type,
            function_refs=function_refs,
            params=params,
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

        fld = ParsedField(
            field_code=param_code,
            field_name=description or param_code,
            field_type=param_type.upper(),
            required=is_required.lower() == "true" if is_required else False,
            term_set=term_type_code_path if term_type_code_path else None,
        )
        self._fields[param_code] = fld

    def _parse_response_parameter(self, g: Any, subject: Any) -> None:
        field_code = self._get_predicate_value(g, subject, "fieldCode")
        if not field_code:
            return

        field_type = self._get_predicate_value(g, subject, "fieldType") or "string"
        term_type_code_path = self._get_predicate_value(g, subject, "term_type_code_path")

        fld = ParsedField(
            field_code=field_code,
            field_name=field_code,
            field_type=field_type.upper(),
            term_set=term_type_code_path if term_type_code_path else None,
        )
        if field_code not in self._fields:
            self._fields[field_code] = fld

    def _parse_term_relation(self, g: Any, subject: Any) -> None:
        source_code = self._get_predicate_value(g, subject, "source_code")
        target_code = self._get_predicate_value(g, subject, "target_code")
        if not source_code or not target_code:
            return

        relation_name = self._get_predicate_value(g, subject, "relation_name") or ""
        relation_type = self._get_predicate_value(g, subject, "relation_type") or "ONE_TO_MANY"
        joinkeys_str = self._get_predicate_value(g, subject, "joinkeys") or "[]"

        try:
            join_keys = json.loads(joinkeys_str)
        except json.JSONDecodeError:
            join_keys = []

        relation = ParsedRelation(
            source_class=source_code,
            target_class=target_code,
            relation_type=relation_type,
            relation_name=relation_name,
            join_keys=join_keys,
        )
        self._relations.append(relation)

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

        try:
            object_codes = json.loads(object_codes_str)
        except json.JSONDecodeError:
            object_codes = []

        try:
            relations = json.loads(relations_str)
        except json.JSONDecodeError:
            relations = []

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

    def parse_directory(self, ontology_dir: Path, relations_dir: Path | None = None) -> dict[str, Any]:
        if ontology_dir.is_dir():
            for owl_file in ontology_dir.rglob("*.owl"):
                self.parse_file(owl_file)

        if relations_dir and relations_dir.is_dir():
            for owl_file in relations_dir.glob("*.owl"):
                self.parse_file(owl_file)

        self._apply_mappings_to_objects()

        objects = []
        for _obj_code, obj in self._objects.items():
            fields = []
            for _field_code, fld in self._fields.items():
                if fld.source_column or fld.term_set:
                    fields.append({
                        "field_code": fld.field_code,
                        "field_name": fld.field_name,
                        "field_type": fld.field_type,
                        "description": fld.description,
                        "source_column": fld.source_column,
                        "is_primary_key": fld.is_primary_key,
                        "required": fld.required,
                        "term_set": fld.term_set,
                    })

            actions = []
            for action_code in obj.actions:
                if action_code in self._actions:
                    action = self._actions[action_code]
                    actions.append({
                        "action_code": action.action_code,
                        "action_name": action.action_name,
                        "description": action.description,
                        "action_type": action.action_type,
                        "function_refs": action.function_refs,
                        "params": action.params,
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
        for idx, rel in enumerate(self._relations):
            relations.append({
                "relation_code": f"rel_{rel.source_class}__{rel.target_class}_{idx}",
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
        for _view_code, view in self._views.items():
            views.append({
                "view_id": view.view_id,
                "view_name": view.view_name,
                "description": view.description,
                "object_ids": view.object_codes,
            })

        return {
            "objects": objects,
            "relations": relations,
            "datasource_configs": datasource_configs,
            "views": views,
        }

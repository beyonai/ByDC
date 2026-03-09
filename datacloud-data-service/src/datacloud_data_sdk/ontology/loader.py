"""OntologyLoader: 解析 JSON/YAML 本体 -> 内部模型 + 核心实体。"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from datacloud_data_sdk.exceptions import ActionNotFoundError, ObjectNotFoundError
from datacloud_data_sdk.ontology.models import (
    FieldPhysicalMapping,
    OntologyAction,
    OntologyActionParam,
    OntologyClass,
    OntologyField,
    OntologyRelation,
)


@dataclass
class LoaderConfig:
    """OntologyLoader 运行时配置。"""

    plan_generator: Any = None
    event_bus: Any = None
    datasource_configs: dict[str, Any] = field(default_factory=dict)
    kb_source_configs: dict[str, dict] | None = None  # {alias: {endpoint: url}}
    csv_base_dir: str = "/tmp/datacloud_csv"
    sql_execution_mode: str = "internal"
    term_loader: Any = None  # TermLoader，用于术语解析；None 时跳过


class OntologyLoader:
    """本体加载器：解析标准格式 JSON，产出 Ontology* 模型与核心实体。

    Example::

        loader = OntologyLoader()
        loader.load_from_path("resources/ontology/crm_demo/objects_registry.json")
        loader.configure(csv_base_dir="/tmp/csv")
        obj = loader.get_object("sales_bo")
    """

    def __init__(self) -> None:
        self._classes: dict[str, OntologyClass] = {}
        self._relations: list[OntologyRelation] = []
        self._functions: dict[str, dict[str, Any]] = {}
        self._scenes: dict[str, dict[str, Any]] = {}
        self._config = LoaderConfig()

    def load_from_path(self, path: str | Path) -> None:
        """从本地文件加载本体定义。"""
        content = json.loads(Path(path).read_text(encoding="utf-8"))
        self.load_from_content(content)

    def load_from_content(self, content: dict[str, Any], format: str = "json") -> None:
        """从内存 dict 加载本体定义。"""
        for fn in content.get("functions", []):
            self._functions[fn["function_code"]] = fn.get("api_schema", {})

        for obj in content.get("objects", []):
            fields = self._parse_fields(obj.get("fields", []))
            actions = self._parse_actions(obj.get("actions", []), obj["object_code"])
            source_config = obj.get("source_config")
            datasource_alias = (
                source_config.get("alias") if source_config and isinstance(source_config, dict) else None
            ) or obj.get("datasource_alias")
            ontology_class = OntologyClass(
                object_code=obj["object_code"],
                object_name=obj.get("object_name", obj["object_code"]),
                description=obj.get("description", ""),
                source_type=obj.get("source_type", "DB"),
                datasource_alias=datasource_alias,
                table_name=obj.get("table_name"),
                source_config=source_config if isinstance(source_config, dict) else None,
                tags=obj.get("tags", []),
                fields=fields,
                actions=actions,
            )
            self._classes[obj["object_code"]] = ontology_class

        for rel in content.get("relations", []):
            self._relations.append(
                OntologyRelation(
                    relation_code=rel.get("relation_code", ""),
                    relation_name=rel.get("relation_name", ""),
                    source_class=rel.get("source_class", ""),
                    target_class=rel.get("target_class", ""),
                    relation_type=rel.get("relation_type", "ONE_TO_MANY"),
                    join_keys=rel.get("join_keys", []),
                    description=rel.get("description", ""),
                )
            )

        extracted = self._extract_datasource_configs_from_objects()
        if extracted:
            self._config.datasource_configs = {
                **self._config.datasource_configs,
                **extracted,
            }

    def configure(self, **kwargs: Any) -> None:
        """设置运行时配置（plan_generator、datasource_configs、csv_base_dir）。"""
        for k, v in kwargs.items():
            if hasattr(self._config, k):
                setattr(self._config, k, v)

    def _extract_datasource_configs_from_objects(self) -> dict[str, Any]:
        """从 source_type=DB 且含 source_config 的对象提取 DataSourceConfig，按 alias 去重。"""
        from datacloud_data_sdk.sql_executor.config_loader import (
            _dict_to_config,
            _substitute_dict,
        )

        configs: dict[str, Any] = {}
        for cls in self._classes.values():
            if cls.source_type != "DB" or not cls.source_config:
                continue
            sc = cls.source_config
            alias = sc.get("alias") if isinstance(sc, dict) else None
            if not alias or alias in configs:
                continue
            substituted = _substitute_dict(dict(sc))
            configs[alias] = _dict_to_config(alias, substituted)
        return configs

    # --- 本体层 API ---

    def get_ontology_class(self, object_code: str) -> OntologyClass:
        if object_code not in self._classes:
            raise ObjectNotFoundError(object_code)
        return self._classes[object_code]

    def get_ontology_classes(self, object_ids: list[str] | None = None) -> list[OntologyClass]:
        if object_ids is None:
            return list(self._classes.values())
        return [self.get_ontology_class(oid) for oid in object_ids]

    def get_ontology_relations(self) -> list[OntologyRelation]:
        return list(self._relations)

    def get_function_config(self, function_code: str) -> dict[str, Any]:
        return self._functions.get(function_code, {})

    # --- 核心层 API ---

    def get_action(self, object_code: str, action_code: str) -> "Action":
        """获取 Action 实体。"""
        from datacloud_data_sdk.action import Action

        cls = self.get_ontology_class(object_code)
        for a in cls.actions:
            if a.action_code == action_code:
                return Action(a, loader=self)
        raise ActionNotFoundError(object_code, action_code)

    def get_object(self, object_code: str) -> "Object":
        """获取 Object 实体。"""
        from datacloud_data_sdk.object import Object
        from datacloud_data_sdk.relation import Relation

        cls = self.get_ontology_class(object_code)
        rels = [
            Relation(
                from_object=r.source_class,
                to_object=r.target_class,
                cardinality=r.relation_type,
                join_keys=r.join_keys,
                description=r.description,
            )
            for r in self._relations
            if r.source_class == object_code or r.target_class == object_code
        ]
        return Object(cls, rels, loader=self)

    def load_scene(self, scene: dict[str, Any]) -> None:
        """加载场景/视图定义。"""
        self._scenes[scene["view_id"]] = scene

    def load_scene_from_path(self, path: str | Path) -> None:
        """从文件加载场景定义。"""
        content = json.loads(Path(path).read_text(encoding="utf-8"))
        self.load_scene(content)

    def get_view(self, view_id: str) -> "View":
        """获取 View 实体。"""
        from datacloud_data_sdk.relation import Relation
        from datacloud_data_sdk.view import View

        scene = self._scenes.get(view_id)
        if scene is None:
            raise ObjectNotFoundError(view_id)

        object_ids = scene.get("object_ids", [])
        objects = [self.get_object(oid) for oid in object_ids]

        object_set = set(object_ids)
        rels = [
            Relation(
                from_object=r.source_class,
                to_object=r.target_class,
                cardinality=r.relation_type,
                join_keys=r.join_keys,
                description=r.description,
            )
            for r in self._relations
            if r.source_class in object_set and r.target_class in object_set
        ]

        return View(
            view_id=view_id,
            view_name=scene.get("view_name", view_id),
            description=scene.get("description", ""),
            objects=objects,
            relations=rels,
        )

    # --- 内部解析 ---

    @staticmethod
    def _parse_term_meta(raw: dict[str, Any]) -> tuple[str | None, str | None, int | None]:
        """从 termMeta 或 term_set 解析，返回 (term_set, term_type, dataset_id)。"""
        tm = raw.get("termMeta") or raw.get("term_meta")
        if tm and isinstance(tm, dict):
            tc = tm.get("termTypeCode") or tm.get("term_type_code")
            tf = tm.get("termField") or tm.get("term_field")
            tmt = tm.get("termMasterType") or tm.get("term_master_type")
            ds = tm.get("datasetId") or tm.get("dataset_id")
            term_set = f"{tc}.{tf}" if tc and tf else None
            term_type = "enum" if tmt == "dict" else ("lookup" if tmt == "list" else None)
            try:
                dataset_id = int(ds) if ds is not None else None
            except (TypeError, ValueError):
                dataset_id = None
            return (term_set, term_type, dataset_id)
        return (raw.get("term_set"), None, None)

    def _parse_action_param(self, p: dict[str, Any]) -> OntologyActionParam:
        ts, tt, did = self._parse_term_meta(p)
        term_set = ts if ts is not None else p.get("term_set")
        return OntologyActionParam(
            param_code=p["param_code"],
            param_name=p.get("param_name", p["param_code"]),
            direction=p.get("direction", "IN"),
            param_type=p.get("param_type", "STRING"),
            required=p.get("required", False),
            default_value=p.get("default_value"),
            mapping_path=p.get("mapping_path", ""),
            term_set=term_set,
            term_type=tt,
            dataset_id=did,
        )

    def _parse_fields(self, raw_fields: list[dict[str, Any]]) -> list[OntologyField]:
        result = []
        for f in raw_fields:
            ts, tt, did = self._parse_term_meta(f)
            term_set = ts if ts is not None else f.get("term_set")
            result.append(
                OntologyField(
                    field_code=f["field_code"],
                    field_name=f.get("field_name", f["field_code"]),
                    field_type=f.get("field_type", "STRING"),
                    description=f.get("description", ""),
                    aliases=f.get("aliases", []),
                    required=f.get("required", False),
                    is_primary_key=f.get("is_primary_key", False),
                    source_column=f.get("source_column"),
                    term_set=term_set,
                    term_type=tt,
                    dataset_id=did,
                    physical_mappings=[
                        FieldPhysicalMapping(**m) for m in f.get("physical_mappings", [])
                    ],
                )
            )
        return result

    def _parse_actions(
        self, raw_actions: list[dict[str, Any]], belong_class: str
    ) -> list[OntologyAction]:
        return [
            OntologyAction(
                action_code=a["action_code"],
                action_name=a.get("action_name", a["action_code"]),
                description=a.get("description", ""),
                belong_class=belong_class,
                params=[
                    self._parse_action_param(p) for p in a.get("params", [])
                ],
                function_refs=a.get("function_refs", []),
                script=a.get("script"),
            )
            for a in raw_actions
        ]

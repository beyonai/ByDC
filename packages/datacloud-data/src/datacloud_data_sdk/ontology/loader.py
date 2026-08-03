"""
本体加载器模块

本模块提供本体定义的加载和管理能力，从 JSON/YAML 文件解析本体模型，
并提供核心实体（Object、View、Action）的访问接口。

核心功能：
- 从文件或内容加载本体定义
- 管理对象、关系、函数、视图等本体元素
- 提供配置管理（数据源、计划生成器等）
- 创建核心实体实例

使用示例：
    loader = OntologyLoader()
    loader.load_from_path("resources/ontology/crm_demo/objects_registry.json")
    loader.configure(csv_base_dir="/tmp/csv")
    obj = loader.get_object("sales_bo")
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

from datacloud_data_sdk.exceptions import ActionNotFoundError, ObjectNotFoundError
from datacloud_data_sdk.ontology.models import (
    FieldPhysicalMapping,
    OntologyAction,
    OntologyActionParam,
    OntologyClass,
    OntologyField,
    OntologyRelation,
)

if TYPE_CHECKING:
    from datacloud_data_sdk.action import Action
    from datacloud_data_sdk.object import Object
    from datacloud_data_sdk.view import View


DEFAULT_KB_BACKEND = "http_knowledge_import"


def _default_kb_backends() -> dict[str, Any]:
    from datacloud_data_sdk.executor.kb_search_backend import HttpKnowledgeSearchBackend

    return {DEFAULT_KB_BACKEND: HttpKnowledgeSearchBackend()}


def resolve_view_object_ids(view_data: dict[str, Any]) -> list[str]:
    """从视图字典中提取对象 ID 列表，处理所有已知的字段名约定。

    按优先级处理以下键名约定：
    - ``objects``: 字符串列表或包含 ``object_code``/``objectCode`` 的字典列表（规范内部格式）
    - ``object_ids``: 字符串列表
    - ``objectCodes``: 字符串列表（远程后端约定，camelCase）
    - ``object_codes``: 字符串列表（snake_case 替代）

    Args:
        view_data: 视图字典。

    Returns:
        提取到的对象 ID 字符串列表。
    """
    raw = view_data.get("objects")
    if isinstance(raw, list):
        if raw and isinstance(raw[0], str):
            return [str(c) for c in raw if c]
        result: list[str] = []
        for item in raw:
            if isinstance(item, dict):
                code = str(item.get("object_code") or item.get("objectCode") or "")
                if code:
                    result.append(code)
            elif isinstance(item, str) and item:
                result.append(item)
        return result

    codes = (
        view_data.get("object_ids")
        or view_data.get("objectCodes")
        or view_data.get("object_codes")
        or []
    )
    if isinstance(codes, list):
        return [str(c) for c in codes if c]
    return []


@dataclass
class LoaderConfig:
    """
    本体加载器运行时配置

    存储加载器运行所需的各种配置信息。

    Attributes:
        plan_generator: 计划生成器实例
        event_bus: 事件总线实例
        datasource_configs: 数据源配置字典
        kb_source_configs: 知识库配置字典
        csv_base_dir: CSV 文件存储目录
        result_file_storage: 最终结果文件存储实现
        sql_execution_mode: SQL 执行模式
        term_loader: 术语加载器实例
    """

    plan_generator: Any = None
    event_bus: Any = None
    datasource_configs: dict[str, Any] = field(default_factory=dict)
    kb_source_configs: dict[str, dict] | None = None
    csv_base_dir: str | None = None  # None 表示使用系统临时目录
    result_file_storage: Any = None
    sql_execution_mode: str = "internal"
    term_loader: Any = None
    kb_search_backend: Any = None
    kb_backends: dict[str, Any] = field(default_factory=_default_kb_backends)
    default_kb_backend: str | None = DEFAULT_KB_BACKEND
    query_result_csv_threshold: int = 10  # 0 = 不启用溢出截断
    sql_execute_url: str | None = None  # HTTP_SQL 后端服务地址（chatbi 等调用方注入）
    platform: Any = None


class OntologyLoader:
    """
    本体加载器

    解析标准格式 JSON，产出 Ontology* 模型与核心实体。
    是数据服务 SDK 的核心入口类。

    Attributes:
        _classes: 本体类字典
        _relations: 关联关系列表
        _functions: 函数配置字典
        _views: 视图配置字典
        _config: 运行时配置

    Example:
        loader = OntologyLoader()
        loader.load_from_path("resources/ontology/crm_demo/objects_registry.json")
        loader.configure(csv_base_dir="/tmp/csv")
        obj = loader.get_object("sales_bo")
    """

    def __init__(self) -> None:
        """初始化本体加载器"""
        self._classes: dict[str, OntologyClass] = {}
        self._relations: list[OntologyRelation] = []
        self._functions: dict[str, dict[str, Any]] = {}
        self._views: dict[str, dict[str, Any]] = {}
        self._config = LoaderConfig()
        self._resource_path: Path | None = None  # OWL 资源根目录，按需加载依赖对象时使用

    def load_from_path(self, path: str | Path) -> None:
        """
        从本地文件或目录加载本体定义

        Args:
            path: 本体文件路径，或包含 objects/ / functions/ / views/ 子目录的目录路径
        """
        p = Path(path)
        if p.is_dir():
            self._load_from_directory(p)
        else:
            content = json.loads(p.read_text(encoding="utf-8"))
            self.load_from_content(content)

    def _load_from_directory(self, base_dir: Path) -> None:
        """从目录结构加载本体定义（objects/ functions/ views/ 子目录）。"""
        objects_dir = base_dir / "objects"
        if objects_dir.exists():
            for obj_file in objects_dir.glob("*.json"):
                obj_data = json.loads(obj_file.read_text(encoding="utf-8"))
                self.load_from_content({"objects": [obj_data], "functions": [], "relations": []})
        functions_dir = base_dir / "functions"
        if functions_dir.exists():
            for fn_file in functions_dir.glob("*.json"):
                fn_data = json.loads(fn_file.read_text(encoding="utf-8"))
                fn_code = fn_data.get("function_code", fn_file.stem)
                self._functions[fn_code] = fn_data.get("api_schema", {})
        views_dir = base_dir / "views"
        if views_dir.exists():
            for view_file in views_dir.glob("*.json"):
                view_data = json.loads(view_file.read_text(encoding="utf-8"))
                self.load_view(view_data)

    def load_from_json_resource_directory(self, base_dir: str | Path) -> None:
        """从 JSON 格式本体资源目录增量加载，补充进 _classes（不清空已有内容）。

        目录结构：
          {base_dir}/
            {scene_id}/
              objects/
                {object_code}.json   ← ObjectType 格式（snake_case 或 camelCase）
              relations.json         ← 关系列表

        与 load_from_owl_resource_directory() 的区别：
          OWL 方法调用 _load_from_owl_content()，会 clear() 后重载；
          本方法调用 load_from_content()，增量追加，不清空。

        Args:
            base_dir: 本体资源根目录，如 {ONTOLOGY_PATH}/tasks/{trace_id}/
        """
        base_path = Path(base_dir)
        if not base_path.exists():
            return

        for scene_dir in sorted(base_path.iterdir()):
            if not scene_dir.is_dir():
                continue

            objects_dir = scene_dir / "objects"
            if objects_dir.exists():
                for json_file in sorted(objects_dir.glob("*.json")):
                    try:
                        raw = json.loads(json_file.read_text(encoding="utf-8"))
                        normalized = _normalize_object_json(raw)
                        if normalized.get("object_code"):
                            self.load_from_content(
                                {
                                    "objects": [normalized],
                                    "relations": [],
                                    "views": [],
                                }
                            )
                    except Exception:  # noqa: BLE001
                        pass

            relations_file = scene_dir / "relations.json"
            if relations_file.exists():
                try:
                    rel_data = json.loads(relations_file.read_text(encoding="utf-8"))
                    rels = rel_data.get("relations", [])
                    if rels:
                        self.load_from_content(
                            {
                                "objects": [],
                                "relations": rels,
                                "views": [],
                            }
                        )
                except Exception:  # noqa: BLE001
                    pass

    def load_from_owl_directory(self, base_dir: str | Path) -> None:
        """
        从 OWL 目录加载本体定义

        自动查找 base_dir 下的 ontology/ 和 relations/ 子目录，
        解析所有 .owl 文件并构建内部本体模型。

        Args:
            base_dir: 基础目录路径，应包含 ontology/ 和 relations/ 子目录

        Example:
            loader.load_from_owl_directory("mock_env/resource/knowledge/import_package_owl")
        """
        # from datacloud_data_sdk.ontology.owl_parser import OwlParser

        # base_path = Path(base_dir)
        # ontology_dir = base_path / "ontology"
        # relations_dir = base_path / "relations"

        # parser = OwlParser()
        # content = parser.parse_directory(ontology_dir, relations_dir)
        # self._load_from_owl_content(content)
        self.load_from_owl_resource_directory(base_dir=base_dir)

    def load_from_owl_resource_directory(
        self,
        base_dir: str | Path,
        *,
        object_codes: Iterable[str] | None = None,
        view_codes: Iterable[str] | None = None,
    ) -> None:
        """
        从新的 resource/object + resource/view 目录结构加载本体定义。

        Args:
            base_dir: resource 根目录，包含 object/ 和 view/ 子目录
            object_codes: 指定加载的对象编码列表，为空时不限制
            view_codes: 指定加载的视图编码列表，为空时不限制
        """
        from datacloud_data_sdk.ontology.owl_parser import OwlParser

        base_path = Path(base_dir)
        self._resource_path = base_path  # 记录 OWL 资源根目录，供按需加载依赖对象使用
        parser = OwlParser()
        content = parser.parse_resource_directory(
            base_path,
            object_codes=object_codes,
            view_codes=view_codes,
        )
        self._load_from_owl_content(content)

    def load_view_with_deps(self, resource_path: Path, view_id: str) -> None:
        """按需加载指定 view 及其依赖的 objects，追加到当前 loader（不清空）。

        Args:
            resource_path: resource 根目录（含 object/ 和 view/ 子目录）
            view_id: view 编码，对应 resource/view/{view_id}/ 目录
        """
        from datacloud_data_sdk.ontology.owl_parser import OwlParser

        view_dir = resource_path / "view" / view_id
        if not view_dir.is_dir():
            return

        parser = OwlParser()
        parser._parse_new_layout_view_directory(view_dir)

        object_codes: list[str] = []
        if parsed_view := parser._views.get(view_id):
            object_codes = parsed_view.object_codes

        for obj_code in object_codes:
            obj_dir = resource_path / "object" / obj_code
            if obj_dir.is_dir():
                parser._parse_new_layout_object_directory(obj_dir)

        parser._apply_mappings_to_objects()
        self.load_from_content(parser._build_content())

    def load_object_with_deps(self, resource_path: Path, object_code: str) -> None:
        """按需加载指定 object，追加到当前 loader（不清空）。

        Args:
            resource_path: resource 根目录（含 object/ 子目录）
            object_code: object 编码，对应 resource/object/{object_code}/ 目录
        """
        from datacloud_data_sdk.ontology.owl_parser import OwlParser

        obj_dir = resource_path / "object" / object_code
        if not obj_dir.is_dir():
            return

        parser = OwlParser()
        parser._parse_new_layout_object_directory(obj_dir)
        parser._apply_mappings_to_objects()
        self.load_from_content(parser._build_content())

    def _load_from_owl_content(self, content: dict[str, Any]) -> None:
        """
        从 OWL 解析后的内容加载本体定义

        Args:
            content: OwlParser.parse_directory() 返回的内容字典
        """
        self._classes.clear()
        self._relations.clear()
        self._views.clear()
        self._functions.clear()

        for fn_code, fn_config in content.get("functions", {}).items():
            if isinstance(fn_config, dict):
                self._functions[fn_code] = fn_config

        for obj in content.get("objects", []):
            obj_code: str = obj.get("object_code") or obj.get("objectCode") or obj.get("code", "")
            if not obj_code:
                continue
            fields = self._parse_fields(obj.get("fields", []))
            actions = self._parse_actions(obj.get("actions", []), obj_code)
            datasource_alias = obj.get("datasource_alias")
            source_config = obj.get("source_config")
            ontology_class = OntologyClass(
                object_code=obj_code,
                object_name=obj.get("object_name", obj_code),
                description=obj.get("description", ""),
                source_type=obj.get("source_type", "DB"),
                datasource_alias=datasource_alias,
                table_name=obj.get("table_name"),
                source_config=source_config,
                ext_property=obj.get("ext_property", {}),
                tags=obj.get("tags", []),
                fields=fields,
                actions=actions,
                term_sync=self._parse_term_sync(obj),
            )
            self._classes[obj_code] = ontology_class

        for rel in content.get("relations", []):
            self._relations.append(
                OntologyRelation(
                    relation_code=rel.get("relation_code", ""),
                    relation_name=rel.get("relation_name", ""),
                    source_class=rel.get("source_class", ""),
                    target_class=rel.get("target_class", ""),
                    relation_type=rel.get("relation_type", "ONE_TO_MANY"),
                    join_keys=rel.get("join_keys", []),
                    cascade_delete=(
                        rel.get("cascade_delete") is True
                        or (rel.get("attribute") or {}).get("cascade_delete") is True
                    ),
                    description=rel.get("description", ""),
                    resolve_action_code=rel.get("resolve_action_code"),
                    resolve_param_binding=rel.get("resolve_param_binding"),
                )
            )

        for ds_alias, ds_config in content.get("datasource_configs", {}).items():
            if ds_alias not in self._config.datasource_configs:
                from datacloud_data_sdk.sql_executor.config_loader import _dict_to_config

                self._config.datasource_configs[ds_alias] = _dict_to_config(ds_alias, ds_config)

        for view in content.get("views", []):
            self._views[view["view_id"]] = view

    def load_from_content(self, content: dict[str, Any], format: str = "json") -> None:
        """
        从内存字典加载本体定义

        解析本体内容，构建内部模型。

        Args:
            content: 本体内容字典
            format: 格式类型（json/yaml）
        """
        raw_functions = content.get("functions", {}) or {}
        if isinstance(raw_functions, dict):
            for fn_code, fn_config in raw_functions.items():
                if isinstance(fn_config, dict):
                    self._functions[fn_code] = fn_config
        elif raw_functions:
            for fn in raw_functions:
                self._functions[fn["function_code"]] = fn.get("api_schema", {})

        for obj in content.get("objects", []):
            obj_code: str = obj.get("object_code") or obj.get("objectCode") or obj.get("code", "")
            if not obj_code:
                continue
            fields = self._parse_fields(obj.get("fields", []))
            actions = self._parse_actions(obj.get("actions", []), obj_code)
            source_config = obj.get("source_config")
            datasource_alias = (
                source_config.get("alias")
                if source_config and isinstance(source_config, dict)
                else None
            ) or obj.get("datasource_alias")
            ontology_class = OntologyClass(
                object_code=obj_code,
                object_name=obj.get("object_name", obj_code),
                description=obj.get("description", ""),
                source_type=obj.get("source_type", "DB"),
                datasource_alias=datasource_alias,
                table_name=obj.get("table_name"),
                source_config=source_config if isinstance(source_config, dict) else None,
                ext_property=obj.get("ext_property", {}),
                tags=obj.get("tags", []),
                fields=fields,
                actions=actions,
                term_sync=self._parse_term_sync(obj),
            )
            self._classes[obj_code] = ontology_class

        for rel in content.get("relations", []):
            self._relations.append(
                OntologyRelation(
                    relation_code=rel.get("relation_code", ""),
                    relation_name=rel.get("relation_name", ""),
                    source_class=rel.get("source_class", ""),
                    target_class=rel.get("target_class", ""),
                    relation_type=rel.get("relation_type", "ONE_TO_MANY"),
                    join_keys=rel.get("join_keys", []),
                    cascade_delete=(
                        rel.get("cascade_delete") is True
                        or (rel.get("attribute") or {}).get("cascade_delete") is True
                    ),
                    description=rel.get("description", ""),
                    resolve_action_code=rel.get("resolve_action_code"),
                    resolve_param_binding=rel.get("resolve_param_binding"),
                )
            )

        extracted = self._extract_datasource_configs_from_objects()
        if extracted:
            self._config.datasource_configs = {
                **self._config.datasource_configs,
                **extracted,
            }

        for view in content.get("views", []):
            self._views[view["view_id"]] = view

    def configure(self, **kwargs: Any) -> None:
        """设置运行时配置（plan_generator、datasource_configs、csv_base_dir 等）。"""
        for k, v in kwargs.items():
            if hasattr(self._config, k):
                setattr(self._config, k, v)
        self._ensure_default_kb_backend()

    def _ensure_default_kb_backend(self) -> None:
        """Ensure the built-in knowledge backend is available unless explicitly replaced."""
        if not self._config.kb_backends:
            self._config.kb_backends = _default_kb_backends()
        if not self._config.default_kb_backend:
            self._config.default_kb_backend = DEFAULT_KB_BACKEND
        if (
            self._config.default_kb_backend == DEFAULT_KB_BACKEND
            and DEFAULT_KB_BACKEND not in self._config.kb_backends
        ):
            self._config.kb_backends[DEFAULT_KB_BACKEND] = _default_kb_backends()[
                DEFAULT_KB_BACKEND
            ]

    @property
    def result_file_storage(self) -> Any:
        """暴露已配置的结果文件存储后端，供工具运行时（如 file_io）注入到 InvocationContext。"""
        return self._config.result_file_storage

    @property
    def sql_execute_url(self) -> str | None:
        """暴露 HTTP_SQL 后端地址，供 DataSourceManager 在选 connector 时读取。"""
        return self._config.sql_execute_url

    def _extract_datasource_configs_from_objects(self) -> dict[str, Any]:
        """从 DB/DYNAMIC_TABLE 对象 source_config 提取 DataSourceConfig，按 alias 去重。"""
        from datacloud_data_sdk.sql_executor.config_loader import (
            _dict_to_config,
            _substitute_dict,
        )

        configs: dict[str, Any] = {}
        for cls in self._classes.values():
            if cls.source_type not in {"DB", "DYNAMIC_TABLE"} or not cls.source_config:
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

    def get_class(self, object_code: str) -> OntologyClass:
        """别名方法，供 OqlRouter 调用。"""
        return self.get_ontology_class(object_code)

    def get_ontology_classes(self, object_ids: list[str] | None = None) -> list[OntologyClass]:
        if object_ids is None:
            return list(self._classes.values())
        return [self.get_ontology_class(oid) for oid in object_ids]

    def get_ontology_relations(self) -> list[OntologyRelation]:
        return list(self._relations)

    def get_function_config(self, function_code: str) -> dict[str, Any]:
        return self._functions.get(function_code, {})

    def load_by_entity_code(self, entity_code: str) -> OntologyClass | None:
        """按 entity_code 查找已加载的 OntologyClass，不存在返回 None。"""
        return self._classes.get(entity_code)

    def with_extra_classes(self, extra_codes: list[str]) -> OntologyLoader:
        """返回一个浅拷贝，按需从 OWL 目录追加加载指定对象，原 loader 不受影响。"""
        import copy

        clone = copy.copy(self)
        clone._classes = dict(self._classes)  # noqa: SLF001

        if self._resource_path is None:
            return clone

        for entity_code in extra_codes:
            if entity_code in clone._classes:  # noqa: SLF001
                continue
            obj_dir = self._resource_path / "object" / entity_code
            if obj_dir.is_dir():
                clone.load_object_with_deps(self._resource_path, entity_code)

        return clone

    def get_action_params(self, action_code: str) -> dict[str, Any]:
        """读取指定 action 的入参/出参绑定信息，供 ParamLinkGraph 构建串联索引。

        遍历所有已加载的 OntologyClass，找到包含 action_code 的 class，
        返回参数绑定信息。

        Returns:
            {
              "belong_entity": "ops_langfuse_trace",
              "request_params": [
                  {"param_code": "trace_id", "object_property": "trace_id", "json_path": "..."},
                  ...
              ],
              "response_params": [
                  {"field_code": "span_id", "object_property": "span_id", "json_path": "..."},
                  ...
              ],
            }

        Raises:
            KeyError: action_code 在所有已加载对象中均未找到。
        """
        for cls in self._classes.values():
            for action in cls.actions:
                if action.action_code != action_code:
                    continue
                request_params = []
                response_params = []
                for p in action.params:
                    if p.direction in ("OUT",):
                        response_params.append(
                            {
                                "field_code": p.param_code,
                                "object_property": p.object_property or "",
                                "json_path": p.json_path or "",
                            }
                        )
                    else:
                        request_params.append(
                            {
                                "param_code": p.param_code,
                                "object_property": p.object_property or "",
                                "json_path": p.json_path or "",
                            }
                        )
                return {
                    "belong_entity": cls.object_code,
                    "request_params": request_params,
                    "response_params": response_params,
                }
        raise KeyError(action_code)

    # --- 核心层 API ---

    def get_action(self, object_code: str, action_code: str) -> Action:
        """获取 Action 实体。"""
        from datacloud_data_sdk.action import Action

        cls = self.get_ontology_class(object_code)
        for a in cls.actions:
            if a.action_code == action_code:
                return Action(a, loader=self)
        raise ActionNotFoundError(object_code, action_code)

    def get_object(self, object_code: str) -> Object:
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

    def load_view(self, view: dict[str, Any]) -> None:
        """加载视图定义。"""
        self._views[view["view_id"]] = view

    def load_view_from_path(self, path: str | Path) -> None:
        """从文件加载视图定义。"""
        content = json.loads(Path(path).read_text(encoding="utf-8"))
        self.load_view(content)

    def load_scene(self, scene: dict[str, Any]) -> None:
        """[已废弃] 加载场景/视图定义，请使用 load_view。"""
        self.load_view(scene)

    def load_scene_from_path(self, path: str | Path) -> None:
        """[已废弃] 从文件加载场景定义，请使用 load_view_from_path。"""
        self.load_view_from_path(path)

    def get_view(self, view_id: str) -> View:
        """获取 View 实体。"""
        from datacloud_data_sdk.relation import Relation
        from datacloud_data_sdk.view import View

        scene = self._views.get(view_id)
        if scene is None:
            raise ObjectNotFoundError(view_id)

        object_ids = resolve_view_object_ids(scene)
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

        view = View(
            view_id=view_id,
            view_name=scene.get("view_name", view_id),
            description=scene.get("description", ""),
            objects=objects,
            relations=rels,
            loader=self,
        )
        self._populate_view_virtual_actions(view, scene)
        return view

    def get_views(self, view_ids: list[str] | None = None) -> list[View]:
        """获取全部或指定的 View 实体列表。"""
        target_view_ids = view_ids if view_ids is not None else list(self._views)
        return [self.get_view(view_id) for view_id in target_view_ids]

    def _populate_view_virtual_actions(self, view: Any, scene: dict) -> None:
        """将 scene 中注入的虚拟动作填充到 View 实例。"""
        virtual_actions = scene.get("_virtual_actions", [])
        if virtual_actions:
            view.actions = list(virtual_actions)
        # 填充视图字段元数据
        from datacloud_data_sdk.virtual_action.models import ViewFieldMeta

        fields = scene.get("fields", [])
        if fields:
            view.fields = [f for f in fields if isinstance(f, ViewFieldMeta)]

    # --- 内部解析 ---

    @staticmethod
    def _parse_term_sync(obj: dict[str, Any]) -> Any:
        """从对象定义中解析 term_sync 配置，返回 TermSyncConfig 或 None。"""
        raw = obj.get("term_sync") or obj.get("ext_property", {}).get("term_sync")
        if not raw or not isinstance(raw, dict) or not raw.get("enabled"):
            return None
        try:
            from datacloud_knowledge.sync.config import (  # type: ignore[import-untyped]
                TermSyncConfig,
            )

            return TermSyncConfig.from_dict(raw)
        except Exception:  # noqa: BLE001
            return None

    @staticmethod
    def _parse_term_meta(
        raw: dict[str, Any],
    ) -> tuple[str | None, str | None, str | None, int | None, int | None]:
        """从 termMeta / terminology / term_set 解析，返回 (term_set, term_type, term_field, dataset_id, library_id)。"""
        tm = raw.get("termMeta") or raw.get("term_meta") or raw.get("terminology")
        if tm and isinstance(tm, dict):
            tc = tm.get("termTypeCode") or tm.get("term_type_code")
            tf = tm.get("termField") or tm.get("term_field")
            tmt = tm.get("termMasterType") or tm.get("term_master_type")
            ds = tm.get("datasetId") or tm.get("dataset_id")
            ls = tm.get("libraryId") or tm.get("library_id")
            term_set = f"{tc}.{tf}" if tc and tf else None
            term_type = "enum" if tmt == "dict" else ("lookup" if tmt == "list" else None)
            term_field = tf
            try:
                dataset_id = int(ds) if ds is not None else None
            except (TypeError, ValueError):
                dataset_id = None
            try:
                library_id = int(ls) if ls is not None else None
            except (TypeError, ValueError):
                library_id = None
            return (term_set, term_type, term_field, dataset_id, library_id)
        return (raw.get("term_set"), None, None, None, None)

    def _parse_action_param(self, p: dict[str, Any]) -> OntologyActionParam:
        ts, tt, tf, did, lid = self._parse_term_meta(p)
        term_set = ts if ts is not None else p.get("term_set")
        param_code = p.get("param_code") or p.get("paramCode", "")
        param_name = p.get("param_name") or p.get("paramName", param_code)
        param_type = p.get("param_type") or p.get("paramType", "STRING")
        required: bool = bool(p.get("required") or p.get("isRequired", False))
        mapping_path = p.get("mapping_path") or p.get("mappingPath", "")
        # 规范化 direction：兼容 "input"/"output"（workspace 存储格式）和 "IN"/"OUT"（OWL 格式）
        _dir_raw = (p.get("direction") or "IN").upper()
        direction = {"INPUT": "IN", "OUTPUT": "OUT"}.get(_dir_raw, _dir_raw)
        return OntologyActionParam(
            param_code=param_code,
            param_name=param_name,
            direction=direction,
            param_type=param_type,
            required=required,
            default_value=p.get("default_value"),
            data_format=p.get("data_format") or None,
            mapping_path=mapping_path,
            json_path=p.get("json_path", ""),
            object_property=p.get("object_property"),
            object_code=p.get("object_code"),
            term_set=term_set,
            term_type=tt,
            term_field=tf,
            dataset_id=did,
            library_id=lid,
        )

    def _parse_fields(self, raw_fields: list[dict[str, Any]]) -> list[OntologyField]:
        from datacloud_data_sdk.virtual_action.rules import apply_analytic_metadata

        result = []
        for f in raw_fields:
            ts, tt, tf, did, lid = self._parse_term_meta(f)
            term_set = ts if ts is not None else f.get("term_set")
            ont_field = OntologyField(
                field_code=f["field_code"],
                field_name=f.get("field_name", f["field_code"]),
                field_type=f.get("field_type", "STRING"),
                data_format=f.get("data_format"),
                description=f.get("description", ""),
                aliases=f.get("aliases", []),
                required=f.get("required", False),
                is_primary_key=f.get("is_primary_key", False),
                source_column=f.get("source_column") or f.get("sourceColumn"),
                term_set=term_set,
                term_type=tt if tt is not None else f.get("term_type"),
                term_field=tf if tf is not None else f.get("term_field"),
                dataset_id=did,
                library_id=lid,
                physical_mappings=[
                    FieldPhysicalMapping(**m) for m in f.get("physical_mappings", [])
                ],
                property_kind=f.get("property_kind", "physical"),
                derived_config=f.get("derived_config"),
                relation_ref=f.get("relation_ref"),
                resolve_action_code=f.get("resolve_action_code"),
                resolve_param_binding=f.get("resolve_param_binding"),
            )
            # 从 ext_property 解析 analytic_role/kind 及派生操作符
            ext_property = f.get("ext_property")
            if ext_property:
                apply_analytic_metadata(ont_field, ext_property)
            result.append(ont_field)
        return result

    def _parse_actions(
        self, raw_actions: list[dict[str, Any]], belong_class: str
    ) -> list[OntologyAction]:
        result: list[OntologyAction] = []
        for a in raw_actions:
            action_type = a.get("action_type") or a.get("actionType")
            if not action_type:
                continue  # 未配置 action_type 时跳过该动作
            function_refs: list[str] = list(a.get("function_refs", []) or [])
            script = a.get("script")
            request_url = a.get("request_url") or a.get("requestUrl")
            request_method = a.get("request_method") or a.get("requestMethod")
            action_code: str = a.get("action_code") or a.get("actionCode", "")
            # Auto-generate function config when action has request_url but no script.
            # Handles both: (a) empty function_refs → generate fn_code + config;
            # (b) existing function_refs but missing config → fill in config.
            # This ensures all loading paths (OWL / remote / scene) produce
            # usable function configs for _execute_api.
            if request_url and not script:
                if not function_refs:
                    fn_code = self._build_generated_function_code(action_code)
                    function_refs = [fn_code]
                for fn_code in function_refs:
                    if fn_code not in self._functions:
                        fn_config = self._build_function_config_from_url(
                            request_url, request_method, a
                        )
                        if fn_config:
                            self._functions[fn_code] = fn_config
            result.append(
                OntologyAction(
                    action_code=action_code,
                    action_name=a.get("action_name") or a.get("actionName") or action_code,
                    description=a.get("description") or a.get("actionDesc", ""),
                    belong_class=belong_class,
                    params=[self._parse_action_param(p) for p in a.get("params", [])],
                    function_refs=function_refs,
                    action_type=action_type,
                    script=script,
                    request_url=request_url,
                    request_method=request_method,
                    object_references=a.get("object_references") or a.get("objectReferences", []),
                )
            )
        return result

    @staticmethod
    def _build_generated_function_code(action_code: str) -> str:
        """Generate a stable function code from an action code."""
        fragment = re.sub(r"[^0-9A-Za-z_]+", "_", action_code).strip("_")
        if not fragment:
            fragment = "action"
        if fragment[0].isdigit():
            fragment = f"n_{fragment}"
        return f"fn_{fragment}"

    @staticmethod
    def _build_function_config_from_url(
        request_url: str,
        request_method: str | None,
        action_dict: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Build a minimal OpenAPI function config from a request URL.

        Returns None if the URL cannot be split into server + path.
        """
        if not request_url:
            return None
        parsed = urlsplit(request_url)
        if not (parsed.scheme and parsed.netloc):
            return None
        server_url = f"{parsed.scheme}://{parsed.netloc}"
        path = parsed.path or "/"
        method = (request_method or "POST").lower()
        action_name = action_dict.get("action_name") or action_dict.get("action_code", "")
        config: dict[str, Any] = {
            "openapi": "3.0.3",
            "info": {"title": action_name, "version": "1.0.0"},
            "servers": [{"url": server_url}],
            "paths": {path: {method: {"summary": action_dict.get("description", "")}}},
        }
        return config


def _normalize_object_json(data: dict[str, Any]) -> dict[str, Any]:
    """将 JSON 文件中的对象数据规范化为 load_from_content() 期望的 snake_case 格式。

    JSONWriter 写入的是驼峰格式（objectCode/objectName），
    load_from_content() 期望 snake_case（object_code/object_name）。
    两种格式均支持，优先 snake_case。
    """
    return {
        "object_code": data.get("object_code") or data.get("objectCode", ""),
        "object_name": data.get("object_name") or data.get("objectName", ""),
        "description": data.get("description") or data.get("objectDesc", ""),
        "source_type": data.get("source_type") or data.get("sourceType", "DB"),
        "fields": data.get("fields") or data.get("properties", []),
        "actions": data.get("actions", []),
        "datasource_alias": data.get("datasource_alias") or data.get("datasourceAlias"),
        "table_name": data.get("table_name") or data.get("tableName"),
        "source_config": data.get("source_config") or data.get("sourceConfig"),
        "ext_property": data.get("ext_property") or data.get("extProperty", {}),
        "tags": data.get("tags", []),
    }

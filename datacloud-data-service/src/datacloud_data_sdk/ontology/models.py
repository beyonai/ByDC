"""本体内部模型：OntologyClass / Field / Action / Relation。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class FieldPhysicalMapping:
    """字段到物理存储的映射。"""

    source_type: str  # DB / API
    source_ref: str  # DB 列名 或 $.response.xxx
    datasource_alias: str


@dataclass
class OntologyField:
    """对象字段定义。"""

    field_code: str
    field_name: str
    field_type: str  # STRING / NUMBER / DATE / BOOLEAN / INTEGER / ARRAY / OBJECT
    description: str = ""
    aliases: list[str] = field(default_factory=list)
    required: bool = False
    is_primary_key: bool = False
    source_column: str | None = None
    term_set: str | None = None
    term_type: str | None = None  # "enum" | "lookup"
    dataset_id: int | None = None
    physical_mappings: list[FieldPhysicalMapping] = field(default_factory=list)


@dataclass
class OntologyActionParam:
    """动作参数定义。"""

    param_code: str
    param_name: str
    direction: str  # IN / OUT / INOUT
    param_type: str
    required: bool = False
    default_value: Any = None
    mapping_path: str = ""
    term_set: str | None = None
    term_type: str | None = None  # "enum" | "lookup"
    dataset_id: int | None = None


@dataclass
class OntologyAction:
    """对象动作定义，支持 API 调用或 Python 脚本执行。

    执行优先级：script（非空）> function_refs > 抛 ActionNotConfiguredError
    """

    action_code: str
    action_name: str
    description: str
    belong_class: str
    params: list[OntologyActionParam]
    function_refs: list[str]
    script: str | None = None


@dataclass
class OntologyRelation:
    """对象间关联关系。"""

    relation_code: str
    relation_name: str = ""
    source_class: str = ""
    target_class: str = ""
    relation_type: str = ""  # ONE_TO_MANY / MANY_TO_ONE / ONE_TO_ONE / MANY_TO_MANY
    join_keys: list[dict[str, str]] = field(default_factory=list)
    description: str = ""


@dataclass
class OntologyClass:
    """本体对象/类定义。"""

    object_code: str
    object_name: str
    description: str
    source_type: str  # DB / API / KNOWLEDGE_BASE
    datasource_alias: str | None = None
    table_name: str | None = None
    source_config: dict[str, Any] | None = None
    tags: list[str] = field(default_factory=list)
    fields: list[OntologyField] = field(default_factory=list)
    actions: list[OntologyAction] = field(default_factory=list)

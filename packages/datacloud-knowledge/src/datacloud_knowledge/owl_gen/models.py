"""OWL 生成器数据模型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Column:
    """数据库表字段。"""

    name: str
    sql_type: str
    nullable: bool
    comment: str
    is_primary_key: bool = False


@dataclass
class Table:
    """数据库表。"""

    code: str
    name: str
    desc: str
    columns: list[Column] = field(default_factory=list)
    primary_keys: list[str] = field(default_factory=list)


@dataclass
class TermBinding:
    """字段→术语类型绑定。

    表示某个表的某个字段对应一种术语类型，
    其 DISTINCT 值将作为该术语类型下的术语值导入。
    """

    table_code: str
    column_name: str
    term_type_code: str
    term_data_type: str  # LIST_TERM / DICT_TERM


@dataclass
class ObjectRelation:
    """对象间关系（JOIN 关系）。"""

    relation_id: str
    source_code: str
    target_code: str
    relation_name: str
    join_keys: list[dict[str, str]]


@dataclass
class FieldRole:
    """字段维度/度量角色（百应方案 §3.2.1）。"""

    property_role: str  # DIMENSION | MEASURE
    rule_type: str  # id | name | datetime | period | description | numeric | virtual_tag | primary_key | raw_number | basic_metric | snapshot_metric | derived_metric | formula_metric
    formula: str = ""  # 计算属性的 SQL 公式，空字符串表示存储字段


@dataclass
class ViewFieldMapping:
    """视图字段→对象字段映射。"""

    property_code: str
    property_name: str
    source_object_code: str
    source_object_column_code: str
    role: FieldRole


@dataclass
class ViewConfig:
    """单个视图的配置。"""

    view_code: str
    view_name: str
    view_desc: str
    object_codes: list[str]
    field_mappings: list[ViewFieldMapping] = field(default_factory=list)

@dataclass
class OwlGenConfig:
    """OWL 生成配置 — 参数化，支持不同业务场景复用。

    职责：描述"要生成什么"，不包含"怎么生成"的逻辑。
    """

    # ── 领域 & 本体库 ──
    domain_code: str
    domain_name: str
    domain_desc: str
    library_code: str
    library_name: str
    library_desc: str

    # ── 数据源描述（写入 OWL 的 dbsource 节点）──
    db_code: str
    db_type: str
    db_params: dict[str, Any]

    # ── 要处理的表 ──
    table_codes: list[str]
    table_names: dict[str, str]  # code → 中文名
    table_descs: dict[str, str]  # code → 描述

    # ── 字段→术语绑定 ──
    term_bindings: list[TermBinding]

    # ── 对象间关系 ──
    object_relations: list[ObjectRelation]


    # ── 输出目录 ──
    output_dir: Path

    # ── 视图（多视图优先）──
    views: list[ViewConfig] = field(default_factory=list)
    # 向后兼容：仍可设置单视图字段，resolved_views() 自动转换
    view_code: str = ""
    view_name: str = ""
    view_desc: str = ""

    # ── MySQL 连接参数（schema_reader 使用）──
    mysql_host: str = ""
    mysql_port: int = 3306
    mysql_user: str = ""
    mysql_password: str = ""
    mysql_database: str = ""

    # ── 字段角色（对象层）──
    # key = (table_code, column_name)
    field_roles: dict[tuple[str, str], FieldRole] = field(default_factory=dict)

    # ── 视图字段映射（向后兼容，推荐用 ViewConfig.field_mappings）──
    view_field_mappings: list[ViewFieldMapping] = field(default_factory=list)

    def resolved_views(self) -> list[ViewConfig]:
        """返回视图列表：优先 views，否则从旧字段自动包装。"""
        if self.views:
            return self.views
        if self.view_code:
            return [
                ViewConfig(
                    view_code=self.view_code,
                    view_name=self.view_name,
                    view_desc=self.view_desc,
                    object_codes=self.table_codes,
                    field_mappings=self.view_field_mappings,
                )
            ]
        return []

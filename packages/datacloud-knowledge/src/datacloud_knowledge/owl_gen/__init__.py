"""owl_gen — 通用业务库表 → OWL 导入包生成器。

用法::

    from datacloud_knowledge.owl_gen import OwlGenConfig, generate

    config = OwlGenConfig(...)
    generate(config)
"""

from datacloud_knowledge.owl_gen.generator import generate, generate_from_tables
from datacloud_knowledge.owl_gen.models import (
    Column,
    FieldRole,
    ObjectPropConfig,
    ObjectRelation,
    OwlGenConfig,
    ResolvedObjectProp,
    Table,
    TermBinding,
    TermTypeConfig,
    ViewConfig,
    ViewFieldMapping,
)

__all__ = [
    "Column",
    "FieldRole",
    "ObjectPropConfig",
    "ObjectRelation",
    "OwlGenConfig",
    "ResolvedObjectProp",
    "Table",
    "TermBinding",
    "TermTypeConfig",
    "ViewConfig",
    "ViewFieldMapping",
    "generate",
    "generate_from_tables",
]

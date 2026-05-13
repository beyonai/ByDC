"""DataCloud Knowledge SDK — 知识服务底座。

提供术语构建、术语查询、语义消歧等能力，
解决"用户怎么说"和"系统怎么懂"之间的语义鸿沟。

公共 API 速览：
    from datacloud_knowledge.provider import (
        get_object_props,              # 查询对象的属性列表
        get_prop_values_with_aliases,  # 查询属性的可选值及别名
        resolve_field_aliases,         # 字段别名消歧
        search_terms_by_type,          # 术语检索
        prepare_query_clarification,   # 查询澄清分析
        finalize_query_clarification,  # 澄清回填
    )
"""

__version__ = "0.2.0"

__all__ = [
    "__version__",
]

"""DataCloud Knowledge SDK — 知识服务底座。

提供术语构建、术语查询、语义消歧等能力，
解决"用户怎么说"和"系统怎么懂"之间的语义鸿沟。

公共 API 速览：
    from datacloud_knowledge.provider import (
        get_object_props_by_code,       # 按对象 code 查询属性列表
        get_prop_enum_values,           # 按属性 code 查询可选枚举值
        resolve_field_aliases,          # 字段别名消歧
        search_terms_by_type,           # 术语检索
        prepare_query_clarification,    # 查询澄清分析
        finalize_query_clarification,   # 澄清回填
    )
"""

__version__ = "0.2.0"

__all__ = [
    "__version__",
]

"""Label 映射 — HTTP adapter 的内部实现细节。

定义内部领域语义到外部 API labelTypeCode 的映射约定。

Label 模型：
    外部 API 的 label 系统是两层结构：
        labelTypeCode (标签类型编码，在外部系统中注册)
            └── labelCode (标签编码值)

内部领域语义 → Label 映射：
    | 内部语义     | 注册的 labelTypeCode | 过滤方式    |
    |-------------|---------------------|-----------|
    | 术语分类      | typeCategory        | 等值       |
    | 用户别名      | userId              | 等值       |
    | 关系源       | relationSource      | 等值       |
    | 作用域       | scope               | 等值       |
    | 属性归属      | propOf              | 等值       |

注意：具体的 labelTypeCode 命名需与外部 API 团队协商注册。
"""

from __future__ import annotations

# ── labelTypeCode 常量 ─────────────────────────────────────────────────

LABEL_TYPE_CATEGORY = "typeCategory"
"""术语分类（对应 term_type 的 type_category）。"""

LABEL_USER_ID = "userId"
"""用户别名关联（用户级术语名称的作用域用户）。"""

LABEL_RELATION_SOURCE = "relationSource"
"""关系源术语编码。"""

LABEL_SCOPE = "scope"
"""作用域标识（如视图/对象编码）。"""

LABEL_PROP_OF = "propOf"
"""属性归属对象编码。"""

# ── labelFilter 使用示例 ──────────────────────────────────────────────
#
# from datacloud_knowledge.contracts.term_provider_types import LabelFilter
#
# # 按术语分类过滤
# LabelFilter(LABEL_TYPE_CATEGORY, filter_value="3")
#
# # 按用户别名过滤
# LabelFilter(LABEL_USER_ID, filter_value="user123")
#
# # 按作用域过滤
# LabelFilter(LABEL_SCOPE, filter_value="sales_crm")
#

__all__ = [
    "LABEL_PROP_OF",
    "LABEL_RELATION_SOURCE",
    "LABEL_SCOPE",
    "LABEL_TYPE_CATEGORY",
    "LABEL_USER_ID",
]

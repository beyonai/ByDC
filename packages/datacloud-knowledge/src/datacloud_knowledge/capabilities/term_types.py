"""术语类型与绑定定义。

定义 capabilities/ 层的术语数据类型枚举和术语绑定类型。
零外部依赖。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

# ═══════════════════════════════════════════════════════════════════════════════
# 术语数据类型
# ═══════════════════════════════════════════════════════════════════════════════

TermDataType = Literal[
    "view",
    "obj",
    "prop",
    "list",
    "dict",
    "enum",
    "synonym",
]
"""术语数据类型枚举。

- view:    视图 — 业务视角的数据聚合
- obj:     对象 — 数据实体
- prop:    属性 — 对象/视图下的字段
- list:    列表 — 扁平值集合
- dict:    字典 — 键值对集合
- enum:    枚举 — 有限取值集合
- synonym: 同义词/别名 — 术语的替代名称
"""


# ═══════════════════════════════════════════════════════════════════════════════
# 术语绑定
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True, slots=True)
class TermBinding:
    """术语绑定 — 描述属性值与属性之间的绑定关系。

    Attributes:
        property_term_code: 属性术语编码。
        value_term_code:    值术语编码。
        binding_type:       绑定类型。
    """

    property_term_code: str
    """属性术语编码（prop 的 term_code）。"""
    value_term_code: str
    """值术语编码（child term 的 term_code）。"""
    binding_type: str = "enum"
    """绑定类型，默认 "enum"（枚举值绑定）。"""


# ═══════════════════════════════════════════════════════════════════════════════
# 公开 API 导出
# ═══════════════════════════════════════════════════════════════════════════════

__all__ = [
    "TermBinding",
    "TermDataType",
]

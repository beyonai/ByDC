"""
对象关联关系模块

本模块定义了 Relation 数据类，用于表示本体对象之间的关联关系。
关联关系描述了对象间的连接方式，包括连接键和基数等元数据。

核心功能：
- 定义对象间的关联关系
- 存储连接键映射
- 支持多种基数类型（一对一、一对多、多对多等）

使用示例：
    relation = Relation(
        from_object="po_users",
        to_object="po_organization",
        cardinality="many_to_one",
        join_keys=[{"from": "org_id", "to": "id"}],
        description="用户所属组织"
    )
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Relation:
    """
    对象间关联关系数据类
    
    描述两个对象之间的关联关系，包括连接方式和基数。
    
    Attributes:
        from_object: 源对象代码
        to_object: 目标对象代码
        cardinality: 关联基数，如 "one_to_one", "one_to_many", "many_to_one", "many_to_many"
        join_keys: 连接键映射列表，每个元素包含 from 和 to 字段
        description: 关联关系描述
    
    Example:
        Relation(
            from_object="sales_order",
            to_object="sales_customer",
            cardinality="many_to_one",
            join_keys=[{"from": "customer_id", "to": "id"}],
            description="订单所属客户"
        )
    """

    from_object: str
    to_object: str
    cardinality: str
    join_keys: list[dict[str, str]]
    description: str = ""

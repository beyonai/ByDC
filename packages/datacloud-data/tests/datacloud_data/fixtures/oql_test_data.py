"""
OQL 测试数据和 Mock 注册表

提供测试用的本体对象、字段、关系定义。
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class MockField:
    """Mock 字段"""
    field_code: str
    field_name: str
    data_type: str
    source_column: Optional[str] = None
    physical_mappings: dict = field(default_factory=dict)
    term_set: Optional[str] = None


@dataclass
class MockRelation:
    """Mock 关系"""
    relation_code: str
    target_class: str
    join_keys: dict = field(default_factory=dict)


@dataclass
class MockAction:
    """Mock 动作"""
    action_code: str
    action_name: str
    params: list = field(default_factory=list)


@dataclass
class MockClass:
    """Mock 本体类"""
    object_code: str
    object_name: str
    source_type: str  # "DB" or "API"
    datasource_alias: Optional[str] = None
    table_name: Optional[str] = None
    fields: list[MockField] = field(default_factory=list)
    relations: list[MockRelation] = field(default_factory=list)
    actions: list[MockAction] = field(default_factory=list)


class MockRegistry:
    """Mock 本体注册表"""

    def __init__(self):
        self.classes: dict[str, MockClass] = {}
        self._init_test_data()

    def _init_test_data(self):
        """初始化测试数据"""
        # 航班对象（DB）
        flight_cls = MockClass(
            object_code="Flight",
            object_name="航班",
            source_type="DB",
            datasource_alias="mysql_main",
            table_name="flights",
            fields=[
                MockField("flight_id", "航班ID", "String", source_column="id"),
                MockField("flight_number", "航班号", "String", source_column="flight_no"),
                MockField("departure_time", "出发时间", "DateTime", source_column="depart_time"),
                MockField("arrival_time", "到达时间", "DateTime", source_column="arrive_time"),
                MockField("crew_id", "机组ID", "String", source_column="crew_id"),
                MockField("status", "状态", "String", source_column="status"),
            ],
            relations=[
                MockRelation("crew", "Crew", {"crew_id": "crew_id"}),
            ]
        )
        self.classes["Flight"] = flight_cls

        # 机组对象（DB）
        crew_cls = MockClass(
            object_code="Crew",
            object_name="机组",
            source_type="DB",
            datasource_alias="mysql_main",
            table_name="crews",
            fields=[
                MockField("crew_id", "机组ID", "String", source_column="id"),
                MockField("crew_name", "机组名称", "String", source_column="name"),
                MockField("captain", "机长", "String", source_column="captain"),
                MockField("manual_id", "操作手册ID", "String", source_column="manual_id"),
            ],
            relations=[
                MockRelation("manual", "Manual", {"manual_id": "manual_id"}),
            ]
        )
        self.classes["Crew"] = crew_cls

        # 操作手册对象（API）
        manual_cls = MockClass(
            object_code="Manual",
            object_name="操作手册",
            source_type="API",
            datasource_alias="api_manual",
            fields=[
                MockField("manual_id", "手册ID", "String"),
                MockField("manual_name", "手册名称", "String"),
                MockField("version", "版本", "String"),
                MockField("content", "内容", "String"),
            ],
            actions=[
                MockAction("query", "查询", []),
            ]
        )
        self.classes["Manual"] = manual_cls

    def get_class(self, object_code: str) -> Optional[MockClass]:
        """获取本体类"""
        return self.classes.get(object_code)


class MockDatasourceRegistry:
    """Mock 数据源注册表"""

    def __init__(self):
        self.datasources = {
            "mysql_main": MockDatasource("mysql_main", "MYSQL"),
            "api_manual": MockDatasource("api_manual", "API"),
        }

    def get(self, alias: str) -> Optional[MockDatasource]:
        """获取数据源"""
        return self.datasources.get(alias)


@dataclass
class MockDatasource:
    """Mock 数据源"""
    alias: str
    db_type: str


class MockTermResolver:
    """Mock 术语解析器"""

    def resolve(self, term: str, object_code: str, field_code: str) -> str:
        """解析术语"""
        # 简化实现：直接返回原值
        return term


# 测试数据集
TEST_FLIGHT_RECORDS = [
    {
        "flight_id": "F001",
        "flight_number": "CA001",
        "departure_time": "2024-01-01 08:00:00",
        "arrival_time": "2024-01-01 12:00:00",
        "crew_id": "C001",
        "status": "completed",
    },
    {
        "flight_id": "F002",
        "flight_number": "CA002",
        "departure_time": "2024-01-01 14:00:00",
        "arrival_time": "2024-01-01 18:00:00",
        "crew_id": "C002",
        "status": "completed",
    },
]

TEST_CREW_RECORDS = [
    {
        "crew_id": "C001",
        "crew_name": "机组A",
        "captain": "张三",
        "manual_id": "M001",
    },
    {
        "crew_id": "C002",
        "crew_name": "机组B",
        "captain": "李四",
        "manual_id": "M002",
    },
]

TEST_MANUAL_RECORDS = [
    {
        "manual_id": "M001",
        "manual_name": "波音737操作手册",
        "version": "1.0",
        "content": "...",
    },
    {
        "manual_id": "M002",
        "manual_name": "空客A320操作手册",
        "version": "2.0",
        "content": "...",
    },
]

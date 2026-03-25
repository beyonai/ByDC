"""
事件类型定义模块

本模块定义了数据服务 SDK 中使用的所有事件类型。
事件用于在系统内部进行状态变更通知和解耦通信。

事件类型分类：
- 查询流程事件：QueryRequestReceived, ObjectViewBuilt, QueryPlanGenerated 等
- 执行流程事件：ExecutionTasksReady, StepsExecuted, AggregationCompleted 等
- 验证流程事件：PlanValidated, PlanRetryRequested, PlanValidationFailed 等

所有事件都继承自 BaseEvent，包含请求追踪信息。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class BaseEvent:
    """
    事件基类
    
    所有事件的基类，包含请求追踪信息。
    
    Attributes:
        request_id: 请求 ID
        trace_id: 追踪 ID
    """
    
    request_id: str
    trace_id: str


@dataclass
class QueryRequestReceived(BaseEvent):
    """
    查询请求接收事件
    
    当系统接收到新的查询请求时触发。
    
    Attributes:
        question: 用户问题
        view_ids: 视图 ID 列表
        object_ids: 对象 ID 列表
        tenant_id: 租户 ID
    """
    
    question: str = ""
    view_ids: list[str] = field(default_factory=list)
    object_ids: list[str] = field(default_factory=list)
    tenant_id: str = ""


@dataclass
class ObjectViewBuilt(BaseEvent):
    """
    对象视图构建完成事件
    
    当对象视图从本体构建完成时触发。
    
    Attributes:
        object_view: 对象视图数据
        question: 用户问题
    """
    
    object_view: dict = field(default_factory=dict)
    question: str = ""


@dataclass
class QueryPlanGenerated(BaseEvent):
    """
    查询计划生成完成事件
    
    当 LLM 生成查询计划后触发。
    
    Attributes:
        plan: 生成的计划
        object_view: 对象视图数据
        question: 用户问题
    """
    
    plan: dict = field(default_factory=dict)
    object_view: dict = field(default_factory=dict)
    question: str = ""


@dataclass
class PlanValidated(BaseEvent):
    """
    计划验证完成事件
    
    当查询计划验证完成后触发。
    
    Attributes:
        valid: 是否验证通过
        plan: 验证的计划
        object_view: 对象视图数据
        question: 用户问题
        errors: 验证错误列表
        retry_count: 重试次数
    """
    
    valid: bool = False
    plan: dict = field(default_factory=dict)
    object_view: dict = field(default_factory=dict)
    question: str = ""
    errors: list[str] = field(default_factory=list)
    retry_count: int = 0


@dataclass
class PlanRetryRequested(BaseEvent):
    """
    计划重试请求事件
    
    当计划验证失败需要重试时触发。
    
    Attributes:
        object_view: 对象视图数据
        question: 用户问题
        validation_errors: 验证错误列表
        retry_count: 重试次数
    """
    
    object_view: dict = field(default_factory=dict)
    question: str = ""
    validation_errors: list[str] = field(default_factory=list)
    retry_count: int = 0


@dataclass
class PlanValidationFailed(BaseEvent):
    """
    计划验证失败事件
    
    当计划验证最终失败时触发。
    
    Attributes:
        errors: 错误列表
        last_plan: 最后一次尝试的计划
    """
    
    errors: list[str] = field(default_factory=list)
    last_plan: dict = field(default_factory=dict)


@dataclass
class PlanRewritten(BaseEvent):
    """
    计划重写完成事件
    
    当计划被重写优化后触发。
    
    Attributes:
        rewritten_plan: 重写后的计划
    """
    
    rewritten_plan: dict = field(default_factory=dict)


@dataclass
class ExecutionTasksReady(BaseEvent):
    """
    执行任务就绪事件
    
    当执行任务准备就绪时触发。
    
    Attributes:
        tasks: 任务列表
        aggregation: 聚合配置
    """
    
    tasks: list[dict] = field(default_factory=list)
    aggregation: dict = field(default_factory=dict)


@dataclass
class StepsExecuted(BaseEvent):
    """
    步骤执行完成事件
    
    当所有执行步骤完成后触发。
    
    Attributes:
        step_results: 步骤结果映射
        aggregation: 聚合配置
    """
    
    step_results: dict[str, str] = field(default_factory=dict)
    aggregation: dict = field(default_factory=dict)


@dataclass
class AggregationCompleted(BaseEvent):
    """
    聚合完成事件
    
    当结果聚合完成后触发。
    
    Attributes:
        records: 聚合后的记录列表
        columns: 列定义列表
    """
    
    records: list[dict] = field(default_factory=list)
    columns: list[dict] = field(default_factory=list)
    meta: dict = field(default_factory=dict)

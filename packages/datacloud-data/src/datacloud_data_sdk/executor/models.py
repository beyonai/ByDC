"""
执行层任务模型

本模块定义了执行器支持的各种任务类型的数据模型。
每种任务类型对应一种执行方式。

任务类型：
- ApiExecTask: API 调用任务，执行对象上的动作
- SqlExecTask: SQL 查询任务，执行数据库查询
- ScriptExecTask: 脚本执行任务，运行 Python 脚本
- KbExecTask: 知识库检索任务，查询知识库

所有任务都支持输出引用(output_ref)和步骤绑定(bind_from_step)，
用于实现步骤间的数据传递。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ApiExecTask:
    """
    API 执行任务

    调用对象上的动作执行 API 请求。

    Attributes:
        object_code: 对象代码
        action_code: 动作代码
        params: 执行参数字典
        output_ref: 输出引用名称，用于后续步骤引用
        bind_from_step: 绑定的前置步骤 ID
        bind_key: 绑定的键名，用于从前置步骤获取值
    """

    object_code: str
    action_code: str
    params: dict[str, Any] = field(default_factory=dict)
    output_ref: str = ""
    bind_from_step: str = ""
    bind_key: str = ""


@dataclass
class SqlExecTask:
    """
    SQL 执行任务

    在指定数据源上执行 SQL 查询。

    Attributes:
        datasource_alias: 数据源别名
        sql_template: SQL 模板，支持参数占位符
        output_ref: 输出引用名称
        bind_from_step: 绑定的前置步骤 ID
        bind_key: 绑定的键名
    """

    datasource_alias: str
    sql_template: str
    output_ref: str = ""
    bind_from_step: str = ""
    bind_key: str = ""


@dataclass
class ScriptExecTask:
    """
    脚本执行任务

    执行 Python 脚本代码。

    Attributes:
        object_code: 对象代码
        action_code: 动作代码
        script: Python 脚本代码
        params: 执行参数字典
        output_ref: 输出引用名称
    """

    object_code: str
    action_code: str
    script: str
    params: dict[str, Any] = field(default_factory=dict)
    output_ref: str = ""


@dataclass
class KbExecTask:
    """
    知识库执行任务

    在知识库中执行检索查询。

    Attributes:
        datasource_alias: 数据源别名
        query: 查询文本
        tags: 标签过滤条件
        output_ref: 输出引用名称
    """

    datasource_alias: str
    query: str
    tags: dict[str, Any] = field(default_factory=dict)
    output_ref: str = ""

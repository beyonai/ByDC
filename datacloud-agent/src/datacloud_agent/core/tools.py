"""
Tool definitions module for OpenClaw Gateway.

Provides 5 atomic business tools:
- know: Knowledge retrieval
- query: Data query (NL2Data)
- compute: Computation
- render: Rendering
- store: Storage
"""

from langchain_core.tools import tool


@tool
def know(query: str) -> str:
    """
    知识检索工具。用于查询特定主题的知识信息。

    从知识服务检索业务知识和本体知识。当用户询问业务概念、
    术语解释、数据模型定义等问题时使用此工具。

    Args:
        query: 要查询的主题或关键词，例如 "用户", "订单模型", "业务规则"

    Returns:
        关于该主题的知识信息，包括概念定义、业务规则、数据模型等
    """
    return f"[Knowledge] 关于 '{query}' 的知识信息"


@tool
def query(data: str) -> str:
    """
    数据查询工具。用于执行自然语言到数据查询（NL2Data）。

    当用户需要从数据仓库查询具体数据、执行SQL查询、或获取
    业务数据统计信息时使用此工具。

    Args:
        data: 数据查询请求，描述需要查询的数据和条件，
              例如 "2024年1月的销售额", "用户活跃度统计"

    Returns:
        查询结果数据，可以是表格、统计值或其他数据格式
    """
    return f"[Query] 查询结果: '{data}'"


@tool
def compute(expression: str) -> str:
    """
    计算工具。用于执行数学计算和数据分析。

    当用户需要进行数值计算、统计分析、数据聚合、公式求值
    等操作时使用此工具。

    Args:
        expression: 计算表达式或分析请求，
                   例如 "sum([1,2,3])", "平均值", "增长率计算"

    Returns:
        计算结果，包括数值、统计指标或分析报告
    """
    return f"[Compute] 计算结果: '{expression}'"


@tool
def render(format_type: str, content: str) -> str:
    """
    渲染工具。用于生成可视化输出和数据呈现。

    当用户需要生成图表、表格、报表或其他可视化形式的数据
    展示时使用此工具。

    Args:
        format_type: 渲染格式类型，例如 "chart", "table", "markdown", "html"
        content: 要渲染的内容数据，可以是原始数据或分析结果

    Returns:
        渲染后的输出，可以是图表URL、HTML代码、Markdown表格等
    """
    return f"[Render] 格式: {format_type}, 内容: '{content}'"


@tool
def store(key: str, value: str) -> str:
    """
    存储工具。用于保存数据到记忆服务。

    当用户需要保存重要的查询结果、计算数据、或需要
    跨会话持久化存储的信息时使用此工具。

    Args:
        key: 存储键名，用于唯一标识存储的数据，
            例如 "user_preference", "last_query_result"
        value: 要存储的值，可以是任意字符串格式的数据

    Returns:
        存储确认信息，包括键名和存储状态
    """
    return f"[Store] 已存储 key='{key}', value='{value}'"


def get_business_tools():
    """
    获取所有业务工具列表。

    Returns:
        包含5个业务工具的列表
    """
    return [know, query, compute, render, store]


def get_system_prompt() -> str:
    """
    获取系统提示词，强制要求使用工具。

    Returns:
        系统提示词字符串，包含工具使用指导
    """
    return """你是一个智能数据分析助手。当用户询问任何问题时，你必须使用可用的工具来获取信息。

可用的工具：
- know: 用于检索业务知识和本体知识
- query: 用于执行数据查询（NL2Data）
- compute: 用于执行数学计算和数据分析
- render: 用于生成可视化输出
- store: 用于保存数据到记忆服务

重要：对于每个用户查询，请分析是否需要使用工具。如果需要获取信息或执行操作，请主动调用相应的工具。
"""
